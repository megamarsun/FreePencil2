"""プリビズの .blend に STEP0(全自動)をそのまま押して、要所のコマを EEVEE + FreePencil で撮る(効果が出ているかの確かめ)。

  blender -b --factory-startup --python fp_stills.py -- <previz.blend> <出力フォルダ> [--frames 1500,2880,3900,4643]
      [--res 1280] [--modes WHITE,CEL] [--style ...] [--save <出力.blend>] [--curves-to-mesh]

プリビズはワークベンチなので EEVEE に切り替えてから押す(STEP0 は描画方式を変えない)。--curves-to-mesh は背景のパイプ・
ケーブル(カーブ)をメッシュに変えてから押す(STEP0 はメッシュだけを塗り分ける)。
look.py が持ち上げた背景の色は元(fp_orig_color)に戻してから押す(ワークベンチ用の明るさで、材質の色ではない)。
手直しはしない(STEP0 を押しただけの絵を見る)。カメラは各コマのマーカーのカメラ。
"""
import sys
import time
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:]
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d   # noqa: E731
SRC, OUT = Path(ARGV[0]).resolve(), Path(ARGV[1]).resolve()
FRAMES = [int(x) for x in arg("--frames", "1500,2880,3900,4643").split(",")]
RES = int(arg("--res", "1280"))
MODES = arg("--modes", "WHITE,CEL").split(",")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "batch"))
import bpy        # noqa: E402
import fp_batch   # noqa: E402

fp_batch.install_addon()
ai = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.ai"))
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(SRC))
sc = bpy.context.scene
for m in bpy.data.materials:
    if "fp_orig_color" in m:
        m.diffuse_color = (*m["fp_orig_color"], 1)
sc.render.engine = "BLENDER_EEVEE_NEXT"
if "--curves-to-mesh" in ARGV:
    cur = [o for o in sc.objects if o.type == "CURVE" and not o.hide_render]
    with bpy.context.temp_override(selected_editable_objects=cur, selected_objects=cur, active_object=cur[0]):
        bpy.ops.object.convert(target="MESH")
    print("@@ curves -> mesh", len(cur), flush=True)
mks = sorted([m for m in sc.timeline_markers if m.camera], key=lambda m: m.frame)


def cam_at(f):
    return [m for m in mks if m.frame <= f][-1].camera


sc.frame_set(FRAMES[0])
sc.camera = cam_at(FRAMES[0])
sc.render.resolution_x, sc.render.resolution_y = RES, RES * 9 // 16
sc.render.resolution_percentage = 100
for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
    if hasattr(sc, p_):
        setattr(sc, p_, False)
vis = [o.name for o in sc.objects if o.type == "MESH" and not o.hide_render and o.visible_get() and len(o.data.polygons)]
t0 = time.time()
r = ai.auto(arg("--style"), vis)
print("@@ STEP0", round(time.time() - t0, 1), "s style", sc.fp_auto_style, "engine", sc.render.engine,
      "warnings", r.get("warnings", []), flush=True)
if arg("--save"):
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(arg("--save")).resolve()))
for f in FRAMES:
    sc.frame_set(f)
    sc.camera = cam_at(f)
    for mode in MODES:
        sc.fp_preview_mode = mode
        sc.render.filepath = str(OUT / f"{f}_{mode}.png")
        t = time.time()
        bpy.ops.render.render(write_still=True)
        print("@@ shot", f, mode, round(time.time() - t, 1), "s", flush=True)
