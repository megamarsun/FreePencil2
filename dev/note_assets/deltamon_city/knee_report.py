"""knee_scan.py の npz から、ひざのガタつき(骨盤から見たひざの位置の細かい揺れ)をショットごとに数える。

  python knee_report.py <ks.npz> [しきい値 cm(既定 1.0)]

揺れ = 骨盤の座標でのひざの位置 − それを 1.5 コマでならした物。IK を切った物(P_fk)があれば並べる。
ガタつきの場所を探す目安で、良し悪しは画像で決める。
"""
import sys

import numpy as np

z = np.load(sys.argv[1])
TH = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
fr, P, W, H = z["frames"], z["P"], z["W"], z["H"]
SH = [1, 299, 565, 789, 986, 1168, 1701, 2032, 2268, 2680, 2956, 3388, 3672, 3979, 4352, 5087, 5401]
Hi = np.linalg.inv(H)


def gauss(a, s):
    r = int(3 * s)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / s) ** 2)
    k /= k.sum()
    return np.stack([np.convolve(np.pad(a[:, i], r, mode="edge"), k, mode="valid") for i in range(a.shape[1])], 1)


def local(X):
    return np.einsum("nij,nj->ni", Hi, np.c_[X, np.ones(len(X))])[:, :3]


def jitter(P, side):
    o = 0 if side == "L" else 4
    kl = local(P[:, o + 1])
    return np.linalg.norm(kl - gauss(kl, 1.5), axis=1) * 100


def bend(P, side):
    o = 0 if side == "L" else 4
    h, k, a = P[:, o], P[:, o + 1], P[:, o + 2]
    u = (h - k) / np.linalg.norm(h - k, axis=1)[:, None]
    v = (a - k) / np.linalg.norm(a - k, axis=1)[:, None]
    return np.degrees(np.arccos(np.clip((u * v).sum(1), -1, 1)))


fk = "P_fk" in z
for side in "LR":
    j, b, w = jitter(P, side), bend(P, side), W[:, 0 if side == "L" else 1]
    jf = jitter(z["P_fk"], side) if fk else np.zeros_like(j)
    bad = j > TH
    print(f"{side}: >{TH}cm {bad.sum()} コマ (IK 切り {(jf > TH).sum()})  うち IK が効いている {(bad & (w > 0.01)).sum()}"
          f"  脚がほぼ伸びている(>165度) {(bad & (b > 165)).sum()}")
    for i in range(16):
        m = (fr >= SH[i]) & (fr < SH[i + 1])
        top = fr[m][np.argsort(-j[m])[:4]]
        print(f"  S{i + 1:02d} {(j[m] > TH).sum():4d} (IK切り {(jf[m] > TH).sum():4d})  最大 {j[m].max():4.1f} cm  "
              f"{' '.join(map(str, sorted(top)))}")
