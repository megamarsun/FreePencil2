"""BVH(mb_terrain.py の書き出し)を MMD / VRM のモデルに乗せる。kimodo_tools/tools/retarget_mmd.py の写しで、
足の接地の判定だけ地形に合わせた(--foot-ground <run.npz>: 左右の足の下の地面の高さ)。元の判定は動き全体で一番低い
高さからの高さで見ていたので、階段や段の上では足がずっと宙にあると見なされて止まらなかった。

元の説明: SOMA の BVH(Kimodo の書き出し、標準 T ポーズ)を MMD のモデルに乗せる。

  blender -b <blend> --python retarget_mmd.py -- <bvh> <アーマチュア名の一部> <out.blend> [--start 1]
      [--render <dir>] [--only]

ボーンの回転を「ワールドでの変化量」で移す: 目標の姿勢 = (元の今の向き · 元の休みの向き⁻¹) · 合わせ · 目標の休みの向き。
腕だけは T ポーズと MMD の休みの姿勢(腕が下がっている)を「合わせ」で揃える。体幹と脚はどちらも立ち姿なので揃えない。
脚の IK は切り、センターを腰の動きで動かす(元の大きさは腰の高さの比で合わせる)。
"""
import math
import sys
from pathlib import Path

import addon_utils
import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

ARGV = sys.argv[sys.argv.index("--") + 1:]
BVH, KEY, OUT = ARGV[0], ARGV[1], ARGV[2]
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d  # noqa: E731
START = int(arg("--start", "1"))
RENDER = arg("--render")
# 女性らしく: 太ももの開き(横への振り)とねじり(ひざが外を向く)をこの割合に弱める。1 で元のまま
FEM = float(arg("--fem", "1.0"))
# 足を外へ開く角度(度)。脚全体を腰の前後の軸で外へ回し、足首の向きはそのまま(足裏を床に平らに)。
# MotionBricks の G1 は足を腰幅で運ぶが、アリシアに乗せると足首の間が腰幅の 2/3 まで狭まり、足が交差して見えた
STANCE = math.radians(float(arg("--stance", "0")))
# 腕を外へ開く角度(度)。腕・ひじ・手首をまとめて肩から外へ回す(手がスカートに埋まった)
ARM_OUT = math.radians(float(arg("--arm-out", "0")))
# 腕の振りの割合(1 で元のまま)。胸に対して真下へ垂らした向きとの間を取る。小さいほど振りがおとなしい
ARM_SWING = float(arg("--arm-swing", "1.0"))
# ひじを曲げて手を前へ上げる角度(度)。前腕と手をひじから体の左右の軸で回す
ELBOW = math.radians(float(arg("--elbow", "0")))
# 腰を振る: 立っている足の側の腰を上げる角度(度)と、腰をその側へ寄せる量(m、元の動きの大きさ)
SWAY = math.radians(float(arg("--sway", "0")))
SWAY_SHIFT = float(arg("--sway-shift", "0"))
# 脚も腰と一緒に倒す割合(既定 1)。脚ごと倒すと足首が横へ 9cm ほど動き、踏み替えで反対へ戻るので、
# けり出しと着地で足が左右に振れて見えた。0 なら脚の向きは元のまま、上がった側の腰の分だけ体を下げる
SWAY_LEGS = float(arg("--sway-legs", "1"))
# なで肩: 肩の骨の先を休みの姿勢でこの角度(度)だけ下げてから動きを掛ける。腕の向きは変えない
SLOPE = math.radians(float(arg("--slope", "0")))
# 手首を外へ開く: 手の先を手の甲の側へ反らせる角度(度)
WRIST = math.radians(float(arg("--wrist", "0")))
# 手を前腕にそろえる割合(0 で元の手首のまま、1 で前腕と同じ向き)。元の G1 の手首は反り・ひねりが強い
HAND_FOLLOW = float(arg("--hand-follow", "0"))
# 手のひらを胴体へ向ける割合(0〜1)。前腕ごと長さの軸まわりにひねる。休みの姿勢(T ポーズ)では手のひらが下。
# 手首だけでひねると(90 度ほど)手首の肌が絞られて細くねじれた
PALM_IN = float(arg("--palm-in", "0"))
# 親指を下げる角度(度)。付け根(親指０)を手の先の向きへ寄せる
THUMB_DOWN = math.radians(float(arg("--thumb-down", "0")))
# 指を軽く曲げる(元の骨格に指が無く、MMD の指がまっすぐ伸びたままになるため)。倍率、0 で曲げない
FINGERS = float(arg("--fingers", "1.0"))
# 髪の揺れを抑える(減衰を強める)。速い動きで髪が真横に飛ぶのを防ぐ
DAMP = "--damp" in ARGV
# 足の接地を IK で止める(元の足が低くて止まっているコマ。体の比率や --fem の違いで足がすべるのを防ぐ)
FOOTLOCK = "--footlock" in ARGV
# 足の止め方の強さ(0〜1)と、止める/離すのにかけるコマ数。強く短いと、離した瞬間に足が前へ弾かれて見えた
FOOT_STRENGTH = float(arg("--footlock-strength", "1.0"))
FOOT_RAMP = int(arg("--footlock-ramp", "3"))
# 脚の振りに合わせて腕を振る: 同じ側の太ももの前後の角度にこの倍率を掛けて逆へ振る(脚より 2 コマ遅らせる)。
# 前へ振ったときは、その角度にもう一つの倍率を掛けてひじを曲げ足す
ARM_GAIT = float(arg("--arm-gait", "0"))
ARM_GAIT_BEND = float(arg("--arm-gait-bend", "0"))
GRID = "--grid" in ARGV          # 床に方眼を置く(足の滑りと立ち位置を見るため)
FOOT_GROUND = arg("--foot-ground")    # mb_terrain.py の npz(foot_ground: コマ×左右、MuJoCo の高さ m)
# 歩きでは ひじを伸ばす: 前腕を上腕の向きへこの割合で寄せ、--elbow と --arm-gait-bend は走る時だけ効かせる。
# 走りは --foot-ground の npz の道のり s の速さで決める(1.4〜1.9 m/s で入れ替え)。歩きでひじが 90 度近く曲がって見えた
WALK_STRAIGHT = float(arg("--walk-straight", "0"))

# 目標(MMD) : (元(SOMA), 腕のように休みの姿勢を揃えるか)
MAP = {"下半身": ("Hips", False), "上半身": ("Spine1", False), "上半身2": ("Chest", False),
       "首": ("Neck1", False), "頭": ("Head", False)}
for s, S in (("L", "Left"), ("R", "Right")):
    MAP.update({f"肩.{s}": (f"{S}Shoulder", True), f"腕.{s}": (f"{S}Arm", True),
                f"ひじ.{s}": (f"{S}ForeArm", True), f"手首.{s}": (f"{S}Hand", True),
                f"足.{s}": (f"{S}Leg", False), f"ひざ.{s}": (f"{S}Shin", False),
                f"足首.{s}": (f"{S}Foot", False)})

scene = bpy.context.scene
tgt = next(o for o in bpy.data.objects if o.type == 'ARMATURE' and KEY in o.name)
tb = tgt.data.bones

# VRM のモデル: 人型の骨の対応(VRM アドオン)で MMD の骨の名前を読み替える。腰の移動はセンターの代わりに腰の骨、
# 足の IK は骨を足して付ける。揺れ物(SpringBone)は動きを付けたあとで焼き込む
VRM = {}
if "vrm_addon_extension" in tgt.data:
    _m = next(m.__name__ for m in addon_utils.modules() if m.__name__.endswith(".vrm"))
    addon_utils.enable(_m, default_set=True, persistent=False)
    hb = tgt.data.vrm_addon_extension.vrm1.humanoid.human_bones
    hn = lambda p: getattr(hb, p).node.bone_name  # noqa: E731
    VRM = {"下半身": hn("hips"), "上半身": hn("spine"), "上半身2": hn("chest"), "首": hn("neck"), "頭": hn("head")}
    for s, S in (("L", "left"), ("R", "right")):
        VRM.update({f"肩.{s}": hn(f"{S}_shoulder"), f"腕.{s}": hn(f"{S}_upper_arm"),
                    f"ひじ.{s}": hn(f"{S}_lower_arm"), f"手首.{s}": hn(f"{S}_hand"),
                    f"足.{s}": hn(f"{S}_upper_leg"), f"ひざ.{s}": hn(f"{S}_lower_leg"),
                    f"足首.{s}": hn(f"{S}_foot"), f"足ＩＫ.{s}": f"fp_foot_ik.{s}"})
        for fn, vn in (("人指", "index"), ("中指", "middle"), ("薬指", "ring"), ("小指", "little")):
            for i, part in enumerate(("proximal", "intermediate", "distal")):
                VRM[f"{fn}{'１２３'[i]}.{s}"] = hn(f"{S}_{vn}_{part}")
        for i, part in enumerate(("metacarpal", "proximal", "distal")):
            VRM[f"親指{'０１２'[i]}.{s}"] = hn(f"{S}_thumb_{part}")
    VRM = {k: v for k, v in VRM.items() if v}
    tgt.data["fp_humanoid"] = VRM          # 後の道具(build_backrooms.py)がアドオン無しで骨の名前を読む
TN = lambda n: VRM.get(n, n)  # noqa: E731
ROOT_MOVE = TN("下半身") if VRM else None       # 腰の骨そのものを動かす(VRM にセンターは無い)

MAP = {TN(k): v for k, v in MAP.items()}
if TN("上半身2") not in tb:
    MAP[TN("上半身")] = ("Chest", False)
MAP = {k: v for k, v in MAP.items() if k in tb}

# 全ての親(群舞での立ち位置)は元の動きの最初のコマのまま残す
keep = {}
if tgt.animation_data and tgt.animation_data.action:
    scene.frame_set(int(tgt.animation_data.action.frame_range[0]))
    for n in ("全ての親",):
        if n in tgt.pose.bones:
            keep[n] = tgt.pose.bones[n].matrix_basis.copy()
    tgt.animation_data.action = None
for pb in tgt.pose.bones:
    pb.matrix_basis = Matrix.Identity(4)
for n, m in keep.items():
    tgt.pose.bones[n].matrix_basis = m
for pb in tgt.pose.bones:                 # 脚の IK を切る(髪の IK はもともと切ってある)
    for c in pb.constraints:
        if c.type == 'IK' and not c.mute:
            c.mute = True
if VRM and FOOTLOCK and TN("足ＩＫ.L") not in tb:   # 足の IK の骨(親なし、足首の所)とひざの IK(切ったまま)
    bpy.context.view_layer.objects.active = tgt
    bpy.ops.object.mode_set(mode='EDIT')
    for side in ("L", "R"):
        eb = tgt.data.edit_bones.new(TN(f"足ＩＫ.{side}"))
        ft = tgt.data.edit_bones[TN(f"足首.{side}")]
        eb.head, eb.tail = ft.head.copy(), ft.head + Vector((0, 0, -0.1))
    bpy.ops.object.mode_set(mode='OBJECT')
    for side in ("L", "R"):
        c = tgt.pose.bones[TN(f"ひざ.{side}")].constraints.new('IK')
        c.target, c.subtarget, c.chain_count, c.mute = tgt, TN(f"足ＩＫ.{side}"), 2, True
    tb = tgt.data.bones

# ---------------------------------------------------------------- 元を読む
bpy.ops.import_anim.bvh(filepath=BVH, axis_forward='-Z', axis_up='Y', frame_start=START,
                        use_fps_scale=False, rotate_mode='NATIVE', global_scale=1.0)
src = bpy.context.object
sb = src.data.bones
act = src.animation_data.action
F0, F1 = int(act.frame_range[0]), int(act.frame_range[1])

tw = tgt.matrix_world
rest_t = lambda n: tw @ tb[n].matrix_local  # noqa: E731
# 向き: 元の左(LeftLeg - RightLeg)を目標の左(足.L - 足.R)にそろえる
lt = (rest_t(TN("足.L")).translation - rest_t(TN("足.R")).translation)
ls = (sb["LeftLeg"].head_local - sb["RightLeg"].head_local)
ang = math.atan2(lt.y, lt.x) - math.atan2(ls.y, ls.x)
# 大きさ: 腰の高さの比
foot_t = (rest_t(TN("足首.L")).translation.z + rest_t(TN("足首.R")).translation.z) / 2
hip_t = rest_t(TN("下半身")).translation.z - foot_t
foot_s = (sb["LeftFoot"].head_local.z + sb["RightFoot"].head_local.z) / 2
hip_s = sb["Hips"].head_local.z - foot_s
k = hip_t / hip_s
K_SCALE = k          # k は後のループの変数に上書きされる(最後の表示の scale がコマ数になっていた)
src.rotation_euler = (0, 0, ang)
src.scale = (k, k, k)
bpy.context.view_layer.update()
sw = src.matrix_world
rest_s = {n: (sw @ sb[n].matrix_local).to_3x3().normalized() for n in sb.keys()}
hips_rest = sw @ sb["Hips"].head_local


def align(tn, sn):
    """目標の骨の休みの向きを、元の骨の休みの向きへ回す最小の回転(ワールド)。"""
    dt = (rest_t(tn).to_3x3() @ Vector((0, 1, 0))).normalized()
    ds = (rest_s[sn] @ Vector((0, 1, 0))).normalized()
    return dt.rotation_difference(ds).to_matrix()


C = {tn: (align(tn, sn) if a else Matrix.Identity(3)) for tn, (sn, a) in MAP.items()}
DROP = {}
for S in ("Left", "Right"):
    d = (rest_s[f"{S}Shoulder"] @ Vector((0, 1, 0))).normalized()
    axis = d.cross(Vector((0, 0, -1))).normalized()
    DROP[f"{S}Shoulder"] = Matrix.Rotation(SLOPE, 3, axis)
    h = (rest_s[f"{S}Hand"] @ Vector((0, 1, 0))).normalized()      # T ポーズでは手の甲が上
    DROP[f"{S}Hand"] = Matrix.Rotation(WRIST, 3, h.cross(Vector((0, 0, 1))).normalized())

HAND_T = {sn: tn for tn, (sn, _) in MAP.items() if sn.endswith(("Hand", "ForeArm"))}

# 腰を振る向き: 左足で立つと +1、右足で立つと -1(元の足首の高さの差。前後 7 コマでならす)
sway_s = {}
if SWAY or SWAY_SHIFT:
    hz = []
    for f in range(F0, F1 + 1):
        scene.frame_set(f)
        hz.append((sw @ src.pose.bones["RightFoot"].head).z - (sw @ src.pose.bones["LeftFoot"].head).z)
    raw = [math.tanh(z / (0.03 * k)) for z in hz]
    for i, f in enumerate(range(F0, F1 + 1)):
        win = raw[max(0, i - 3): i + 4]
        sway_s[f] = sum(win) / len(win)

# 腕の振り: 太ももの前後の角度(元の動き、前へ +)。前後 5 コマでならし、2 コマ遅らせる
arm_gait = {}
if ARM_GAIT:
    pit = {"Left": [], "Right": []}
    for f in range(F0, F1 + 1):
        scene.frame_set(f)
        pb_ = src.pose.bones
        l_ = (sw @ pb_["LeftLeg"].head) - (sw @ pb_["RightLeg"].head)
        l_.z = 0
        fw_ = l_.normalized().cross(Vector((0, 0, 1)))
        for S in pit:
            v_ = (sw @ pb_[f"{S}Shin"].head) - (sw @ pb_[f"{S}Leg"].head)
            pit[S].append(math.atan2(v_.dot(fw_), -v_.z))
    for S, p_ in pit.items():
        sm = [sum(p_[max(0, i - 2): i + 3]) / len(p_[max(0, i - 2): i + 3]) for i in range(len(p_))]
        arm_gait[S] = [-ARM_GAIT * sm[max(0, i - 2)] for i in range(len(sm))]

# 走っている割合(コマごと、0〜1)
run_w = None
if WALK_STRAIGHT and FOOT_GROUND:
    s_ = np.load(FOOT_GROUND)["s"]
    v_ = np.convolve(np.gradient(s_) * 30, np.ones(15) / 15, "same")
    r_ = np.clip((v_ - 1.4) / 0.5, 0, 1)
    r_ = r_ * r_ * (3 - 2 * r_)
    run_w = np.convolve(np.pad(r_, 10, mode="edge"), np.ones(21) / 21, "valid")

# 目標の骨を親から順に
order = sorted(tb, key=lambda b: len(b.parent_recursive))
twi = tw.inverted()
fcu_keys = []
foot_src = {"L": [], "R": []}      # 元の足首(ワールド)
foot_tgt = {"L": [], "R": []}      # 目標の足首(骨の空間)
ik_base = {"L": [], "R": []}       # 足ＩＫの親までの姿勢(骨の空間)
for f in range(F0, F1 + 1):
    scene.frame_set(f)
    ps = {n: (sw @ src.pose.bones[n].matrix).to_3x3().normalized() for n in sb.keys()}
    hips_now = sw @ src.pose.bones["Hips"].head
    D = {n: ps[n] @ rest_s[n].inverted() for n in ps}      # ワールドでの変化量
    if FEM != 1.0:
        for S in ("Left", "Right"):
            th, sh, ft = f"{S}Leg", f"{S}Shin", f"{S}Foot"
            rel = (D["Hips"].inverted() @ D[th]).to_euler('XYZ')   # x: 前後に振る / y: 横に開く / z: ねじる
            rel.y *= FEM
            rel.z *= FEM
            new_th = D["Hips"] @ rel.to_matrix()
            new_sh = new_th @ (D[th].inverted() @ D[sh])           # ひざ・足首は太ももからの相対で付いていく
            new_ft = new_sh @ (D[sh].inverted() @ D[ft])
            D[th], D[sh], D[ft] = new_th, new_sh, new_ft
    if STANCE:
        left = D["Hips"] @ (sw.to_3x3() @ (sb["LeftLeg"].head_local - sb["RightLeg"].head_local))
        left.z = 0
        left.normalize()
        for S, out in (("Left", left), ("Right", -left)):
            rot = Matrix.Rotation(STANCE, 3, Vector((0, 0, -1)).cross(out))   # 下向きを外へ倒す回転
            D[f"{S}Leg"] = rot @ D[f"{S}Leg"]
            D[f"{S}Shin"] = rot @ D[f"{S}Shin"]
    left = D["Hips"] @ (sw.to_3x3() @ (sb["LeftLeg"].head_local - sb["RightLeg"].head_local))
    left.z = 0
    left.normalize()
    if ARM_SWING != 1.0:
        for S in ("Left", "Right"):
            a, fa, h = f"{S}Arm", f"{S}ForeArm", f"{S}Hand"
            new_a = D["Chest"].to_quaternion().slerp(D[a].to_quaternion(), ARM_SWING).to_matrix()
            new_fa = new_a @ (D[a].inverted() @ D[fa])
            new_h = new_fa @ (D[fa].inverted() @ D[h])
            D[a], D[fa], D[h] = new_a, new_fa, new_h
    if ARM_OUT:
        for S, out in (("Left", left), ("Right", -left)):
            rot = Matrix.Rotation(ARM_OUT, 3, Vector((0, 0, -1)).cross(out))
            for n in (f"{S}Arm", f"{S}ForeArm", f"{S}Hand"):
                D[n] = rot @ D[n]
    wr = 1.0
    if WALK_STRAIGHT:
        wr = float(run_w[min(f - F0, len(run_w) - 1)]) if run_w is not None else 0.0
        k_ = min(1.0, max(0.0, WALK_STRAIGHT * (1 - wr)))
        for S in ("Left", "Right"):
            a, fa, h = f"{S}Arm", f"{S}ForeArm", f"{S}Hand"
            # G1 の休みの姿勢は ひじが 90 度曲がっているので、回転でなく骨の向き(肩→ひじ、ひじ→手首)で寄せる
            up = D[a] @ (sw.to_3x3() @ (sb[fa].head_local - sb[a].head_local))
            lo = D[fa] @ (sw.to_3x3() @ (sb[h].head_local - sb[fa].head_local))
            want = lo.normalized().slerp(up.normalized(), k_) if k_ > 0 else lo.normalized()
            rot = lo.normalized().rotation_difference(want).to_matrix()
            D[fa] = rot @ D[fa]
            D[h] = rot @ D[h]
    if ELBOW and wr > 0:
        rot = Matrix.Rotation(-ELBOW * wr, 3, left)       # 下向きを前へ起こす
        for S in ("Left", "Right"):
            D[f"{S}ForeArm"] = rot @ D[f"{S}ForeArm"]
            D[f"{S}Hand"] = rot @ D[f"{S}Hand"]
    if arm_gait:
        for S in ("Left", "Right"):
            a_ = arm_gait[S][f - F0]                      # 前へ +
            rot = Matrix.Rotation(-a_, 3, left)
            for n in (f"{S}Arm", f"{S}ForeArm", f"{S}Hand"):
                D[n] = rot @ D[n]
            if ARM_GAIT_BEND and a_ > 0 and wr > 0:
                rot = Matrix.Rotation(-a_ * ARM_GAIT_BEND * wr, 3, left)
                D[f"{S}ForeArm"] = rot @ D[f"{S}ForeArm"]
                D[f"{S}Hand"] = rot @ D[f"{S}Hand"]
    if HAND_FOLLOW:
        for S in ("Left", "Right"):
            q = D[f"{S}Hand"].to_quaternion().slerp(D[f"{S}ForeArm"].to_quaternion(), HAND_FOLLOW)
            D[f"{S}Hand"] = q.to_matrix()
    if PALM_IN:
        for S, inward in (("Left", -left), ("Right", left)):
            tn, tf = HAND_T[f"{S}Hand"], HAND_T[f"{S}ForeArm"]
            ax = (D[f"{S}ForeArm"] @ C[tf] @ (rest_t(tf).to_3x3() @ Vector((0, 1, 0)))).normalized()   # ひじから手首へ
            palm = D[f"{S}Hand"] @ C[tn] @ Vector((0, 0, -1))
            want = inward - ax * inward.dot(ax)
            palm = palm - ax * palm.dot(ax)
            if want.length > 1e-4 and palm.length > 1e-4:
                ang = palm.normalized().angle(want.normalized())
                if palm.cross(want).dot(ax) < 0:
                    ang = -ang
                rot = Matrix.Rotation(ang * PALM_IN, 3, ax)
                D[f"{S}ForeArm"] = rot @ D[f"{S}ForeArm"]
                D[f"{S}Hand"] = rot @ D[f"{S}Hand"]
    if sway_s:
        s_ = sway_s[f]
        fwd = left.cross(Vector((0, 0, 1)))
        rot = Matrix.Rotation(SWAY * s_, 3, fwd)          # 左足で立つと左の腰が上がる
        D["Hips"] = rot @ D["Hips"]
        if SWAY_LEGS:
            rot_l = Matrix.Rotation(SWAY * s_ * SWAY_LEGS, 3, fwd)
            for S in ("Left", "Right"):                   # 脚は腰に付いて回り、足首の向きはそのまま
                D[f"{S}Leg"] = rot_l @ D[f"{S}Leg"]
                D[f"{S}Shin"] = rot_l @ D[f"{S}Shin"]
        hips_now = hips_now + left * (SWAY_SHIFT * k * s_)
        hips_now.z -= lt.length / 2 * math.sin(abs(SWAY * s_)) * (1 - SWAY_LEGS)   # 立ち足の腰が上がった分
    for n, m in DROP.items():
        D[n] = D[n] @ m
    pose = {}
    for b in order:
        pb = tgt.pose.bones[b.name]
        rel = (b.parent.matrix_local.inverted() @ b.matrix_local) if b.parent else b.matrix_local
        base = (pose[b.parent.name] @ rel) if b.parent else rel
        if b.name in MAP:
            sn = MAP[b.name][0]
            R = D[sn] @ C[b.name] @ rest_t(b.name).to_3x3().normalized()
            R_arm = twi.to_3x3() @ R
            want = R_arm.to_4x4()
            want.translation = base.translation
            if b.name == ROOT_MOVE:
                want.translation = base.translation + twi.to_3x3() @ (hips_now - hips_rest)
            basis = base.inverted() @ want
            if b.name != ROOT_MOVE:
                basis.translation = (0, 0, 0)
        elif b.name == "センター":
            basis = pb.matrix_basis.copy() if b.name in keep else Matrix.Identity(4)
            d = twi.to_3x3() @ (hips_now - hips_rest)
            basis = Matrix.Translation(base.to_3x3().inverted() @ d)
        elif b.name in keep:
            basis = keep[b.name]
        else:
            basis = Matrix.Identity(4)
        pose[b.name] = base @ basis
        if b.name in MAP or b.name == "センター":
            pb.matrix_basis = basis
            t = f - F0 + START
            if pb.rotation_mode == 'QUATERNION':
                pb.keyframe_insert("rotation_quaternion", frame=t, group=b.name)
            else:
                pb.keyframe_insert("rotation_euler", frame=t, group=b.name)
            if b.name in ("センター", ROOT_MOVE):
                pb.keyframe_insert("location", frame=t, group=b.name)
    for side, S_ in (("L", "Left"), ("R", "Right")):
        foot_src[side].append(sw @ src.pose.bones[f"{S_}Foot"].head)
        foot_tgt[side].append(pose[TN(f"足首.{side}")].translation.copy())
        ikb = tb.get(TN(f"足ＩＫ.{side}"))
        if ikb is not None:
            ik_base[side].append(pose[ikb.parent.name] @ (ikb.parent.matrix_local.inverted() @ ikb.matrix_local)
                                 if ikb.parent else ikb.matrix_local.copy())

# ---------------------------------------------------------------- 足の接地を IK で止める
if FOOTLOCK:
    import numpy as np
    for side in ("L", "R"):
        if not ik_base[side]:
            continue
        P = np.array([tuple(v) for v in foot_src[side]])
        g = np.zeros(len(P))
        if FOOT_GROUND:
            fg = np.load(FOOT_GROUND)["foot_ground"][:, 0 if side == "L" else 1] * K_SCALE
            g[:min(len(g), len(fg))] = fg[:len(g)]
        h = P[:, 2] - g
        # 基準は一番低いコマでなく下から 5% の高さ。足が地面に 80 cm めり込むコマが 1 つあると、ほかが全部宙と見なされた
        h = h - (np.percentile(h, 5) if FOOT_GROUND else h.min())
        v = np.r_[0, np.linalg.norm(np.diff(P[:, :2], axis=0), axis=1)] * 30      # 横の速さ m/秒
        on = (h < 0.04) & (v < 0.25)
        # 目標の足首も低いコマだけ。元の G1 は足を低く運ぶので、目標が足を上げ始めたコマまで接地と見て、
        # 上がる足を宙で引き留めて離す(床を弾くように見える)ことがあった
        T = [tuple(t) for t in foot_tgt[side]]
        hz = np.array([t[2] for t in T]) - g
        on &= hz - (np.percentile(hz, 5) if FOOT_GROUND else hz.min()) < 0.03
        # 3 コマ以下の切れ目はつなぐ(一つの接地が二つに割れると、止める位置が途中で飛んだ)
        idx = np.flatnonzero(on)
        for p_, q_ in zip(idx[:-1], idx[1:]):
            if 1 < q_ - p_ <= 4:
                on[p_:q_] = True
        # 4 コマ未満の接地は捨てる
        segs, i = [], 0
        while i < len(on):
            if on[i]:
                j = i
                while j + 1 < len(on) and on[j + 1]:
                    j += 1
                if j - i + 1 >= 4:
                    segs.append((i, j))
                i = j + 1
            else:
                i += 1
        target = [Vector(t) for t in T]
        w = np.zeros(len(T))
        acc = [[0.0, Vector()] for _ in T]       # 出入りが重なるコマは止める位置を重みで混ぜる
        for a, b in segs:
            lock = sum((Vector(T[k]) for k in range(a, b + 1)), Vector()) / (b - a + 1)
            for k in range(max(0, a - FOOT_RAMP), min(len(T), b + FOOT_RAMP + 1)):
                t_ = 1.0 if a <= k <= b else 1.0 - (min(abs(k - a), abs(k - b))) / (FOOT_RAMP + 1)
                wk = t_ * t_ * (3 - 2 * t_) * FOOT_STRENGTH       # なめらかに
                w[k] = max(w[k], wk)
                acc[k][0] += wk
                acc[k][1] += wk * Vector((lock.x, lock.y, 0))
        for k in range(len(T)):
            if acc[k][0] > 0:
                c_ = acc[k][1] / acc[k][0]
                target[k] = Vector((c_.x, c_.y, T[k][2]))   # 横だけ止める(高さは元の動きのまま)
        ik = tgt.pose.bones[TN(f"足ＩＫ.{side}")]
        knee = tgt.pose.bones[TN(f"ひざ.{side}")]
        con = next(c for c in knee.constraints if c.type == 'IK')
        con.mute = False
        for k in range(len(T)):
            fr = START + k
            base = ik_base[side][k]
            ik.location = base.to_3x3().inverted() @ (target[k] - base.translation)
            ik.keyframe_insert("location", frame=fr, group=ik.name)
            con.influence = float(w[k])
            con.keyframe_insert("influence", frame=fr)
        print("@@ footlock", side, len(segs), "contacts", int(on.sum()), "frames", flush=True)

# ---------------------------------------------------------------- 指を軽く曲げる
# 手のひら側へ。小指ほど深く曲げると力の抜けた手に見える
CURL = {"人指": (12, 20, 12), "中指": (18, 26, 14), "薬指": (24, 30, 16), "小指": (30, 34, 18)}
if FINGERS:
    for side in ("L", "R"):
        if TN(f"人指１.{side}") not in tb or TN(f"小指１.{side}") not in tb:
            continue
        ml = lambda n: tb[n].matrix_local  # noqa: E731
        across = (ml(TN(f"人指１.{side}")).translation - ml(TN(f"小指１.{side}")).translation).normalized()
        # 手のひらの向き。across を軸に回すと指が人差し指の側へ横に倒れ、手のひらが外を向いて見えた
        hb = tb[TN(f"手首.{side}")]
        hd = (hb.tail_local - hb.head_local).normalized()
        palm = hd.cross(across) if side == "L" else across.cross(hd)
        for fn, angs in CURL.items():
            for i, deg in enumerate(angs, 1):
                n = TN(f"{fn}{'１２３'[i - 1]}.{side}")
                if n not in tb:
                    continue
                d = (tb[n].tail_local - tb[n].head_local).normalized()
                axis = d.cross(palm).normalized()
                ax_l = ml(n).to_3x3().inverted() @ axis
                pb = tgt.pose.bones[n]
                pb.rotation_mode = 'QUATERNION'
                pb.rotation_quaternion = Quaternion(ax_l, math.radians(deg * FINGERS))
                pb.keyframe_insert("rotation_quaternion", frame=START, group=n)
        for i, deg in enumerate((0, 14, 16)):      # 親指は少しだけ
            n = TN(f"親指{'０１２'[i]}.{side}")
            down = THUMB_DOWN if i == 0 else 0.0
            if n not in tb or not (deg or down):
                continue
            d = (tb[n].tail_local - tb[n].head_local).normalized()
            to_l = ml(n).to_3x3().inverted()
            q = Quaternion(to_l @ d.cross(palm).normalized(), math.radians(deg * FINGERS))
            if down:
                q = Quaternion(to_l @ d.cross(hd).normalized(), down) @ q
            pb = tgt.pose.bones[n]
            pb.rotation_mode = 'QUATERNION'
            pb.rotation_quaternion = q
            pb.keyframe_insert("rotation_quaternion", frame=START, group=n)
    print("@@ fingers relaxed", FINGERS)

src.hide_viewport = src.hide_render = True
scene.frame_start, scene.frame_end = START, START + F1 - F0
if VRM:   # 揺れ物(SpringBone)を 60 回/秒で計算して、毎コマの向きをキーにする(描くときにアドオンが要らない)
    sb1 = tgt.data.vrm_addon_extension.spring_bone1
    joints = list(dict.fromkeys(j.node.bone_name for sp in sb1.springs for j in sp.joints
                                if j.node.bone_name in tgt.pose.bones))
    if joints:
        def step(n):
            sb1.enable_animation = True
            for _ in range(n):
                bpy.ops.vrm.update_spring_bone1_animation(delta_time=1 / 60)
            sb1.enable_animation = False
        scene.frame_set(START)
        step(90)                                  # 最初の姿勢で落ち着かせる
        for f in range(scene.frame_start, scene.frame_end + 1):
            scene.frame_set(f)
            step(2)
            for n in joints:
                pb = tgt.pose.bones[n]
                pb.keyframe_insert("rotation_quaternion" if pb.rotation_mode == 'QUATERNION' else "rotation_euler",
                                   frame=f, group=n)
        print("@@ spring bones baked", len(joints), "bones", flush=True)
rbw = scene.rigidbody_world
if rbw:                                   # 髪・胸の物理を新しい動きで焼き直す
    rbw.enabled = True
    rbw.point_cache.frame_start, rbw.point_cache.frame_end = START - 30, scene.frame_end
    bpy.ops.ptcache.free_bake_all()
    scene.frame_set(START - 30)
    # 剛体を今の骨の位置に置き直す(置き直さないと、胸の剛体が前の踊りの位置に残って胸が伸びた)
    mod = next(m.__name__ for m in addon_utils.modules() if m.__name__.endswith("mmd_tools"))
    addon_utils.enable(mod, default_set=False, persistent=False)
    root = tgt.parent
    while root and root.parent:
        root = root.parent
    for o in scene.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = root
    root.select_set(True)
    if DAMP:   # 髪が腕と当たらないようにする(腕を振ると髪が払われて真横へ飛んだ)
        rbs = [o for o in root.children_recursive if getattr(o, "mmd_type", "") == "RIGID_BODY"]
        armk = ("腕", "ひじ", "手", "arm", "Arm", "elbow", "Elbow", "hand", "Hand")
        hairk = ("髪", "ツイン", "テール", "もみあげ", "hair", "Hair", "tail", "Tail")
        groups = {o.mmd_rigid.collision_group_number for o in rbs if any(h in o.name for h in armk)}
        for o in rbs:
            if o.mmd_rigid.type != "0" and any(h in o.name for h in hairk):
                for g in groups:
                    o.mmd_rigid.collision_group_mask[g] = True
        print("@@ hair noarm groups", sorted(groups))
    bpy.ops.mmd_tools.clean_rig()
    bpy.ops.mmd_tools.build_rig()
    if DAMP:
        hair = ("髪", "ツイン", "テール", "もみあげ", "hair", "Hair", "tail", "Tail")
        nd = 0
        for o in root.children_recursive:
            if getattr(o, "mmd_type", "") == "RIGID_BODY" and o.rigid_body and o.mmd_rigid.type != "0" and any(h in o.name for h in hair):
                o.rigid_body.linear_damping = max(o.rigid_body.linear_damping, 0.8)
                o.rigid_body.angular_damping = max(o.rigid_body.angular_damping, 0.95)
                nd += 1
        print("@@ hair damped", nd)
    if "--only" in ARGV:   # 隠した他のモデルの剛体を物理から外す(元の踊りのまま動いていて、髪を叩いて真横へ飛ばした)
        mine = set(root.children_recursive)
        nr = 0
        for coll in (rbw.collection, rbw.constraints):
            if coll is None:
                continue
            for o in list(coll.objects):
                if o not in mine:
                    coll.objects.unlink(o)
                    nr += 1
        print("@@ removed other rigid bodies", nr)
    rbw.substeps_per_frame = 6
    with bpy.context.temp_override(scene=scene, point_cache=rbw.point_cache):
        bpy.ops.ptcache.bake(bake=True)
    print("@@ physics baked", rbw.point_cache.frame_start, rbw.point_cache.frame_end)
print("@@ retarget", tgt.name, "frames", F0, F1, "scale", round(K_SCALE, 4), "turn", round(math.degrees(ang), 1))

if "--only" in ARGV:  # 目標のモデルだけ残す
    keep_objs = {tgt} | set(tgt.children_recursive)
    for o in bpy.data.objects:
        if o.type in {'MESH', 'ARMATURE', 'EMPTY'} and o not in keep_objs and o is not src:
            o.hide_render = True
if GRID:
    import bmesh
    path = []
    for f in range(scene.frame_start, scene.frame_end + 1, 5):
        scene.frame_set(f)
        path.append(tgt.matrix_world @ tgt.pose.bones[TN("下半身")].head)
    cx = sum(p.x for p in path) / len(path)
    cy = sum(p.y for p in path) / len(path)
    half = max(3.0, max(max(abs(p.x - cx), abs(p.y - cy)) for p in path) + 2.0)
    cell = 0.5
    n = int(math.ceil(half / cell))
    half = n * cell
    me = bpy.data.meshes.new("fp_grid")
    bm = bmesh.new()
    def quad(x0, y0, x1, y1, z):
        vs = [bm.verts.new((x0, y0, z)), bm.verts.new((x1, y0, z)), bm.verts.new((x1, y1, z)), bm.verts.new((x0, y1, z))]
        return bm.faces.new(vs)
    floor_faces = [quad(cx - half, cy - half, cx + half, cy + half, 0.0)]
    w = 0.012
    line_faces = []
    for i in range(-n, n + 1):
        line_faces.append(quad(cx + i * cell - w, cy - half, cx + i * cell + w, cy + half, 0.002))
        line_faces.append(quad(cx - half, cy + i * cell - w, cx + half, cy + i * cell + w, 0.002))
    for fc in line_faces:
        fc.material_index = 1
    bm.to_mesh(me)
    bm.free()
    for name, col in (("fp_grid_floor", (0.93, 0.93, 0.9, 1)), ("fp_grid_line", (0.35, 0.38, 0.45, 1))):
        m = bpy.data.materials.new(name)
        m.diffuse_color = col
        m.use_nodes = True
        m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = col
        me.materials.append(m)
    grid = bpy.data.objects.new("fp_grid", me)
    scene.collection.objects.link(grid)
    # 腰を追うカメラ(前から少し見下ろす)。腰の位置は前後 15 コマでならして揺れを抑える
    cam_d = bpy.data.cameras.new("fp_grid_cam")
    cam_d.lens = 50
    cam = bpy.data.objects.new("fp_grid_cam", cam_d)
    scene.collection.objects.link(cam)
    hp = {}
    for f in range(scene.frame_start, scene.frame_end + 1):
        scene.frame_set(f)
        hp[f] = tgt.matrix_world @ tgt.pose.bones[TN("下半身")].head
    dist = float(arg("--cam-dist", "4.5"))
    el = math.radians(18)
    for f in hp:
        win = [hp[g] for g in range(f - 15, f + 16) if g in hp]
        c = sum(win, Vector()) / len(win)
        target = Vector((c.x, c.y, 0.85))
        cam.location = target + Vector((0, -math.cos(el), math.sin(el))) * dist
        cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)
    scene.camera = cam
    print("@@ grid", round(half * 2, 1), "m cells", cell, "cam dist", dist)
bpy.ops.wm.save_as_mainfile(filepath=str(Path(OUT).resolve()))

if RENDER:
    rd = Path(RENDER)
    rd.mkdir(parents=True, exist_ok=True)
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.color_type = 'TEXTURE'
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 1280, 720, 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = False
    for f in range(scene.frame_start, scene.frame_end + 1):
        scene.frame_set(f)
        scene.render.filepath = str(rd / f"{f:04d}.png")
        bpy.ops.render.render(write_still=True)
    print("@@ rendered", rd)
