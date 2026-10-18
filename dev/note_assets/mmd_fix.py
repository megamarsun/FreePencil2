"""MMD のキャラを、AI の窓口だけでアニメの線画/セルに仕上げる(4 体の検証用)。

  blender -b --factory-startup --python mmd_fix.py -- <Name> <stage_dir> [--res 1920] [--tag fix]

キャラごとの違い(材質の名前)だけを表にし、手直しの手順は全員同じ:
  1. STEP0(キャラ)
  2. 半透明の重ね(髪の影・頬・目の光)を BLEND に戻す(ざらざらの点と板の縁の線を消す)
  3. 目・顔の材質の塗り分けを 1 色にそろえる(眼球の丸い線を消す。目は絵の色で描く)
  4. セル: 日は正面(カメラの向きから 25° 上)、落とす影は切る、しきい値 0.25
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "batch"))
import fp_batch                                   # noqa: E402
fp_batch.install_addon()
import bpy                                        # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:]
NAME, D = ARGV[0], Path(ARGV[1]).resolve()
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d   # noqa: E731
TAG = arg("--tag", "fix")
CAST = "--cast" in ARGV

import importlib.util  # noqa: E402
_sp = importlib.util.spec_from_file_location("mmd_chars", str(Path(__file__).resolve().parent / "mmd_chars.py"))
_m = importlib.util.module_from_spec(_sp)
_sp.loader.exec_module(_m)
CHARS = _m.CHARS
C = CHARS[NAME]
bpy.ops.wm.open_mainfile(filepath=str(D / f"{NAME}_clean.blend"))
sc = bpy.context.scene
if arg("--res"):
    r = int(arg("--res"))
    sc.render.resolution_x, sc.render.resolution_y = r, r * 9 // 16
fp = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.ai"))
mesh = next(o for o in sc.objects if o.type == "MESH" and not o.hide_render)


def shoot(step):
    fp.render(f"{NAME}_{TAG}_{step}", scale=1.0, grid=False)


fp.preview("NONE")
shoot("0model")
fp.auto("WEIGHTED")
fp.preview("WHITE")
shoot("1step0")
fp.soft_overlays(C["overlay"])
fp.clip_alpha(skip=C["overlay"])
shoot("2overlay")
fp.merge({"objects": [mesh.name], "material": C["face"]})
shoot("3face")
import math  # noqa: E402
from mathutils import Matrix  # noqa: E402
cam, sun = sc.camera, next(o for o in sc.objects if o.type == "LIGHT")
for up, th in ((0, 0.25), (10, 0.15), (25, 0.15)):
    sun.rotation_euler = (cam.matrix_world.to_3x3() @ Matrix.Rotation(math.radians(up), 3, "X")
                          @ Matrix.Rotation(math.radians(-15), 3, "Y")).to_euler()
    fp.cel(threshold=th, cast_shadows=CAST)
    shoot(f"4cel_u{up}_t{int(th*100)}")
fp.preview("WHITE")
bpy.ops.wm.save_as_mainfile(filepath=str(D / f"{NAME}_{TAG}.blend"))
print("@@@ done", NAME, flush=True)
