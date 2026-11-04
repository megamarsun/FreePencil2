"""ひざのガタつきを絵で見る: ひざの曲がり(度)をコマに沿って描き、ひざの IK の効き具合を下に重ねる。

  python knee_plot.py <ks.npz> <out.png> <コマ0>-<コマ1>[,<コマ0>-<コマ1>...] [--cmp <前の ks.npz>]

なめらかな山と谷になっていれば良い。1〜2 コマのとがり・段差がガタつき。--cmp で前を灰色で重ねる。
"""
import sys

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

A = sys.argv[1:]
z = np.load(A[0])
spans = [tuple(int(v) for v in s.split("-")) for s in A[2].split(",")]
zc = np.load(A[A.index("--cmp") + 1]) if "--cmp" in A else None


def bend(P, o):
    h, k, a = P[:, o], P[:, o + 1], P[:, o + 2]
    u = (h - k) / np.linalg.norm(h - k, axis=1)[:, None]
    v = (a - k) / np.linalg.norm(a - k, axis=1)[:, None]
    return 180 - np.degrees(np.arccos(np.clip((u * v).sum(1), -1, 1)))


fig, axs = plt.subplots(len(spans), 1, figsize=(16, 3.2 * len(spans)), squeeze=False)
for ax, (f0, f1) in zip(axs[:, 0], spans):
    for d, alpha, lw, tag in ((zc, 0.35, 1.2, "before"), (z, 1.0, 1.4, "")):
        if d is None:
            continue
        fr = d["frames"]
        m = (fr >= f0) & (fr <= f1)
        for o, col, side in ((0, "tab:blue", "L"), (4, "tab:red", "R")):
            ax.plot(fr[m], bend(d["P"], o)[m], color=col if d is z else "gray", alpha=alpha, lw=lw,
                    marker="." if d is z else None, ms=3, label=f"{side} {tag}".strip())
    fr = z["frames"]
    m = (fr >= f0) & (fr <= f1)
    ax2 = ax.twinx()
    ax2.fill_between(fr[m], z["W"][m, 0], color="tab:blue", alpha=0.08, step="mid")
    ax2.fill_between(fr[m], z["W"][m, 1], color="tab:red", alpha=0.08, step="mid")
    ax2.set_ylim(0, 4)
    ax2.set_yticks([])
    ax.set_xlim(f0, f1)
    ax.set_ylabel("knee bend (deg)")
    ax.set_title(f"frames {f0}-{f1}  (shaded = knee IK influence)", fontsize=10)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right", fontsize=8)
fig.tight_layout()
fig.savefig(A[1], dpi=90)
print("@@ plot", A[1])
