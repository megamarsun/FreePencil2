"""配管の街(プリビズ): リターゲット済みのデルタもんの .blend に、道筋どおりの地形・パイプとケーブルの谷・赤い灯り・
16 本のショットのカメラを足して保存する。表示はワークベンチ(ソリッド表示と同じ絵)。

  blender -b <dm.blend> --python build_city.py -- <course_final.json> <run.npz> <out.blend>

地形は MuJoCo の座標(m)で作り、親の空(City_Root)でリターゲット後の世界へ合わせる(腰の通り道で合わせた相似変換)。
台本は storyboard.md。
"""
import json
import math
import random
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

ARGV = sys.argv[sys.argv.index("--") + 1:]
CS = json.load(open(ARGV[0], encoding="utf-8"))
D = np.load(ARGV[1])
OUT = ARGV[2]
random.seed(7)
rng = np.random.default_rng(7)

sc = bpy.context.scene
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE" and "Armature" in o.name)
HIPS = arm.data["fp_humanoid"]["下半身"]
names = list(D["body_names"])
PEL = D["xpos"][:, names.index("pelvis")]              # MuJoCo の腰(コマ, 3)
NF = len(PEL)

# ---------------------------------------------------------------- MuJoCo → 世界(腰の通り道で相似変換を合わせる)
fr = np.linspace(1, NF, 40).astype(int)
W = []
for f in fr:
    sc.frame_set(int(f))
    W.append(tuple(arm.matrix_world @ arm.pose.bones[HIPS].head))
W = np.array(W)
S_ = PEL[fr - 1]
a2, b2 = S_[:, :2], W[:, :2]
ma, mb = a2.mean(0), b2.mean(0)
U, sig, Vt = np.linalg.svd((b2 - mb).T @ (a2 - ma))
Rm = U @ np.diag([1, np.sign(np.linalg.det(U @ Vt))]) @ Vt
k = sig.sum() / ((a2 - ma) ** 2).sum()
t2 = mb - k * Rm @ ma
tz = (W[:, 2] - k * S_[:, 2]).mean()
err = np.linalg.norm((k * (Rm @ a2.T)).T + t2 - b2, axis=1)
print("@@ fit scale", round(k, 4), "rot", round(math.degrees(math.atan2(Rm[1, 0], Rm[0, 0])), 2),
      "err mean", round(err.mean(), 3), "max", round(err.max(), 3), "z err", round(np.abs(W[:, 2] - k * S_[:, 2] - tz).max(), 3),
      flush=True)
M = Matrix(((Rm[0, 0] * k, Rm[0, 1] * k, 0, t2[0]), (Rm[1, 0] * k, Rm[1, 1] * k, 0, t2[1]), (0, 0, k, tz), (0, 0, 0, 1)))

# ---------------------------------------------------------------- 道と高さ
path = np.array(CS["path"])
seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
L = float(seg[-1])
HK = np.array(CS["heights"])
FEATS = CS["features"]
WIDTH = 2.4


def h_at(s, side=0):
    """地面の高さ。side=-1 は段の手前(左極限)、+1 は先(右極限)。"""
    s = float(np.clip(s, 0, L))
    idx = np.where(np.abs(HK[:, 0] - s) < 1e-6)[0]
    if len(idx):
        return HK[idx[0], 1] if side < 0 else HK[idx[-1], 1]
    i = int(np.searchsorted(HK[:, 0], s))
    i = min(max(i, 1), len(HK) - 1)
    s0, h0 = HK[i - 1]
    s1, h1 = HK[i]
    return h0 + (h1 - h0) * (s - s0) / max(s1 - s0, 1e-9)


def pt(s):
    s = float(np.clip(s, 0, L))
    return np.array([np.interp(s, seg, path[:, 0]), np.interp(s, seg, path[:, 1])])


def tan(s):
    d = pt(min(s + 0.2, L)) - pt(max(s - 0.2, 0))
    return d / (np.linalg.norm(d) + 1e-9)


def nrm(s):
    t = tan(s)
    return np.array([-t[1], t[0]])


def in_feat(s, typ):
    for f in FEATS:
        if f["type"] == typ and f["s0"] <= s <= f["s1"]:
            return f
    return None


# ---------------------------------------------------------------- 材質(ワークベンチの色)
def mat(name, col):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = (*col, 1)
    m.roughness = 0.6
    m.metallic = 0.0
    return m


MAT = {"deck": mat("city_deck", (0.30, 0.36, 0.46)), "deck_edge": mat("city_deck_edge", (0.85, 0.62, 0.12)),
       "rail": mat("city_rail", (0.17, 0.21, 0.28)), "cable": mat("city_cable", (0.025, 0.03, 0.05)),
       "machine": mat("city_machine", (0.09, 0.12, 0.19)), "floor": mat("city_abyss", (0.02, 0.028, 0.045)),
       "red": mat("city_red_lamp", (1.0, 0.06, 0.04)), "lamp_cool": mat("city_cool_lamp", (0.55, 0.85, 1.0))}
PIPE_MATS = [mat(f"city_pipe_{i}", c) for i, c in enumerate(
    [(0.05, 0.08, 0.15), (0.09, 0.14, 0.24), (0.13, 0.20, 0.33), (0.19, 0.28, 0.42), (0.07, 0.10, 0.17),
     (0.24, 0.32, 0.44)])]

root = bpy.data.objects.new("City_Root", None)
coll = bpy.data.collections.new("City")
sc.collection.children.link(coll)
coll.objects.link(root)
root.matrix_world = M
SUB = {}


def sub(name):
    if name not in SUB:
        c = bpy.data.collections.new(f"City_{name}")
        coll.children.link(c)
        SUB[name] = c
    return SUB[name]


def add_mesh(name, bm, m, group):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(m)
    o = bpy.data.objects.new(name, me)
    sub(group).objects.link(o)
    o.parent = root
    return o


def add_curve(name, pts, r, m, group, res=6, cyclic=False):
    """太さ r のパイプ(点の列、MuJoCo の座標)。"""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = r
    cu.bevel_resolution = 2 if r < 0.05 else 4
    cu.use_fill_caps = True
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for p_, q in zip(sp.points, pts):
        p_.co = (q[0], q[1], q[2], 1)
    sp.use_cyclic_u = cyclic
    cu.materials.append(m)
    o = bpy.data.objects.new(name, cu)
    sub(group).objects.link(o)
    o.parent = root
    return o


def box(bm, c, size, rotz=0.0):
    r = bmesh.ops.create_cube(bm, size=1.0)
    vs = r["verts"]
    bmesh.ops.scale(bm, vec=size, verts=vs)
    bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(rotz, 3, "Z"), verts=vs)
    bmesh.ops.translate(bm, vec=c, verts=vs)


def cyl(bm, a, b, r, seg_=12):
    a, b = Vector(a), Vector(b)
    d = b - a
    r_ = bmesh.ops.create_cone(bm, cap_ends=True, segments=seg_, radius1=r, radius2=r, depth=d.length)
    q = Vector((0, 0, 1)).rotation_difference(d.normalized())
    bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=q.to_matrix(), verts=r_["verts"])
    bmesh.ops.translate(bm, vec=(a + b) / 2, verts=r_["verts"])


# ---------------------------------------------------------------- 足場(道の帯。段・坂・飛び降り・溝)
cuts = sorted(set([round(x, 4) for x in HK[:, 0]] + list(np.arange(0, L, 0.25).round(4)) + [L]))
for f in FEATS:
    if f["type"] == "gap":
        cuts += [f["s0"], f["s1"]]
cuts = sorted(set(cuts))
bm = bmesh.new()
edge_bm = bmesh.new()
TH = 0.28
prev = None
for s0, s1 in zip(cuts[:-1], cuts[1:]):
    if s1 - s0 < 1e-4:
        continue
    mid = (s0 + s1) / 2
    if in_feat(mid, "gap"):
        prev = None
        continue
    br = in_feat(mid, "bridge")
    th = 0.12 if br else TH
    ha, hb = h_at(s0, +1), h_at(s1, -1)
    pa, pb, na, nb = pt(s0), pt(s1), nrm(s0), nrm(s1)
    w = WIDTH / 2
    v = [bm.verts.new((*(pa + na * w), ha)), bm.verts.new((*(pa - na * w), ha)),
         bm.verts.new((*(pb - nb * w), hb)), bm.verts.new((*(pb + nb * w), hb)),
         bm.verts.new((*(pa + na * w), ha - th)), bm.verts.new((*(pa - na * w), ha - th)),
         bm.verts.new((*(pb - nb * w), hb - th)), bm.verts.new((*(pb + nb * w), hb - th))]
    for q in ((0, 1, 2, 3), (7, 6, 5, 4), (0, 3, 7, 4), (1, 5, 6, 2)):
        bm.faces.new([v[i] for i in q])
    # 段の縁(前後の高さが違う所)は立ち上がりの面と、黄色い縁取り
    hp = h_at(s0, -1)
    if prev is None or abs(hp - ha) > 1e-3:
        bm.faces.new([v[1], v[0], v[4], v[5]])
        if prev is not None and abs(hp - ha) > 1e-3:
            top, bot = max(hp, ha), min(hp, ha) - th
            vv = [bm.verts.new((*(pa + na * w), top)), bm.verts.new((*(pa - na * w), top)),
                  bm.verts.new((*(pa - na * w), bot)), bm.verts.new((*(pa + na * w), bot))]
            bm.faces.new(vv)
            e0 = edge_bm.verts.new((*(pa + na * w), top + 0.004))
            e1 = edge_bm.verts.new((*(pa - na * w), top + 0.004))
            dirn = 1 if ha > hp else -1
            e2 = edge_bm.verts.new((*(pa - na * w + tan(s0) * 0.06 * dirn), top + 0.004))
            e3 = edge_bm.verts.new((*(pa + na * w + tan(s0) * 0.06 * dirn), top + 0.004))
            edge_bm.faces.new([e0, e1, e2, e3])
    if s1 >= L - 1e-4 or in_feat(s1 + 1e-3, "gap"):
        bm.faces.new([v[3], v[2], v[6], v[7]])
    prev = (s1, hb)
add_mesh("Walkway", bm, MAT["deck"], "walkway")
add_mesh("Walkway_Edges", edge_bm, MAT["deck_edge"], "walkway")

# 手すり: 橋・階段・高い所(谷側)。柱 1 m おき、手すりは高さ 1.0 m
rail_bm = bmesh.new()
for side in (1, -1):
    s, run = 0.4, []
    while s < L - 0.3:
        if in_feat(s, "gap") or in_feat(s + 0.6, "gap") or in_feat(s - 0.6, "gap"):
            if len(run) > 1:
                add_curve(f"Rail_{side}_{len(rail_bm.verts)}", run, 0.025, MAT["rail"], "walkway")
            run = []
            s += 0.5
            continue
        # 飛び降りと跳び乗りの縁の 0.7 m 以内は手すり無し(足を引っかけて見えた)
        near_ledge = any(f["type"] == "ledge" and abs(f["s"] - s) < 0.7 for f in FEATS)
        hh = max(h_at(s - 0.15), h_at(s + 0.15))
        p = pt(s) + nrm(s) * side * (WIDTH / 2 - 0.06)
        if not near_ledge:
            cyl(rail_bm, (*p, hh), (*p, hh + 1.0), 0.03, 8)
            run.append((*p, hh + 1.0))
        elif len(run) > 1:
            add_curve(f"Rail_{side}_{int(s * 10)}", run, 0.025, MAT["rail"], "walkway")
            run = []
        s += 1.0
    if len(run) > 1:
        add_curve(f"Rail_{side}_end", run, 0.025, MAT["rail"], "walkway")
add_mesh("Rail_Posts", rail_bm, MAT["rail"], "walkway")

# 足場の下の柱(橋以外)、橋は上の梁から吊る
sup_bm = bmesh.new()
s = 2.0
while s < L - 1:
    if not in_feat(s, "bridge") and not in_feat(s, "gap"):
        for side in (1, -1):
            p = pt(s) + nrm(s) * side * (WIDTH / 2 - 0.3)
            cyl(sup_bm, (*p, -16), (*p, h_at(s) - TH), 0.16, 10)
    s += 5.0
add_mesh("Walkway_Supports", sup_bm, MAT["machine"], "walkway")
for f in FEATS:
    if f["type"] != "bridge":
        continue
    s = f["s0"]
    while s <= f["s1"]:
        hh = f["h"]
        for side in (1, -1):
            p = pt(s) + nrm(s) * side * (WIDTH / 2 - 0.05)
            top = p + nrm(s) * side * 1.5
            add_curve(f"BridgeHanger_{int(s * 10)}_{side}", [(*p, hh), (*top, hh + 9.0)], 0.018, MAT["cable"],
                      "cables", res=1)
        s += 2.0
    for side in (1, -1):         # 橋の下の太いケーブル(たるむ)
        ss = np.linspace(f["s0"], f["s1"], 40)
        sag = 0.9 * np.sin(np.linspace(0, math.pi, 40))
        add_curve(f"BridgeCable_{int(f['s0'])}_{side}",
                  [(*(pt(x) + nrm(x) * side * 1.0), f["h"] - 0.25 - g) for x, g in zip(ss, sag)], 0.06,
                  MAT["cable"], "cables")

# パイプ越えのパイプ(道を横切って谷の壁まで)
for f in FEATS:
    if f["type"] == "pipe_x":
        p, n_ = pt(f["s"]), nrm(f["s"])
        zc = f["h"] + f.get("top", 0.32) - f["r"]
        a, b = p + n_ * 9, p - n_ * 9
        add_curve(f"CrossPipe_{int(f['s'] * 10)}", [(*a, zc - 0.3), (*(p + n_ * 3), zc), (*(p - n_ * 3), zc),
                                                    (*b, zc - 0.5)], f["r"], PIPE_MATS[3], "pipes")

# ---------------------------------------------------------------- 谷: 道に沿って這うパイプ
dense = np.linspace(0, L, int(L / 0.5))
P2 = np.array([pt(x) for x in dense])
N2 = np.array([nrm(x) for x in dense])
HS = np.array([h_at(x) for x in dense])
HSm = np.convolve(np.pad(HS, 20, mode="edge"), np.ones(41) / 41, mode="valid")


def offset_line(d, z_fn, s_a, s_b, wob=0.0, ph=0.0):
    """道から横へ d m・高さ z_fn(s) の線。内回りで折り返す所(道に近すぎる点)は捨てる。"""
    out = []
    for i, x in enumerate(dense):
        if x < s_a or x > s_b:
            continue
        dd = d + wob * math.sin(x * 0.21 + ph) + wob * 0.5 * math.sin(x * 0.53 + ph * 2)
        q = P2[i] + N2[i] * dd
        near = np.min(np.linalg.norm(P2[max(0, i - 40):i + 40] - q, axis=1))
        if near < abs(dd) - 0.4:
            continue
        out.append((q[0], q[1], z_fn(x, i)))
    return out


n_pipes = 0
for side in (1, -1):
    # 壁: 太さのちがうパイプの束を高さを変えて重ねる
    for b_ in range(26):
        d0 = side * rng.uniform(3.0, 10.0)
        z0 = rng.uniform(-12, 9)
        r = float(rng.choice([0.06, 0.1, 0.15, 0.22, 0.32, 0.5, 0.8, 1.2], p=[.12, .16, .16, .16, .14, .12, .09, .05]))
        if abs(d0) < 2.6 + r:
            d0 = side * (2.6 + r)
        sa = rng.uniform(-10, L * 0.6)
        sb = sa + rng.uniform(30, L)
        amp = rng.uniform(0.3, 2.5)
        ph = rng.uniform(0, 6.28)
        nb = int(rng.choice([1, 1, 2, 3, 4]))
        m_ = PIPE_MATS[int(rng.integers(len(PIPE_MATS)))]
        for j in range(nb):
            dj = d0 + side * j * (2.2 * r + 0.05)
            zf = (lambda z0_, j_, amp_, ph_: (lambda x, i: z0_ + 0.35 * HSm[i] + amp_ * math.sin(x * 0.07 + ph_) + j_ * 0.0))(
                z0, j, amp, ph)
            pts = offset_line(dj, zf, sa, sb, wob=0.4, ph=ph)
            if len(pts) > 3:
                add_curve(f"WallPipe_{side}_{b_}_{j}", pts, r, m_, "pipes")
                n_pipes += 1
    # 縦のパイプ(底から上へ)
    s = rng.uniform(0, 6)
    while s < L:
        d = side * rng.uniform(3.5, 9)
        p = pt(s) + nrm(s) * d
        r = float(rng.choice([0.12, 0.25, 0.45]))
        add_curve(f"Riser_{side}_{int(s)}", [(*p, -16), (*p, -4), (*(p + nrm(s) * side * 0.4), 4), (*(p + nrm(s) * side * 0.4), 14)],
                  r, PIPE_MATS[int(rng.integers(len(PIPE_MATS)))], "pipes", res=4)
        s += rng.uniform(4, 11)
print("@@ wall pipes", n_pipes, flush=True)

# 機械の箱(壁に張り付く)
mbm = bmesh.new()
s = 1.0
while s < L:
    for side in (1, -1):
        if rng.random() < 0.6:
            d = side * rng.uniform(5.0, 11.0)
            p = pt(s) + nrm(s) * d
            sz = Vector((rng.uniform(1, 4), rng.uniform(1, 3), rng.uniform(0.8, 5)))
            ang = math.atan2(tan(s)[1], tan(s)[0])
            box(mbm, Vector((*p, rng.uniform(-10, 7))), sz, ang)
    s += rng.uniform(2.5, 5)
add_mesh("Machines", mbm, MAT["machine"], "machines")

# 谷の底
fb = bmesh.new()
lo, hi = path.min(0) - 30, path.max(0) + 30
vv = [fb.verts.new((lo[0], lo[1], -16)), fb.verts.new((hi[0], lo[1], -16)), fb.verts.new((hi[0], hi[1], -16)),
      fb.verts.new((lo[0], hi[1], -16))]
fb.faces.new(vv)
add_mesh("Abyss_Floor", fb, MAT["floor"], "machines")

# ---------------------------------------------------------------- 頭の上を渡るケーブル(たるむ)と梁
n_cab = 0
s = 0.5
while s < L + 4:
    for _ in range(int(rng.integers(1, 4))):
        x = s + rng.uniform(-0.7, 0.7)
        if x > L:
            continue
        a = pt(x) + nrm(x) * rng.uniform(3.5, 9) + tan(x) * rng.uniform(-2, 2)
        b = pt(x) - nrm(x) * rng.uniform(3.5, 9) + tan(x) * rng.uniform(-2, 2)
        hb_ = HSm[min(int(x / L * (len(dense) - 1)), len(dense) - 1)]
        za, zb = hb_ + rng.uniform(4, 10), hb_ + rng.uniform(4, 10)
        sag = rng.uniform(1.0, 4.0)
        tt = np.linspace(0, 1, 18)
        pts = [(*(a + (b - a) * u), za + (zb - za) * u - sag * 4 * u * (1 - u)) for u in tt]
        add_curve(f"Cable_{n_cab}", pts, float(rng.choice([0.015, 0.025, 0.04, 0.07])), MAT["cable"], "cables",
                  res=1)
        n_cab += 1
    s += rng.uniform(0.8, 2.2)
# 道の上の梁(橋を吊る所と出だしの通路)
bbm = bmesh.new()
s = 1.0
while s < L:
    hb_ = HSm[min(int(s / L * (len(dense) - 1)), len(dense) - 1)]
    z = hb_ + 9.0 + rng.uniform(-0.5, 1.5)
    a, b = pt(s) + nrm(s) * 9, pt(s) - nrm(s) * 9
    cyl(bbm, (*a, z), (*b, z), 0.22, 10)
    s += rng.uniform(4, 7)
add_mesh("Overhead_Beams", bbm, MAT["machine"], "machines")
print("@@ cables", n_cab, flush=True)

# 出だしの通路の天井: 道を跨いで弧を描く太いパイプ
for i, x in enumerate(np.arange(1.5, 21, 2.3)):
    p, n_ = pt(x), nrm(x)
    arc = [(*(p + n_ * (5.5 * math.cos(a_))), 1.0 + 6.5 * math.sin(a_)) for a_ in np.linspace(0.05, math.pi - 0.05, 16)]
    add_curve(f"ArchPipe_{i}", arc, float(rng.choice([0.25, 0.4, 0.6])), PIPE_MATS[int(rng.integers(len(PIPE_MATS)))],
              "pipes")

# ---------------------------------------------------------------- 赤い灯り(出だしの奥と、最後の行き先)
lamp_bm = bmesh.new()


def lamp(p3, r):
    bmesh.ops.create_uvsphere(lamp_bm, u_segments=16, v_segments=10, radius=r,
                              matrix=Matrix.Translation(Vector(p3)))


a_end = pt(21.0) + tan(21.0) * 0.0
# 出だしの通路のまっすぐ奥(曲がり角の先の壁)。S01 の画面の奥に入る所。通路の奥 22 m では壁のパイプに隠れて見えなかった
LAMP_A = (*(pt(21.0) + tan(19.0) * 6.0), h_at(21.0) + 2.6)
lamp(LAMP_A, 0.5)
endp = pt(L) + tan(L) * 9.0
lamp((*endp, h_at(L) + 2.4), 0.6)                                           # 最後の機械の赤い目
add_mesh("Red_Lamps", lamp_bm, MAT["red"], "lights")
# 最後の機械(赤い目の後ろの大きな塊)
cbm = bmesh.new()
ang = math.atan2(tan(L)[1], tan(L)[0])
box(cbm, Vector((*(endp + tan(L) * 3.0), h_at(L) + 2.0)), Vector((5, 9, 12)), ang)
add_mesh("Core_Machine", cbm, MAT["machine"], "machines")
# 道ばたの小さな青白い灯り(足もとの目印)
cl = bmesh.new()
s = 3.0
while s < L:
    for side in (1, -1):
        p = pt(s) + nrm(s) * side * (WIDTH / 2 + 0.1)
        bmesh.ops.create_cube(cl, size=0.12, matrix=Matrix.Translation(Vector((*p, h_at(s) + 0.05))))
    s += 4.0
add_mesh("Path_Lights", cl, MAT["lamp_cool"], "lights")
# EEVEE で開いたとき用の灯り(プリビズの絵はワークベンチ)
for nm, p3, col, en in (("RedLight_A", (LAMP_A[0], LAMP_A[1], LAMP_A[2] - 0.6), (1, 0.05, 0.03), 800),
                        ("RedLight_End", (*(endp - tan(L) * 0.8), h_at(L) + 2.4), (1, 0.05, 0.03), 3000)):
    ld = bpy.data.lights.new(nm, "POINT")
    ld.color, ld.energy = col, en
    lo_ = bpy.data.objects.new(nm, ld)
    sub("lights").objects.link(lo_)
    lo_.parent = root
    lo_.location = p3

# ---------------------------------------------------------------- ワークベンチの見た目
sh = sc.display.shading
sc.render.engine = "BLENDER_WORKBENCH"
sh.light = "STUDIO"
sh.color_type = "TEXTURE"
sh.show_cavity = True
sh.cavity_type = "BOTH"
sh.show_shadows = True
sh.shadow_intensity = 0.6
sh.background_type = "WORLD"
sc.display.light_direction = (-0.35, 0.25, 0.9)
if sc.world is None:
    sc.world = bpy.data.worlds.new("World")
sc.world.color = (0.012, 0.018, 0.035)
sc.render.film_transparent = False

# ---------------------------------------------------------------- カメラ(ショットごと)
S_run = D["s"]


def world(p3):
    return M @ Vector(p3)


HIP_W = np.array([tuple(world(p)) for p in PEL])


def gaussian_filter1d(a, sigma, axis=0):
    """scipy の gaussian_filter1d の代わり(Blender に scipy が無い)。端は端の値で延ばす。"""
    a = np.asarray(a, dtype=float)
    r = max(1, int(sigma * 3))
    w = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    w /= w.sum()
    a2 = np.moveaxis(a, axis, 0)
    pad = np.concatenate([np.repeat(a2[:1], r, 0), a2, np.repeat(a2[-1:], r, 0)], 0)
    out = sum(w[i] * pad[i:i + len(a2)] for i in range(2 * r + 1))
    return np.moveaxis(out, 0, axis)


HIP_S = gaussian_filter1d(HIP_W, 6, axis=0)
TAN = np.array([tan(x) for x in S_run])
TAN_S = gaussian_filter1d(TAN, 20, axis=0)
TAN_S /= np.linalg.norm(TAN_S, axis=1, keepdims=True)
R2 = Matrix(((Rm[0, 0], Rm[0, 1], 0), (Rm[1, 0], Rm[1, 1], 0), (0, 0, 1)))


def frame_vec(f):
    """コマ f の向き(世界): 前・左・上。"""
    f = int(np.clip(f, 1, NF)) - 1
    fw = (R2 @ Vector((TAN_S[f, 0], TAN_S[f, 1], 0))).normalized()
    up = Vector((0, 0, 1))
    return fw, up.cross(fw).normalized(), up


SHOTS = json.load(open(ARGV[0].replace("course_final.json", "shots.json"), encoding="utf-8"))
cams = []
for sh_ in SHOTS:
    cd = bpy.data.cameras.new("CAM_" + sh_["id"])
    cd.lens = sh_["lens"]
    cd.clip_start, cd.clip_end = 0.05, 400
    co = bpy.data.objects.new("CAM_" + sh_["id"], cd)
    sub("cameras").objects.link(co)
    f0, f1 = sh_["f"]
    pos, look = [], []
    for f in range(f0, f1 + 1):
        u = (f - f0) / max(1, f1 - f0)
        u = u * u * (3 - 2 * u) if sh_.get("ease", True) else u
        af = sh_.get("anchor")
        fa = f if af is None else af
        base = Vector(HIP_S[min(fa, NF) - 1])
        fw, lf, up = frame_vec(fa)
        o = [a + (b - a) * u for a, b in zip(sh_["o0"], sh_.get("o1", sh_["o0"]))]
        p = base + fw * o[0] + lf * o[1] + up * o[2]
        # 見る所: キャラ(今のコマ)+ 前/左/上のずれ
        fwc, lfc, upc = frame_vec(f)
        lk = sh_.get("look", [0, 0, 0.25])
        tgt = Vector(HIP_S[min(f, NF) - 1]) + fwc * lk[0] + lfc * lk[1] + upc * lk[2]
        pos.append(p)
        look.append(tgt)
    pos = gaussian_filter1d(np.array([tuple(p) for p in pos]), 3, axis=0)
    look = gaussian_filter1d(np.array([tuple(p) for p in look]), sh_.get("look_smooth", 4), axis=0)
    for i, f in enumerate(range(f0, f1 + 1)):
        p, tg = Vector(pos[i]), Vector(look[i])
        co.location = p
        co.rotation_euler = (tg - p).to_track_quat("-Z", "Y").to_euler()
        co.keyframe_insert("location", frame=f)
        co.keyframe_insert("rotation_euler", frame=f)
    mk = sc.timeline_markers.new(sh_["id"], frame=f0)
    mk.camera = co
    cams.append(co)
sc.camera = cams[0]
sc.frame_start, sc.frame_end = 1, 5400

# カメラの通り道から 0.6 m 以内を通る背景のパイプ・ケーブルを消す(レンズの前をケーブルが横切る・パイプの中に入って画面が灰色)。
# 足場・手すり・橋・道を横切るパイプ(パイプ越え)は消さない
Minv = M.inverted()
campts = []
for co in cams:
    fc = co.animation_data.action.fcurves
    xs = [c for c in fc if c.data_path == "location"]
    for kp in range(0, len(xs[0].keyframe_points), 2):
        campts.append(tuple(Minv @ Vector([xs[a].keyframe_points[kp].co[1] for a in range(3)])))
CP = np.array(campts)
removed = []
for o in list(bpy.data.objects):
    if o.type != "CURVE" or not o.name.startswith(("WallPipe", "Riser", "Cable_", "BridgeHanger", "ArchPipe")):
        continue
    sp = o.data.splines[0]
    P_ = np.array([tuple(p.co)[:3] for p in sp.points])
    A_, B_ = P_[:-1], P_[1:]
    lo_, hi_ = np.minimum(A_, B_).min(0) - 3, np.maximum(A_, B_).max(0) + 3
    near = CP[np.all((CP > lo_) & (CP < hi_), axis=1)]
    if not len(near):
        continue
    AB = B_ - A_
    t_ = np.clip(np.einsum("cij,ij->ci", near[:, None, :] - A_[None], AB) / (np.einsum("ij,ij->i", AB, AB) + 1e-9), 0, 1)
    dmin = np.linalg.norm(near[:, None, :] - (A_[None] + t_[..., None] * AB[None]), axis=2).min()
    if dmin < o.data.bevel_depth + 0.6:
        removed.append(o.name)
        bpy.data.objects.remove(o)
print("@@ cleared for cameras", len(removed), removed[:12], flush=True)
sc.render.fps = 30
sc.render.resolution_x, sc.render.resolution_y = 1920, 1080

# ビューポートもカメラから・ソリッド(ワークベンチと同じ)で開くように
for scr in bpy.data.screens:
    for ar in scr.areas:
        if ar.type == "VIEW_3D":
            for sp in ar.spaces:
                if sp.type == "VIEW_3D":
                    sp.shading.type = "SOLID"
                    sp.shading.light = "STUDIO"
                    sp.shading.color_type = "TEXTURE"
                    sp.shading.show_cavity = True
                    sp.shading.show_shadows = True
                    sp.shading.background_type = "WORLD"
                    sp.region_3d.view_perspective = "CAMERA"
                    sp.overlay.show_overlays = False
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("@@ saved", OUT, flush=True)
