"""階段 B の上(s 17〜20)で、腰と膝が本当の段からどれだけ上にあるかを見る。腰 0.6 m 未満・膝 0.1 m 未満が膝つき。"""
import json
import sys

import numpy as np

c = json.load(open(sys.argv[1], encoding="utf-8"))
H = np.array(c["heights"])
d = np.load(sys.argv[2])
n = list(d["body_names"])
X, S = d["xpos"], d["s"]


def true_g(s):
    i = np.searchsorted(H[:, 0], s, side="right") - 1
    return H[max(i, 0), 1]


pi = n.index("pelvis")
kn = [n.index("left_knee_link"), n.index("right_knee_link")]
low = []
for i in range(len(S)):
    if 17.0 <= S[i] <= 20.0:
        g = true_g(S[i])
        p = X[i, pi, 2] - g
        k = min(X[i, j, 2] for j in kn) - g
        low.append((p, k, i + 1))
print("min pelvis", round(min(x[0] for x in low), 2), "at", min(low)[2],
      "min knee", round(min(x[1] for x in low), 2), "frames pelvis<0.6", sum(x[0] < 0.6 for x in low))
