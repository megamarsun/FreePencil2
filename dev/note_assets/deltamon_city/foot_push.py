"""足が床・段に埋まったコマだけ、足を真上へ押し上げる(埋まった分だけ。引っ張らない)。

  blender -b <previz.blend> --python foot_push.py -- <出力.blend> [--measure-only] [--ramp 3] [--sigma 2] [--no-hip] [--log out.txt]
      [--tol 0.025] [--no-knee] [--bob-at 4148-4182,...] [--glide-at 3745-3795,...]

靴の裏の点を足首・つま先の骨に乗せて毎コマ動かし、床(Walkway・Walkway_Grates)の中に入った点を
見つける(点から真上へ撃って越える面の数が奇数なら中)。街は腰の通り道で置いてあり床が一様に 4 cm ほど高いので、
先に街をその分下げる。埋まっていないコマは何もしない(動きは MotionBricks のまま)。
埋まったコマは、床の外へ一番近い向き(真上か、段の蹴上げなら足の前後の水平)へ その分だけ足首を出す: 股関節は動かさず、もも・すねを 2 本の骨の三角形で解き直し、
ひざは元の側へ出し、足の向き(世界での向き)は元のまま。
押し出しの量は前後 --ramp コマへ広げてから --sigma コマで ならす(コマごとに量が違うと ひざがガタついた)。
先に腰を上げられる分は腰で受ける: もう片方の足が宙にある間は、その足が床に着かない高さまで腰(root.x)ごと上げる
(脚の形が変わらないので ひざが動かない)。両足が着いている間は脚で受ける。
そのコマは足の IK(fp_foot_ik)を切り、解いた姿勢を FK で焼き込む(IK の結果を元にしているので、つなぎ目で跳ばない)。
"""
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

A = sys.argv[sys.argv.index("--") + 1:]
OUT = A[0]
MEASURE = "--measure-only" in A
arg = lambda n, d: A[A.index(n) + 1] if n in A else d   # noqa: E731
RAMP = int(arg("--ramp", "3"))
RELAX = "--no-relax" not in A
KNEE = "--no-knee" not in A
SIGMA = float(arg("--sigma", "2"))
HIP = "--no-hip" not in A
BOB_AT = [tuple(int(v) for v in r.split("-")) for r in arg("--bob-at", "").split(",") if r]       # 腰の跳ねを ならす範囲
GLIDE_AT = [tuple(int(v) for v in r.split("-")) for r in arg("--glide-at", "").split(",") if r]   # 滑りを直すコマの範囲
GLIDE_TO = {"skim": 0.10, "slide": 0.05}     # 滑る足を上げる先(床から m)。こする足は振り出しらしく高めに
LOG = arg("--log", None)
WIN = 0.30            # 足の点の この高さ上までの床だけ見る(手すりの上などを床と見なさない)
TOL = float(arg("--tol", "0.004"))    # これ未満の埋まりは無視(--tol 0.025 で 毎歩の かかと・つま先の 2 cm ほどは押さない)
DEBUG = [int(x) for x in arg("--debug-frames", "").split(",") if x]      # 確かめ用: そのコマの押し出しの候補を出して終わる

sc = bpy.context.scene
arm = bpy.data.objects["Armature"]
shoe = bpy.data.objects["1_deltamon_shoes"]
F0, F1 = sc.frame_start, sc.frame_end

# ---------------------------------------------------------------- 床(世界座標の BVH)
root = bpy.data.objects["City_Root"]


def floor_bvh():
    verts, polys = [], []
    # 修飾は無い。隠していても測れるよう元のメッシュで。黄色い縁取り(Walkway_Edges)は上の面に 4 mm 浮かせた 1 枚の面で、
    # 中か外かの数え(下の inside)を狂わせるので入れない
    for n in ("Walkway", "Walkway_Grates"):
        o = bpy.data.objects[n]
        me = o.data
        mw = root.matrix_world @ o.matrix_parent_inverse @ o.matrix_basis
        base = len(verts)
        verts += [mw @ v.co for v in me.vertices]
        polys += [[base + i for i in p.vertices] for p in me.polygons]
    return BVHTree.FromPolygons(verts, polys)


bvh = floor_bvh()

# ---------------------------------------------------------------- 靴の裏の点(骨の空間)
SIDES = {"L": ("thigh_stretch.l", "leg_stretch.l", "foot.l", "toes_01.l"),
         "R": ("thigh_stretch.r", "leg_stretch.r", "foot.r", "toes_01.r")}
to_arm = arm.matrix_world.inverted() @ shoe.matrix_world
gi = {g.name: g.index for g in shoe.vertex_groups}
sole = {}
for side, (_, _, foot, toe) in SIDES.items():
    pts = []
    for v in shoe.data.vertices:
        w = {g.group: g.weight for g in v.groups}
        wf, wt = w.get(gi.get(foot), 0), w.get(gi.get(toe), 0)
        if max(wf, wt) < 0.5:
            continue
        pts.append((foot if wf >= wt else toe, to_arm @ v.co))
    zmin = min(p.z for _, p in pts)
    pts = [(b, p) for b, p in pts if p.z < zmin + 0.03]        # 靴の裏から 3 cm まで
    sole[side] = [(b, arm.data.bones[b].matrix_local.inverted() @ p) for b, p in pts[::max(1, len(pts) // 80)]]
    print("@@ sole", side, len(sole[side]), "points", flush=True)

# 測る間は骨だけ動かす(重い物の評価を止める)
hidden = [o for o in sc.objects if o is not arm and not o.hide_viewport]
for o in hidden:
    o.hide_viewport = True


def depth(side):
    """靴の裏が床より下に入った深さ(m)の一番深い所"""
    mw = arm.matrix_world
    d = 0.0
    for b, p in sole[side]:
        w = mw @ (arm.pose.bones[b].matrix @ p)
        hit = bvh.ray_cast(w + Vector((0, 0, WIN)), Vector((0, 0, -1)), WIN)
        if hit[0] is not None:
            d = max(d, hit[0].z - w.z)
    return d


def inside(w):
    """点が床の中なら、真上の床の上の面までの距離。外なら None。真上へ撃って面を何枚 越えるかの奇数・偶数で見る
    (面の向きは段の所でそろっていなかった)"""
    o, n, first = w.copy(), 0, None
    while True:
        hit = bvh.ray_cast(o, Vector((0, 0, 1)), 3.0)
        if hit[0] is None:
            break
        n += 1
        if first is None:
            first = hit[0].z - w.z
        o = hit[0] + Vector((0, 0, 1e-4))
    return first if n % 2 == 1 and first < WIN else None


def push_vec(side):
    """床の中に入った靴の裏の点を、一番近い外へ出す動き(真上か、足の前後の水平)。入っていなければ 0"""
    mw = arm.matrix_world
    P = arm.pose.bones
    fwd = mw.to_3x3() @ (P[SIDES[side][2]].matrix.to_3x3() @ Vector((0, 1, 0)))
    fwd.z = 0
    fwd = fwd.normalized() if fwd.length > 1e-6 else Vector((1, 0, 0))
    up, back, ahead = 0.0, 0.0, 0.0
    n = 0
    for b, p in sole[side]:
        w = mw @ (P[b].matrix @ p)
        dz = inside(w)
        if dz is None:
            continue
        n += 1
        up = max(up, dz)
        hb = bvh.ray_cast(w, -fwd, 2 * WIN)
        hf = bvh.ray_cast(w, fwd, 2 * WIN)
        back = max(back, hb[3] if hb[0] is not None else 9.0)
        ahead = max(ahead, hf[3] if hf[0] is not None else 9.0)
    if n == 0:
        return Vector()
    if DEBUG:
        print("@@ dbg", sc.frame_current, side, "points in", n, "up", round(up, 3), "back", round(back, 3), "ahead", round(ahead, 3))
    m = min(up, back, ahead)
    if m == up:
        return Vector((0, 0, up))
    return -fwd * back if m == back else fwd * ahead


def clearance(side):
    """足の裏の一番低い点から真下の床までの高さ(床の中なら 0、下に床が無ければ 1 m)"""
    mw = arm.matrix_world
    c = 1.0
    for b, p in sole[side]:
        w = mw @ (arm.pose.bones[b].matrix @ p)
        hit = bvh.ray_cast(w, Vector((0, 0, -1)), 1.0)
        if hit[0] is not None:
            c = min(c, w.z - hit[0].z)
    return max(c, 0.0)


def measure():
    out = {s: np.zeros(F1 - F0 + 1) for s in SIDES}
    vec = {s: np.zeros((F1 - F0 + 1, 3)) for s in SIDES}
    clr = {s: np.zeros(F1 - F0 + 1) for s in SIDES}
    leg = {s: np.zeros((F1 - F0 + 1, 3, 3)) for s in SIDES}      # 股関節・足首・ひざ(アーマチュアの空間)
    anc = {s: np.zeros((F1 - F0 + 1, 3)) for s in SIDES}         # 足首(世界)
    tilt = {s: np.zeros(F1 - F0 + 1) for s in SIDES}             # 足首 - つま先の付け根の高さ(0 で足が平ら)
    for f in range(F0, F1 + 1):
        sc.frame_set(f)
        for s in SIDES:
            out[s][f - F0] = depth(s)
            vec[s][f - F0] = push_vec(s)
            clr[s][f - F0] = clearance(s)
            P = arm.pose.bones
            leg[s][f - F0] = (P[SIDES[s][0]].head, P[SIDES[s][2]].head, P[SIDES[s][1]].head)
            anc[s][f - F0] = arm.matrix_world @ P[SIDES[s][2]].head
            tilt[s][f - F0] = (arm.matrix_world @ P[SIDES[s][2]].head).z - (arm.matrix_world @ P[SIDES[s][2]].tail).z
    measure.clr = clr
    measure.leg = leg
    measure.anc = anc
    measure.tilt = tilt
    return out, vec


if DEBUG:
    for f in DEBUG:
        sc.frame_set(f)
        for sd in SIDES:
            push_vec(sd)
    sys.exit(0)
D, V = measure()
LEG0 = {s: measure.leg[s].copy() for s in SIDES}        # 元の動きの 股関節-足首(押す前)
# 街は腰の通り道で合わせて置いてあり(build_city.py)、床が足の裏より一様に高い。立っている足(深い方の足。上げている足は 0 になる)の
# 埋まりの中央値だけ街を下げる(動きでなく地形を合わせる)。残った所だけ押し上げる
off = float(np.median(np.maximum(D["L"], D["R"])))
print("@@ floor offset cm", round(off * 100, 2), flush=True)
if off > 0.005 and "--no-offset" not in A:
    mw = root.matrix_world.copy()
    mw.translation.z -= off
    root.matrix_world = mw
    bvh = floor_bvh()
    D, V = measure()
def report(tag, V):
    for s in SIDES:
        m = np.linalg.norm(V[s], axis=1)
        print("@@", tag, s, "frames", int((m > TOL).sum()), "max cm", round(m.max() * 100, 1),
              "at", int(np.argmax(m)) + F0, "sideways", int(((m > TOL) & (np.abs(V[s][:, 2]) < 1e-9)).sum()), flush=True)


report("before", V)
if LOG:
    np.savetxt(LOG, np.c_[np.arange(F0, F1 + 1), V["L"], V["R"]], fmt="%.4f")

if MEASURE:
    np.savez(OUT.replace(".blend", "_clr.npz"), L=measure.clr["L"], R=measure.clr["R"],
             aL=measure.anc["L"], aR=measure.anc["R"], tL=measure.tilt["L"], tR=measure.tilt["R"])
    sys.exit(0)

# ---------------------------------------------------------------- 押し上げる量(埋まった分を必ず上回る、なめらかな包み)
# 前後 RAMP コマへは、近いコマの押し出しを なめらかに弱めて広げる(一番大きい物を取る)
def gauss(x, sigma):
    """コマに沿った ガウスのならし(端は端の値で延ばす)"""
    if sigma <= 0:
        return x.copy()
    r = int(3 * sigma + 0.5)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    pad = np.concatenate([np.repeat(x[:1], r, 0), x, np.repeat(x[-1:], r, 0)])
    if x.ndim == 1:
        return np.convolve(pad, k, "valid")
    return np.stack([np.convolve(pad[:, i], k, "valid") for i in range(x.shape[1])], 1)


def envelope(V, ramp, sigma=0.0):
    lift = {}
    for s in SIDES:
        m = np.linalg.norm(V[s], axis=1)
        d = np.where((m > TOL)[:, None], V[s] * ((m + 0.003) / np.maximum(m, 1e-9))[:, None], 0.0)
        e, em = d.copy(), np.linalg.norm(d, axis=1)
        for k in range(1, ramp + 1):
            t = 1 - k / (ramp + 1)
            w = t * t * (3 - 2 * t)
            for src, dst in ((slice(None, -k), slice(k, None)), (slice(k, None), slice(None, -k))):
                cand = d[src] * w
                cm = np.linalg.norm(cand, axis=1)
                better = cm > em[dst]
                e[dst][better] = cand[better]
                em[dst][better] = cm[better]
        if sigma > 0:
            # ならすと山が低くなるので、ならした後も埋まった分を下回らないよう、足りないコマは大きさを足す
            g = gauss(e, sigma)
            gm = np.linalg.norm(g, axis=1)
            need = np.linalg.norm(d, axis=1)
            short = (need > 0) & (gm < need)
            g[short] *= (need[short] / np.maximum(gm[short], 1e-9))[:, None]
            g[np.linalg.norm(g, axis=1) < 1e-4] = 0.0
            e = g
        lift[s] = e
    return lift

act = arm.animation_data.action
# 足を止める IK(ひざの IK)の、元の効き具合。効き始め・切れ目で ひざが跳ねる(下の smooth_knees)
IKW0 = {}
for s_, (_, lg_, _, _) in SIDES.items():
    con_ = next(c for c in arm.pose.bones[lg_].constraints if c.type == 'IK')
    fcu = act.fcurves.find(f'pose.bones["{lg_}"].constraints["{con_.name}"].influence')
    IKW0[s_] = np.array([fcu.evaluate(f) if fcu else con_.influence for f in range(F0, F1 + 1)])


def fc(path, i):
    c = act.fcurves.find(path, index=i)
    if c is None:
        c = act.fcurves.new(path, index=i, action_group=path.split('"')[1] if '"' in path else "")
    return c


def key(path, i, f, v):
    c = fc(path, i)
    c.keyframe_points.insert(f, v, options={'FAST', 'REPLACE'})


def two_bone(side, f, dv):
    """股関節を止めたまま足首を dv(世界)だけ動かす、もも・すね・足の姿勢(アーマチュアの空間)"""
    th, lg, ft, _ = SIDES[side]
    P = arm.pose.bones
    up = arm.matrix_world.inverted().to_3x3() @ dv
    Mt, Ml, Mf = P[th].matrix.copy(), P[lg].matrix.copy(), P[ft].matrix.copy()
    H, K, An = Mt.translation.copy(), Ml.translation.copy(), Mf.translation.copy()
    L1, L2 = (K - H).length, (An - K).length
    At = An + up
    Dv = At - H
    Dl = min(Dv.length, L1 + L2 - 1e-4)
    u = Dv.normalized()
    At = H + u * Dl
    a = (L1 * L1 - L2 * L2 + Dl * Dl) / (2 * Dl)
    h = max(0.0, L1 * L1 - a * a) ** 0.5
    # ひざを出す向き: 元のひざの側。ただし脚がほぼ伸びていた所は その側が決まらない(横へ折れた。4291)ので、
    # 足先の向き(ひざは つま先の側へ曲がる)へ寄せる
    p = (K - H) - u * (K - H).dot(u)
    fw = Mf.to_3x3() @ Vector((0, 1, 0))
    fw = fw - u * fw.dot(u)
    fw = fw.normalized() if fw.length > 1e-6 else Vector((0, 0, 1))
    w = min(1.0, p.length / (0.2 * L1))
    p = p.normalized() * w + fw * (1 - w) if p.length > 1e-6 else fw
    p = p.normalized() if p.length > 1e-6 else fw
    K2 = H + u * a + p * h
    R1 = (K - H).rotation_difference(K2 - H).to_matrix().to_4x4()
    Mt2 = Matrix.Translation(H) @ R1 @ Matrix.Translation(-H) @ Mt
    Ml1 = Matrix.Translation(H) @ R1 @ Matrix.Translation(-H) @ Ml
    R2 = (Ml1.to_3x3() @ (Ml.to_3x3().inverted() @ (An - K))).rotation_difference(At - K2).to_matrix().to_4x4()
    Ml2 = Matrix.Translation(K2) @ R2 @ Matrix.Translation(-K2) @ Ml1
    Mf2 = Mf.copy()
    Mf2.translation = At                  # 足の向きは元のまま、位置だけ上げる
    return (th, Mt2), (lg, Ml2), (ft, Mf2), (At - An).length - up.length


def basis(name, M, parent_M):
    b = arm.data.bones[name]
    rest = b.parent.matrix_local.inverted() @ b.matrix_local if b.parent else b.matrix_local
    return (parent_M @ rest).inverted() @ M


def apply(lift):
    short = {s: 0 for s in SIDES}
    for f in range(F0, F1 + 1):
        todo = [s for s in SIDES if np.linalg.norm(lift[s][f - F0]) > 0]
        if not todo:
            continue
        sc.frame_set(f)
        res = {}
        for s in todo:
            res[s] = two_bone(s, f, Vector(lift[s][f - F0]))
        for s in todo:
            (th, Mt), (lg, Ml), (ft, Mf), miss = res[s]
            if miss < -0.002:
                short[s] += 1
            P = arm.pose.bones
            con = next(c for c in P[lg].constraints if c.type == 'IK')
            cpath = f'pose.bones["{lg}"].constraints["{con.name}"].influence'
            key(cpath, 0, f, 0.0)
            for name, M, parent in ((th, Mt, P[th].parent.matrix), (lg, Ml, Mt), (ft, Mf, Ml)):
                q = basis(name, M, parent).to_quaternion()
                for i in range(4):
                    key(f'pose.bones["{name}"].rotation_quaternion', i, f, q[i])
        # 入る前・出た後のコマは元の値のまま(キーが毎コマあるので そのまま残っている)
    for c in act.fcurves:
        c.update()
    print("@@ pushed", {s: int((np.linalg.norm(lift[s], axis=1) > 0).sum()) for s in SIDES}, "frames; leg too short", short,
          flush=True)


# 押した後に また入った所(前後へ広げた分が段の中へ入った、足の向きで別の点が入った)は、その姿勢から もう一度押す。
# 2 回目からは広げるのを 1 コマだけにする
# ---------------------------------------------------------------- 腰で受ける分
def hip_raise(V, C):
    """片足を上へ押す所で、もう片方の足が宙にある分だけ腰を上げる量(世界の m)"""
    n = F1 - F0 + 1
    raw = np.zeros(n)
    for i in range(n):
        need = []
        for s in SIDES:
            v = V[s][i]
            m = float(np.linalg.norm(v))
            if m > TOL:
                need.append(v[2] + 0.003 if abs(v[0]) + abs(v[1]) < 1e-9 else 0.0)   # 横へ出す所は脚で
            else:
                need.append(C[s][i] - 0.005)          # 宙の足は床から 5 mm 手前まで上げてよい
        if any(np.linalg.norm(V[s][i]) > TOL for s in SIDES):
            raw[i] = max(0.0, min(need))
    # 開く(小さい方で削ってから大きい方で戻す)→ ならす。1 コマだけの山・谷を作らない
    k = 2
    lo = np.array([raw[max(0, i - k):i + k + 1].min() for i in range(n)])
    op = np.array([lo[max(0, i - k):i + k + 1].max() for i in range(n)])
    h = gauss(op, SIGMA * 1.5)
    # 宙の足が床へ着いてしまわないよう、上げてよい高さを超える所は切る
    cap = np.full(n, 1.0)
    for s in SIDES:
        cap = np.minimum(cap, np.where(np.linalg.norm(V[s], axis=1) > TOL, 1.0, C[s] - 0.002))
    return np.clip(np.minimum(h, np.maximum(cap, 0.0)), 0.0, None)


def apply_hip(h):
    pb = arm.pose.bones["root.x"]
    path = 'pose.bones["root.x"].location'
    up_arm = arm.matrix_world.inverted().to_3x3() @ Vector((0, 0, 1))
    for f in range(F0, F1 + 1):
        if abs(h[f - F0]) < 1e-6:
            continue
        sc.frame_set(f)
        par = pb.parent.matrix @ (pb.parent.bone.matrix_local.inverted() @ pb.bone.matrix_local) if pb.parent             else pb.bone.matrix_local
        dl = par.to_3x3().inverted() @ (up_arm * float(h[f - F0]))
        for i in range(3):
            c = fc(path, i)
            key(path, i, f, c.evaluate(f) + dl[i])
    for c in act.fcurves:
        c.update()
    print("@@ hip moved", int((np.abs(h) > 0).sum()), "frames, max cm", round(h.max() * 100, 1), "min cm", round(h.min() * 100, 1),
          flush=True)


if HIP:
    h = hip_raise(V, measure.clr)
    apply_hip(h)
    D, V = measure()
    report("after hip", V)

V2 = V
for it in range(3):
    apply(envelope(V2, RAMP if it == 0 else 1, SIGMA if it == 0 else 1.0))
    D2, V2 = measure()
    report(f"after pass {it + 1}", V2)
    if max(np.linalg.norm(V2[s], axis=1).max() for s in SIDES) <= TOL:
        break


# ---------------------------------------------------------------- 腰を上げて ひざを ゆるめる
def relax_raise():
    """押したことで股関節-足首が元より縮んだ脚(ひざが余計に曲がった)を元の長さへ戻し、一瞬だけ縮む所を埋める腰の上げ幅。
    どちらの脚も伸び切らない(脚の長さの 97% まで)分だけ。足の位置は今のまま"""
    P = arm.pose.bones
    up = (arm.matrix_world.inverted().to_3x3() @ Vector((0, 0, 1))).normalized()
    up = np.array(up)
    Lmax = {}
    for s in SIDES:
        th, lg, ft, _ = SIDES[s]
        Lmax[s] = (P[lg].head - P[th].head).length + (P[ft].head - P[lg].head).length
    leg = measure.leg
    n = F1 - F0 + 1
    need, cap = np.zeros(n), np.full(n, 1.0)

    def raise_to(Hp, Ap, d):
        v = Hp - Ap
        dz = v @ up
        hor2 = max(v @ v - dz * dz, 0.0)
        return (np.sqrt(max(d * d - hor2, 0.0)) - dz) if d * d > hor2 else 0.0

    # 目標の脚の長さ: 押す前の長さと、今の長さの へこみを埋めた物(前後 3 コマで 大きい方→小さい方で閉じてから ならす)。
    # ひざが 1〜2 コマだけ急に曲がる(足を止める IK が効き始める所など)と、股関節-足首が一瞬縮む。そこを腰で埋める
    tgt = {}
    for s in SIDES:
        d1 = np.linalg.norm(leg[s][:, 0] - leg[s][:, 1], axis=1)
        d0 = np.linalg.norm(LEG0[s][:, 0] - LEG0[s][:, 1], axis=1)
        k3 = 3
        hi = np.array([d1[max(0, i - k3):i + k3 + 1].max() for i in range(n)])
        cl = np.array([hi[max(0, i - k3):i + k3 + 1].min() for i in range(n)])
        tgt[s] = np.maximum(np.where(d1 < d0 - 0.002, d0, 0.0), gauss(cl, 1.0))
    for i in range(n):
        for s in SIDES:
            H1, A1 = leg[s][i][:2]
            d1 = np.linalg.norm(H1 - A1)
            if d1 < tgt[s][i] - 0.002:
                need[i] = max(need[i], raise_to(H1, A1, tgt[s][i]))
            cap[i] = min(cap[i], raise_to(H1, A1, 0.97 * Lmax[s]))
    k = 2
    dil = np.array([need[max(0, i - k):i + k + 1].max() for i in range(n)])
    r = gauss(dil, 3.0)
    # 上限は 小さい方で前後 3 コマ削ってから ならし、もとの上限も超えない(ならした上限を超えた所で脚が伸び切って跳ねた)
    cap = np.maximum(cap, 0.0)
    ero = np.array([cap[max(0, i - 3):i + 4].min() for i in range(n)])
    r = np.minimum(np.minimum(r, gauss(ero, 1.5)), cap)
    r[r < 0.002] = 0.0
    return r, need


def apply_relax(r):
    pb = arm.pose.bones["root.x"]
    path = 'pose.bones["root.x"].location'
    up_arm = arm.matrix_world.inverted().to_3x3() @ Vector((0, 0, 1))
    P = arm.pose.bones
    for f in range(F0, F1 + 1):
        if abs(r[f - F0]) < 1e-6:
            continue
        sc.frame_set(f)
        keep = {s: P[SIDES[s][2]].matrix.translation.copy() for s in SIDES}     # 足首(今の、押した後の位置)
        par = pb.parent.matrix @ (pb.parent.bone.matrix_local.inverted() @ pb.bone.matrix_local) if pb.parent             else pb.bone.matrix_local
        dl = par.to_3x3().inverted() @ (up_arm * float(r[f - F0]))
        for i in range(3):
            key(path, i, f, fc(path, i).evaluate(f) + dl[i])
        fc(path, 0).update()
        sc.frame_set(f)
        for s in SIDES:                  # 足は元の所に置いたまま、脚を解き直す(引っ張らない: 足は動かない)
            dv = arm.matrix_world.to_3x3() @ (keep[s] - P[SIDES[s][2]].matrix.translation)
            (th, Mt), (lg, Ml), (ft, Mf), miss = two_bone(s, f, dv)
            con = next(c for c in P[lg].constraints if c.type == 'IK')
            key(f'pose.bones["{lg}"].constraints["{con.name}"].influence', 0, f, 0.0)
            for name, M, parent in ((th, Mt, P[th].parent.matrix), (lg, Ml, Mt), (ft, Mf, Ml)):
                q = basis(name, M, parent).to_quaternion()
                for j in range(4):
                    key(f'pose.bones["{name}"].rotation_quaternion', j, f, q[j])
    for c in act.fcurves:
        c.update()
    print("@@ root moved, legs re-solved", int((np.abs(r) > 0).sum()), "frames, max cm", round(r.max() * 100, 1),
          "min cm", round(r.min() * 100, 1), flush=True)


if RELAX:
    r, need = relax_raise()
    print("@@ relax need frames", int((need > 0.002).sum()), "max cm", round(need.max() * 100, 1), flush=True)
    apply_relax(r)
    D2, V2 = measure()
    report("after relax", V2)


# ---------------------------------------------------------------- 腰の小さい跳ねを ならす
# MotionBricks は段を上がりきる所で腰を 1 コマで 5 cm 突き上げて山を作り、すぐ 13 cm 沈んでから また上がることがあり、
# 小さく跳んだように見えた(4159)。見て跳ねていた範囲(--bob-at 4148-4182,...)の腰の高さを、範囲の両端の高さと傾きを
# つなぐ なめらかな線(3 次)に置き換える。下げるのは いくらでも、上げるのは どちらの脚も伸び切らない(脚の長さの 97%)まで。
# 足は今の所に置いたまま脚を解き直す
def bob_flatten():
    n = F1 - F0 + 1
    P = arm.pose.bones
    mw = arm.matrix_world
    z = np.zeros(n)
    H = {s: np.zeros((n, 3)) for s in SIDES}
    An = {s: np.zeros((n, 3)) for s in SIDES}
    for f in range(F0, F1 + 1):
        sc.frame_set(f)
        z[f - F0] = (mw @ P["root.x"].head).z
        for s in SIDES:
            H[s][f - F0] = mw @ P[SIDES[s][0]].head
            An[s][f - F0] = mw @ P[SIDES[s][2]].head
    Lmax = {}
    for s in SIDES:
        th, lg, ft, _ = SIDES[s]
        sc.frame_set(F0)
        Lmax[s] = ((mw @ P[lg].head) - (mw @ P[th].head)).length + ((mw @ P[ft].head) - (mw @ P[lg].head)).length
    amt = np.zeros(n)
    for a_, b_ in BOB_AT:
        i0, i1 = a_ - F0, b_ - F0
        m0, m1 = z[i0] - z[i0 - 1], z[i1 + 1] - z[i1]
        T = i1 - i0
        for i in range(i0, i1 + 1):
            t = (i - i0) / T
            h00, h10, h01, h11 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t, -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
            tgt = h00 * z[i0] + h10 * T * m0 + h01 * z[i1] + h11 * T * m1
            d = tgt - z[i]
            if d > 0:            # 上げる分は脚が伸び切らない所まで
                for s in SIDES:
                    v = H[s][i] - An[s][i]
                    R = 0.97 * Lmax[s]
                    # |v + r e_z| <= R を満たす一番大きい r
                    disc = v[2] ** 2 - (v @ v - R * R)
                    d = min(d, max(0.0, -v[2] + disc ** 0.5) if disc > 0 else 0.0)
            amt[i] = d
        print("@@ bob", a_, b_, "lower max cm", round(-amt[i0:i1 + 1].min() * 100, 1),
              "raise max cm", round(amt[i0:i1 + 1].max() * 100, 1), flush=True)
    return amt


if BOB_AT:
    apply_relax(bob_flatten())
    D2, V2 = measure()
    report("after bob", V2)


# ---------------------------------------------------------------- 床すれすれを滑る足を持ち上げる
# 元の MotionBricks は坂の地面で歩いたので、段の上では宙の足が踏み面と同じ高さのまま前へ流れ、立った足が滑るように見えた
# (3754: 振り出す足が 4〜7 cm の高さで床をこする・段に乗った足が 35 cm 流れる)。次の 2 つが続く所だけ、
# 床から GLIDE_TO の高さまで上げる(押し上げるだけ。止めはしない):
#   こする: 足がほぼ平ら(傾き 6 cm 未満)・足の裏が床から 7 cm 未満で、コマあたり 3 cm 以上進むコマが 4 コマ以上
#   流れる: 足が平ら(傾き 3.5 cm 未満)・床から 4.5 cm 未満で、コマあたり 2.5 cm 以上進むコマが 5 コマ以上(立った足のゆっくりした滑りは上げると宙に浮くので外す)
# MotionBricks は普通の歩きでも着地の前に足を低く平らに運ぶので、通しで探すと毎歩 引っかかった(175 か所)。
# 歩き全体を変えないよう、見て滑っていた範囲(--glide-at 3745-3795,...)の中だけで探す
def glide_lift():
    n = F1 - F0 + 1
    lift = {}
    for s in SIDES:
        a = measure.anc[s]
        v = np.r_[0, np.linalg.norm(np.diff(a[:, :2], axis=0), axis=1)]
        v = np.maximum(v, np.r_[v[1:], 0])
        c = measure.clr[s]
        need = np.zeros(n)
        tl = np.abs(measure.tilt[s])
        win = np.zeros(n, bool)
        for a_, b_ in GLIDE_AT:
            win[max(0, a_ - F0):b_ - F0 + 1] = True
        for tag, low, nmin in (("skim", (c < 0.07) & (tl < 0.06) & (v > 0.03), 4),
                               ("slide", (c < 0.045) & (tl < 0.035) & (v > 0.025), 5)):
            low = low & win
            i = 0
            while i < n:
                if not low[i]:
                    i += 1
                    continue
                j = i
                while j + 1 < n and low[j + 1]:
                    j += 1
                if j - i + 1 >= nmin:
                    need[i:j + 1] = np.maximum(need[i:j + 1], GLIDE_TO[tag] - c[i:j + 1])
                    print("@@ glide", tag, s, i + F0, j + F0, "max lift cm", round(need[i:j + 1].max() * 100, 1), flush=True)
                i = j + 1
        e = need.copy()
        for k in range(1, 4):
            t = 1 - k / 4
            w = t * t * (3 - 2 * t)
            e[k:] = np.maximum(e[k:], need[:-k] * w)
            e[:-k] = np.maximum(e[:-k], need[k:] * w)
        g = np.maximum(gauss(e, 2.0), need)
        g[g < 0.002] = 0.0
        lift[s] = np.c_[np.zeros(n), np.zeros(n), g]
    return lift


if GLIDE_AT:
    measure()
    apply(glide_lift())
    D2, V2 = measure()
    report("after glide", V2)

if LOG:
    np.savetxt(LOG.replace(".txt", "_after.txt"), np.c_[np.arange(F0, F1 + 1), V2["L"], V2["R"]], fmt="%.4f")
for o in hidden:
    o.hide_viewport = False
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("@@ wrote", OUT, flush=True)
