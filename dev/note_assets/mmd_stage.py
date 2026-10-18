"""MMD のモデルとモーションを読み、FreePencil を当てる前の場面(.blend)を作る。

  blender -b --factory-startup --python mmd_stage.py -- --pmx <model.pmx> --out <dir> --name <名前>
          [--vmd <motion.vmd>] [--frame 120] [--shot upper|full] [--res 1280] [--preview]

mmd_tools(extensions.blender.org の拡張機能)で読む。日はカメラの向きから 25° 上・左へ 15°
(アニメの顔は正面から光を当てる。anime-girl で 12 通り比べて決めた)。背景は透過にしない。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import addon_utils
import bpy
from mathutils import Matrix, Vector

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d   # noqa: E731
PMX = Path(arg("--pmx")).resolve()
VMD = arg("--vmd")
OUT = Path(arg("--out", ".")).resolve()
OUT.mkdir(parents=True, exist_ok=True)
NAME = arg("--name", PMX.stem)
FRAME = int(arg("--frame", "120"))
SHOT = arg("--shot", "upper")
RES = int(arg("--res", "1280"))
YAW = float(arg("--yaw", "15"))

mod = next((m.__name__ for m in addon_utils.modules() if m.__name__.endswith("mmd_tools")), None)
if mod is None:
    sys.exit("mmd_tools が入っていません")
addon_utils.enable(mod, default_set=False, persistent=False)

bpy.ops.wm.read_homefile(use_empty=True)
sc = bpy.context.scene
bpy.ops.mmd_tools.import_model(filepath=str(PMX), scale=0.08, types={"MESH", "ARMATURE", "MORPHS"},
                               log_level="ERROR")
root = next(o for o in sc.objects if getattr(o, "mmd_type", "") == "ROOT")
arm = next(o for o in root.children_recursive if o.type == "ARMATURE")
meshes = [o for o in root.children_recursive if o.type == "MESH" and len(o.data.polygons)]
if VMD:
    bpy.context.view_layer.objects.active = root
    root.select_set(True)
    bpy.ops.mmd_tools.import_vmd(filepath=str(Path(VMD).resolve()), scale=0.08, use_pose_mode=False,
                                 margin=0)
    sc.frame_end = max(sc.frame_end, int(max((fc.range()[1] for a in bpy.data.actions
                                              for fc in a.fcurves), default=250)))
sc.frame_set(FRAME)
bpy.context.view_layer.update()

# 足りない絵(MMD 共通のトゥーン toon01.bmp など)は、材質の中でつなぎを外す。残すと色が赤紫になる
import os  # noqa: E402
missing = {im for im in bpy.data.images
           if im.source == "FILE" and not os.path.exists(bpy.path.abspath(im.filepath))}
for mat in bpy.data.materials:
    if not mat.node_tree:
        continue
    for n in mat.node_tree.nodes:
        if n.bl_idname == "ShaderNodeTexImage" and n.image in missing:
            for o in n.outputs:
                for lk in list(o.links):
                    mat.node_tree.links.remove(lk)
print("@@@ missing images", sorted(im.name for im in missing), flush=True)

# 体の向き: 上半身の骨の前(MMD は -Y が前)
pb = arm.pose.bones
ub = next((pb[n] for n in ("上半身", "上半身2", "upper body") if n in pb), None)
# 骨の向きの軸はモデルごとに違うので、休みの姿勢からどれだけ回ったかを、モデルの前(-Y)に掛ける
if ub:
    rot = (ub.matrix.to_3x3() @ ub.bone.matrix_local.to_3x3().inverted())
    fwd_body = arm.matrix_world.to_3x3() @ rot @ Vector((0, -1, 0))
else:
    fwd_body = Vector((0, -1, 0))
fwd_body.z = 0
fwd_body.normalize()

# 大きさ: ポーズを付けた見えている形の箱
dg = bpy.context.evaluated_depsgraph_get()
pts = []
for o in meshes:
    ev = o.evaluated_get(dg)
    me = ev.to_mesh()
    mw = o.matrix_world
    step = max(1, len(me.vertices) // 20000)
    pts += [mw @ me.vertices[i].co for i in range(0, len(me.vertices), step)]
    ev.to_mesh_clear()
zs = sorted(p.z for p in pts)
z_top, z_bot = zs[int(len(zs) * 0.999)], zs[int(len(zs) * 0.001)]
cx = sum(p.x for p in pts) / len(pts)
cy = sum(p.y for p in pts) / len(pts)
if SHOT == "full":
    lo_z, hi_z = z_bot, z_top
elif SHOT == "face":
    nk = arm.matrix_world @ pb[next(n for n in ("首", "neck") if n in pb)].head
    hd = arm.matrix_world @ pb[next(n for n in ("頭", "head") if n in pb)].head
    # 頭の骨から上の、頭の幅のあたりの点だけで高さを取る(耳やツインテールの先で広がらないように)
    near = [p for p in pts if (Vector((p.x, p.y)) - Vector((hd.x, hd.y))).length < 0.25 and p.z > nk.z]
    zz = sorted(p.z for p in near)
    lo_z, hi_z = nk.z - (hd.z - nk.z) * 1.2, zz[int(len(zz) * 0.97)]
    cx, cy = hd.x, hd.y
else:
    lo_z, hi_z = z_top - (z_top - z_bot) * 0.55, z_top
height = (hi_z - lo_z) * 1.10
ctr = Vector((cx, cy, (lo_z + hi_z) / 2))
cd = bpy.data.cameras.new("Cam")
cd.lens = {"full": 50, "face": 100}.get(SHOT, 85)
cd.sensor_fit = "VERTICAL"
cam = bpy.data.objects.new("Cam", cd)
sc.collection.objects.link(cam)
sc.camera = cam
yaw = math.radians(YAW)
f = Matrix.Rotation(yaw, 3, "Z") @ fwd_body
dist = height / (2 * math.tan(cd.angle_y / 2))
d = Vector((f.x, f.y, 0.10)).normalized()
cam.location = ctr + d * dist
cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
sc.render.resolution_x, sc.render.resolution_y = RES, RES * 9 // 16

sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
sun.data.energy = 3.5
sc.collection.objects.link(sun)
m = (cam.matrix_world.to_3x3() @ Matrix.Rotation(math.radians(25), 3, "X")
     @ Matrix.Rotation(math.radians(-15), 3, "Y"))
sun.rotation_euler = m.to_euler()
sc.view_settings.view_transform = "Standard"
sc.eevee.taa_render_samples = 16
world = bpy.data.worlds.new("W")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.05, 0.06, 1)
sc.world = world
for o in sc.objects:                        # 剛体・ジョイントなどの見えない物は描かない
    if o.type == "MESH" and o not in meshes:
        o.hide_render = True
    if o.type == "EMPTY" and o is not root:
        o.hide_render = True
for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
    if hasattr(sc, p_):
        setattr(sc, p_, False)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{NAME}_clean.blend"))
print("@@@ saved", NAME, "meshes", [(o.name, len(o.data.polygons), len(o.data.materials)) for o in meshes],
      "frames", sc.frame_start, sc.frame_end, flush=True)
if "--preview" in ARGV:
    sc.render.filepath = str(OUT / f"{NAME}_preview.png")
    bpy.ops.render.render(write_still=True)
    print("@@@ preview", sc.render.filepath, flush=True)
