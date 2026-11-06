"""キャラの体を通り抜ける頭上のケーブルを持ち上げる(face_fix.py の後)。

  blender -b <previz.blend> --python cable_clear.py -- <出力.blend> [--margin 0.35] [--every 2]

build_city.py の頭上のケーブル(Cable_・BridgeCable_)は 1〜4 m たるむので、低い所が歩く高さまで下がって体に埋まった(4643)。
全コマ(--every おき)の骨の位置を集め、ケーブルの点から水平 0.45 m 以内に体の点があり、その点 + --margin より低い所があれば、
たるみを減らす形(両端は止めたまま、真ん中ほど上げる 4u(1-u))で、足りない分を全部まかなうだけ上げる。
"""
import sys

import bpy
import numpy as np
from mathutils import Vector

A = sys.argv[sys.argv.index("--") + 1:]
OUT = A[0]
arg = lambda n, d: A[A.index(n) + 1] if n in A else d   # noqa: E731
MARGIN = float(arg("--margin", "0.35"))
EVERY = int(arg("--every", "2"))
NEAR = 0.45

sc = bpy.context.scene
arm = bpy.data.objects["Armature"]
hidden = [o for o in sc.objects if o is not arm and not o.hide_viewport]
for o in hidden:
    o.hide_viewport = True

bones = [pb for pb in arm.pose.bones if pb.bone.use_deform]
pts = []
for f in range(sc.frame_start, sc.frame_end + 1, EVERY):
    sc.frame_set(f)
    mw = arm.matrix_world
    for pb in bones:
        pts.append((*(mw @ pb.head), f))
        pts.append((*(mw @ pb.tail), f))
    hd = arm.pose.bones["head.x"]
    pts.append((*(mw @ (hd.tail + (hd.tail - hd.head) * 0.6)), f))      # 頭のてっぺん(髪・耳)
B = np.array(pts)
print("@@ body points", len(B), flush=True)
for o in hidden:
    o.hide_viewport = False

lifted = []
for o in sc.objects:
    if o.type != "CURVE" or not o.name.startswith(("Cable_", "BridgeCable_")):
        continue
    sp = o.data.splines[0]
    M = o.matrix_world
    W = np.array([tuple(M @ Vector(tuple(p.co)[:3])) for p in sp.points])
    n = len(W)
    u0 = np.linspace(0, 1, n)
    # 線の上を細かく取る
    ud = np.linspace(0, 1, (n - 1) * 8 + 1)
    Q = np.stack([np.interp(ud, u0, W[:, k]) for k in range(3)], 1)
    lo, hi = Q.min(0) - NEAR - 0.5, Q.max(0) + NEAR + 0.5
    sel = B[np.all((B[:, :3] > lo) & (B[:, :3] < hi), axis=1)]
    if not len(sel):
        continue
    r = o.data.bevel_depth
    need = np.zeros(len(Q))
    for k, q in enumerate(Q):
        d = np.hypot(sel[:, 0] - q[0], sel[:, 1] - q[1])
        m = d < NEAR
        if m.any():
            need[k] = max(0.0, (sel[m, 2] + MARGIN + r - q[2]).max())
    if need.max() <= 0:
        continue
    bump = 4 * ud * (1 - ud)
    L = float((need / np.maximum(bump, 0.15)).max())
    inv = M.inverted().to_3x3()
    for i, p in enumerate(sp.points):
        dl = inv @ Vector((0, 0, L * 4 * u0[i] * (1 - u0[i])))
        p.co = (p.co[0] + dl.x, p.co[1] + dl.y, p.co[2] + dl.z, p.co[3])
    lifted.append((o.name, round(L, 2)))
print("@@ lifted", len(lifted), lifted, flush=True)

bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("@@ wrote", OUT, flush=True)
