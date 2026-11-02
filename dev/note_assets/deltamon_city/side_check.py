"""キャラを真横(と前)から撮る確かめ用。  blender -b <blend> --python side_check.py -- <出力フォルダ> <コマ,コマ,...>"""
import sys
from pathlib import Path
import bpy
from mathutils import Vector
A = sys.argv[sys.argv.index("--") + 1:]
OUT = Path(A[0]); OUT.mkdir(parents=True, exist_ok=True)
sc = bpy.context.scene
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE" and "Armature" in o.name)
hips = arm.data["fp_humanoid"]["下半身"]
cd = bpy.data.cameras.new("SideCheck"); cd.lens = 40
cam = bpy.data.objects.new("SideCheck", cd); sc.collection.objects.link(cam)
sc.camera = cam
for m in sc.timeline_markers:      # ショットの切り替え(マーカーのカメラ)が撮るときに勝つので外す
    m.camera = None
sc.render.resolution_x, sc.render.resolution_y = 960, 540
for f in [int(x) for x in A[1].split(",")]:
    sc.frame_set(f)
    h = arm.matrix_world @ arm.pose.bones[hips].head
    fw = (arm.matrix_world.to_3x3() @ arm.pose.bones[hips].matrix.to_3x3() @ Vector((0, 0, 1)))
    fw.z = 0
    fw.normalize()
    side = Vector((0, 0, 1)).cross(fw)
    for nm, off in (("side", side * 3.2), ("front", fw * 3.2)):
        sc.camera = cam
        cam.location = h + off + Vector((0, 0, 0.1))
        cam.rotation_euler = (h - cam.location).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = str(OUT / f"{f:04d}_{nm}.png")
        bpy.ops.render.render(write_still=True)
