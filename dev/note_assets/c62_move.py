"""C62 デモのカメラワークを撮る。STEP0 の前にカメラの動きをキーにする(遠い区画をまとめるが近づく先を測る)。

  blender -b --factory-startup --python c62_move.py -- --keys "t:x:y:z:pitch:yaw,..." --frames 336
      [--pre out/c62/c62_pre.blend] [--bg out/c62/c62_move_bg.blend(あれば STEP0 を飛ばす)]
      [--out out/c62/move] [--res 1920] [--samples 16] [--only 1,50,...] [--mode cel|3d|white]

  --mode cel   セル(影と色)。アドオンの機能だけ(STEP0 を押して、プレビューをセルにしただけ)
  --mode 3d    元の 3D(コンポジタを切った素のレンダー)。最後のワイプ用
  --mode white 線画だけ
"""
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
HERE = Path(__file__).resolve().parent
PRE = Path(arg("--pre", str(HERE / "out" / "c62" / "c62_pre.blend"))).resolve()
BG = Path(arg("--bg", str(HERE / "out" / "c62" / "c62_move_bg.blend"))).resolve()
OUT = Path(arg("--out", str(HERE / "out" / "c62" / "move"))).resolve()
RES = int(arg("--res", "1920"))
N = int(arg("--frames", "336"))
ONLY = {int(v) for v in arg("--only", "").split(",") if v}
MODE = arg("--mode", "cel")
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import bpy, fp_batch          # noqa: E402
import cam_path               # noqa: E402

KEYS = cam_path.parse(arg("--keys"))
fp_batch.install_addon()
if BG.exists() and "--restep" not in ARGV:
    bpy.ops.wm.open_mainfile(filepath=str(BG))
    sc = bpy.context.scene
else:
    bpy.ops.wm.open_mainfile(filepath=str(PRE))
    sc = bpy.context.scene
    cam_path.bake(sc, sc.camera, KEYS, N)
    sc.fp_auto_style = "BACKGROUND"
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    print("@@@ STEP0 done", flush=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(BG))
sc.render.resolution_x = RES
sc.render.resolution_y = RES * 9 // 16
sc.eevee.taa_render_samples = int(arg("--samples", "16"))
if MODE == "3d":
    sc.render.use_compositing = False
    sc.render.film_transparent = False
    sc.render.resolution_percentage = 200       # セルと同じ大きさ(4K)で出す
    sc.view_settings.view_transform = "AgX" if "AgX" in [i.identifier for i in sc.view_settings.bl_rna.properties["view_transform"].enum_items] else "Filmic"
else:
    sc.fp_preview_mode = "CEL" if MODE == "cel" else "WHITE"
cam = sc.camera
cam.animation_data_clear()            # 塗りは STEP0 で決まった。撮影はスクリプトで置く
d = OUT / MODE
d.mkdir(parents=True, exist_ok=True)
for i in range(N):
    if ONLY and (i + 1) not in ONLY:
        continue
    loc, rot = cam_path.pose(KEYS, i, N)
    cam.location = loc
    cam.rotation_euler = rot
    sc.render.filepath = str(d / f"f{i + 1:04d}.png")
    bpy.ops.render.render(write_still=True)
print("@@@ done", MODE, flush=True)
