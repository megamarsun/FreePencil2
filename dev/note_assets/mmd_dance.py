"""MMD のダンスの場面を作る: モデル + モーション + 物理(髪・スカートの揺れ)+ 全身が入る止めカメラ。

  blender -b --factory-startup --python mmd_dance.py -- --pmx <pmx>[;<pmx>…] --vmd <vmd> --out <dir> --name <名前>
          --start 300 --len 300 [--res 1920] [--yaw 15] [--gap 0.75]

--pmx に ; で区切って複数渡すと、左から順に gap(m)おきに並べて同じダンスを踊らせる。

カメラは、使う区間の全身が入るよう、何コマかの見えている形の箱から決める。
日はカメラの向きから 10° 上(回す向きは -10。+ だと下からになる)・左へ 15°(アニメの顔は正面から)。
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import addon_utils
import bpy
from mathutils import Matrix, Vector

ARGV = sys.argv[sys.argv.index("--") + 1:]
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d   # noqa: E731
PMXS = [Path(p).resolve() for p in arg("--pmx").split(";")]
VMD = Path(arg("--vmd")).resolve()
GAP = float(arg("--gap", "0.75"))
OUT = Path(arg("--out")).resolve()
OUT.mkdir(parents=True, exist_ok=True)
NAME = arg("--name")
START, LEN = int(arg("--start", "300")), int(arg("--len", "300"))
RES = int(arg("--res", "1920"))
YAW = float(arg("--yaw", "15"))

mod = next(m.__name__ for m in addon_utils.modules() if m.__name__.endswith("mmd_tools"))
addon_utils.enable(mod, default_set=False, persistent=False)
bpy.ops.wm.read_homefile(use_empty=True)
sc = bpy.context.scene
sc.render.fps = 30
roots, meshes = [], []
for k, pmx in enumerate(PMXS):
    before = set(sc.objects)
    bpy.ops.mmd_tools.import_model(filepath=str(pmx), scale=0.08,
                                   types={"MESH", "ARMATURE", "PHYSICS", "MORPHS"}, log_level="ERROR")
    root = next(o for o in set(sc.objects) - before if getattr(o, "mmd_type", "") == "ROOT")
    root.location.x = (k - (len(PMXS) - 1) / 2) * GAP
    roots.append(root)
    meshes += [o for o in root.children_recursive if o.type == "MESH" and len(o.data.polygons)
               and getattr(o, "mmd_type", "NONE") == "NONE"]
    for o in sc.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = root
    root.select_set(True)
    bpy.ops.mmd_tools.import_vmd(filepath=str(VMD), scale=0.08, use_pose_mode=False, margin=0)

# 足りない MMD 共通のトゥーン絵のつなぎを外す(残すと色が赤紫になる)
missing = {im for im in bpy.data.images
           if im.source == "FILE" and not os.path.exists(bpy.path.abspath(im.filepath))}
for mat in bpy.data.materials:
    for n in (mat.node_tree.nodes if mat.node_tree else []):
        if n.bl_idname == "ShaderNodeTexImage" and n.image in missing:
            for o in n.outputs:
                for lk in list(o.links):
                    mat.node_tree.links.remove(lk)

HAIR_KEYS = ("髪", "ツイン", "テール", "もみあげ", "hair", "Hair", "tail", "Tail", "Pony", "pony")
ARM_KEYS = ("腕", "ひじ", "手", "arm", "Arm", "elbow", "Elbow", "hand", "Hand")
FIX = (arg("--hair-fix", "") or "").split(",")


def _rigids(root):
    return [o for o in root.children_recursive if getattr(o, "mmd_type", "") == "RIGID_BODY"]


if "noarm" in FIX:
    # 髪が腕と当たらないようにする。モデルによっては髪が体とは当たらず腕とだけ当たる設定で、
    # 腕を振ると髪が前へ払われ、体をすり抜けて前に回り込んだ(ツインテールの巻き込み)
    for root in roots:
        rbs = _rigids(root)
        arm_groups = {o.mmd_rigid.collision_group_number for o in rbs if any(k in o.name for k in ARM_KEYS)}
        n = 0
        for o in rbs:
            if o.mmd_rigid.type != "0" and any(k in o.name for k in HAIR_KEYS):
                for g in arm_groups:
                    o.mmd_rigid.collision_group_mask[g] = True
                n += 1
        print("@@@ hair noarm", root.name, n, sorted(arm_groups), flush=True)
sc.frame_start, sc.frame_end = START, START + LEN - 1
# 物理: 剛体を組み、区間の頭の少し前から計算する(助走が無いと最初のコマで髪が跳ねる)
for root in roots:
    for o in sc.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = root
    root.select_set(True)
    try:
        bpy.ops.mmd_tools.build_rig()
    except Exception as e:                          # noqa: BLE001
        print("@@@ build_rig:", e, flush=True)
if "damp" in FIX:
    # 髪の揺れを抑える(減衰を強める)。払われても前へ回り込みにくくする
    for root in roots:
        for o in _rigids(root):
            if o.rigid_body and o.mmd_rigid.type != "0" and any(k in o.name for k in HAIR_KEYS):
                o.rigid_body.linear_damping = max(o.rigid_body.linear_damping, 0.8)
                o.rigid_body.angular_damping = max(o.rigid_body.angular_damping, 0.95)
rbw = sc.rigidbody_world
if rbw is not None:
    # モーションの頭(1 コマ目)から計算する。途中のコマから始めると、そのコマのポーズに剛体が
    # いきなり置かれ、ツインテールが体に挟まって片側に寄ったまま戻らなかった(1 体でも出た)
    rbw.point_cache.frame_start = int(arg("--physics-from", "1"))
    rbw.point_cache.frame_end = START + LEN
    rbw.substeps_per_frame = 6
    with bpy.context.temp_override(scene=sc, point_cache=rbw.point_cache):
        bpy.ops.ptcache.bake(bake=True)
    print("@@@ physics baked", rbw.point_cache.frame_start, rbw.point_cache.frame_end, flush=True)
for o in sc.objects:                                # 剛体・ジョイントの形は描かない
    if o.type in ("MESH", "EMPTY") and o not in meshes and o not in roots:
        o.hide_render = True

# 区間の見えている形の箱
dg = bpy.context.evaluated_depsgraph_get()
pts = []
for f in range(START, START + LEN, max(1, LEN // 12)):
    sc.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    for o in meshes:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        mw = o.matrix_world.copy()
        step = max(1, len(me.vertices) // 4000)
        pts += [mw @ me.vertices[i].co for i in range(0, len(me.vertices), step)]
        ev.to_mesh_clear()
xs, ys, zs = (sorted(p[i] for p in pts) for i in range(3))
q = lambda a, t: a[int(len(a) * t)]                 # noqa: E731
lo = Vector((q(xs, 0.002), q(ys, 0.002), q(zs, 0.001)))
hi = Vector((q(xs, 0.998), q(ys, 0.998), q(zs, 0.999)))
ctr = (lo + hi) / 2
cd = bpy.data.cameras.new("Cam")
cd.lens = 50
cd.sensor_fit = "VERTICAL"
cam = bpy.data.objects.new("Cam", cd)
sc.collection.objects.link(cam)
sc.camera = cam
yaw = math.radians(YAW)
height = (hi.z - lo.z) * 1.12
width = max(hi.x - lo.x, hi.y - lo.y) * 1.15
dist = max(height / (2 * math.tan(cd.angle_y / 2)), width / (2 * math.tan(cd.angle_y / 2)) / (16 / 9))
d = Vector((math.sin(yaw), -math.cos(yaw), 0.08)).normalized()
cam.location = ctr + d * (dist + (hi.y - lo.y) / 2)
cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
sc.render.resolution_x, sc.render.resolution_y = RES, RES * 9 // 16
bpy.context.view_layer.update()                    # カメラの向きを入れてから日を合わせる(入れないと真上から)
sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
sun.data.energy = 3.5
sc.collection.objects.link(sun)
sun.rotation_euler = (cam.matrix_world.to_3x3() @ Matrix.Rotation(math.radians(-10), 3, "X")
                      @ Matrix.Rotation(math.radians(-15), 3, "Y")).to_euler()
sc.view_settings.view_transform = "Standard"
sc.eevee.taa_render_samples = 16
w = bpy.data.worlds.new("W")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.05, 0.06, 1)
sc.world = w
for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
    if hasattr(sc, p_):
        setattr(sc, p_, False)
sc.frame_set(START)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{NAME}_dance_clean.blend"))
print("@@@ saved", NAME, START, LEN, flush=True)
