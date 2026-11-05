"""デルタもんが配管の街を行く 3 分の道筋(course.json)を作る。MotionBricks(mb_terrain.py)と地形づくり(build_city.py)が読む。

  python make_course.py <out.json> [--pipes stile|low|box] [--climb stairs|ledge]

  --pipes deck(既定): 3 本のパイプの上に 1 枚の足場(2 段上がり、F の飛び降りで下りる)。stile: 1 本ずつまたぎ台(2 段上がって 2 段下りる)。low: 上が 0.12 m の細いパイプをまたぐ。box: 前の 0.25 m
  --set-poses: 上りの手前と上で一度立ち止まって構える
  --stairs-ramp: 階段の所の足場も坂のまま書く(place_stairs.py で足跡から段を作る前の物)
  --climb stairs(既定): I の 0.8 m の段は横の小階段 5 段で上る。ledge: 前のよじ登り
  MotionBricks の公開のクリップは歩き方の違いだけで、またぐ・よじ登る動きが無い。本当の高さの箱を見せると上に両足で乗り、
  見せないと足が抜けた。そこで MotionBricks が歩いて越えられる形(階段)に地形のほうを変えた

道は「まっすぐ」と「曲がる(円弧)」をつないだ線。地形の仕掛け(階段・橋・坂・パイプ越え・飛び降り・溝・跳び乗り)は
道のり s で置く。座標は MuJoCo(x 前, y 左, z 上, m)。台本は storyboard.md。
"""
import json
import math
import sys

import numpy as np

OUT = sys.argv[1]
PIPES = sys.argv[sys.argv.index("--pipes") + 1] if "--pipes" in sys.argv else "deck"
CLIMB = sys.argv[sys.argv.index("--climb") + 1] if "--climb" in sys.argv else "stairs"
# --stairs-ramp: 階段の足場(heights)も坂にする。動きを作ってから place_stairs.py で足跡に合わせた段に置き換える
STAIRS_RAMP = "--stairs-ramp" in sys.argv
# --set-poses: 上りの手前と上り切った所で一度立ち止まって構える(手前で足をそろえてから上り始め、上で姿勢を戻す)
SET_POSES = "--set-poses" in sys.argv

# ---------------------------------------------------------------- 道
# ("S", 長さ) まっすぐ / ("T", 角度(度, 左が正), 半径)
LEGS = [("S", 14.0),             # A 出だし: 奥の赤い灯りへ向かう通路
        ("S", 4.0),              # B 階段の上り
        ("S", 3.0),
        ("T", 50, 4.0),
        ("S", 14.0),             # C 吊り橋
        ("T", -70, 4.0),
        ("S", 8.0),              # D 太いパイプに沿って下る坂
        ("S", 9.0),              # E パイプ越え
        ("T", 60, 4.0),
        ("S", 8.0),              # F 飛び降り 2 段
        ("S", 16.0),             # G 走る
        ("T", -80, 5.0),
        ("S", 9.0),              # H 通路(I の段の手前)
        ("S", 6.0),              # I 跳び乗る
        ("T", 40, 4.0),
        ("S", 6.0),              # J 長い階段
        ("S", 4.0),
        ("S", 22.0)]             # K 赤い灯りへの最後の橋

pts = [np.array([0.0, 0.0])]
hd = 0.0
for lg in LEGS:
    if lg[0] == "S":
        n = max(2, int(lg[1] / 0.25))
        for i in range(1, n + 1):
            pts.append(pts[-1] + np.array([math.cos(hd), math.sin(hd)]) * lg[1] / n)
    else:
        ang, r = math.radians(lg[1]), lg[2]
        n = max(4, int(abs(ang) * r / 0.25))
        sgn = 1 if ang > 0 else -1
        c = pts[-1] + r * np.array([math.cos(hd + sgn * math.pi / 2), math.sin(hd + sgn * math.pi / 2)])
        a0 = hd - sgn * math.pi / 2
        for i in range(1, n + 1):
            a = a0 + ang * i / n
            pts.append(c + r * np.array([math.cos(a), math.sin(a)]))
        hd += ang
P = np.array(pts)
seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
L = float(seg[-1])

# 区切りの道のり(上の LEGS の頭)
heads = [0.0]
for lg in LEGS:
    heads.append(heads[-1] + (lg[1] if lg[0] == "S" else abs(math.radians(lg[1])) * lg[2]))
A0, B0, B1 = heads[0], heads[1], heads[2]
C0, C1 = heads[4], heads[5]
D0, D1 = heads[6], heads[7]
E0, E1 = heads[7], heads[8]
F0, F1 = heads[9], heads[10]
G0, G1 = heads[10], heads[11]
H0 = heads[12]
I0 = heads[13]
J0, J1 = heads[15], heads[16]
K0 = heads[17]

# ---------------------------------------------------------------- 高さ
H = []          # 足が乗る地面(地形・接地合わせ)
feats = []


def knot(s, h):
    H.append([round(s, 4), round(h, 4)])


lvl = 0.0
knot(0, lvl)
# B 階段 12 段で 1.8 m 上がる(けあげ 0.15・踏み面 0.38、約 22 度)。30 度(0.18/0.32)では体を 60 度以上倒してよじ登った
n, rise, run = 12, 0.15, 0.38
s = B0 + 0.4
knot(s, lvl)
for i in range(n):
    lvl += rise
    knot(s, lvl)
    s += run
    knot(s, lvl)
feats.append({"type": "stairs", "s0": B0 + 0.4, "s1": s, "h0": 0.0, "h1": lvl, "n": n, "name": "B"})
# C 吊り橋(高さそのまま)
feats.append({"type": "bridge", "s0": C0 - 0.5, "s1": C1 + 0.5, "h": lvl})
# D 坂: 1.8 → 0.6
knot(D0, lvl)
feats.append({"type": "ramp", "s0": D0, "s1": D1 - 1.0, "h0": lvl, "h1": 0.6})
lvl = 0.6
knot(D1 - 1.0, lvl)
# E パイプ越え: 道を横切るパイプ 3 本
#   stile: パイプの上にまたぎ台。けあげ 0.15・踏み面 0.32 で 2 段上がり、上 0.6 m、2 段下りる
#   low: 上が 0.12 m の細いパイプ(MotionBricks のふつうの一歩で越えられる高さ)
#   box: 上が 0.25 m のパイプ(足が抜けるか、上に両足で乗った。0.32 m では体を 70 度倒して乗り越えた)
#   deck(既定): 3 本の上にまとめて 1 枚の足場。2 段上がり(0.30 m)、そのまま F の飛び降りへ続く(下りの段は無い)。
#   またぎ台を 1 本ずつ上り下りさせると、毎回 台の上で両足をそろえて 60 度前へかがんだ
if PIPES == "deck":
    rise, run = 0.15, 0.36
    s = E0 + 1.6 - 0.6 - 2 * run
    h0 = lvl
    knot(s, lvl)
    for i in range(2):
        lvl += rise
        knot(s, lvl)
        s += run
        knot(s, lvl)
    feats.append({"type": "stairs", "s0": E0 + 1.6 - 0.6 - 2 * run, "s1": s, "h0": h0, "h1": lvl, "n": 2,
                  "name": "deck"})
for k, sc in enumerate((E0 + 1.6, E0 + 4.2, E0 + 6.8)):
    if PIPES == "deck":
        feats.append({"type": "pipe_x", "s": sc, "h": h0, "r": 0.2, "top": 0.25, "under": True})
        continue
    if PIPES == "stile":
        rise, run, top = 0.15, 0.32, 0.6
        s = sc - top / 2 - 2 * run
        h0 = lvl
        knot(s, lvl)
        for i in range(2):
            lvl += rise
            knot(s, lvl)
            s += run
            knot(s, lvl)
        feats.append({"type": "stairs", "s0": sc - top / 2 - 2 * run, "s1": s, "h0": h0, "h1": lvl, "n": 2,
                      "name": f"stile{k}up"})
        s += top
        knot(s, lvl)
        s0_ = s
        for i in range(2):
            lvl -= rise
            knot(s, lvl)
            s += run
            knot(s, lvl)
        feats.append({"type": "stairs", "s0": s0_, "s1": s, "h0": h0 + 2 * rise, "h1": lvl, "n": 2,
                      "name": f"stile{k}down"})
        feats.append({"type": "pipe_x", "s": sc, "h": h0, "r": 0.2, "top": 0.25, "under": True})
        continue
    w, top, r = (0.45, 0.25, 0.2) if PIPES == "box" else (0.18, 0.12, 0.09)
    knot(sc - w / 2, lvl)
    knot(sc - w / 2, lvl + top)
    knot(sc + w / 2, lvl + top)
    knot(sc + w / 2, lvl)
    feats.append({"type": "pipe_x", "s": sc, "h": lvl, "r": r, "top": top})
# F 飛び降り 2 段: 0.6 → 0.0 → -0.6
for k, sd in enumerate((F0 + 2.0, F0 + 5.0)):
    knot(sd, lvl)
    feats.append({"type": "ledge", "s": sd, "h0": lvl, "h1": lvl - 0.6})
    lvl -= 0.6
    knot(sd, lvl)
# G 走る(平ら)。溝は走りの一番長い一歩の間に、動きを作った後で置く(place_gap.py)。
# MotionBricks の公開のクリップに跳ぶ動きは無く、溝の上に山を見せても見えない坂を歩いて越えるだけだった
# I 0.8 m の段。stairs: 横に付いた小階段 5 段(けあげ 0.16・踏み面 0.36)で上る。ledge: よじ登る
#   (よじ登りは手本が無く、腰だけ上げると段に体が入り、体ごと上げると浮き上がった)
sj = I0 + 2.0
if CLIMB == "stairs":
    n, rise, run = 5, 0.16, 0.36
    s = sj - 1.0
    h0 = lvl
    knot(s, lvl)
    for i in range(n):
        lvl += rise
        knot(s, lvl)
        s += run
        knot(s, lvl)
    feats.append({"type": "stairs", "s0": sj - 1.0, "s1": s, "h0": h0, "h1": lvl, "n": n, "name": "I"})
else:
    knot(sj, lvl)
    feats.append({"type": "ledge", "s": sj, "h0": lvl, "h1": lvl + 0.8})
    lvl += 0.8
    knot(sj, lvl)
# J 長い階段: 8 段 + 踊り場 1.5 m + 8 段で 2.48 m 上がる(0.155 / 0.36)。踊り場の無い 16 段では途中で足がもつれ、
# 上で足を高く蹴り上げた
n, rise, run = 8, 0.155, 0.36
s = J0
for fl in range(2):
    knot(s, lvl)
    h0 = lvl
    s0_ = s
    for i in range(n):
        lvl += rise
        knot(s, lvl)
        s += run
        knot(s, lvl)
    feats.append({"type": "stairs", "s0": s0_, "s1": s, "h0": h0, "h1": lvl, "n": n, "name": f"J{fl}"})
    s += 1.5
# K 最後の橋
feats.append({"type": "bridge", "s0": K0 + 1.0, "s1": L - 3.0, "h": lvl})
knot(L, lvl)

H = sorted(H, key=lambda k: k[0])
# 階段は MotionBricks に段でなく坂を見せ(段の頭の 0.4 m 手前から終わりの 0.2 m 先まで)、0.4 m 先を見せる。
# 段のまま見せると、腰が遅れたあと大きな高さの差で跳ねて、上の段で頭が下になった(S04)。足は接地合わせで段に乗る
stairs = [f for f in feats if f["type"] == "stairs"]
ST = {f["name"]: f for f in stairs}
HMB = [list(k) for k in H if not any(f["s0"] - 0.4 <= k[0] <= f["s1"] + 0.2 for f in stairs)]
for f in stairs:
    HMB += [[f["s0"] - 0.4, f["h0"]], [f["s1"] + 0.2, f["h1"]]]
# パイプは MotionBricks に低いなだらかな山(0.12 m・幅 1.2 m)で見せる。0.25 m の段のまま見せると体を 66 度倒して越えた。
# 足は接地合わせでパイプの上に乗る
pipes = [f for f in feats if f["type"] == "pipe_x" and not f.get("under")]
HMB = [k for k in HMB if not any(abs(k[0] - f["s"]) <= 0.3 for f in pipes)]
for f in pipes:
    HMB += [[f["s"] - 0.6, f["h"]], [f["s"], f["h"] + 0.12], [f["s"] + 0.6, f["h"]]]
HMB = sorted(HMB, key=lambda k: k[0])
if STAIRS_RAMP:
    H = [k for k in H if not any(f["s0"] - 0.4 <= k[0] <= f["s1"] + 0.2 for f in stairs)]
    for f in stairs:
        H += [[f["s0"] - 0.4, f["h0"]], [f["s1"] + 0.2, f["h1"]]]
    H = sorted(H, key=lambda k: k[0])

course = {
    "path": P.round(4).tolist(),
    "length": L,
    "heights": H,
    "mb_heights": HMB,
    # 跳ぶ所だけ先を見せる(跳び乗り・溝)。飛び降りと階段は 0
    # 階段は 0.4(B と、踊り場をはさむ J の 2 本はまとめて 1 区間。分けると J1 の上り始めで前へかがんだ)
    "leads": sorted([[0, 0.0], [ST["B"]["s0"] - 1.5, 0.4], [ST["B"]["s1"] + 0.5, 0.0],
                     [ST["J0"]["s0"] - 1.5, 0.4], [ST["J1"]["s1"] + 0.5, 0.0]]
                    + ([[ST["I"]["s0"] - 1.5, 0.4], [ST["I"]["s1"] + 0.5, 0.0]] if CLIMB == "stairs"
                       else [[sj - 2.5, 1.0], [sj + 1.0, 0.0]])
                    # またぎ台は上りだけ先を見せ、上に着いたら 0(下りで先を見せると、上で両足をそろえて前へかがんだ)
                    + ([[ST["deck"]["s0"] - 1.5, 0.4], [ST["deck"]["s1"] + 0.5, 0.0]] if PIPES == "deck" else [])
                    + (sum([[[ST[f"stile{k}up"]["s0"] - 1.5, 0.4], [ST[f"stile{k}up"]["s1"], 0.0]] for k in range(3)], [])
                       if PIPES == "stile" else [])),
    "nofit": [] if CLIMB == "stairs" else [[sj - 1.2, sj + 1.2]],
    # slow_walk は 0.35 m/s ほど(walk は 0.95 m/s)。橋の渡り始めと最後の 6 m だけ
    "modes": [[0, "slow_walk", None], [4.0, "walk", None], [C0, "slow_walk", None], [C0 + 4.0, "walk", None],
              [G0 + 2.0, "walk", 2.6], [G1 - 1.0, "walk", None],
              [L - 6.0, "slow_walk", None]],
    "waits": [[0.3, 120, None],                       # 出だし: 奥を見て立つ
              [ST["B"]["s1"] + 1.0, 45, None],      # 階段を上りきって一息(段の上で止めると足が別の段に乗って膝をついた)
              [(C0 + C1) / 2, 100, None],             # 橋の真ん中: 下をのぞく(道の向きのまま)
              [F0 + 1.2, 40, None],                   # 飛び降りの前
              [(ST["I"]["s0"] if CLIMB == "stairs" else sj) - 1.6, 30, None],   # 0.8 m の段の前で見上げる
              [ST["J1"]["s1"] + 1.0, 60, None]]      # 長い階段の上
             # 小階段の手前は 1.6 m 手前の見上げで構える(段の直前でもう一度止めると、両足ですべり上がった)
             + ([[ST["B"]["s0"] - 0.8, 25, None],                     # 階段 B の手前で構える
                 [ST["I"]["s1"] + 0.8, 25, None],                     # 小階段の上
                 [ST["J0"]["s0"] - 0.8, 25, None],                    # 長い階段の手前
                 [ST["J0"]["s1"] + 0.5, 20, None]]                    # 踊り場で構え直す(止めないと前へ 50 度かがんだ)
                + ([[ST["deck"]["s0"] - 1.2, 30, None], [ST["deck"]["s1"] + 0.8, 15, None]] if PIPES == "deck" else [])
                if SET_POSES else []),
    "features": feats,
    "sections": {"A": A0, "B": B0, "C": C0, "D": D0, "E": E0, "F": F0, "G": G0, "H": H0, "I": I0,
                 "J": J0, "K": K0, "end": L},
}
json.dump(course, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("@@ course", OUT, "length", round(L, 1), "m", {k: round(v, 1) for k, v in course["sections"].items()})
