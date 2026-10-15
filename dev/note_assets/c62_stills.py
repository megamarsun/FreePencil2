"""c62_pre.blend を開き STEP0(手描き背景、機関車はメカ)を押して、要所の静止画を撮る。

  blender -b --factory-startup --python c62_stills.py -- [--pre out/c62/c62_pre.blend] [--out out/c62/stills]
      [--res 1920] [--cams name=x,y,z,pitch,yaw;...] [--save out/c62/c62_bg.blend]
"""
import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
HERE = Path(__file__).resolve().parent
PRE = Path(arg("--pre", str(HERE / "out" / "c62" / "c62_pre.blend"))).resolve()
OUT = Path(arg("--out", str(HERE / "out" / "c62" / "stills"))).resolve()
RES = int(arg("--res", "1920"))
CAMS = [c.split("=") for c in arg("--cams", "a=6,16,6.5,88,160").split(";")]
sys.path.insert(0, str(HERE.parent / "batch"))
import bpy, fp_batch          # noqa: E402

fp_batch.install_addon()
OUT.mkdir(parents=True, exist_ok=True)
src = Path(arg("--bg", "")) if arg("--bg") else None
if src and src.exists():
    bpy.ops.wm.open_mainfile(filepath=str(src))
    sc = bpy.context.scene
else:
    bpy.ops.wm.open_mainfile(filepath=str(PRE))
    sc = bpy.context.scene
    sc.fp_auto_style = arg("--style", "BACKGROUND")
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    print("@@@ STEP0", {k: round(float(getattr(sc, k)), 3) for k in
                        ("fp_lw_far_amount", "fp_lw_relief", "fp_lw_strength", "fp_fine_lines", "fp_far_lod_px")},
          flush=True)
    if arg("--save"):
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(arg("--save")).resolve()))
sc.fp_preview_mode = arg("--preview", "WHITE")
sc.render.resolution_x = RES
sc.render.resolution_y = RES * 9 // 16
cam = sc.camera
for name, spec in CAMS:
    x, y, z, p, yaw = (float(v) for v in spec.split(","))
    cam.location = (x, y, z)
    cam.rotation_euler = (math.radians(p), 0, math.radians(yaw))
    sc.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    print("@@@ rendered", name, flush=True)
