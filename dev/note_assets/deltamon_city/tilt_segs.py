"""体(胴)が 30 度より倒れたコマの区間を出す。  python tilt_segs.py <run.npz>"""
import sys, numpy as np, mujoco
D = np.load(sys.argv[1]); S = D["s"]
m = mujoco.MjModel.from_xml_path("E:/10_cowork/00_code/motionbricks/motionbricks/assets/skeletons/g1/scene_29dof.xml"); d = mujoco.MjData(m)
ti = [mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "torso_link")][0]
tl = []
for q in D["qpos"]:
    d.qpos[:] = q; mujoco.mj_forward(m, d); tl.append(np.degrees(np.arccos(np.clip(d.xmat[ti][8], -1, 1))))
tl = np.array(tl); b = np.where(tl > 30)[0]
st = None
for i, f in enumerate(b):
    st = f if st is None else st
    if i == len(b) - 1 or b[i + 1] > f + 3:
        print("frames", st + 1, f + 1, "s", round(S[st], 1), round(S[f], 1), "max", round(tl[st:f + 1].max(), 1)); st = None
