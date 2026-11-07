"""fp_stills.py --save で残した .blend(STEP0 済み・日あり)から、続いたコマを撮る(全編の動画用)。

  blender -b --factory-startup --python fp_film.py -- <fp_stills で保存した.blend> <出力フォルダ> --start 1 --end 5400 [--mode MONO_LIGHT] [--tex 0.1]
      [--frames 900,1890]

STEP0 は 1 回だけ押して保存したものを使う(手分けして撮るとき、手ごとに STEP0 を押すと塗り分けがずれて、つなぎ目で絵が変わるおそれがある)。
日(Demo_Sun)は各コマでカメラ基準に向け直す。出力は f_0001.png …。もうあるコマは飛ばす(途中から撮り直せる)。
"""
import sys
import time
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:]
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d   # noqa: E731
SRC, OUT = Path(ARGV[0]).resolve(), Path(ARGV[1]).resolve()
S, E = int(arg("--start", "1")), int(arg("--end", "5400"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "batch"))
import bpy        # noqa: E402
import fp_batch   # noqa: E402

fp_batch.install_addon()
cel_light = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.cel_light"))
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(SRC))
sc = bpy.context.scene
sc.fp_preview_mode = arg("--mode", "MONO_LIGHT")
if arg("--tex"):     # テクスチャのモノクロ化(mono_tex.py)。値は黒い材質の下限
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import mono_tex   # noqa: E402
    mono_tex.apply(sc, float(arg("--tex")))
sun = bpy.data.objects.get("Demo_Sun")
mks = sorted([m for m in sc.timeline_markers if m.camera], key=lambda m: m.frame)
print("@@ engine", sc.render.engine, "mode", sc.fp_preview_mode, "sun", bool(sun), flush=True)
for f in ([int(x) for x in arg("--frames").split(",")] if arg("--frames") else range(S, E + 1)):
    p = OUT / f"f_{f:04d}.png"
    if p.exists():
        continue
    t = time.time()
    sc.frame_set(f)
    sc.camera = [m for m in mks if m.frame <= f][-1].camera
    if sun:
        sun.rotation_euler = cel_light.key_direction(sc).to_track_quat("Z", "Y").to_euler()
    sc.render.filepath = str(p)
    bpy.ops.render.render(write_still=True)
    print("@@ shot", f, round(time.time() - t, 1), "s", flush=True)
print("@@ done", S, E, flush=True)
