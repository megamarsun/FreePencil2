"""retarget_terrain.py の足の止め方を npz の上でまねて、止める位置と元の足の横のずれが大きいコマを探す。"""
import sys
import numpy as np
D = np.load(sys.argv[1]); n = list(D["body_names"]); X = D["xpos"]; G = D["foot_ground"]; S = D["s"]
RAMP = 5
for i, side in enumerate(("left", "right")):
    P = X[:, n.index(side + "_ankle_pitch_link")]
    h = P[:, 2] - G[:, i]; h = h - np.percentile(h, 5)
    v = np.r_[0, np.linalg.norm(np.diff(P[:, :2], axis=0), axis=1)] * 30
    on = (h < 0.04) & (v < 0.25)
    idx = np.flatnonzero(on)
    for p_, q_ in zip(idx[:-1], idx[1:]):
        if 1 < q_ - p_ <= 4:
            on[p_:q_] = True
    segs, k = [], 0
    while k < len(on):
        if on[k]:
            j = k
            while j + 1 < len(on) and on[j + 1]:
                j += 1
            if j - k + 1 >= 4:
                segs.append((k, j))
            k = j + 1
        else:
            k += 1
    worst = []
    for a, b in segs:
        lock = P[a:b + 1, :2].mean(0)
        d = np.linalg.norm(P[max(0, a - RAMP):b + RAMP + 1, :2] - lock, axis=1).max()
        worst.append((d, a + 1, b + 1, round(S[a], 1), b - a + 1))
    worst.sort(reverse=True)
    print(side, "segments", len(segs), "worst:", [(round(w[0], 2), w[1], w[2], w[3], w[4]) for w in worst[:8]])
