"""配管の谷の背景を組み直す配置(Blender の外、shapely で計算する)。bg_build.py が読んで作る。

  python bg_layout.py <course_final.json> <probe.npz> <出力 layout.json> [--plot 上から.png]

build_city.py の背景は、パイプが道の途中の乱数の所で生えて途中で消え(道から横へずらした線の折り返しを捨てた所でも切れた)、
ケーブル 181 本は宙の端どうしを結んで交差し、機械の箱は宙に浮いていて、ぶつ切りでぐちゃぐちゃに見えた。作りの決まり:

1. 谷の壁: 道(前後に 25 m 延ばす)から横へ D(s) m の所に、底(-16 m)から上(+16 m)まで続く 1 枚の壁で谷を囲む。
   道を太らせた形(shapely の buffer)の縁なので、曲がり角の内側でも折り返さない。出だしの通路は狭く(6.5 m)、
   その先は 11 m。カメラが道から離れる所は、カメラから壁の手前のパイプまで 2 m 空くまで広げる。
2. 壁を這うパイプ: 壁から一定の距離・一定の高さで、谷を一周する輪(どこにも端が無い)。束ねて段ごとに太さを変える。
   柱ごとに受け金物で壁に留める。
3. 縦のパイプ: 底から上まで まっすぐ。壁の柱(8 m おき)の間に立てる。
4. 機械の箱: 壁に背中を付け、パイプの段の すき間に収める。
5. 道を跨ぐ門形の梁(10 m 前後おき): 両端を壁の柱に載せ、方杖で支える。出だしの通路は弧のパイプ(台本 S02)を壁から壁へ。
6. 頭の上のケーブル: 必ず梁と梁、梁と壁の金物を結ぶ(宙で切れる端を作らない)。たるみは長さの 6〜11%。
7. カメラの通り道から梁・方杖は 1.5 m、ケーブル・弧のパイプは 0.8 m 以内に入るなら置かない。

座標は City_Root の中(MuJoCo の m)。probe.npz は Blender で撮ったカメラ位置(cam: 位置+向き)と腰(hip)。
"""
import json
import math
import sys

import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

A = sys.argv[1:]
CS = json.load(open(A[0], encoding="utf-8"))
PR = np.load(A[1])
OUT = A[2]
arg = lambda n, d=None: A[A.index(n) + 1] if n in A else d   # noqa: E731
rng = np.random.default_rng(11)

path = np.array(CS["path"])
seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
L = float(seg[-1])
HK = np.array(CS["heights"])
FEATS = CS["features"]
EXT = 25.0
Z_BOT, Z_TOP = -16.0, 16.0

# 前後に延ばした道
t0 = path[1] - path[0]
t0 /= np.linalg.norm(t0)
t1 = path[-1] - path[-2]
t1 /= np.linalg.norm(t1)
PX = np.vstack([path[0] - t0 * EXT, path, path[-1] + t1 * EXT])
SX = np.r_[-EXT, seg, L + EXT]


def pt(s):
    return np.array([np.interp(s, SX, PX[:, 0]), np.interp(s, SX, PX[:, 1])])


def tan(s):
    d = pt(s + 0.3) - pt(s - 0.3)
    return d / (np.linalg.norm(d) + 1e-9)


def nrm(s):
    t = tan(s)
    return np.array([-t[1], t[0]])


def ground(s):
    return float(np.interp(np.clip(s, 0, L), HK[:, 0], HK[:, 1]))


SD = np.arange(-EXT, L + EXT + 0.01, 0.5)
G_s = np.array([ground(s) for s in SD])
G_s = np.convolve(np.pad(G_s, 16, mode="edge"), np.ones(33) / 33, mode="valid")    # 梁の高さ用(なめらか)


def ground_sm(s):
    return float(np.interp(s, SD, G_s))


def s_of(q):
    """点 q(x, y)に一番近い道の位置 s と、道からの横の距離。"""
    best = (1e9, 0.0)
    for i in range(len(PX) - 1):
        a, b = PX[i], PX[i + 1]
        ab = b - a
        u = float(np.clip(np.dot(q - a, ab) / (np.dot(ab, ab) + 1e-12), 0, 1))
        dd = float(np.linalg.norm(a + ab * u - q))
        if dd < best[0]:
            best = (dd, SX[i] + u * (SX[i + 1] - SX[i]))
    return best[1], best[0]


# ---------------------------------------------------------------- 1. 谷の幅と壁
CAM = PR["cam"][:, :3]
HIP = PR["hip"]
PIPE_DEPTH = 3.3                     # 壁から一番手前のパイプの外側まで
D = np.where(SD <= 24, 6.5, np.where(SD >= 31, 11.0, 6.5 + (SD - 24) / 7 * 4.5))
need = np.zeros_like(SD)
for q in CAM[::2]:
    s, l = s_of(q[:2])
    m = np.abs(SD - s) < 3
    need[m] = np.maximum(need[m], l + 2.0 + PIPE_DEPTH)
D = np.maximum(D, need)
# 急に膨らまないよう: 前後 10 m の最大を取ってから 前後 6 m で ならす
Dm = np.array([D[max(0, i - 20):i + 21].max() for i in range(len(D))])
D = np.convolve(np.pad(Dm, 12, mode="edge"), np.ones(25) / 25, mode="valid")

pieces = []
for i in range(len(SD) - 1):
    a, b = pt(SD[i]), pt(SD[i + 1])
    pieces.append(LineString([a, b]).buffer((D[i] + D[i + 1]) / 2, quad_segs=16))
VAL = unary_union(pieces).simplify(0.02)
if VAL.geom_type != "Polygon":
    VAL = max(VAL.geoms, key=lambda g: g.area)
VAL = Polygon(VAL.exterior)
print("@@ valley area", round(VAL.area), "width min/max", round(D.min(), 1), round(D.max(), 1), flush=True)


def ring(poly, step=0.5, smooth=2):
    """多角形の縁を step m おきの点の輪に(角は Chaikin で丸める)。"""
    c = np.array(poly.exterior.coords)[:-1]
    for _ in range(smooth):
        q = np.roll(c, -1, axis=0)
        c = np.stack([0.75 * c + 0.25 * q, 0.25 * c + 0.75 * q], 1).reshape(-1, 2)
    ls = LineString(np.vstack([c, c[:1]]))
    n = max(8, int(ls.length / step))
    return np.array([ls.interpolate(i / n, normalized=True).coords[0] for i in range(n)])


WALL = ring(VAL, 0.5, smooth=0)
WALL_LS = LineString(np.vstack([WALL, WALL[:1]]))


def wall_frame(k, R):
    """輪 R の k 番目の点の 接線と、谷の内向きの法線。"""
    t = R[(k + 1) % len(R)] - R[k - 1]
    t /= np.linalg.norm(t) + 1e-9
    n_ = np.array([-t[1], t[0]])
    if not VAL.contains(Point(R[k] + n_ * 0.05)):
        n_ = -n_
    return t, n_


def inset(d):
    g = VAL.buffer(-d, join_style="round", quad_segs=16)
    if g.geom_type != "Polygon":
        g = max(g.geoms, key=lambda x: x.area)
    return g


tubes, boxes = [], []


def tube(name, pts, r, mat, group, cyclic=False):
    tubes.append({"name": name, "pts": [list(map(float, p)) for p in pts], "r": float(r), "mat": mat,
                  "group": group, "cyclic": cyclic})


def segbox(a, b, w, h, mat, group, side=None):
    """a→b を長さの向きにした角材(幅 w は side の向き、高さ h)。"""
    boxes.append({"a": list(map(float, a)), "b": list(map(float, b)), "w": float(w), "h": float(h), "mat": mat,
                  "group": group, "side": None if side is None else list(map(float, side))})


# ---------------------------------------------------------------- 2. 壁を這うパイプ(谷を一周する輪)
# (高さ, 太さ, 本数, 重ね方 v=縦 h=奥へ, 材質)
BUNDLES = [(-13.0, 0.9, 2, "h", 1), (-9.5, 0.35, 4, "v", 3), (-6.5, 1.2, 1, "h", 0), (-3.4, 0.22, 4, "v", 5),
           (-1.2, 0.55, 2, "h", 2), (1.4, 0.16, 3, "v", 4), (3.6, 0.8, 2, "h", 1), (6.6, 0.28, 3, "v", 3),
           (9.4, 1.0, 1, "h", 2), (12.6, 0.45, 3, "h", 0)]
GAP_BOT = 0.05
RISER_OFF = 0.38
PIPE_OFF0 = 0.75
levels = []                              # (z の下, z の上, 奥の深さ)
for bi, (z, r, n, how, mi) in enumerate(BUNDLES):
    zs, ds = [], []
    for j in range(n):
        if how == "v":
            zs.append(z + j * (2 * r + GAP_BOT))
            ds.append(PIPE_OFF0 + r)
        else:
            zs.append(z)
            ds.append(PIPE_OFF0 + r + j * (2 * r + GAP_BOT))
    for j, (zj, dj) in enumerate(zip(zs, ds)):
        R = ring(inset(dj), 0.5, smooth=3)
        tube(f"WallPipe_{bi}_{j}", [(*p, zj) for p in R], r, f"pipe_{mi}", "pipes", cyclic=True)
    levels.append((min(zs) - r, max(zs) + r, max(ds) + r, r))
print("@@ wall pipe rings", sum(b[2] for b in BUNDLES), flush=True)

# 壁の柱(8 m おき)と受け金物、縦のパイプ(柱の間)
per = WALL_LS.length
n_col = int(per / 8.0)
COLS = []
for i in range(n_col):
    p = np.array(WALL_LS.interpolate(i / n_col, normalized=True).coords[0])
    k = int(np.argmin(np.linalg.norm(WALL - p, axis=1)))
    t, n_ = wall_frame(k, WALL)
    COLS.append((p, t, n_))
    segbox((*p + n_ * 0.25, Z_BOT), (*p + n_ * 0.25, Z_TOP), 0.7, 0.5, "machine", "wall", side=t)
    for (zl, zh, dep, r) in levels:
        segbox((*p, zl - 0.12), (*p + n_ * dep, zl - 0.12), 0.25, 0.24, "machine", "wall", side=t)
    # 縦のパイプ: 柱と柱の真ん中に、2 本に 1 本
    if i % 2 == 0:
        q = np.array(WALL_LS.interpolate((i + 0.5) / n_col, normalized=True).coords[0])
        k2 = int(np.argmin(np.linalg.norm(WALL - q, axis=1)))
        _, n2 = wall_frame(k2, WALL)
        rr = float(rng.choice([0.12, 0.18, 0.24]))
        c = q + n2 * (RISER_OFF + 0.0)
        tube(f"Riser_{i}", [(*c, Z_BOT), (*c, Z_TOP)], rr, f"pipe_{int(rng.integers(6))}", "pipes")
print("@@ wall columns", n_col, flush=True)

# ---------------------------------------------------------------- 4. 機械の箱(パイプの段の すき間に、壁に背中を付けて)
gaps = []
lv = sorted(levels)
for (a, b) in zip(lv[:-1], lv[1:]):
    if b[0] - a[1] > 1.6:
        gaps.append((a[1] + 0.25, b[0] - 0.25))
pos = 3.0
while pos < per - 3:
    p = np.array(WALL_LS.interpolate(pos).coords[0])
    k = int(np.argmin(np.linalg.norm(WALL - p, axis=1)))
    t, n_ = wall_frame(k, WALL)
    g0, g1 = gaps[int(rng.integers(len(gaps)))]
    hgt = min(g1 - g0, rng.uniform(1.2, 2.6))
    zc = rng.uniform(g0 + hgt / 2, g1 - hgt / 2)
    wid = rng.uniform(1.6, 4.0)
    dep = rng.uniform(1.0, 2.2)
    # 柱にかからない所へ
    if min(np.linalg.norm(c_[0] - p) for c_ in COLS) > wid / 2 + 0.5:
        segbox((*p - t * wid / 2 + n_ * dep / 2, zc - hgt / 2), (*p + t * wid / 2 + n_ * dep / 2, zc - hgt / 2), dep, hgt,
               "machine", "machines", side=n_)
    pos += rng.uniform(5, 11)

# ---------------------------------------------------------------- 5. 門形の梁・出だしの弧のパイプ
CAMS_ALL = CAM


def seg_dist(a, b, P):
    a, b = np.asarray(a), np.asarray(b)
    ab = b - a
    u = np.clip(((P - a) @ ab) / (ab @ ab + 1e-12), 0, 1)
    return np.linalg.norm(P - (a + u[:, None] * ab), axis=1).min()


def poly_dist(pts, P):
    pts = np.asarray(pts)
    lo, hi = pts.min(0) - 3, pts.max(0) + 3
    Q = P[np.all((P > lo) & (P < hi), axis=1)]
    if not len(Q):
        return 1e9
    return min(seg_dist(a, b, Q) for a, b in zip(pts[:-1], pts[1:]))


def wall_hits(s):
    """道の s から横(法線)へ伸ばした線が壁に当たる 2 点(+側, -側)。"""
    p, n_ = pt(s), nrm(s)
    out = []
    for sg in (1, -1):
        ln = LineString([p, p + n_ * sg * 60])
        x = ln.intersection(WALL_LS)
        if x.is_empty:
            return None
        cand = [np.array(g.coords[0]) for g in getattr(x, "geoms", [x])]
        out.append(min(cand, key=lambda c: np.linalg.norm(c - p)))
    return out


BRIDGES = [f for f in FEATS if f["type"] == "bridge"]


def beam_z(s):
    for f in BRIDGES:
        if f["s0"] - 2 <= s <= f["s1"] + 2:
            return f["h"] + 9.0
    return ground_sm(s) + 9.5


gantries = []
ss = list(np.arange(26.0, L + 6, 10.0))
for f in BRIDGES:                          # 橋の吊り桁を受ける梁を両端に
    ss += [f["s0"] - 1.5, f["s1"] + 1.5]
ss = sorted(ss)
keep = []
for s in ss:
    if keep and s - keep[-1] < 5.0:
        # 橋の端の梁を優先
        if any(abs(s - (f["s0"] - 1.5)) < 1e-6 or abs(s - (f["s1"] + 1.5)) < 1e-6 for f in BRIDGES):
            keep[-1] = s
        continue
    keep.append(s)
n_skip = 0
for s in keep:
    h = wall_hits(s)
    if h is None:
        continue
    # 曲がり角では横の線が壁に斜めに当たって長い梁になる。谷の幅の 1.25 倍を超えたら置かない
    if np.linalg.norm(h[0] - h[1]) > 1.25 * 2 * float(np.interp(s, SD, D)):
        n_skip += 1
        continue
    z = beam_z(s)
    A_, B_ = (*h[0], z), (*h[1], z)
    n_ = nrm(s)
    br = []
    for P_, sg in ((h[0], 1), (h[1], -1)):
        br.append(((*P_, z - 2.8), (*(P_ - n_ * sg * 2.8), z - 0.35)))
    parts = [(A_, B_)] + br
    if min(seg_dist(a, b, CAMS_ALL) for a, b in parts) < 1.5:
        n_skip += 1
        continue
    t_ = tan(s)
    segbox((A_[0], A_[1], z - 0.35), (B_[0], B_[1], z - 0.35), 0.4, 0.7, "machine", "beams", side=t_)
    for a, b in br:
        segbox(a, b, 0.25, 0.25, "machine", "beams", side=t_)
    # 梁の下の柱(壁に沿って底から梁まで)
    for P_ in h:
        segbox((*P_ + (pt(s) - P_) / np.linalg.norm(pt(s) - P_) * 0.45, Z_BOT),
               (*P_ + (pt(s) - P_) / np.linalg.norm(pt(s) - P_) * 0.45, z + 0.35), 0.9, 0.9, "machine", "beams", side=t_)
    gantries.append({"s": float(s), "a": np.array(A_), "b": np.array(B_), "z": z})
print("@@ gantries", len(gantries), "skipped (camera / corner)", n_skip, flush=True)

# 橋の吊り桁: 吊りケーブルの上の端(道の中心から 2.65 m・橋 + 9 m)を、両端の梁まで
for f in BRIDGES:
    for sg in (1, -1):
        xs = np.linspace(f["s0"] - 1.5, f["s1"] + 1.5, 24)
        pts = [(*(pt(x) + nrm(x) * sg * 2.65), f["h"] + 9.0) for x in xs]
        tube(f"BridgeGirder_{int(f['s0'])}_{sg}", pts, 0.2, "machine", "beams")

# 出だしの通路: 壁から壁への弧のパイプ(台本 S02 の天井)
arches = 0
for i, s in enumerate(np.arange(-8.0, 18.0, 2.3)):
    h = wall_hits(s)
    if h is None:
        continue
    r = float(rng.choice([0.25, 0.4, 0.6]))
    a, b = h
    z0 = ground_sm(s) + 0.2
    pts = [(*(a + (b - a) * u), z0 + 7.0 * math.sin(math.pi * u) ** 0.8) for u in np.linspace(0, 1, 25)]
    if poly_dist(pts, CAMS_ALL) < r + 0.8:
        continue
    tube(f"ArchPipe_{i}", pts, r, f"pipe_{int(rng.integers(6))}", "pipes")
    arches += 1
print("@@ arches", arches, flush=True)

# ---------------------------------------------------------------- 6. 頭の上のケーブル(梁と梁、梁と壁を結ぶ)
BODY = np.column_stack([HIP[:, 0], HIP[:, 1], HIP[:, 2] + 1.3])


def catenary(a, b, sag, n=24):
    a, b = np.asarray(a), np.asarray(b)
    return [a + (b - a) * u - np.array([0, 0, sag * 4 * u * (1 - u)]) for u in np.linspace(0, 1, n)]


n_cab = 0
n_cab_skip = 0
for g0, g1 in zip(gantries[:-1], gantries[1:]):
    if g1["s"] - g0["s"] > 16:
        continue
    # 橋の上は吊りケーブルが並ぶので張らない(後ろから見ると線が重なって網のようになった)
    if any(f["s0"] - 2 <= (g0["s"] + g1["s"]) / 2 <= f["s1"] + 2 for f in BRIDGES):
        continue
    for side_u in (rng.uniform(0.15, 0.3), rng.uniform(0.7, 0.85)):
        for j in range(int(rng.integers(2, 5))):
            u0 = side_u + j * 0.012 + rng.uniform(-0.004, 0.004)
            u1 = side_u + j * 0.012 + rng.uniform(-0.03, 0.03)
            a = g0["a"] + (g0["b"] - g0["a"]) * u0 - [0, 0, 0.72]
            b = g1["a"] + (g1["b"] - g1["a"]) * u1 - [0, 0, 0.72]
            span = np.linalg.norm(b - a)
            pts = catenary(a, b, span * rng.uniform(0.06, 0.11))
            r = float(rng.choice([0.02, 0.03, 0.045, 0.07]))
            if poly_dist(pts, CAMS_ALL) < r + 0.8 or poly_dist(pts, BODY) < 1.0:
                n_cab_skip += 1
                continue
            tube(f"Cable_{n_cab}", pts, r, "cable", "cables")
            n_cab += 1
# 梁から壁へ垂れ下がるケーブル(壁の金物へ)
for g in gantries:
    for end, sg in ((g["a"], 1), (g["b"], -1)):
        if rng.random() < 0.5:
            continue
        a = g["a"] + (g["b"] - g["a"]) * (0.3 if sg == 1 else 0.7) - [0, 0, 0.72]
        s_ = g["s"] + rng.uniform(-4, 4)
        hw = wall_hits(s_)
        if hw is None:
            continue
        w_ = hw[0] if sg == 1 else hw[1]
        b = np.array([*w_, g["z"] - rng.uniform(2.5, 5.0)])
        inward = (pt(s_) - w_) / np.linalg.norm(pt(s_) - w_)
        b[:2] += inward * 0.75                 # 柱の前の金物
        pts = catenary(a, b, np.linalg.norm(b - a) * rng.uniform(0.08, 0.14))
        if poly_dist(pts, CAMS_ALL) < 0.9 or poly_dist(pts, BODY) < 1.0:
            n_cab_skip += 1
            continue
        tube(f"Cable_{n_cab}", pts, float(rng.choice([0.03, 0.05])), "cable", "cables")
        segbox(b - [0, 0, 0.25] - np.r_[inward, 0] * 0.75, b - [0, 0, 0.25] + np.r_[inward, 0] * 0.1, 0.3, 0.5,
               "machine", "wall", side=np.r_[inward[1], -inward[0], 0][:2])
        n_cab += 1
print("@@ cables", n_cab, "skipped", n_cab_skip, flush=True)


# ---------------------------------------------------------------- 道を横切るパイプ・最後の機械の台・出だしの赤い灯りの腕
for f in FEATS:
    if f["type"] != "pipe_x":
        continue
    h = wall_hits(f["s"])
    p, n_ = pt(f["s"]), nrm(f["s"])
    zc = f["h"] + f.get("top", 0.32) - f["r"]
    pts = [(*h[0], zc - 1.2), (*(h[0] + (p - h[0]) * 0.25), zc - 0.6), (*(p + n_ * 3), zc), (*(p - n_ * 3), zc),
           (*(h[1] + (p - h[1]) * 0.25), zc - 0.7), (*h[1], zc - 1.4)]
    tube(f"CrossPipe_{int(f['s'] * 10)}", pts, f["r"], "pipe_warm" if f.get("under") else "pipe_3", "pipes")
# 最後の機械(build_city.py: 道の終わりの 9 m 先 + 3 m、5x9x12 m、中心は h+2)の下に、底からの台
tl = path[-1] - path[-2]
tl /= np.linalg.norm(tl)
endp = path[-1] + tl * 12.0
hL = ground(L)
segbox((*endp - tl * 2.2, Z_BOT), (*endp + tl * 2.2, Z_BOT), 8.0, hL - 4.0 - Z_BOT, "machine", "machines",
       side=np.array([-tl[1], tl[0]]))
# 出だしの赤い灯り(道の 21 m + 6 m 先・高さ +2.6)は谷の中に浮いていた。同じ向き(通路のまっすぐ奥)の壁の手前 0.7 m へ移し、
# 壁に板を付けて持つ
s19 = tan(19.0)
LAMP = np.array([*(pt(21.0) + s19 * 6.0), ground(21.0) + 2.6])
o2 = pt(21.0)
hit = LineString([o2, o2 + s19 * 80]).intersection(WALL_LS)
hp = min([np.array(g.coords[0]) for g in getattr(hit, "geoms", [hit])], key=lambda c: np.linalg.norm(c - o2))
LAMP_NEW = np.array([*(hp - s19 * 0.7), LAMP[2]])
segbox((*hp - s19 * 0.6, LAMP[2] - 1.8), (*hp - s19 * 0.6, LAMP[2] + 1.8), 2.2, 0.4, "machine", "machines",
       side=np.array([-s19[1], s19[0]]))
print("@@ lamp moved", round(float(np.linalg.norm(LAMP_NEW - LAMP)), 2), "m", flush=True)

json.dump({"wall": WALL.tolist(), "z": [Z_BOT, Z_TOP], "tubes": tubes, "boxes": boxes,
           "lamp_a": [LAMP.tolist(), LAMP_NEW.tolist()]}, open(OUT, "w", encoding="utf-8"))
print("@@ wrote", OUT, len(tubes), "tubes", len(boxes), "boxes", flush=True)

if arg("--plot"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(24, 9))
    ax.fill(*WALL.T, color="#e8ecf2")
    ax.plot(*np.vstack([WALL, WALL[:1]]).T, "k-", lw=1.5)
    for tb in tubes:
        P = np.array(tb["pts"])
        col = {"pipes": "#4a6a9a", "cables": "#222", "beams": "#a05"}.get(tb["group"], "g")
        ax.plot(P[:, 0], P[:, 1], "-", color=col, lw=0.4 if tb["group"] == "cables" else 0.8)
    for bx in boxes:
        a, b = np.array(bx["a"]), np.array(bx["b"])
        ax.plot([a[0], b[0]], [a[1], b[1]], "-", color="#c60" if bx["group"] == "beams" else "#777", lw=1.2)
    ax.plot(PX[:, 0], PX[:, 1], "g-", lw=2)
    ax.scatter(CAM[:, 0], CAM[:, 1], s=1, c="r")
    ax.set_aspect("equal")
    plt.savefig(arg("--plot"), dpi=60, bbox_inches="tight")
