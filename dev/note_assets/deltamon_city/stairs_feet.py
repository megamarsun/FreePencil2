"""階段と道を横切るパイプの所だけ、足を置き直す。腰の高さも両足から決め直す。

  blender -b <city.blend> --python stairs_feet.py -- <course_final.json> <run.npz> <出力.blend> [--only stairs|pipe_x]

MotionBricks には階段を坂として見せているので、足は段に合っていない(段にめり込む・段の角に乗る・
振り出しで足を後ろに蹴り上げる)。そこで階段の区間だけ:
  1. 足の運びを腰の進みから決め直す: 左右で踏み面を 1 段ずつ交互に使い、腰が踏み面の 0.17 m 手前に来たら
     下ろし、0.30 m 過ぎたら上げる。足の裏が丸ごと踏み面に乗る位置に置く(MotionBricks の足の止まり方は
     階段ではすべったり沈んだりして、接地の見分けに使えなかった)
  2. 接地と接地の間は、先に上へ上げてから前へ運ぶ(ひざが前に出る)。段の角より上を通す
  3. 腰の高さは高い方の足+立った時の腰の高さ。足が届かない高さにはしない
  4. 上半身の前かがみを 15 度までに戻す
  5. 足の向き: 左右の振り(つま先の開き)はもとの動きのまま、前後と横の傾きを消して足の裏を踏み面に平らに。
     振り出しの間だけ つま先を少し上げて段の角をよける(足首の回転はすねに対する値なので、IK ですねが
     変わると足も一緒に傾いていた)
  パイプ(pipe_x)も同じ仕組みで、パイプの手前・上・先に 1 歩ずつ下ろす(足場はパイプの所で 0.25 m の箱に
  なっているので、縁石のように一度乗る)。上を越える足は真上で足の裏が 0.06 m 空く山にする(MotionBricks には 0.12 m のなだらかな山として見せているので、足がパイプに埋まっていた)。
  腰は着いている足の高さに乗せる
  段・パイプをよける持ち上げは、出る時・着く時に 0 になる形にする(足の的が着く・離れる 1 コマで跳ぶと、ひざが跳ねた)
  6. ひざは IK に任せず、もも・すねの角度を自分で解く(2 本の骨の三角形)。ひざは必ず道の前の側に出す
     (ひざの IK には向きの的が無く、もとの動きで すねを後ろへ振っている所では ひざが逆に曲がった)
地形は City_Root の下にある MuJoCo の座標。build_city.py の後に回す。
"""
import json
import math
import sys

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

A = sys.argv[sys.argv.index("--") + 1:]
C = json.load(open(A[0], encoding="utf-8"))
S = np.load(A[1])["s"]
OUT = A[2]
HEEL, TOE = 0.07, 0.17        # 足首から かかと / つま先 まで(MuJoCo の m)
LIFT = 0.08                   # 振り出しで段の角の上に空ける高さ
PAD = 8                       # 前後でもとの動きへつなぐコマ数
LAND_AHEAD = 0.17             # 足は腰より この分 先の踏み面に下ろし
LIFT_BEHIND = 0.30            # 腰が この分 過ぎたら上げる(片足で 2 段ずつ、左右で 1 段ずつ)
HALF_W = 0.09                 # 道の真ん中から左右の足まで
LEAN = 15.0                   # 上半身の前かがみの上限(度)
TOE_UP = 12.0                 # 振り出しの真ん中でつま先を上げる角度(度)。着いている間は足の裏を踏み面に平らに

path = np.array(C["path"])
seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
sc = bpy.context.scene
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE" and "Armature" in o.name)
HUM = arm.data["fp_humanoid"]
TN = lambda n: HUM.get(n, n)  # noqa: E731
M = bpy.data.objects["City_Root"].matrix_world.copy()
Mi = M.inverted()
SCL = M.to_scale()[0]
AW = arm.matrix_world.copy()
AWi = AW.inverted()
START = 1


def pt(s):
    return np.array([np.interp(s, seg, path[:, 0]), np.interp(s, seg, path[:, 1])])


def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def gauss(a, sig):
    r = int(3 * sig)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sig) ** 2)
    k /= k.sum()
    return np.convolve(np.pad(a, r, mode="edge"), k, mode="valid")


# 休みの姿勢の長さ(MuJoCo の m に直す)
bl = arm.data.bones
osc = AW.to_scale()[0]
rest = lambda n: bl[TN(n)].head_local * osc  # noqa: E731
ANK = (rest("足首.L").z + rest("足首.R").z) / 2 / SCL
HIP_UP = (rest("下半身").z - (rest("足.L").z + rest("足.R").z) / 2) / SCL
LEG = ((rest("足.L") - rest("足首.L")).length) / SCL
STAND = (rest("下半身").z - (rest("足首.L").z + rest("足首.R").z) / 2) / SCL
print("@@ rest ankle", round(ANK, 3), "leg", round(LEG, 3), "stand", round(STAND, 3), flush=True)

# 階段をまとめる(踊り場をはさむ 2 本は 1 区間)。道を横切るパイプも続けて並ぶものを 1 区間に
groups = []
for kind, key in (("stairs", "s0"), ("pipe_x", "s")):
    fs_ = sorted([f for f in C["features"] if f["type"] == kind], key=lambda f: f[key])
    gk = []
    for f in fs_:
        if kind == "pipe_x":
            # 足場はパイプの所で上の高さの箱になっている(heights)。その幅を使う
            hw = max([abs(k[0] - f["s"]) for k in C["heights"]
                      if abs(k[0] - f["s"]) < 0.5 and abs(k[1] - f["h"] - f["top"]) < 1e-4] or [f["r"]])
            f = dict(f, s0=f["s"] - hw, s1=f["s"] + hw, h0=f["h"], h1=f["h"])
        if gk and f["s0"] - gk[-1][-1]["s1"] < 3.0:
            gk[-1].append(f)
        else:
            gk.append([f])
    groups += [(kind, g) for g in gk]
PIPE_CLEAR = 0.04             # パイプの手前と先に下ろす足の裏とパイプの間
SLOPE = 2.0                   # 振り出す足が段をよける高さの、段からの離れ具合による下がり(m/m)

ikb = {s: arm.pose.bones[TN(f"足ＩＫ.{s}")] for s in "LR"}
knee_ik = {s: next(c for c in arm.pose.bones[TN(f"ひざ.{s}")].constraints if c.type == "IK") for s in "LR"}
ankle = {s: arm.pose.bones[TN(f"足首.{s}")] for s in "LR"}
thigh = {s: arm.pose.bones[TN(f"足.{s}")] for s in "LR"}
shin = {s: arm.pose.bones[TN(f"ひざ.{s}")] for s in "LR"}
L_TH = {s: (shin[s].bone.head_local - thigh[s].bone.head_local).length for s in "LR"}   # アーマチュアの単位
L_SH = {s: (ankle[s].bone.head_local - shin[s].bone.head_local).length for s in "LR"}
hipb = arm.pose.bones[TN("下半身")]
neck = arm.pose.bones[TN("首")]
spine = arm.pose.bones.get(TN("上半身"))
chest = arm.pose.bones.get(TN("上半身2"))
fc = arm.animation_data.action.fcurves


def fval(path_, idx, f):
    cu = fc.find(path_, index=idx)
    return cu.evaluate(f) if cu else 0.0


ONLY = A[A.index("--only") + 1] if "--only" in A else None      # 試し用: stairs か pipe_x だけ
arg = lambda n, d: float(A[A.index(n) + 1]) if n in A else d    # noqa: E731
STAND_K = arg("--stand", 0.97)    # 腰の高さ = 着いている足 + 立った時の腰の高さ × これ
REACH_K = arg("--reach", 0.97)    # 足が届く長さ = 脚の長さ × これ
HEEL_MAX = math.radians(arg("--heel", 0.0))   # 後ろの足のかかとを上げてよい角度。0 なら上げない(腰を両足で抑える)
BALL = 0.12                       # 足首から つま先の付け根(かかとを上げる時に曲がる所)まで
for kind, grp in [g for g in groups if ONLY in (None, g[0])]:
    s_ref = grp[0]["s0"]
    p0 = pt(s_ref)
    t = pt(grp[-1]["s1"]) - p0
    t /= np.linalg.norm(t)
    n = np.array([-t[1], t[0]])
    # 踏み面: (始め, 終わり, 高さ)。手前と先の床も入れる。パイプは上の高さの箱として入れる(足を通さない所)
    tr = [(s_ref - 5.0, s_ref, grp[0]["h0"])]
    for f in grp:
        if tr[-1][1] < f["s0"]:
            tr.append((tr[-1][1], f["s0"], f["h0"]))      # 踊り場・パイプの間の床
        if kind == "pipe_x":
            tr.append((f["s0"], f["s1"], f["h"] + f["top"]))
            continue
        run = (f["s1"] - f["s0"]) / f["n"]
        rise = (f["h1"] - f["h0"]) / f["n"]
        for k in range(f["n"]):
            tr.append((f["s0"] + k * run, f["s0"] + (k + 1) * run, f["h0"] + (k + 1) * rise))
    tr.append((grp[-1]["s1"], grp[-1]["s1"] + 5.0, grp[-1]["h1"]))

    def ground_max(s0_, s1_):
        return max(h for a, b, h in tr if b > s0_ and a < s1_)

    def ground_soft(s0_, s1_):
        """足の裏 [s0_, s1_] の下と近くの高さ。離れた段ほど SLOPE で低く見る(段の縁で的が段差に跳ばない)。"""
        return max(h - SLOPE * max(a - s1_, s0_ - b, 0.0) for a, b, h in tr)

    sA, sB = grp[0]["s0"] - 0.9, grp[-1]["s1"] + 0.7
    fa = int(np.searchsorted(np.maximum.accumulate(S), sA)) + START
    fb = int(np.searchsorted(np.maximum.accumulate(S), sB)) + START
    frames = list(range(fa - PAD, fb + PAD + 1))
    # もとの動き(足の IK を切った FK)の足首と腰を読む
    for s_ in "LR":
        knee_ik[s_].mute = True
    raw = {s_: [] for s_ in "LR"}
    hip_raw = []
    for fr in frames:
        sc.frame_set(fr)
        for s_ in "LR":
            raw[s_].append(Mi @ (AW @ ankle[s_].head))
        hip_raw.append(Mi @ (AW @ hipb.head))
    for s_ in "LR":
        knee_ik[s_].mute = False

    def to_line(v):
        d = np.array([v.x, v.y]) - p0
        return s_ref + d @ t, d @ n, v.z

    def from_line(s, lat, z):
        xy = p0 + t * (s - s_ref) + n * lat
        return Vector((xy[0], xy[1], z))

    # 足の置き場(踏み面の真ん中)を道のり順に並べる。手前と先の床・踊り場にも同じ間隔で置く
    slots = []
    if kind == "pipe_x":
        # パイプの手前・上・先に 1 歩ずつ(縁石のように上に一度乗る)。そのほかは 0.38 m おき(手前の間は 0.19〜0.57 m)。
        # 上をひとまたぎにすると歩幅が 0.8 m を超え、脚が届くように腰が沈んでひざまずいたように見えた
        half = (TOE + HEEL) / 2 + PIPE_CLEAR
        x = grp[0]["s0"] - half - 12 * 0.38
        for f in grp:
            a = f["s0"] - half
            while x < a - 0.19:
                slots.append((x, f["h"]))
                x += 0.38
            slots += [(a, f["h"]), (f["s"], f["h"] + f["top"]), (f["s1"] + half, f["h"])]
            x = f["s1"] + half + 0.38
        slots += [(x + m * 0.38, grp[-1]["h"]) for m in range(12)]
    else:
        for m in range(12, 0, -1):
            slots.append((s_ref - 0.19 - (m - 1) * 0.38, grp[0]["h0"]))
        prev = None
        for f in grp:
            if prev is not None:                       # 踊り場
                k_ = max(1, round((f["s0"] - prev["s1"]) / 0.38))
                sp_ = (f["s0"] - prev["s1"]) / k_
                slots += [(prev["s1"] + sp_ * (m + 0.5), prev["h1"]) for m in range(k_)]
            run = (f["s1"] - f["s0"]) / f["n"]
            rise = (f["h1"] - f["h0"]) / f["n"]
            slots += [(f["s0"] + (k + 0.5) * run, f["h0"] + (k + 1) * rise) for k in range(f["n"])]
            prev = f
        slots += [(grp[-1]["s1"] + 0.19 + m * 0.38, grp[-1]["h1"]) for m in range(12)]
    # 腰の進み(道のり)。待ちで止まる所は足も止まる
    Hs = np.maximum.accumulate(gauss(np.array([to_line(v)[0] for v in hip_raw]), 2.0))
    Hl = gauss(np.array([to_line(v)[1] for v in hip_raw]), 8.0)

    def when(sv):
        """腰が道のり sv に着くコマ(frames の添字、小数)。"""
        i_ = int(np.searchsorted(Hs, sv))
        if i_ <= 0:
            return -1e9
        if i_ >= len(Hs):
            return 1e9
        a_, b_ = Hs[i_ - 1], Hs[i_]
        return i_ - 1 + (sv - a_) / max(b_ - a_, 1e-6)

    tgt = {}
    swing = {}                     # 振り出しの進み sin(πu)。着いている間は 0
    support = {}
    for side, par, sgn in (("L", 0, 1), ("R", 1, -1)):
        mine = slots[par::2]
        land = [when(c - LAND_AHEAD) for c, h in mine]
        lift = [when(c + LIFT_BEHIND) for c, h in mine]
        out = []
        sw = []
        sup = []                   # 腰を乗せる高さ(振り出しの間は出た所と着く所の低い方)
        for k in range(len(frames)):
            cur = None
            w_ = 0.0
            sup_ = None
            for q, (c, h) in enumerate(mine):
                if land[q] <= k <= lift[q]:
                    lk = int(min(max(land[q], 0), len(frames) - 1))
                    cur = (c - (TOE - HEEL) / 2, Hl[lk] + sgn * HALF_W, h + ANK)
                    break
                if q + 1 < len(mine) and lift[q] < k < land[q + 1]:
                    u = (k - lift[q]) / (land[q + 1] - lift[q])
                    (ca, ha), (cb, hb) = mine[q], mine[q + 1]
                    sa_, sb_ = ca - (TOE - HEEL) / 2, cb - (TOE - HEEL) / 2
                    za, zb = ha + ANK, hb + ANK
                    def swing_at(u):
                        """振り出しの u での (道のり, 高さ)。高さは段・パイプをよける前の物。"""
                        if kind == "pipe_x":       # パイプ: 前へは早めに運び終え、後半で下ろす
                            hs = smooth((u - 0.15) / 0.45)
                        else:
                            hs = smooth((u - 0.2) / 0.8)
                        sp = sa_ + (sb_ - sa_) * hs
                        if zb > za + 0.02:          # 上る: 先に上げてから前へ(ひざが前に出る)
                            z = za + (zb - za) * smooth(u / 0.6)
                        else:
                            z = za + (zb - za) * hs
                        return sp, z + LIFT * math.sin(math.pi * u)

                    sp, z = swing_at(u)
                    if kind == "pipe_x":
                        # パイプの段の上を通る間は足の裏を 0.06 m 空ける。足りない分を、出る時・着く時に 0 になる
                        # なだらかな山(plat)で全体に足す。振り出しは 7 コマほどしか無いので、終わりの 2 割だけで
                        # 0 に戻すと着く 1 コマ前でまだ高く、着いた 1 コマで足の的が 0.2 m 落ちて ひざが跳ねた。
                        # 上げるのは早く、下ろすのは振り出しの後半を全部使う(短いと 2 コマで脚が伸びきった)
                        def plat(u_):
                            return smooth(u_ / 0.25) * smooth((1 - u_) / 0.5)

                        extra = 0.0
                        for j in range(1, 40):
                            uj = j / 40
                            pj = plat(uj)
                            if pj < 0.02:
                                continue
                            sj, zj = swing_at(uj)
                            need = ground_max(sj - HEEL, sj + TOE) + ANK + 0.06 * pj - zj
                            extra = max(extra, need / pj)
                        z += extra * plat(u)
                    else:
                        # 段に近づくにつれて上げ、真上で足の裏が 0.03 m 空く。出る時・着く時は 0 にする
                        env = smooth(min(u, 1 - u) / 0.2)
                        floor = ground_soft(sp - HEEL, sp + TOE) + ANK + 0.03
                        z += max(0.0, floor - z) * env
                    cur = (sp, Hl[k] + sgn * HALF_W, z)
                    w_ = math.sin(math.pi * u)
                    sup_ = min(za, zb)
                    break
            if cur is None:
                cur = out[-1] if out else to_line(raw[side][k])
            out.append(cur)
            sw.append(w_)
            sup.append(cur[2] if sup_ is None else sup_)
        tgt[side] = out
        swing[side] = sw
        support[side] = sup
        print("@@", kind, round(s_ref, 2), side, "steps", sum(0 <= x <= len(frames) for x in land), flush=True)

    # 腰の高さ: 届かない高さにはしない
    H = np.array([to_line(v) for v in hip_raw])
    # 高い方の足に立つ高さ。後ろの足が低くても腰は沈ませない(平均にすると一段ごとに腰が沈んだ)
    # パイプでは振り出す足を高く上げるので、腰は着いている足の高さに乗せる(上げた足に釣られて腰が浮かない)
    src = support if kind == "pipe_x" else {s_: [p[2] for p in tgt[s_]] for s_ in "LR"}
    zh = np.array([max(src["L"][k], src["R"][k]) + STAND * STAND_K for k in range(len(frames))])
    reach = lambda dh: math.sqrt(max((REACH_K * LEG) ** 2 - dh * dh, 0.01))  # noqa: E731
    for k in range(len(frames)):
        for s_ in "LR":
            fs, fl, fz = tgt[s_][k]
            if HEEL_MAX > 0 and swing[s_][k] > 0:
                continue                          # 振り出している足は ひざを曲げればよい。腰を抑えない
            # 腰より後ろの着いている足は、かかとを上げて足首が上がる分だけ届く
            up_ = BALL * math.sin(HEEL_MAX) if fs < H[k, 0] else 0.0
            dh = math.hypot(fs - H[k, 0], fl - H[k, 1])
            zh[k] = min(zh[k], fz + up_ + HIP_UP + reach(dh))
    cap = zh.copy()
    zh = gauss(zh, 3.0)
    # ならした後にもう一度 届く高さで抑える(ならすと抑えた所の前後で腰が上がり、足が届かず脚が伸びきった)
    zh = np.minimum(zh, gauss(cap, 1.5))
    # かかと上げ: 後ろの着いている足の足首を、腰から届く高さまで つま先の付け根を中心に持ち上げる。
    # 振り出しに入ったら少しずつ戻す(足が離れる 1 コマで足首が落ちないように)
    heel = {s_: np.zeros(len(frames)) for s_ in "LR"}
    if HEEL_MAX > 0:
        for s_ in "LR":
            hr = heel[s_]
            for k in range(len(frames)):
                fs, fl, fz = tgt[s_][k]
                if swing[s_][k] > 0:
                    hr[k] = hr[k - 1] * 0.6 if k else 0.0
                elif fs < H[k, 0]:
                    dh = math.hypot(fs - H[k, 0], fl - H[k, 1])
                    hr[k] = min(max(zh[k] - HIP_UP - reach(dh) - fz, 0.0), BALL * math.sin(HEEL_MAX))
            heel[s_] = np.maximum(hr, gauss(hr, 1.5))
            for k in range(len(frames)):
                th = math.asin(min(heel[s_][k] / BALL, 1.0))
                fs, fl, fz = tgt[s_][k]
                tgt[s_][k] = (fs + BALL * (1 - math.cos(th)), fl, fz + heel[s_][k])
        print("@@", kind, "heel up max", {s_: round(float(heel[s_].max()), 3) for s_ in "LR"}, flush=True)
    if "--debug" in A:
        for k in range(0, len(frames), 12):
            fr = frames[k]
            print("@@ dbg", fr, "S", round(float(S[fr - START]), 2), "hip", np.round(H[k], 2), "zh", round(zh[k], 2),
                  "rawL", np.round(to_line(raw["L"][k]), 2), "tgtL", np.round(tgt["L"][k], 2), flush=True)

    for k, fr in enumerate(frames):
        r = smooth(min(fr - (fa - PAD), (fb + PAD) - fr) / PAD) if (fr < fa or fr > fb) else 1.0
        sc.frame_set(fr)
        # 腰
        dz = (zh[k] - H[k, 2]) * r
        Mp = hipb.matrix.copy()
        Mp.translation += AWi.to_3x3() @ (M.to_3x3() @ Vector((0, 0, dz)))
        basis = arm.convert_space(pose_bone=hipb, matrix=Mp, from_space='POSE', to_space='LOCAL')
        hipb.location = basis.translation
        hipb.keyframe_insert("location", frame=fr, group=hipb.name)
        # 足の IK
        for s_ in "LR":
            pb = ikb[s_]
            base = pb.bone.matrix_local
            old = Vector([fval(f'pose.bones["{pb.name}"].location', i, fr) for i in range(3)])
            old_arm = base.translation + base.to_3x3() @ old
            new_arm = AWi @ (M @ from_line(*tgt[s_][k]))
            p = old_arm.lerp(new_arm, r)
            pb.location = base.to_3x3().inverted() @ (p - base.translation)
            pb.keyframe_insert("location", frame=fr, group=pb.name)
            con = knee_ik[s_]
            path_ = f'pose.bones["{TN("ひざ." + s_)}"].constraints["{con.name}"].influence'
            w0 = fc.find(path_).evaluate(fr) if fc.find(path_) else 0.0
            con.influence = w0 * (1 - r) + r
            con.keyframe_insert("influence", frame=fr)
    fw_w = (M.to_3x3() @ Vector((t[0], t[1], 0))).normalized()
    # ひざ: IK を切り、もも・すねを三角形で解く。ひざは道の前の側(向きの的が無い IK は逆に曲がることがあった)
    fw_a = (AWi.to_3x3() @ fw_w).normalized()

    def aim(pb, head, to, r):
        """ボーンの向き(Y)を head→to へ最小の回しで向け、もとの回転と r で混ぜてキーを打つ。"""
        Rc = pb.matrix.to_3x3()
        Rn = Rc.to_quaternion().copy()
        Rn.rotate(Rc.col[1].normalized().rotation_difference((to - head).normalized()))
        Mp = Rn.to_matrix().to_4x4()
        Mp.translation = head
        basis = arm.convert_space(pose_bone=pb, matrix=Mp, from_space='POSE', to_space='LOCAL')
        q_old = pb.rotation_quaternion.copy()
        pb.rotation_quaternion = q_old.slerp(basis.to_quaternion(), r)
        pb.keyframe_insert("rotation_quaternion", frame=fr, group=pb.name)
        bpy.context.view_layer.update()

    flipped = 0
    for k, fr in enumerate(frames):
        r = smooth(min(fr - (fa - PAD), (fb + PAD) - fr) / PAD) if (fr < fa or fr > fb) else 1.0
        sc.frame_set(fr)
        for s_ in "LR":
            Hh = thigh[s_].head.copy()
            if (shin[s_].head - (Hh + ankle[s_].head) / 2) @ fw_a < 0:
                flipped += 1                      # IK の答えで ひざが後ろに出ていたコマ
            T = AWi @ (M @ from_line(*tgt[s_][k]))
            l1, l2 = L_TH[s_], L_SH[s_]
            dv = T - Hh
            d = min(max(dv.length, abs(l1 - l2) + 1e-4), (l1 + l2) * 0.9999)
            u = dv.normalized()
            a_ = (l1 * l1 - l2 * l2 + d * d) / (2 * d)
            h_ = math.sqrt(max(l1 * l1 - a_ * a_, 0.0))
            pp = (fw_a - u * (fw_a @ u)).normalized()
            K = Hh + u * a_ + pp * h_
            con = knee_ik[s_]
            path_ = f'pose.bones["{TN("ひざ." + s_)}"].constraints["{con.name}"].influence'
            w0 = fc.find(path_).evaluate(fr) if fc.find(path_) else 0.0
            con.influence = w0 * (1 - r)
            con.keyframe_insert("influence", frame=fr)
            bpy.context.view_layer.update()
            aim(thigh[s_], Hh, K, r)
            aim(shin[s_], shin[s_].head.copy(), Hh + u * d, r)
    print("@@ knees flipped by IK (frames x legs)", flipped, flush=True)
    # 上半身の前かがみを LEAN まで戻す(MotionBricks の上り方は頭が下がるほど腰を折る)
    right_w = fw_w.cross(Vector((0, 0, 1))).normalized()
    right_a = (AWi.to_3x3() @ right_w).normalized()
    lean_max = 0.0
    for k, fr in enumerate(frames):
        r = smooth(min(fr - (fa - PAD), (fb + PAD) - fr) / PAD) if (fr < fa or fr > fb) else 1.0
        sc.frame_set(fr)
        v = AW @ neck.head - AW @ hipb.head
        pitch = math.atan2(v @ fw_w, v.z)
        lean_max = max(lean_max, math.degrees(pitch))
        c = max(0.0, pitch - math.radians(LEAN)) * r
        for pb, part in ((spine, 0.6), (chest, 0.4)):
            if pb is None or c <= 0:
                continue
            Mp = pb.matrix.copy()
            hd = Mp.translation.copy()
            R = Matrix.Translation(hd) @ Matrix.Rotation(c * part, 4, right_a) @ Matrix.Translation(-hd)
            basis = arm.convert_space(pose_bone=pb, matrix=R @ Mp, from_space='POSE', to_space='LOCAL')
            if pb.rotation_mode == 'QUATERNION':
                pb.rotation_quaternion = basis.to_quaternion()
                pb.keyframe_insert("rotation_quaternion", frame=fr, group=pb.name)
            else:
                pb.rotation_euler = basis.to_euler(pb.rotation_mode)
                pb.keyframe_insert("rotation_euler", frame=fr, group=pb.name)
            bpy.context.view_layer.update()
    # 足の向き: 休みの姿勢(足の裏が床に平ら)に、もとの動きの左右の振りだけを掛ける
    up_a = (AWi.to_3x3() @ Vector((0, 0, 1))).normalized()
    tilt_max = 0.0
    for k, fr in enumerate(frames):
        r = smooth(min(fr - (fa - PAD), (fb + PAD) - fr) / PAD) if (fr < fa or fr > fb) else 1.0
        sc.frame_set(fr)
        for s_ in "LR":
            pb = ankle[s_]
            R0 = pb.bone.matrix_local.to_3x3()
            Rc = pb.matrix.to_3x3()
            q = (Rc @ R0.inverted()).to_quaternion()
            ax = Vector(q[1:]).project(up_a)
            twist = Quaternion((q.w, ax.x, ax.y, ax.z)).normalized()
            tilt_max = max(tilt_max, math.degrees(q.rotation_difference(twist).angle))
            flat = twist.to_matrix() @ R0
            fwd = flat @ Vector((0, 1, 0))            # ボーンの向き(足首 → つま先の付け根)
            right = fwd.cross(up_a).normalized()
            th = math.asin(min(heel[s_][k] / BALL, 1.0))     # かかと上げ(つま先を下げる向き)
            Rd = Matrix.Rotation(math.radians(TOE_UP) * swing[s_][k] - th, 3, right) @ flat
            Mp = Rd.to_4x4()
            Mp.translation = pb.matrix.translation
            basis = arm.convert_space(pose_bone=pb, matrix=Mp, from_space='POSE', to_space='LOCAL')
            q_old = pb.rotation_quaternion.copy()
            pb.rotation_quaternion = q_old.slerp(basis.to_quaternion(), r)
            pb.keyframe_insert("rotation_quaternion", frame=fr, group=pb.name)
    print("@@", kind, "group", round(s_ref, 2), "frames", fa, fb, "lean max before", round(lean_max, 1),
          "foot tilt max before", round(tilt_max, 1), flush=True)

bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("@@ saved", OUT, flush=True)
