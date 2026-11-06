"""頭上のケーブルを直す(face_fix.py の後): キャラの体を通り抜けるものを持ち上げ、宙で切れている端を延ばす。

  blender -b <previz.blend> --python cable_clear.py -- <出力.blend> [--margin 0.35] [--every 2] [--no-extend]

build_city.py の頭上のケーブル(Cable_・BridgeCable_)は 1〜4 m たるむので、低い所が歩く高さまで下がって体に埋まった(4643)。
全コマ(--every おき)の骨の位置を集め、ケーブルの点から水平 0.45 m 以内に体の点があり、その点 + --margin より低い所があれば、
たるみを減らす形(両端は止めたまま、真ん中ほど上げる 4u(1-u))で、足りない分を全部まかなうだけ上げる。

頭上のケーブル(Cable_)は道の左右 3.5〜9 m の所で終わっていて、背景で宙に切れて見えた。両端を同じ たるみの線(横は まっすぐ、
高さは 2 次)のまま 1 m ずつ延ばし、横へ EXT_H m か、端から EXT_Z m 上がるまで続ける。カメラの通り道から 0.8 m・
体から水平 0.45 m(体より上 --margin まで)へ入る・端より 0.5 m 下へ垂れていくなら、その側は延ばさない(レンズの前を横切る・体に埋まる・道の脇で切れるのを作らない)。
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
EXTEND = "--no-extend" not in A
EXT_H, EXT_Z = 30.0, 18.0

sc = bpy.context.scene
arm = bpy.data.objects["Armature"]
hidden = [o for o in sc.objects if o is not arm and not o.hide_viewport]
for o in hidden:
    o.hide_viewport = True

bones = [pb for pb in arm.pose.bones if pb.bone.use_deform]
cams = {m.camera for m in sc.timeline_markers if m.camera} | ({sc.camera} if sc.camera else set())
pts = []
cpts = []
for f in range(sc.frame_start, sc.frame_end + 1, EVERY):
    sc.frame_set(f)
    mw = arm.matrix_world
    for pb in bones:
        pts.append((*(mw @ pb.head), f))
        pts.append((*(mw @ pb.tail), f))
    hd = arm.pose.bones["head.x"]
    pts.append((*(mw @ (hd.tail + (hd.tail - hd.head) * 0.6)), f))      # 頭のてっぺん(髪・耳)
    for c in cams:
        cpts.append(tuple(c.matrix_world.translation))
B = np.array(pts)
CP = np.array(cpts)
print("@@ body points", len(B), flush=True)
for o in hidden:
    o.hide_viewport = False

lifted = []
lift_of = {}
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
    lift_of[o.name] = L
print("@@ lifted", len(lifted), lifted, flush=True)


def blocked(q, r):
    if len(CP) and np.linalg.norm(CP - q, axis=1).min() < r + 0.8:
        return True
    d = np.hypot(B[:, 0] - q[0], B[:, 1] - q[1])
    m = d < NEAR
    return bool(m.any() and (q[2] < B[m, 2] + MARGIN + r).any())


if EXTEND:
    added = 0
    for o in sc.objects:
        # 橋の下のケーブル(BridgeCable_)は橋に沿って両端が橋に付いているので延ばさない(延ばすと道に沿って伸び、正面から棒に見えた)
        if o.type != "CURVE" or not o.name.startswith("Cable_"):
            continue
        sp = o.data.splines[0]
        M = o.matrix_world
        W = np.array([tuple(M @ Vector(tuple(p.co)[:3])) for p in sp.points])
        n = len(W)
        u0 = np.linspace(0, 1, n)
        cx, cy, cz = np.polyfit(u0, W[:, 0], 1), np.polyfit(u0, W[:, 1], 1), np.polyfit(u0, W[:, 2], 2)
        # 持ち上げたケーブルは延ばす所を持ち上げる前の たるみで(持ち上げで弓なりになり、延ばすと下へ垂れて道へ届いた)
        Lf = lift_of.get(o.name, 0.0)
        cz = cz + np.array([4 * Lf, -4 * Lf, 0.0])
        Lh = float(np.hypot(cx[0], cy[0]))
        if Lh < 1e-3:
            continue
        du = 1.0 / Lh
        r = o.data.bevel_depth
        ext = {}
        for side, u_end, sgn in (("a", 0.0, -1), ("b", 1.0, 1)):
            z_end = np.polyval(cz, u_end)
            out = []
            k = 1
            while k * du * Lh <= EXT_H:
                u = u_end + sgn * k * du
                q = np.array([np.polyval(cx, u), np.polyval(cy, u), np.polyval(cz, u)])
                # 途中で止めると また切れて見えるので、ぶつかる側・端より下へ垂れていく側は延ばさない
                if blocked(q, r) or q[2] < z_end - 0.5:
                    out = []
                    break
                out.append(q)
                if q[2] - z_end > EXT_Z:
                    break
                k += 1
            ext[side] = out
        allp = list(reversed(ext["a"])) + list(W) + ext["b"]
        if len(allp) == n:
            continue
        inv = M.inverted()
        sp.points.add(len(allp) - n)
        for p_, q in zip(sp.points, allp):
            lq = inv @ Vector(tuple(q))
            p_.co = (lq.x, lq.y, lq.z, 1)
        added += 1
    print("@@ extended", added, "cables", flush=True)

bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("@@ wrote", OUT, flush=True)
