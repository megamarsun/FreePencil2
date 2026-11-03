"""階段の足の乗り方を確かめる: 階段の真横から平行投影で、腰を追って撮る。手すり・ケーブルなどは隠し、通路とキャラだけ。

  blender -b <city.blend> --python stairs_check.py -- <出力フォルダ> <コマ0> <コマ1> [--every 3] [--scale 3.2] [--dz -0.35]

--scale 1.4 --dz -0.75 で足もとの寄り(足の裏が踏み面に平らか見る)。

カメラの向きは、コマ0 とコマ1 の腰を結んだ向き(階段はまっすぐ)に直交。右側から見る。
"""
import sys
from pathlib import Path

import bpy
from mathutils import Vector

A = sys.argv[sys.argv.index("--") + 1:]
arg = lambda n, d=None: A[A.index(n) + 1] if n in A else d   # noqa: E731
OUT = Path(A[0])
OUT.mkdir(parents=True, exist_ok=True)
F0, F1 = int(A[1]), int(A[2])
EVERY = int(arg("--every", "3"))
SCALE = float(arg("--scale", "3.2"))
DZ = float(arg("--dz", "-0.35"))
sc = bpy.context.scene
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE" and "Armature" in o.name)
hips = arm.data["fp_humanoid"]["下半身"]
keep = {"Walkway", "Walkway_Edges"}
root = bpy.data.objects["City_Root"]
for o in root.children_recursive:
    if o.name not in keep:
        o.hide_render = True
for o in sc.objects:
    if o.type == "LIGHT":
        o.hide_render = True
for m in sc.timeline_markers:
    m.camera = None


def hip(f):
    sc.frame_set(f)
    return arm.matrix_world @ arm.pose.bones[hips].head


d = hip(F1) - hip(F0)
d.z = 0
d.normalize()
right = d.cross(Vector((0, 0, 1)))
cd = bpy.data.cameras.new("StairsCheck")
cd.type = "ORTHO"
cd.ortho_scale = SCALE
cam = bpy.data.objects.new("StairsCheck", cd)
sc.collection.objects.link(cam)
sc.camera = cam
sc.render.resolution_x, sc.render.resolution_y = 640, 640
sc.render.resolution_percentage = 100
sc.render.image_settings.file_format = "PNG"
sc.render.use_stamp = True
for k in ("date", "time", "render_time", "filename", "scene", "memory", "camera", "lens", "marker"):
    setattr(sc.render, "use_stamp_" + k, False)
sc.render.use_stamp_frame = True
sc.render.stamp_font_size = 14
sh = sc.display.shading
sh.show_shadows = False
sh.show_cavity = False
for f in range(F0, F1 + 1, EVERY):
    h = hip(f)
    cam.location = h + right * 10 + Vector((0, 0, DZ))
    cam.rotation_euler = (-right).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = str(OUT / f"{f:04d}.png")
    bpy.ops.render.render(write_still=True)
print("@@ stairs_check", F0, F1, OUT, flush=True)
