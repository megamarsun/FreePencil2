"""手作業デモの場面: anime-girl にポーズを付け、上半身を斜め前から撮るカメラと日を置く。

  blender -b --factory-startup --python girl_scene.py -- --out <dir> [--res 960] [--preview]

FreePencil はまだ当てない(当てる前の .blend を残す)。--preview はソリッドで撮ってポーズを見る。
"""
from __future__ import annotations

import glob
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d   # noqa: E731
OUT = Path(arg("--out", ".")).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES = int(arg("--res", "960"))
YAW = float(arg("--yaw", "18"))           # カメラを正面から回す角度(度)

blend = glob.glob(str(Path.home() / "blenderkit_data" / "models" / "anime-girl*" / "*.blend"))[0]
bpy.ops.wm.open_mainfile(filepath=blend)
sc = bpy.context.scene
arm = bpy.data.objects["Armature"]
bpy.context.view_layer.update()


def rot_about_head(pb, axis, deg):
    """骨を、その付け根を中心にアーマチュア空間の軸で回す(操作用の骨を回す)。"""
    m = pb.matrix.copy()
    h = m.translation.copy()
    r = Matrix.Rotation(math.radians(deg), 4, axis)
    pb.matrix = Matrix.Translation(h) @ r @ Matrix.Translation(-h) @ m
    bpy.context.view_layer.update()


pose = arm.pose.bones
# 腕を下ろす。このリグは IK/FK の切り替えで操作用の骨が効かないことがあるので、腕の骨の
# 拘束を切って腕の骨そのものを回す(T ポーズの腕は ±X。Y 軸まわりで下へ)
for side in ("Left", "Right"):
    for part in ("Shoulder", "Arm", "ForeArm", "Hand"):
        for c in pose[f"mixamorig:{side}{part}"].constraints:
            c.mute = True
bpy.context.view_layer.update()
A = float(arg("--arm", "68"))
rot_about_head(pose["mixamorig:LeftArm"], "Y", A)
rot_about_head(pose["mixamorig:RightArm"], "Y", -A)
# 肘を少し曲げて、手を前へ
rot_about_head(pose["mixamorig:LeftForeArm"], "X", -20)
rot_about_head(pose["mixamorig:RightForeArm"], "X", -20)
# 首と頭: カメラの方へ少し向けて、かしげる
rot_about_head(pose["Ctrl_Neck"], "Z", -YAW * 0.25)
rot_about_head(pose["Ctrl_Head"], "Z", -YAW * 0.25)
rot_about_head(pose["Ctrl_Head"], "Y", 6)
rot_about_head(pose["Ctrl_Spine2"], "Z", -YAW * 0.15)

# 上半身(頭のてっぺんから腰の少し上まで)を収める
vis = [o for o in sc.objects if o.type == "MESH" and len(o.data.polygons)]
for o in sc.objects:
    if o.type == "MESH" and not len(o.data.polygons):
        o.hide_render = True
dg = bpy.context.evaluated_depsgraph_get()
head = arm.matrix_world @ pose["mixamorig:Head"].head
top = arm.matrix_world @ pose["mixamorig:HeadTop_End"].head
hips = arm.matrix_world @ pose["mixamorig:Spine"].head
up = top - hips
ctr = hips + up * 0.62
height = up.length * 1.12
cd = bpy.data.cameras.new("Cam")
cd.lens = 70
cam = bpy.data.objects.new("Cam", cd)
sc.collection.objects.link(cam)
sc.camera = cam
# キャラの正面(-Y 側)から YAW だけ回し、少し上から
yaw = math.radians(YAW)
dist = height / (2 * math.tan(cd.angle_y / 2)) * 1.0
fwd = Vector((math.sin(yaw), -math.cos(yaw), 0.12)).normalized()
cam.location = ctr + fwd * dist
cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
sc.render.resolution_x, sc.render.resolution_y = RES, RES * 9 // 16
cd.sensor_fit = "VERTICAL"

sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
sun.data.energy = 3.5
sun.rotation_euler = (math.radians(55), 0, math.radians(YAW + 40))
sc.collection.objects.link(sun)
sc.eevee.taa_render_samples = 16
for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
    if hasattr(sc, p_):
        setattr(sc, p_, False)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "girl_clean.blend"))
print("@@@ saved", OUT / "girl_clean.blend", flush=True)

if "--preview" in ARGV:
    sc.render.filepath = str(OUT / "pose_preview.png")
    bpy.ops.render.render(write_still=True)
    print("@@@ preview", sc.render.filepath, flush=True)
