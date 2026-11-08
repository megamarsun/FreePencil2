"""デルタもんの全身を 1 枚(本編 fp_v30.blend から)。
  blender -b --factory-startup <fp_v30.blend> --python dm_touchup.py -- <出力.png> [--fix] [--save <出力.blend>]
--fix で AI の手直し(目・眉の絵を黒く・鼻の点・口の線を弱く・キャラの線を弱く・襟に線)。"""
import bpy, sys, math, mathutils, colorsys
import numpy as np
from pathlib import Path
ARGV=sys.argv[sys.argv.index("--")+1:]
arg=lambda n,d=None: ARGV[ARGV.index(n)+1] if n in ARGV else d
OUT=Path(ARGV[0]); FIX="--fix" in ARGV; F=int(arg("--frame","100"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "batch"))
import fp_batch; fp_batch.install_addon()
mod=lambda s: next(m for n,m in sys.modules.items() if n.endswith("freepencil2."+s))
ai,cel_light,cel_shade,shade_normal=(mod(s) for s in ("ai","cel_light","cel_shade","shade_normal"))
sc=bpy.context.scene
MK=[(m,m.camera) for m in sc.timeline_markers]   # 本編のカメラ切り替え(保存の前に戻す)
for m,_ in MK: m.camera=None
sc.frame_set(F)
arm=bpy.data.objects["Armature"]
hp=arm.matrix_world@arm.pose.bones["root.x"].head
cd=bpy.data.cameras.new("DM_Full"); cd.lens=float(arg("--lens","50"))
cam=bpy.data.objects.new("DM_Full",cd); sc.collection.objects.link(cam)
tgt=mathutils.Vector((hp.x,hp.y,hp.z-0.08))
pos=tgt+mathutils.Vector((float(arg("--dx","0.9")),-float(arg("--dist","2.7")),0.15))
cam.location=pos; cam.rotation_euler=(tgt-pos).to_track_quat('-Z','Y').to_euler()
sc.camera=cam
sc.render.resolution_x,sc.render.resolution_y=1080,1620
DM=[o.name for o in sc.objects if o.name.startswith("1_deltamon")]

def uvsel(o, box):
    me=o.data; uv=me.uv_layers.active.data
    u0,v0,u1,v1=box; f=np.zeros(len(me.polygons),bool)
    for p in me.polygons:
        c=np.mean([uv[i].uv for i in p.loop_indices],axis=0)
        f[p.index]=u0<=c[0]<=u1 and v0<=c[1]<=v1
    return f

def grow(o,f,rings):
    me=o.data; f=f.copy()
    for _ in range(rings):
        vs=set()
        for p in me.polygons:
            if f[p.index]: vs.update(p.vertices)
        for p in me.polygons:
            if not f[p.index] and any(v in vs for v in p.vertices): f[p.index]=True
    return f

if FIX:
    # 1. 目の絵: 色の無い灰色(まつ毛・眉)を黒く、瞳の暗い所も締める(写しの絵に差し替え)
    src=bpy.data.images["1_deltamon_Eyes"]; w,h=src.size
    px=np.empty(w*h*4,np.float32); src.pixels.foreach_get(px); px=px.reshape(-1,4)
    rgb=px[:,:3]; mx=rgb.max(1); mn=rgb.min(1); sat=(mx-mn)/np.maximum(mx,1e-4)
    grey=sat<0.18
    t=np.clip((mx-0.88)/0.10,0,1)            # 0.88 未満の灰は黒、0.98 以上の白はそのまま
    rgb[grey]=rgb[grey]*t[grey,None]
    dark=(~grey)&(mx<0.45)                    # 瞳の暗い所
    rgb[dark]*=0.35
    px[:,:3]=rgb
    im=src.copy(); im.name="1_deltamon_Eyes_fp"; im.pixels.foreach_set(px.ravel()); im.pack()
    for m in {s.material for o in sc.objects if o.name=="1_deltamon_eyes" for s in o.material_slots}:
        for n in m.node_tree.nodes:
            if n.type=='TEX_IMAGE' and n.image==src: n.image=im
    # 2. 鼻の点: 顔の絵の左下の小さな四角を真っ黒に
    head=bpy.data.objects["1_deltamon_head"]
    nose=uvsel(head,(0.0,0.0,0.05,0.05))
    print("@@ nose faces",int(nose.sum()))
    src=bpy.data.images["1_deltamon_Face"]; w,h=src.size
    px=np.empty(w*h*4,np.float32); src.pixels.foreach_get(px); px=px.reshape(h,w,4)
    blk=px[:int(h*0.05),:int(w*0.05),:3]; m_=blk.max(2)<0.4; blk[m_]=0.0
    im=src.copy(); im.name="1_deltamon_Face_fp"; im.pixels.foreach_set(px.ravel()); im.pack()
    for n in head.material_slots[0].material.node_tree.nodes:
        if n.type=='TEX_IMAGE' and n.image==src: n.image=im
    # 3. キャラの線を弱く
    print(ai.fade_lines({"objects":DM}, float(arg("--fade","0.2"))))
    # 4. 鼻の点のまわりに線(塗り分けて縁に線)
    if nose.any():
        ai._paint(head,"mecha_color",nose,(0.0,0.0,0.0,1.0))
        ai._paint(head,"line_color",nose,(0.0,0.0,0.0,1.0))
    # 5. 口の線を弱く(口の中と唇のまわり)
    mf=ai.mouth_faces(head)
    if mf is not None:
        mg=grow(head,mf,2); ai._paint(head,"line_color",mg,(float(arg("--mouth","0.38")),)*3+(1.0,))
        print("@@ mouth faces",int(mf.sum()),int(mg.sum()))
    # 6. 襟に線
    cl=bpy.data.objects["1_deltamon_cloth"]
    col=uvsel(cl,(0.425,0.855,0.575,0.94))
    print("@@ collar faces",int(col.sum()))
    def shift(c): out=c.copy(); out[:,:3]=np.clip(out[:,:3]-0.45,0,1); return out
    ai._paint(cl,"mecha_color",col,shift)
    ai._refresh(None)
    ai._refresh("line_color")
    print("@@ rim",sc.fp_cel_rim,sc.fp_cel_rim_style,tuple(sc.fp_cel_rim_color))
    cel_shade.set_cel(sc, True)

# 本編と同じリム(run_v30.sh の --set と fp_v30.py の GLOW)
sc.fp_cel_rim_style="GLOW"; sc.fp_cel_rim_side="AUTO"; sc.fp_cel_rim_width=6.0; sc.fp_cel_rim_color=(0.4,0.5,0.48)
cel_shade.set_cel(sc, True)
print("@@ rimB",sc.fp_cel_rim,sc.fp_cel_rim_style,tuple(sc.fp_cel_rim_color),sc.fp_line_color)
shade_normal.follow(sc); cel_light.aim_key(sc); cel_shade.update_sun(sc)
OUT.parent.mkdir(parents=True,exist_ok=True)
sc.render.filepath=str(OUT); bpy.ops.render.render(write_still=True)
if arg("--save"):
    for m,c in MK: m.camera=c
    bpy.ops.wm.save_as_mainfile(filepath=arg("--save"))
print("@@ done")
