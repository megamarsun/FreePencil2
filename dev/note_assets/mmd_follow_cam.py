"""並んだダンスの場面のカメラを、キャラたちの真ん中を追うカメラにする(動きはならす)。

  blender -b <Four_dance_clean.blend> --python mmd_follow_cam.py -- [--margin 1.10]

このダンスは横に歩くので、区間の全部が入るように止めたカメラだと、どのコマでも 4 体が
片側に寄って小さく写った。コマごとの見えている形の箱の真ん中と大きさを、前後 15 コマで
ならしてカメラに入れる(大きさは区間の最大に合わせて、ズームはしない)。
"""
import math
import sys

import bpy
from mathutils import Matrix, Vector

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
MARGIN = float(ARGV[ARGV.index("--margin") + 1]) if "--margin" in ARGV else 1.10
sc = bpy.context.scene
cam = sc.camera
meshes = [o for o in sc.objects if o.type == "MESH" and not o.hide_render and len(o.data.polygons)]
F0, F1 = sc.frame_start, sc.frame_end
ctrs, sizes = [], []
for f in range(F0, F1 + 1):
    sc.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    xs, zs = [], []
    for o in meshes:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        mw = o.matrix_world.copy()
        step = max(1, len(me.vertices) // 1500)
        for i in range(0, len(me.vertices), step):
            p = mw @ me.vertices[i].co
            xs.append(p.x)
            zs.append(p.z)
        ev.to_mesh_clear()
    xs.sort()
    zs.sort()
    lo = Vector((xs[int(len(xs) * 0.002)], 0, zs[int(len(zs) * 0.001)]))
    hi = Vector((xs[int(len(xs) * 0.998)], 0, zs[int(len(zs) * 0.999)]))
    ctrs.append((lo + hi) / 2)
    sizes.append((hi.x - lo.x, hi.z - lo.z))


def smooth(seq, k=15):
    out = []
    for i in range(len(seq)):
        a, b = max(0, i - k), min(len(seq), i + k + 1)
        s = Vector((0, 0, 0))
        for v in seq[a:b]:
            s += v
        out.append(s / (b - a))
    return out


ctrs = smooth(ctrs)
w = max(s[0] for s in sizes) * MARGIN
h = max(s[1] for s in sizes) * MARGIN
cd = cam.data
aspect = sc.render.resolution_x / sc.render.resolution_y
need_h = max(h, w / aspect)
dist = need_h / (2 * math.tan(cd.angle_y / 2))
d = Vector((0.0, -1.0, 0.06)).normalized()
cam.animation_data_clear()
for i, f in enumerate(range(F0, F1 + 1)):
    c = Vector((ctrs[i].x, 0.0, ctrs[i].z))
    cam.location = c + d * dist
    cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.keyframe_insert("location", frame=f)
    cam.keyframe_insert("rotation_euler", frame=f)
# 日はカメラについて行く(向きはカメラの向きから 10° 上・左へ 15°。回す向きは -10)
sun = next(o for o in sc.objects if o.type == "LIGHT")
sc.frame_set(F0)
bpy.context.view_layer.update()
sun.rotation_euler = (cam.matrix_world.to_3x3() @ Matrix.Rotation(math.radians(-10), 3, "X")
                      @ Matrix.Rotation(math.radians(-15), 3, "Y")).to_euler()
bpy.ops.wm.save_mainfile()
print("@@@ follow cam", F0, F1, f"w={w:.2f} h={h:.2f} dist={dist:.2f}",
      f"x {min(c.x for c in ctrs):.2f}..{max(c.x for c in ctrs):.2f}", flush=True)
