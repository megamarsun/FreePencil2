"""bg_layout.py 用に、previz の .blend からカメラの通り道(マーカーで切り替わる今のカメラの位置と向き、2 コマおき)と腰の位置を
City_Root の中の座標で撮る。

  blender -b <previz.blend> --python probe_bg.py -- <出力.npz>
"""
import bpy, numpy as np, sys
sc=bpy.context.scene
root=bpy.data.objects["City_Root"]
Mi=root.matrix_world.inverted()
print("@@ root", [list(r) for r in root.matrix_world])
from collections import Counter
cnt=Counter()
for o in root.children:
    cnt[(o.users_collection[0].name, o.name.split("_")[0])]+=1
for k,v in sorted(cnt.items()): print("@@ obj",k,v)
cams=[m.camera for m in sorted(sc.timeline_markers,key=lambda m:m.frame)]
arm=bpy.data.objects["Armature"]
C=[];H=[]
for f in range(1,5401,2):
    sc.frame_set(f)
    cam=None
    for m in sorted(sc.timeline_markers,key=lambda m:m.frame):
        if m.frame<=f: cam=m.camera
    C.append(tuple(Mi@cam.matrix_world.translation)+tuple(Mi.to_3x3()@(cam.matrix_world.to_3x3()@__import__('mathutils').Vector((0,0,-1)))))
    H.append(tuple(Mi@(arm.matrix_world@arm.pose.bones["root.x"].head)))
np.savez(sys.argv[-1],cam=np.array(C),hip=np.array(H))
print("@@ mats",[(m.name,tuple(round(x,3) for x in m.diffuse_color)) for m in bpy.data.materials if m.name.startswith("city")])
print("@@ world",tuple(sc.world.color), sc.display.shading.light, sc.display.shading.color_type)
