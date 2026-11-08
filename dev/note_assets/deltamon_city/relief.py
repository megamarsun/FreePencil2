"""  blender -b --factory-startup <fp_v30.blend> --python relief.py -- <出力.blend> [--text FreePencil2 --size 1.0 --up 2.3]
最後の機械の正面(赤い目の板)に「FreePencil2」の浮き彫りを足す。機械と同じ材質で、文字の縁に線が出る。"""
import bpy, sys, bmesh, numpy as np
from mathutils import Vector, Matrix
ARGV=sys.argv[sys.argv.index("--")+1:]
arg=lambda n,d=None: ARGV[ARGV.index(n)+1] if n in ARGV else d
sc=bpy.context.scene
cm=bpy.data.objects["Core_Machine"]; me=cm.data; mw=cm.matrix_world
lamps=bpy.data.objects["Red_Lamps"]
lv=np.array([tuple(lamps.matrix_world@v.co) for v in lamps.data.vertices])
# 正面: 機械の面のうち、赤い目に一番近い大きな面
best=None
for p in me.polygons:
    c=mw@p.center; n=(mw.to_3x3()@p.normal).normalized()
    d=np.linalg.norm(lv-np.array(c),axis=1).min()
    if p.area>20 and (best is None or d<best[0]): best=(d,c,n,p.area)
d,c,n,a=best
eye=lv[np.linalg.norm(lv-np.array(c),axis=1)<3.0].mean(0); eye=Vector(eye)
print("@@ face",[round(x,2) for x in c],[round(x,2) for x in n],round(a,1),"eye",[round(x,2) for x in eye])
# 文字
td=bpy.data.curves.new("FP_Relief","FONT"); td.body=arg("--text","FreePencil2")
td.align_x='CENTER'; td.align_y='CENTER'; td.size=float(arg("--size","1.0"))
td.extrude=float(arg("--depth","0.06")); td.bevel_depth=0.015; td.resolution_u=6
to=bpy.data.objects.new("FP_Relief",td); sc.collection.objects.link(to)
up=Vector((0,0,1)); right=up.cross(n).normalized()
plane_pt=c+n*(n.dot(eye-c))  # unused
base=eye-n*(n.dot(eye-c))     # 目の真後ろの板の上
pos=base+up*float(arg("--up","2.3"))+n*(td.extrude+0.01)
R=Matrix((right,up,n)).transposed().to_4x4()
to.matrix_world=Matrix.Translation(pos)@R
# メッシュにして機械と同じ材質に
dg=bpy.context.evaluated_depsgraph_get()
m2=bpy.data.meshes.new_from_object(to.evaluated_get(dg))
mo=bpy.data.objects.new("FP_Relief_Mesh",m2); mo.matrix_world=to.matrix_world
for col in cm.users_collection: col.objects.link(mo)
sc.collection.objects.unlink(to); bpy.data.objects.remove(to)
mo.data.materials.append(cm.material_slots[0].material)
for p in mo.data.polygons: p.use_smooth=False
# 下の赤い灯りが文字の影を上へ大きく落とし、文字が二重に見えた
mo.visible_shadow=False
# 線の色の層を機械からそろえる(無いと塗り分けの色が既定になる)
for a in cm.data.color_attributes:
    if a.name not in mo.data.color_attributes:
        na=mo.data.color_attributes.new(a.name,a.data_type,a.domain)
        v=list(a.data[0].color) if len(a.data) else [1,1,1,1]
        for e in na.data: e.color=v
# 文字だけ少し違う塗り分けにして縁に線を出す
mc=mo.data.color_attributes.get("mecha_color")
if mc:
    for e in mc.data:
        e.color=[min(1,x+0.25) for x in e.color[:3]]+[1]
mo.parent=cm.parent; mo.matrix_parent_inverse=cm.parent.matrix_world.inverted() if cm.parent else Matrix()
print("@@ relief verts",len(m2.vertices),"dims",[round(x,2) for x in mo.dimensions])
bpy.ops.wm.save_as_mainfile(filepath=ARGV[0])
