"""MotionBricks(G1)を高低差のある道筋に沿って歩かせ、毎コマの姿勢を BVH と npz に書く(mb_maze.py の地形版)。

  cd E:/10_cowork/00_code/motionbricks/motionbricks
  <motionbricks の python> <このファイル> <course.json> <出力名(拡張子なし)> [--seed 1234] [--tail 90]

地形の高さは MotionBricks の「目標の姿勢」に入れる。MotionBricks は 4 コマの文脈(今の姿勢)と、
少し先の目標の姿勢(歩きのクリップを目標の位置と向きへ置いたもの)の間を埋めて動きを作る。
目標の腰の高さに「目標の位置の地面の高さ − 今の地面の高さ」を足すと、その間を埋める動きが段を上がり下りする。
文脈の高さは今の地面の高さを引いて渡し(学習で見た腰の高さのまま)、作った動きに足して戻す。

course.json:
  path    [[x, y], ...]          MuJoCo の座標(x 前, y 左, m)。自分と交わらない道
  heights [[s, h], ...]          道のり s(m)での地面の高さ h(m)。間は直線。同じ s を 2 つ並べると段
  modes   [[s, mode, vel], ...]  s から先の歩き方(clip_holder_G1 の名前)。vel は速さ(m/s、null で既定)
  waits   [[s, frames, yaw], ...] s に着いたら frames コマ立ち止まる。yaw(度、null で道の向き)を向く
  look    先を見る距離(m、既定 1.0)

出力:
  <名前>.bvh  リターゲット用(mb_maze.py と同じ骨)
  <名前>.npz  qpos(コマ, 36)・root_positions・xpos(コマ, 体, 3)・ground(コマ: その時の地面の高さ)・s(コマ)
"""
import json
import os
import sys
from types import SimpleNamespace

import mujoco
import numpy as np
import torch as t
from scipy.spatial.transform import Rotation as R

MB = "E:/10_cowork/00_code/motionbricks/motionbricks"
sys.path.insert(0, MB)
os.chdir(MB)
from motionbricks.motion_backbone.demo.clips import clip_holder_G1          # noqa: E402
from motionbricks.motion_backbone.demo.controllers import base_controller   # noqa: E402
from motionbricks.motion_backbone.demo.utils import navigation_demo         # noqa: E402

A = sys.argv[1:]
arg = lambda n, d=None: A[A.index(n) + 1] if n in A else d  # noqa: E731
COURSE, OUT = A[0], A[1]
SEED = int(arg("--seed", "1234"))
TAIL = int(arg("--tail", "90"))
MAX_STEPS = int(arg("--max-steps", "9000"))

cs = json.load(open(COURSE, encoding="utf-8"))
path = np.array(cs["path"], dtype=float)
seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
HK = np.array(cs["heights"], dtype=float)
# MotionBricks に見せる高さ。無ければ heights。溝を跳ぶ所は溝の上に山を置き、跳ぶ動きを作らせる
HMB = np.array(cs.get("mb_heights", cs["heights"]), dtype=float)
LEADS = sorted(cs.get("leads", [[0, 0.0]]), key=lambda x: x[0])
MODES_AT = sorted(cs.get("modes", [[0, "walk", None]]), key=lambda m: m[0])
WAITS = sorted(cs.get("waits", []), key=lambda w: w[0])
LOOK = float(cs.get("look", 1.0))
# 目標の高さを道の先 lead m の地面にする(区間ごと)。目標の位置そのままの高さだと、腰が地面より 1 m ほど遅れて上下した。
# 0.6 m 以上先を見せると、1 m の段で歩いて上がらずに跳び乗る動きになった(跳ぶ所だけに使う)


def lead_at(s):
    v = 0.0
    for a, b in LEADS:
        if s >= a:
            v = b
    return v
MODES = list(clip_holder_G1.CLIPS.keys())


def ground(s, HK=HK):
    """道のり s の地面の高さ。段(同じ s が 2 つ)は先の値。"""
    s = float(np.clip(s, HK[0, 0], HK[-1, 0]))
    i = int(np.searchsorted(HK[:, 0], s, side="right"))
    if i <= 0:
        return HK[0, 1]
    if i >= len(HK):
        return HK[-1, 1]
    s0, h0 = HK[i - 1]
    s1, h1 = HK[i]
    return h1 if s1 - s0 < 1e-6 else h0 + (h1 - h0) * (s - s0) / (s1 - s0)


def point(s):
    return np.array([np.interp(s, seg, path[:, 0]), np.interp(s, seg, path[:, 1])])


def nearest_s(xy, s_hint, back=1.0, ahead=4.0):
    """s_hint の近く(後ろ back m 〜 先 ahead m)で xy に一番近い道のり。道が近くを通っても飛ばない。"""
    ss = np.linspace(max(0.0, s_hint - back), min(seg[-1], s_hint + ahead), 200)
    pts = np.stack([np.interp(ss, seg, path[:, 0]), np.interp(ss, seg, path[:, 1])], 1)
    return float(ss[int(np.argmin(np.linalg.norm(pts - xy, axis=1)))])


ST = {"s": 0.0, "base": 0.0, "regen": False}


class course_controller(base_controller):
    def __init__(self, **kw):
        super().__init__("G1", **kw)
        self.done_at = None
        self.wait_i = 0
        self.wait_left = 0
        self.wait_yaw = None

    def generate_control_signals(self, viewer, mj_model, mj_data, visualize=False, control_info=None):
        pos = mj_data.qpos[:2].copy()
        ST["s"] = s = nearest_s(pos, ST["s"])
        mode, vel = "walk", None
        for m in MODES_AT:
            if s >= m[0]:
                mode, vel = m[1], m[2]
        tgt = point(min(s + LOOK, seg[-1]))
        d = tgt - pos
        fwd = point(min(s + 0.3, seg[-1])) - point(max(s - 0.3, 0))
        # 立ち止まる
        if self.wait_left == 0 and self.wait_i < len(WAITS) and s >= WAITS[self.wait_i][0]:
            self.wait_left = int(WAITS[self.wait_i][1])
            y = WAITS[self.wait_i][2]
            self.wait_yaw = None if y is None else np.radians(y)
            self.wait_i += 1
        face = d
        if self.wait_left > 0:
            self.wait_left -= 1
            mode, vel = "idle", None
            face = fwd if self.wait_yaw is None else np.array([np.cos(self.wait_yaw), np.sin(self.wait_yaw)])
            d = face * 0.0
        if np.linalg.norm(path[-1] - pos) < 0.35 or self.done_at is not None:
            mode, vel = "idle", None
            if self.done_at is None:
                self.done_at = steps
            face = path[-1] - path[-2]
            d = face * 0.0
        face = face / (np.linalg.norm(face) + 1e-6)
        dn = np.linalg.norm(d)
        mv = np.array([d[0], d[1], 0.0]) / (dn + 1e-6) if dn > 1e-6 else np.zeros(3)
        m = t.tensor([MODES.index(mode)])
        sig = {"movement_direction": t.from_numpy(mv).view([1, -1]),
               "facing_direction": t.from_numpy(np.array([face[0], face[1], 0.0])).view([1, -1]),
               "mode": m.view([1, -1])}
        if vel is not None:
            sig["target_vel"] = t.tensor([float(vel)])
        sig["allowed_pred_num_tokens"] = self.get_default_allowed_pred_num_tokens(m.item())
        ST["base"] = ground(s, HMB)
        return sig


args = SimpleNamespace(humanoid_xml="assets/skeletons/g1/scene_29dof.xml", result_dir="./out",
                       data_root="./datasets", explicit_dataset_folder=None, reprocess_clips=0,
                       controller="wasd", lookat_movement_direction=1, has_viewer=0, pre_filter_qpos=1,
                       source_root_realignment=1, target_root_realignment=1, force_canonicalization=1,
                       skip_ending_target_cond=0, random_speed_scale=0, speed_scale=[1.0, 1.0],
                       generate_dt=2.0, max_steps=MAX_STEPS, random_seed=SEED, num_runs=1, use_qpos=1,
                       planner="default", allowed_mode=None, clips="G1", recording_dir=None)
args.EXP = args.planner
demo = navigation_demo(args)
inf = demo.inferencer
demo.controller = course_controller(min_token=inf._args["min_tokens"], max_token=inf._args["max_tokens"])
FA = demo.full_agent

# ---------------------------------------------------------------- 地形の高さを目標の姿勢へ入れる
_orig_gen = FA.generate_new_frames
_orig_tgt = FA._generate_target_joint_transforms


# 目標の姿勢の関節の高さの入れ方。目標の関節の位置は 前後左右が腰から、高さは床から(学習の床は 0)なので、
# 腰だけ上げると「腰は段の上、足は下の床」という届かない姿勢を見せることになる
#   root: 腰だけ上げる(今まで) / body: 体ごと上げる / feet: 体ごと上げ、足首から先は その足の下の段の高さ、ひざはその間
TGT = arg("--tgt", "root")
# --tgt-stairs: body / feet は階段の前後だけ(飛び降りで体ごと下げると前へ倒れ込んだ)
TGT_AT = [(f["s0"] - 1.5, f["s1"] + 0.5) for f in cs.get("features", []) if f["type"] == "stairs"] \
    if "--tgt-stairs" in A else [(-1e9, 1e9)]
# 関節の高さにも先を見る分(leads)を足すか。--tgt-lead-joints 0 なら関節は目標の位置の高さのまま
LEAD_J = arg("--tgt-lead-joints", "1") != "0"
JN = None


def joint_names(n):
    for get in (lambda: FA._motion_rep.skeleton.bone_order_names, lambda: FA._converter.skeleton.bone_order_names,
                lambda: FA._inferencer.local_motion_rep.skeleton.bone_order_names):
        try:
            v = list(get())
            if len(v) == n:
                return v
        except Exception:
            pass
    from motionbricks.motionlib.core.skeletons import g1 as g1s
    for cls in (g1s.G1Skeleton34, g1s.G1Skeleton32, g1s.G1Skeleton):
        v = list(cls.bone_order_names)
        if len(v) == n:
            return v
    raise RuntimeError(f"関節の名前が見つからない({n} 個)")


def _tgt(input):
    global JN
    gjp, gjr, grp = _orig_tgt(input)
    # 目標の位置(正準の座標)を世界へ戻し、そこの地面の高さを足す。運動の座標は (x=MuJoCo y, z=MuJoCo x, y=上)
    tp = input["target_root_positions"][0].detach().cpu().numpy()      # [2(=mx, mz), 4]
    hd = float(input["first_frame_heading_angle"][0])
    ff = input["first_frame_position"][0].detach().cpu().numpy()
    c, s_ = np.cos(hd), np.sin(hd)

    def world(mx, mz):
        return np.array([c * mz - s_ * mx + ff[0], s_ * mz + c * mx + ff[1]])

    dh, dj = [], []
    for k in range(tp.shape[1]):
        st = nearest_s(world(tp[0, k], tp[1, k]), ST["s"], back=0.5, ahead=3.0)
        dh.append(ground(st + lead_at(ST["s"]), HMB) - ST["base"])
        dj.append(ground(st + (lead_at(ST["s"]) if LEAD_J else 0.0), HMB) - ST["base"])
    grp = grp.clone()
    grp[0, :, 1] += t.tensor(dh, dtype=grp.dtype, device=grp.device)
    if TGT != "root" and any(a <= ST["s"] <= b for a, b in TGT_AT):
        P = gjp[0].detach().cpu().numpy()                                # [4, J, 3]
        if JN is None:
            JN = joint_names(P.shape[1])
            print("@@ target joints", len(JN), "root xz", np.round(P[0, 0, [0, 2]], 3),
                  "y min/max", np.round(P[0, :, 1].min(), 3), np.round(P[0, :, 1].max(), 3), flush=True)
        add = np.zeros(P.shape[:2])
        for k in range(P.shape[0]):
            add[k, 1:] = dj[k]
            if TGT == "feet":
                for side in ("left", "right"):
                    ft = [j for j, nm in enumerate(JN) if nm.startswith(side) and ("ankle" in nm or "toe" in nm)]
                    kn = [j for j, nm in enumerate(JN) if nm.startswith(side) and "knee" in nm]
                    g = max(ground(nearest_s(world(tp[0, k] + P[k, j, 0], tp[1, k] + P[k, j, 2]), ST["s"],
                                             back=1.0, ahead=3.0)) for j in ft) - ST["base"]
                    add[k, ft] = g
                    add[k, kn] = (g + dh[k]) / 2
        gjp = gjp.clone()
        gjp[0, :, :, 1] += t.tensor(add, dtype=gjp.dtype, device=gjp.device)
    ST["regen"] = True
    return gjp, gjr, grp


def _gen(input, controller_dt=0.25, force_generation=False):
    base = ST["base"]
    if "context_mujoco_qpos" in input:
        input["context_mujoco_qpos"] = input["context_mujoco_qpos"].clone()
        input["context_mujoco_qpos"][:, :, 2] -= base
    ST["regen"] = False
    out = _orig_gen(input, controller_dt, force_generation)
    if ST["regen"]:
        FA.frames["mujoco_qpos"][:, :, 2] += base
    return out


FA._generate_target_joint_transforms = _tgt
FA.generate_new_frames = _gen

np.random.seed(SEED)
t.manual_seed(SEED)
FA.reset()
qs, grounds, ss = [], [], []
steps = 0
while steps < MAX_STEPS:
    steps += 1
    qpos = FA.get_next_frame()
    ctx = FA.get_context_mujoco_qpos()
    demo.mj_data.qpos[:] = qpos
    qs.append(np.array(qpos, dtype=float).copy())
    sig = demo.controller.generate_control_signals(None, demo.mj_model, demo.mj_data)
    grounds.append(ST["base"])
    ss.append(ST["s"])
    sig["context_mujoco_qpos"] = ctx
    with t.no_grad():
        FA.generate_new_frames(sig, demo.controller.get_controller_dt() * args.generate_dt)
    if demo.controller.done_at is not None and steps - demo.controller.done_at >= TAIL:
        break
    if steps % 600 == 0:
        print("@@ step", steps, "s", round(ST["s"], 2), "/", round(seg[-1], 2), flush=True)
Q = np.array(qs)
print("@@ frames", len(Q), "reached end at", demo.controller.done_at, flush=True)

# ---------------------------------------------------------------- 体の位置と向き(ゼロ姿勢と毎コマ)→ BVH(mb_maze.py と同じ)
m, d = demo.mj_model, demo.mj_data
names = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, i) for i in range(m.nbody)]


def fk(q):
    d.qpos[:] = q
    mujoco.mj_forward(m, d)
    return d.xpos.copy(), d.xmat.copy().reshape(-1, 3, 3)


# 接地合わせ(後処理): MotionBricks の腰は地形の高さより遅れて上下する(段を降りる所で宙を歩いた)。
# 立っている足(左右で水平に遅い方)の足裏が、その足の下の地面(heights)に乗るように体ごと上下させ、なめらかにする
from scipy.ndimage import gaussian_filter1d   # noqa: E402
FIT_SIGMA = float(arg("--fit-sigma", "3"))
Q0 = Q.copy()
gF = np.zeros((len(Q), 2))
SS = np.array(ss)
if "--no-fit" not in A:
    iL, iR = (names.index(f"{k}_ankle_roll_link") for k in ("left", "right"))
    XP = np.array([fk(q)[0] for q in Q])
    an = XP[:, [iL, iR]]                                   # (コマ, 2, 3)
    sole0 = an[:30, :, 2].min()                            # 立っている間の足首の高さ(平らな所)
    for f in range(len(Q)):
        for k in range(2):
            gF[f, k] = ground(nearest_s(an[f, k, :2], SS[f], back=1.5, ahead=1.5))
    clear = an[:, :, 2] - sole0 - gF                       # 足の下の地面からの高さ
    sp = np.r_[np.zeros((1, 2)), np.linalg.norm(np.diff(an[:, :, :2], axis=0), axis=2)]
    sp = gaussian_filter1d(sp, 1.5, axis=0)
    st = np.argmin(sp, axis=1)
    off = -clear[np.arange(len(Q)), st]
    # 合わせない区間(course の nofit [[s0, s1], ...]): 跳び乗る所は MotionBricks の上がり方のまま。
    # 合わせると、足が上の段に掛かった瞬間に体ごと 0.78 m 持ち上がった。区間の両端の値を直線でつなぐ
    for a, b in cs.get("nofit", []):
        idx = np.where((SS >= a) & (SS <= b))[0]
        if len(idx) > 2:
            f0, f1 = idx[0] - 1, idx[-1] + 1
            if f0 >= 0 and f1 < len(Q):
                off[idx] = np.interp(idx, [f0, f1], [off[f0], off[f1]])
    off = gaussian_filter1d(off, FIT_SIGMA)
    Q[:, 2] += off
    clear2 = clear + off[:, None]
    print("@@ fit ground: offset", round(off.min(), 3), round(off.max(), 3),
          "swing below ground (cm) min", round(clear2.min() * 100, 1),
          "frames <-3cm", int((clear2 < -0.03).any(axis=1).sum()), flush=True)


q0 = np.zeros(m.nq)
q0[3] = 1.0
q0[2] = Q[0, 2]
P0, M0 = fk(q0)
PS, MS = zip(*(fk(q) for q in Q))
PS, MS = np.array(PS), np.array(MS)
B = {n: i for i, n in enumerate(names)}
# 胴の傾き(真上からの角度)。大きいコマは姿勢が崩れている(階段の上で頭が下になった)。数字は目安で、絵で確かめる
tilt = np.degrees(np.arccos(np.clip(MS[:, B["torso_link"], 2, 2], -1, 1)))
bad = np.where(tilt > 40)[0]
print("@@ torso tilt max", round(tilt.max(), 1), "at frame", int(tilt.argmax()) + 1, "s", round(SS[tilt.argmax()], 2),
      "frames >40deg", len(bad), flush=True)

J = [("Hips", None, "pelvis", "pelvis"),
     ("Spine1", "Hips", "waist_yaw_link", "torso_link"),
     ("Chest", "Spine1", "torso_link", "torso_link")]
for s, S in (("left", "Left"), ("right", "Right")):
    J += [(f"{S}Leg", "Hips", f"{s}_hip_pitch_link", f"{s}_hip_yaw_link"),
          (f"{S}Shin", f"{S}Leg", f"{s}_knee_link", f"{s}_knee_link"),
          (f"{S}Foot", f"{S}Shin", f"{s}_ankle_pitch_link", f"{s}_ankle_roll_link")]
for s, S in (("left", "Left"), ("right", "Right")):
    J += [(f"{S}Shoulder", "Chest", f"{s}_shoulder_pitch_link", "torso_link"),
          (f"{S}Arm", f"{S}Shoulder", f"{s}_shoulder_roll_link", f"{s}_shoulder_yaw_link"),
          (f"{S}ForeArm", f"{S}Arm", f"{s}_elbow_link", f"{s}_elbow_link"),
          (f"{S}Hand", f"{S}ForeArm", f"{s}_wrist_roll_link", f"{s}_wrist_yaw_link")]
Pv = np.array([[0, 1, 0], [0, 0, 1], [1, 0, 0]], dtype=float)
sh0 = (P0[B["left_shoulder_pitch_link"]] + P0[B["right_shoulder_pitch_link"]]) / 2
pos0 = {j[0]: P0[B[j[2]]] for j in J}
pos0["Neck1"], pos0["Head"] = sh0 + np.array([0, 0, 0.06]), sh0 + np.array([0, 0, 0.16])
J += [("Neck1", "Chest", None, "torso_link"), ("Head", "Neck1", None, "torso_link")]
END = {"Head": np.array([0, 0, 0.12]), "LeftHand": None, "RightHand": None,
       "LeftFoot": np.array([0.12, 0, -0.03]), "RightFoot": np.array([0.12, 0, -0.03])}
kids = {j[0]: [k[0] for k in J if k[1] == j[0]] for j in J}
rot0 = {j[0]: M0[B[j[3]]] for j in J}
parent = {j[0]: j[1] for j in J}
body_of = dict((j[0], j[3]) for j in J)


def world_delta(f, n):
    w = MS[f][B[body_of[n]]] @ rot0[n].T
    return Pv @ w @ Pv.T


lines = ["HIERARCHY"]


def emit(n, depth):
    ind = "  " * depth
    par = parent[n]
    off = Pv @ pos0[n] if par is None else Pv @ (pos0[n] - pos0[par])
    lines.append(f"{ind}{'ROOT' if par is None else 'JOINT'} {n}")
    lines.append(ind + "{")
    lines.append(f"{ind}  OFFSET {off[0]:.6f} {off[1]:.6f} {off[2]:.6f}")
    ch = "6 Xposition Yposition Zposition Zrotation Xrotation Yrotation" if par is None else \
        "3 Zrotation Xrotation Yrotation"
    lines.append(f"{ind}  CHANNELS {ch}")
    for k in kids[n]:
        emit(k, depth + 1)
    if not kids[n]:
        e = END.get(n)
        if e is None:
            e = pos0[n] - pos0[par]
            e = e / np.linalg.norm(e) * 0.1
        e = Pv @ e
        lines.extend([f"{ind}  End Site", ind + "  {", f"{ind}    OFFSET {e[0]:.6f} {e[1]:.6f} {e[2]:.6f}",
                      ind + "  }"])
    lines.append(ind + "}")


emit("Hips", 0)
order = []


def walk(n):
    order.append(n)
    for k in kids[n]:
        walk(k)


walk("Hips")
lines += ["MOTION", f"Frames: {len(Q)}", f"Frame Time: {1 / 30:.6f}"]
root_bvh = []
for f in range(len(Q)):
    W = {n: world_delta(f, n) for n in order}
    vals = []
    for n in order:
        if parent[n] is None:
            p = Pv @ PS[f][B["pelvis"]]
            root_bvh.append(p)
            vals += list(p)
            L = W[n]
        else:
            L = W[parent[n]].T @ W[n]
        vals += list(R.from_matrix(L).as_euler("ZXY", degrees=True))
    lines.append(" ".join(f"{v:.5f}" for v in vals))
open(OUT + ".bvh", "w").write("\n".join(lines) + "\n")
np.savez(OUT + ".npz", qpos=Q, root_positions=np.array(root_bvh), body_names=np.array(names),
         xpos=PS, ground=np.array(grounds), s=np.array(ss), qpos_raw=Q0,
         foot_ground=gF)        # 左右の足の下の地面の高さ(リターゲットの接地の判定に使う)
print("@@ wrote", OUT + ".bvh", OUT + ".npz", flush=True)
