"""上りの階段を、MotionBricks が足を着いた所に合わせて作り直した course を書く(place_gap.py と同じ「動きが先、地形が後」)。

  python place_stairs.py <course.json> <run.npz> <out course.json> [--debug]

course は make_course.py --stairs-ramp で、階段の所の足場が坂の物。run は mb_terrain.py でその course を歩かせた物
(接地合わせで、立っている足の裏が坂に乗っている)。
1 歩ごとに、立っている足の裏の高さの踏み面を置き、前の足のつま先と次の足のかかとの間に蹴上げを立てる。
段の高さ・奥行きはそろわないが、足は必ず踏み面に乗り、蹴上げに埋まらない。
MotionBricks には段の上り方の手本が無く、決まった段を見せると足が段の途中に着いて埋まった。
"""
import json
import sys

import numpy as np

cs = json.load(open(sys.argv[1], encoding="utf-8"))
D = np.load(sys.argv[2])
OUT = sys.argv[3]
DEBUG = "--debug" in sys.argv
STILL = float(sys.argv[sys.argv.index("--still") + 1]) if "--still" in sys.argv else 0.02
MINF = int(sys.argv[sys.argv.index("--min-frames") + 1]) if "--min-frames" in sys.argv else 2

names = list(D["body_names"])
X, S = D["xpos"], D["s"]
P = np.array(cs["path"])
seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]


def pt(s):
    return np.stack([np.interp(s, seg, P[:, 0]), np.interp(s, seg, P[:, 1])], -1)


def tan(s):
    d = pt(s + 0.2) - pt(s - 0.2)
    return d / np.linalg.norm(d, axis=-1, keepdims=True)


H = np.array(cs["heights"])


def ground(s):
    return np.interp(s, H[:, 0], H[:, 1])


# 足の長さ(足首から): G1 の足は足首の前 0.13 m・後ろ 0.07 m ほど
TOE, HEEL = 0.13, 0.07
# 立っている足: 水平の速さが 1 コマ STILL m 未満が MINF コマ以上続く所(既定 2 cm・2 コマ。1 cm・3 コマでは MotionBricks が両足をすべらせて上る所で足跡が拾えず、60 cm の段になった)
steps = []
for side in ("left", "right"):
    a = X[:, names.index(f"{side}_ankle_roll_link")]
    sole0 = a[:30, 2].min() - ground(S[0])          # 平らな所で立っている時の足首の高さ
    sa = S + ((a[:, :2] - pt(S)) * tan(S)).sum(-1)    # 足首の道のり
    z = a[:, 2] - sole0                              # 足の裏の高さ
    sp = np.r_[0, np.linalg.norm(np.diff(a[:, :2], axis=0), axis=1)]
    sp = np.convolve(sp, np.ones(3) / 3, "same")
    on = sp < STILL
    f = 0
    while f < len(on):
        if on[f]:
            g = f
            while g < len(on) and on[g]:
                g += 1
            if g - f >= MINF:
                steps.append({"side": side[0].upper(), "f0": f, "f1": g - 1,
                              "s": float(np.median(sa[f:g])), "z": float(np.median(z[f:g]))})
            f = g
        else:
            f += 1
steps.sort(key=lambda e: e["s"])

feats = cs["features"]
Hk = [list(k) for k in cs["heights"]]
for ft in feats:
    if ft["type"] != "stairs" or ft["h1"] <= ft["h0"]:
        continue
    a, b = ft["s0"] - 0.4, ft["s1"] + 0.2                # 坂にしてある区間
    h0, h1 = ft["h0"], ft["h1"]
    ev = [e for e in steps if a - 0.3 <= e["s"] <= b + 0.3]
    # 同じ踏み面に乗った足(0.12 m 以内)はまとめる
    tr = []
    for e in ev:
        if tr and e["s"] - tr[-1]["s1"] < 0.12:
            tr[-1]["s1"] = e["s"]
            tr[-1]["z"] = max(tr[-1]["z"], e["z"])
            tr[-1]["ev"].append(e)
        else:
            tr.append({"s0": e["s"], "s1": e["s"], "z": e["z"], "ev": [e]})
    # 高さ: 下の床・上の床に近い物はそろえ、上りなので前より低くしない
    hs = []
    for t_ in tr:
        h = min(max(t_["z"], h0), h1)
        if h < h0 + 0.04:
            h = h0
        if h > h1 - 0.04:
            h = h1
        h = max(h, hs[-1] if hs else h0)
        hs.append(h)
    knots = [[a, h0]]
    risers = []
    cur = h0
    for i, (t_, h) in enumerate(zip(tr, hs)):
        if h - cur < 0.04:                               # 4 cm 未満の段は作らない(前の踏み面のまま)
            continue
        heel = t_["s0"] - HEEL
        prev_toe = (tr[i - 1]["s1"] + TOE) if i > 0 else heel - 0.3
        prev_toe = max(prev_toe, knots[-1][0])                # 坂にしてある区間の始まり・前の蹴上げより手前には立てない
        # 足と足の間が広ければ、足の乗らない段を間に入れる(段を 1 つ飛ばして上る)。
        # 間の段の奥行きは 20 cm 以上、1 段の高さは 13 cm ほど。入れないと奥行き 60〜85 cm の広い段になった
        free = heel - prev_toe
        k = max(1, min(int(round((h - cur) / 0.13)), int(free / 0.20))) if free > 0 else 1
        # 間が 30 cm 以上なら蹴上げを 2 本にし、つま先のすぐ先とかかとのすぐ手前に立てる(1 段飛ばし)。
        # 間の真ん中に 1 本だと、足の乗る段が 歩幅ほど(50 cm)の広さになった
        if free >= 0.30 and h - cur >= 0.10:
            k = max(k, 2)
        m = min(0.06, free / (2 * k)) if free > 0 else 0
        # 足を すべらせて 1 歩抜けた所(間が 60 cm を超える)は、間の段が 40 cm 以下になるまで増やす
        while k >= 2 and (free - 2 * m) / (k - 1) > 0.42 and (h - cur) / (k + 1) >= 0.05:
            k += 1
        for j in range(k):
            if free <= 0:
                r = heel - 0.01
            elif k == 1:
                r = prev_toe + free / 2
            else:
                r = prev_toe + m + (free - 2 * m) * j / (k - 1)
            r = max(r, knots[-1][0] + 0.05)
            hn = cur + (h - cur) * (j + 1) / k
            knots += [[r, knots[-1][1]], [r, hn]]
            risers.append(round(r, 3))
        cur = h
    if cur < h1:                                         # 上の床へ(最後の足が上り切っていない)
        r = max(b, knots[-1][0] + 0.3)
        knots += [[r, cur], [r, h1]]
        risers.append(round(r, 3))
    knots.append([max(b, knots[-1][0]) + 0.01, h1])
    Hk = [k for k in Hk if not (a - 1e-6 <= k[0] <= b + 1e-6)] + knots
    rises = np.diff([h0] + [k[1] for k in knots[2::2]])
    print("@@ stairs", ft.get("name"), "s", round(ft["s0"], 2), "-", round(ft["s1"], 2), "footfalls", len(ev),
          "treads", len(tr), "risers", len(risers), "rise cm", [round(x * 100) for x in rises],
          "run cm", [round(x * 100) for x in np.diff(risers)])
    if DEBUG:
        for t_, h in zip(tr, hs):
            print("   tread s", round(t_["s0"], 2), round(t_["s1"], 2), "z", round(t_["z"], 3), "->", round(h, 3),
                  [(e["side"], e["f0"], e["f1"]) for e in t_["ev"]])
    ft.update({"s0": risers[0], "s1": risers[-1], "n": len(risers), "fitted": True, "risers": risers})
cs["heights"] = sorted(Hk, key=lambda k: (k[0]))
json.dump(cs, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("@@ wrote", OUT)
