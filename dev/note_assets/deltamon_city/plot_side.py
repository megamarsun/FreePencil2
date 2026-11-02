"""MotionBricks の結果を横から見た図: 地面の線・足首の通り道・何コマかおきの棒人間。
  python plot_side.py <course.json> <run.npz> <out.png> [s0 s1]"""
import json, sys
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
cs = json.load(open(sys.argv[1], encoding="utf-8")); D = np.load(sys.argv[2]); out = sys.argv[3]
s0, s1 = (float(sys.argv[4]), float(sys.argv[5])) if len(sys.argv) > 5 else (None, None)
names = list(D["body_names"]); X = D["xpos"]; S = D["s"]
HK = np.array(cs["heights"]); path = np.array(cs["path"])
seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
def s_of(xy):
    ss = np.linspace(0, seg[-1], 4000)
    pts = np.stack([np.interp(ss, seg, path[:, 0]), np.interp(ss, seg, path[:, 1])], 1)
    return ss[np.argmin(np.linalg.norm(pts[None] - xy[:, None], axis=2), axis=1)]
pel = X[:, names.index("pelvis")]
sp = s_of(pel[:, :2])
fig, ax = plt.subplots(figsize=(28, 7), dpi=100)
ax.plot(HK[:, 0], HK[:, 1], "k-", lw=3, label="地面")
for ft in cs.get("features", []):      # 溝は赤い帯
    if ft["type"] == "gap":
        ax.fill_between([ft["s0"], ft["s1"]], ft["h"] - 1.0, ft["h"] + 0.02, color="tab:red", alpha=0.35, lw=0)
for nm, c in (("left_ankle_roll_link", "tab:blue"), ("right_ankle_roll_link", "tab:red")):
    a = X[:, names.index(nm)]
    ax.plot(s_of(a[:, :2]), a[:, 2] - 0.04, c, lw=1, alpha=0.8)
bones = [("pelvis", "left_knee_link"), ("left_knee_link", "left_ankle_roll_link"),
         ("pelvis", "right_knee_link"), ("right_knee_link", "right_ankle_roll_link"),
         ("pelvis", "torso_link"), ("torso_link", "left_elbow_link"), ("torso_link", "right_elbow_link")]
for f in range(0, len(X), 12):
    for a, b in bones:
        pa, pb = X[f, names.index(a)], X[f, names.index(b)]
        sa, sb = s_of(np.array([pa[:2], pb[:2]]))
        ax.plot([sa, sb], [pa[2], pb[2]], color="0.5", lw=0.6)
ax.set_aspect("equal")
if s0 is not None: ax.set_xlim(s0, s1)
ax.grid(alpha=0.3); ax.set_xlabel("道のり s (m)"); ax.set_ylabel("高さ (m)")
plt.rcParams["font.family"] = "MS Gothic"
plt.tight_layout(); plt.savefig(out); print("@@", out)
