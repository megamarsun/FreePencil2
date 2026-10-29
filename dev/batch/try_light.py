"""ライトの当て方(cel_light)の試し撮り。影の形を作った後の .blend(try_shade_shape.py の after.blend)から撮る。

  blender -b --factory-startup --python try_light.py -- <after.blend> <出力フォルダ>

出力:
  cur.png       場面の日のまま(影の形あり)
  key.png       カメラから 左・影の量 0.3・高さ 35°
  side.png      カメラから 左・影の量 0.5・高さ 15°
  key_rim.png   key + リム
  back_rim.png  カメラから 左・影の量 0.8 + リム
  orbit_scene.png / orbit_cam.png  カメラを物の周りに 150° 回した後(場面の日のまま / カメラから)
  light.blend   key_rim の設定で保存
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

ARGV = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = Path(ARGV[0]), Path(ARGV[1])
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fp_batch  # noqa: E402

fp_batch.install_addon()
bpy.ops.wm.open_mainfile(filepath=str(SRC))
sc = bpy.context.scene
OUT.mkdir(parents=True, exist_ok=True)
if sc.fp_preview_mode != "CEL":
    sc.fp_preview_mode = "CEL"


def shot(name):
    bpy.context.view_layer.update()
    sc.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    sun = next((o for o in sc.objects if o.type == "LIGHT" and o.data.type == "SUN"), None)
    print("@@ shot", name, sc.fp_light_mode, round(sc.fp_light_amount, 2),
          "rim" if sc.fp_cel_rim else "", flush=True)


def setv(**kw):
    for k, v in kw.items():
        setattr(sc, k, v)


shot("cur")
setv(fp_light_mode="CAMERA", fp_light_side="LEFT", fp_light_amount=0.3, fp_light_height=math.radians(35))
shot("key")
setv(fp_light_amount=0.5, fp_light_height=math.radians(15))
shot("side")
setv(fp_light_amount=0.3, fp_light_height=math.radians(35), fp_cel_rim=True)
shot("key_rim")
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "light.blend"), copy=True)
setv(fp_light_amount=0.8)
shot("back_rim")

# カメラを物の周りに回す: 物の外枠の中心を軸に、ワールドの Z で 150°
pts = [o.matrix_world @ Vector(c) for o in sc.objects if o.type == "MESH" and o.visible_get()
       for c in o.bound_box]
mid = sum(pts, Vector()) / max(len(pts), 1)
cam = sc.camera
rot = Matrix.Translation(mid) @ Matrix.Rotation(math.radians(150), 4, "Z") @ Matrix.Translation(-mid)
setv(fp_light_amount=0.3, fp_cel_rim=False)
cam.matrix_world = rot @ cam.matrix_world      # 日はハンドラ(render_size._follow_sun)でついて行くはず
shot("orbit_cam")
setv(fp_light_mode="SCENE")
# 場面の日のまま: 開いたときの日に戻す
bpy.ops.wm.open_mainfile(filepath=str(SRC))
sc = bpy.context.scene
cam = sc.camera
cam.matrix_world = rot @ cam.matrix_world
shot("orbit_scene")
print("@@ done", flush=True)
