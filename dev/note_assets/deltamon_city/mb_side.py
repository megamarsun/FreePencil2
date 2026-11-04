"""MotionBricks の出力(npz)を真横から棒人形で並べる。リターゲット前の、MotionBricks そのものの動きを見る。

  python mb_side.py <course.json> <out.png> <名前=run.npz>... [--s 4.0-10.5] [--every 3] [--cols 10]

横軸は道のり s(体の点を腰の所の道の向きへ射影)。段の形を灰色で描き、左脚を青、右脚を赤で描く。
名前ごとに 1 段(行のまとまり)。同じコマ数おきに並べるので、名前どうしを見比べられる。
"""
import json
import sys

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

A = sys.argv[1:]
arg = lambda n, d=None: A[A.index(n) + 1] if n in A else d   # noqa: E731
C = json.load(open(A[0], encoding="utf-8"))
OUT = A[1]
runs = [a.split("=", 1) for a in A[2:] if "=" in a and not a.startswith("--")]
S0, S1 = (float(v) for v in arg("--s", "4.0-10.5").split("-"))
EVERY = int(arg("--every", "3"))
COLS = int(arg("--cols", "10"))
HK = np.array(C["heights"])
path = np.array(C["path"])
seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
CH = [("pelvis", "torso_link"), ("torso_link", "head")]
for s in ("left", "right"):
    CH += [("pelvis", f"{s}_hip_pitch_link"), (f"{s}_hip_pitch_link", f"{s}_knee_link"),
           (f"{s}_knee_link", f"{s}_ankle_roll_link"), (f"{s}_ankle_roll_link", f"{s}_toe")]

data = []
for name, p in runs:
    z = np.load(p)
    X = z["xpos"]
    nm = list(z["body_names"])
    B = {n: i for i, n in enumerate(nm)}
    P = {}
    for a in set(x for c in CH for x in c):
        if a in B:
            P[a] = X[:, B[a]]
    sh = (X[:, B["left_shoulder_pitch_link"]] + X[:, B["right_shoulder_pitch_link"]]) / 2
    P["torso_link"] = sh                         # 肩の真ん中(前かがみが見えるように)
    P["head"] = sh + (sh - X[:, B["pelvis"]]) * 0.45
    # 道のり s と高さの平面に移す: 腰の道のり(npz の s)の所の道の向きへ射影する(階段はまっすぐなので足りる)
    sh_ = z["s"]
    p0 = np.stack([np.interp(sh_, seg, path[:, 0]), np.interp(sh_, seg, path[:, 1])], 1)
    tg = np.stack([np.interp(sh_ + 0.2, seg, path[:, 0]), np.interp(sh_ + 0.2, seg, path[:, 1])], 1) - \
        np.stack([np.interp(sh_ - 0.2, seg, path[:, 0]), np.interp(sh_ - 0.2, seg, path[:, 1])], 1)
    tg /= np.linalg.norm(tg, axis=1)[:, None]
    for a in list(P):
        q = P[a].copy()
        q[:, 0] = sh_ + ((P[a][:, :2] - p0) * tg).sum(1)
        P[a] = q
    for s in ("left", "right"):
        an = P[f"{s}_ankle_roll_link"]
        # つま先: 足首から前へ 0.15 m、少し下
        P[f"{s}_toe"] = an + np.array([0.15, 0, -0.03])
    px = P["pelvis"][:, 0]
    fr = np.where((px >= S0) & (px <= S1))[0][::EVERY]
    data.append((name, P, fr))

n_rows = sum((len(fr) + COLS - 1) // COLS for _, _, fr in data)
fig, axs = plt.subplots(n_rows, COLS, figsize=(COLS * 1.9, n_rows * 2.6), squeeze=False)
r = 0
for name, P, fr in data:
    rows = (len(fr) + COLS - 1) // COLS
    for i in range(rows * COLS):
        ax = axs[r + i // COLS, i % COLS]
        ax.set_axis_off()
        if i >= len(fr):
            continue
        f = fr[i]
        cx = P["pelvis"][f, 0]
        cz = P["pelvis"][f, 2]
        ax.fill_between(HK[:, 0], HK[:, 1], -1, color="0.82", step=None)
        for a, b in CH:
            col = "tab:blue" if a.startswith("left") or b.startswith("left") else \
                "tab:red" if a.startswith("right") or b.startswith("right") else "0.2"
            ax.plot([P[a][f, 0], P[b][f, 0]], [P[a][f, 2], P[b][f, 2]], color=col, lw=2.2,
                    solid_capstyle="round")
        ax.set_xlim(cx - 0.75, cx + 0.75)
        ax.set_ylim(cz - 1.05, cz + 0.95)
        ax.set_aspect("equal")
        ax.text(0.02, 0.97, f"{name} {f + 1}", transform=ax.transAxes, va="top", fontsize=8)
    r += rows
fig.tight_layout(pad=0.2)
fig.savefig(OUT, dpi=int(arg("--dpi", "80")))
print("@@ wrote", OUT, n_rows, "rows")
