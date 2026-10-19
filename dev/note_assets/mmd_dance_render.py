"""MMD のダンスに FreePencil を当て(手直しは mmd_fix.py と同じ)、3D / 線画 / セルの連番を撮る。

  blender -b --factory-startup --python mmd_dance_render.py -- <Name> <dir> [--res 1280] [--every 1]
          [--modes model,line,cel] [--frames 300-330]

連番は <dir>/<Name>_<mode>/0300.png …。物理は mmd_dance.py で焼いてある。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "batch"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fp_batch                                   # noqa: E402
fp_batch.install_addon()
import bpy                                        # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:]
NAME, D = ARGV[0], Path(ARGV[1]).resolve()
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d   # noqa: E731
MODES = arg("--modes", "model,line,cel").split(",")
EVERY = int(arg("--every", "1"))

import importlib.util                             # noqa: E402
spec = importlib.util.spec_from_file_location("mmd_chars", str(Path(__file__).resolve().parent / "mmd_chars.py"))
CH = importlib.util.module_from_spec(spec)
spec.loader.exec_module(CH)
# 名前が CHARS に無ければ(4 体を並べた場面など)、メッシュの名前でキャラを当てる

bpy.ops.wm.open_mainfile(filepath=str(D / f"{NAME}_dance_clean.blend"))
sc = bpy.context.scene
if arg("--res"):
    r = int(arg("--res"))
    sc.render.resolution_x, sc.render.resolution_y = r, r * 9 // 16
f0, f1 = sc.frame_start, sc.frame_end
if arg("--frames"):
    f0, f1 = (int(x) for x in arg("--frames").split("-"))
fp = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.ai"))
meshes = [o for o in sc.objects if o.type == "MESH" and not o.hide_render and len(o.data.polygons)]
pairs = [(o, next(c for c in CH.CHARS.values() if c["mesh"] in o.name)) for o in meshes]


def shoot_seq(mode):
    out = D / f"{NAME}_{mode}"
    out.mkdir(exist_ok=True)
    import time
    t0 = time.time()
    for f in range(f0, f1 + 1, EVERY):
        if (out / f"{f:04d}.png").exists() and "--resume" in ARGV:
            continue
        sc.frame_set(f)
        sc.render.filepath = str(out / f"{f:04d}.png")
        bpy.ops.render.render(write_still=True)
    print("@@@ seq", mode, f0, f1, f"{time.time() - t0:.1f}s", flush=True)


sc.frame_set(f0)
fp.preview("NONE")
if "model" in MODES:
    keep = sc.render.use_compositing
    sc.render.use_compositing = False              # 元の 3D(FreePencil の前と同じ絵)
    shoot_seq("model")
    sc.render.use_compositing = keep
fp.auto("WEIGHTED")
overlay = [k for _, c in pairs for k in c["overlay"]]
fp.soft_overlays(overlay)
fp.clip_alpha(skip=overlay)
fp.weld()                                          # 突き合わせの継ぎ目の線を消す
for o, c in pairs:
    fp.merge({"objects": [o.name], "material": c["face"]})
if "--no-ss" in ARGV:
    # 4K は 2倍レンダを使わない(出力が大きいほど線が画面に対して細くなる。anime-girl で比べて決めた)
    sc.fp_supersample = False
    bpy.ops.freepencil2.link_button()
    bpy.ops.freepencil.measure_line_weight()
if "line" in MODES:
    fp.preview("WHITE")
    shoot_seq("line")
if "cel" in MODES:
    fp.cel(threshold=0.2, cast_shadows=False)
    shoot_seq("cel")
bpy.ops.wm.save_as_mainfile(filepath=str(D / f"{NAME}_dance_fp.blend"))
print("@@@ done", flush=True)
