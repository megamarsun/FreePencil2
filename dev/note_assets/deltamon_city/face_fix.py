"""顔の向き・表情・目線を整える(foot_push.py の後)。

  blender -b <previz.blend> --python face_fix.py -- <出力.blend> [--sigma 8] [--pitch-keep 0.3] [--roll-keep 0.2]

1. 頭の向きを ならす: 頭の骨の世界での向きを前後 --sigma コマの重みで平均し(歩きの左右のゆれ・首振りを取る)、
   下向きは 3 度を超えた分を --pitch-keep 倍に縮め(24 度下を向いていた所は 9 度に)、首をかしげる(横の傾き)は
   --roll-keep 倍にする。直す回転の 35% を首、残りを頭で受ける。
2. 表情: 無表情 0.6 + 笑みの口 0.4 + 困り眉 0.3(元の顔は眉がつり上がった にやり顔)。
3. まばたき: 3〜4.5 秒おきに 2 コマで閉じ 1 コマ閉じたまま 3 コマで開く。
4. 目線: 進む向きの 5 m 先・頭より 0.3 m 下を見る。頭の向きとの差を目の形のキー(LOOKUP など、1 で 25 度とみなす)で付ける。
"""
import math
import random
import sys

import bpy
import numpy as np
from mathutils import Quaternion, Vector

A = sys.argv[sys.argv.index("--") + 1:]
OUT = A[0]
arg = lambda n, d: A[A.index(n) + 1] if n in A else d   # noqa: E731
SIGMA = float(arg("--sigma", "8"))
PITCH_KEEP = float(arg("--pitch-keep", "0.3"))
ROLL_KEEP = float(arg("--roll-keep", "0.2"))
EXPR = {"NEUTRAL": 0.6, "JOY_mouth": 0.4, "SORROW_eyebrow": 0.3}
EYE_DEG = 25.0

sc = bpy.context.scene
arm = bpy.data.objects["Armature"]
act = arm.animation_data.action
F0, F1 = sc.frame_start, sc.frame_end
n = F1 - F0 + 1
P = arm.pose.bones
mw = arm.matrix_world
UP = Vector((0, 0, 1))

hidden = [o for o in sc.objects if o is not arm and not o.hide_viewport]
for o in hidden:
    o.hide_viewport = True


def key(path, i, f, v):
    c = act.fcurves.find(path, index=i) or act.fcurves.new(path, index=i, action_group=path.split('"')[1])
    c.keyframe_points.insert(f, v, options={'FAST', 'REPLACE'})


def basis(pb, M, parent_M):
    b = pb.bone
    rest = b.parent.matrix_local.inverted() @ b.matrix_local if b.parent else b.matrix_local
    return (parent_M @ rest).inverted() @ M


def face_dir(Mh):
    """頭の骨の姿勢(アーマチュアの空間)から顔の前向き(世界)。休みの姿勢で -Y を向いている"""
    b = P["head.x"].bone
    return (mw.to_3x3() @ Mh.to_3x3() @ b.matrix_local.to_3x3().inverted() @ Vector((0, -1, 0))).normalized()


# ---------------------------------------------------------------- 測る
Qh = []
Hp = np.zeros((n, 3))
for f in range(F0, F1 + 1):
    sc.frame_set(f)
    M = mw @ P["head.x"].matrix
    Qh.append(M.to_quaternion())
    Hp[f - F0] = M.translation


def qavg(qs, w):
    ref = qs[len(qs) // 2]
    acc = np.zeros(4)
    for q, wi in zip(qs, w):
        v = np.array(q)
        if np.dot(v, np.array(ref)) < 0:
            v = -v
        acc += wi * v
    return Quaternion(acc / np.linalg.norm(acc))


r = int(3 * SIGMA)
ker = np.exp(-0.5 * (np.arange(-r, r + 1) / SIGMA) ** 2)
target = []
pitch0, pitch1, roll0, roll1 = [], [], [], []
for i in range(n):
    lo, hi = max(0, i - r), min(n, i + r + 1)
    q = qavg(Qh[lo:hi], ker[lo - i + r:hi - i + r])
    m3 = q.to_matrix()
    fd = (m3 @ P["head.x"].bone.matrix_local.to_3x3().inverted() @ Vector((0, -1, 0))).normalized()
    side = fd.cross(UP).normalized()                  # 顔の右(世界、水平)
    pitch = math.asin(max(-1, min(1, -fd.z)))         # 下向きが +
    # 下向きを縮める: 横の軸まわりに上へ
    p_new = pitch if pitch <= math.radians(3) else math.radians(3) + (pitch - math.radians(3)) * PITCH_KEEP
    q = Quaternion(side, pitch - p_new) @ q
    # 横の傾き: 顔の前向きの軸まわり。頭の上(休みの +Z)が世界の上からどれだけ横へ倒れているか
    m3 = q.to_matrix()
    fd = (m3 @ P["head.x"].bone.matrix_local.to_3x3().inverted() @ Vector((0, -1, 0))).normalized()
    upv = (m3 @ P["head.x"].bone.matrix_local.to_3x3().inverted() @ Vector((0, 0, 1))).normalized()
    sd = fd.cross(UP).normalized()
    roll = math.atan2(upv.dot(sd), upv.dot(UP))
    q = Quaternion(fd, -roll * (1 - ROLL_KEEP)) @ q
    target.append(q)
    pitch0.append(math.degrees(pitch))
    pitch1.append(math.degrees(p_new))
    upo = (Qh[i].to_matrix() @ P["head.x"].bone.matrix_local.to_3x3().inverted() @ Vector((0, 0, 1)))
    fdo = face_dir(arm.matrix_world.inverted() @ Qh[i].to_matrix().to_4x4())
    roll0.append(math.degrees(math.atan2(upo.dot(fdo.cross(UP).normalized()), upo.dot(UP))))
    roll1.append(math.degrees(roll * ROLL_KEEP))
print("@@ head pitch down max", round(max(pitch0), 1), "->", round(max(pitch1), 1),
      "roll range", round(min(roll0), 1), round(max(roll0), 1), flush=True)

# ---------------------------------------------------------------- 首と頭に入れる
neck, head = P["neck.x"], P["head.x"]
inv = mw.inverted()
for f in range(F0, F1 + 1):
    sc.frame_set(f)
    i = f - F0
    Mh = mw @ head.matrix
    R = target[i] @ Mh.to_quaternion().inverted()
    Rn = Quaternion().slerp(R, 0.35)
    Mn = mw @ neck.matrix
    pn = Mn.translation.copy()
    Mn2 = Rn.to_matrix().to_4x4() @ Mn
    Mn2.translation = pn
    # 頭は首に付いて動いた後の位置、向きは目標
    Mh_follow = Mn2 @ Mn.inverted() @ Mh
    Mh2 = target[i].to_matrix().to_4x4()
    Mh2.translation = Mh_follow.translation
    q_n = basis(neck, inv @ Mn2, neck.parent.matrix).to_quaternion()
    q_h = basis(head, inv @ Mh2, inv @ Mn2).to_quaternion()
    for j in range(4):
        key('pose.bones["neck.x"].rotation_quaternion', j, f, q_n[j])
        key('pose.bones["head.x"].rotation_quaternion', j, f, q_h[j])
for c in act.fcurves:
    c.update()

# ---------------------------------------------------------------- 目線(進む向きの先)
root = np.zeros((n, 3))
for f in range(F0, F1 + 1):
    sc.frame_set(f)
    root[f - F0] = mw @ P["root.x"].head
vel = np.gradient(root, axis=0)
vel[:, 2] = 0
gk = np.exp(-0.5 * (np.arange(-30, 31) / 10.0) ** 2)
gk /= gk.sum()
vs = np.stack([np.convolve(np.pad(vel[:, k], 30, mode="edge"), gk, "valid") for k in range(3)], 1)
look = {"LOOKUP": np.zeros(n), "LOOKDOWN": np.zeros(n), "LOOKLEFT": np.zeros(n), "LOOKRIGHT": np.zeros(n)}
last = None
for f in range(F0, F1 + 1):
    i = f - F0
    sc.frame_set(f)
    Mh = mw @ head.matrix
    fd = face_dir(head.matrix)
    if np.linalg.norm(vs[i]) > 0.003:
        d = Vector(vs[i]).normalized()
        last = d
    else:
        d = last if last is not None else Vector((fd.x, fd.y, 0)).normalized()
    tgt = Mh.translation + d * 5.0 + Vector((0, 0, -0.3))
    g = (tgt - Mh.translation).normalized()
    sd = fd.cross(UP).normalized()
    up_h = sd.cross(fd)
    yaw = math.degrees(math.atan2(g.dot(sd), g.dot(fd)))          # 右が +
    pit = math.degrees(math.atan2(g.dot(up_h), g.dot(fd)))        # 上が +
    look["LOOKRIGHT"][i] = min(max(yaw / EYE_DEG, 0), 0.8)
    look["LOOKLEFT"][i] = min(max(-yaw / EYE_DEG, 0), 0.8)
    look["LOOKUP"][i] = min(max(pit / EYE_DEG, 0), 0.6)
    look["LOOKDOWN"][i] = min(max(-pit / EYE_DEG, 0), 0.6)
for k in look:
    look[k] = np.convolve(np.pad(look[k], 6, mode="edge"), np.ones(13) / 13, "valid")      # 目は なめらかに

# ---------------------------------------------------------------- まばたき
blink = np.zeros(n)
random.seed(3)
f = 20
while f < n - 8:
    for k, v in enumerate((0.5, 1.0, 1.0, 0.66, 0.33)):
        blink[f + k] = max(blink[f + k], v)
    f += random.randint(90, 135)

# ---------------------------------------------------------------- 形のキーに書く
for o in sc.objects:
    if o.type != 'MESH' or not o.data.shape_keys:
        continue
    kb = o.data.shape_keys.key_blocks
    o.data.shape_keys.animation_data_clear()
    for name, v in EXPR.items():
        if name in kb:
            kb[name].value = v
    for name, arr in list(look.items()) + [("BLINK1_L", blink), ("BLINK1_R", blink)]:
        if name not in kb:
            continue
        for f in range(F0, F1 + 1):
            v = float(arr[f - F0])
            if f > F0 and abs(v - float(arr[f - F0 - 1])) < 1e-4 and abs(v - float(arr[min(n - 1, f - F0 + 1)])) < 1e-4:
                continue
            kb[name].value = v
            kb[name].keyframe_insert("value", frame=f)
    print("@@ shape keys", o.name, [k for k in list(EXPR) + list(look) + ["BLINK1_L"] if k in kb], flush=True)

for o in hidden:
    o.hide_viewport = False
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("@@ wrote", OUT, flush=True)
