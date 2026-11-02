"""走る区間(G)の一番長い一歩(宙に浮く間)を探し、そこに溝を置いた course を書く。
  python place_gap.py <course.json> <run.npz> <out course.json> [--width-max 0.9]"""
import json
import sys

import numpy as np

cs = json.load(open(sys.argv[1], encoding="utf-8"))
D = np.load(sys.argv[2])
OUT = sys.argv[3]
names = list(D["body_names"])
X, S = D["xpos"], D["s"]
g0, g1 = cs["sections"]["G"] + 6.0, cs["sections"]["H"] - 3.0       # 走りが落ち着いた所だけ
path = np.array(cs["path"])
seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]


def s_of(xy, hint):
    ss = np.linspace(hint - 2, hint + 2, 400)
    pts = np.stack([np.interp(ss, seg, path[:, 0]), np.interp(ss, seg, path[:, 1])], 1)
    return float(ss[np.argmin(np.linalg.norm(pts - xy, axis=1))])


cont = []
for k in ("left", "right"):
    a = X[:, names.index(f"{k}_ankle_roll_link")]
    z = a[:, 2] - D["ground"] if False else a[:, 2]
    sp = np.r_[0, np.linalg.norm(np.diff(a[:, :2], axis=0), axis=1)] * 30
    on = sp < 0.35
    f = 0
    while f < len(on):
        if on[f]:
            e = f
            while e + 1 < len(on) and on[e + 1]:
                e += 1
            if e - f >= 1 and g0 <= S[f] <= g1:
                cont.append((f, e, k, s_of(a[f, :2], S[f]), s_of(a[e, :2], S[e])))
            f = e + 1
        else:
            f += 1
cont.sort()
best = None
for c0, c1 in zip(cont[:-1], cont[1:]):
    if c0[2] == c1[2]:
        continue
    toe = c0[4] + 0.12           # 踏み切る足のつま先
    heel = c1[3] - 0.06          # 着く足のかかと
    w = heel - toe
    air = c1[0] - c0[1]
    if best is None or w > best[0]:
        best = (w, toe, heel, air, c0[1], c1[0])
w, toe, heel, air, fa, fb = best
w = min(w, float(sys.argv[sys.argv.index("--width-max") + 1]) if "--width-max" in sys.argv else 0.9)
mid = (toe + heel) / 2
gap = {"type": "gap", "s0": round(mid - w / 2, 3), "s1": round(mid + w / 2, 3),
       "h": float(np.interp(mid, *np.array(cs["heights"]).T)), "takeoff_frame": int(fa), "land_frame": int(fb)}
cs["features"] = [f for f in cs["features"] if f["type"] != "gap"] + [gap]
json.dump(cs, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("@@ strides", len(cont) - 1, "gap", gap, "air frames", air)
