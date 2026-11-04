"""階段の区間だけ、MotionBricks の足を一番近い踏み面へ置く(足の運び・腰の進み・上半身は MotionBricks のまま)。

  blender -b <city.blend> --python tread_snap.py -- <course_final.json> <run.npz> <出力.blend>

mb_terrain.py --tgt body --tgt-stairs で作った動き用。MotionBricks は段の位置を知らないので、
足は段にめり込んだり段の角に掛かったりする。stairs_feet.py のように足の運びを作り直すのでなく、ずらすだけ:
  1. 着いている間(足の接地の IK の効きが 0.5 以上)は、足の裏が丸ごと乗る踏み面へ前後にずらし、高さを踏み面に合わせる
  2. 振り出しの間は、前の接地のずれから次の接地のずれへ なめらかにつなぎ、段の角より上を通す
  3. 腰は両足のずれの高さの平均だけ上下させる(脚の長さを MotionBricks のままに保つ)。足が届かない高さにはしない
  4. 着いている間は足の裏を踏み面に平らに(左右の振りは元のまま)
ひざは後の knee_soft.py で解く(この後に必ず回す)。stairs_feet.py --only pipe_x の後に回す。
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
PAD = 8                       # 前後でもとの動きへつなぐコマ数
CLEAR = 0.03                  # 振り出しで段の角の上に空ける高さ
SLOPE = 2.0
START = 1

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
osc = AW.to_scale()[0]
bl = arm.data.bones
rest = lambda n: bl[TN(n)].head_local * osc  # noqa: E731
ANK = (rest("足首.L").z + rest("足首.R").z) / 2 / SCL
HIP_UP = (rest("下半身").z - (rest("足.L").z + rest("足.R").z) / 2) / SCL
LEG = ((rest("足.L") - rest("足首.L")).length) / SCL
print("@@ rest ankle", round(ANK, 3), "leg", round(LEG, 3), flush=True)

ikb = {s: arm.pose.bones[TN(f"足ＩＫ.{s}")] for s in "LR"}
shin = {s: arm.pose.bones[TN(f"ひざ.{s}")] for s in "LR"}
ankle = {s: arm.pose.bones[TN(f"足首.{s}")] for s in "LR"}
thigh = {s: arm.pose.bones[TN(f"足.{s}")] for s in "LR"}
con = {s: next(c for c in shin[s].constraints if c.type == "IK") for s in "LR"}
hipb = arm.pose.bones[TN("下半身")]
fc = arm.animation_data.action.fcurves


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


def infl(s, f):
    cu = fc.find(f'pose.bones["{shin[s].name}"].constraints["{con[s].name}"].influence')
    return cu.evaluate(f) if cu else con[s].influence


def fval(path_, idx, f):
    cu = fc.find(path_, index=idx)
    return cu.evaluate(f) if cu else 0.0


# 階段をまとめる(踊り場をはさむ 2 本は 1 区間)
st_ = sorted([f for f in C["features"] if f["type"] == "stairs"], key=lambda f: f["s0"])
groups = []
for f in st_:
    if groups and f["s0"] - groups[-1][-1]["s1"] < 3.0:
        groups[-1].append(f)
    else:
        groups.append([f])

for grp in groups:
    s_ref = grp[0]["s0"]
    p0 = pt(s_ref)
    t = pt(grp[-1]["s1"]) - p0
    t /= np.linalg.norm(t)
    n = np.array([-t[1], t[0]])
    # 踏み面 (始め, 終わり, 高さ)。手前と先の床・踊り場も入れる
    tr = [(s_ref - 5.0, s_ref, grp[0]["h0"])]
    for f in grp:
        if tr[-1][1] < f["s0"]:
            tr.append((tr[-1][1], f["s0"], f["h0"]))
        run = (f["s1"] - f["s0"]) / f["n"]
        rise = (f["h1"] - f["h0"]) / f["n"]
        for k in range(f["n"]):
            tr.append((f["s0"] + k * run, f["s0"] + (k + 1) * run, f["h0"] + (k + 1) * rise))
    tr.append((grp[-1]["s1"], grp[-1]["s1"] + 5.0, grp[-1]["h1"]))

    def ground_soft(s0_, s1_):
        return max(h - SLOPE * max(a - s1_, s0_ - b, 0.0) for a, b, h in tr)

    def to_line(v):
        d = np.array([v.x, v.y]) - p0
        return np.array([s_ref + d @ t, d @ n, v.z])

    def from_line(q):
        xy = p0 + t * (q[0] - s_ref) + n * q[1]
        return Vector((xy[0], xy[1], q[2]))

    sA, sB = grp[0]["s0"] - 0.9, grp[-1]["s1"] + 0.7
    fa = int(np.searchsorted(np.maximum.accumulate(S), sA)) + START
    fb = int(np.searchsorted(np.maximum.accumulate(S), sB)) + START
    frames = list(range(fa - PAD, fb + PAD + 1))
    N = len(frames)
    ramp = np.array([smooth(min(fr - (fa - PAD), (fb + PAD) - fr) / PAD) if (fr < fa or fr > fb) else 1.0
                     for fr in frames])
    # 今の足首(FK の足首と接地の IK の的を効きで位置で混ぜた物。knee_soft.py と同じ)と腰
    for s_ in "LR":
        con[s_].mute = True
    D = {s_: np.zeros((N, 3)) for s_ in "LR"}
    W = {s_: np.zeros(N) for s_ in "LR"}
    Hp = np.zeros((N, 3))
    for i, fr in enumerate(frames):
        sc.frame_set(fr)
        for s_ in "LR":
            a_ = AW @ ankle[s_].head
            T_ = AW @ ikb[s_].head
            W[s_][i] = w_ = infl(s_, fr)
            D[s_][i] = to_line(Mi @ (a_ + (T_ - a_) * w_))
        Hp[i] = to_line(Mi @ (AW @ hipb.head))
    for s_ in "LR":
        con[s_].mute = False

    tgt = {}
    stance = {}
    for s_ in "LR":
        # 着いている = 接地の IK が効いている、か、横にほとんど動いていない(しゃがんで両足をそろえた所は
        # 接地の IK が切れていて、振り出し扱いで段の角の上へ持ち上げ、体ごと宙に浮かせた)
        v = np.r_[0, np.linalg.norm(np.diff(D[s_][:, :2], axis=0), axis=1)] * 30
        on = (W[s_] > 0.5) | (gauss(v, 1.0) < 0.35)
        for _ in range(2):                       # 2 コマ以下の切れ目・接地はならす
            on[1:-1] = np.where(on[:-2] == on[2:], on[:-2], on[1:-1])
        segs, i = [], 0
        while i < N:
            if on[i]:
                j = i
                while j + 1 < N and on[j + 1]:
                    j += 1
                segs.append((i, j))
                i = j + 1
            else:
                i += 1
        corr = np.zeros((N, 3))
        have = np.zeros(N, bool)
        for a, b in segs:
            sm = D[s_][a:b + 1, 0].mean()
            # 足の裏 [sm-HEEL, sm+TOE] に掛かる踏み面のうち、今の足の高さに一番近い物へ。はみ出す分だけ前後にずらす
            # (一番重なる物にすると、段の縁に掛かった足を 1 段上へ持ち上げて宙に浮かせた)
            zm = D[s_][a:b + 1, 2].mean() - ANK
            cand = [q for q in tr if min(q[1], sm + TOE) - max(q[0], sm - HEEL) > 0.0]
            best = min(cand, key=lambda q: abs(q[2] - zm))
            lo, hi = best[0] + HEEL + 0.01, best[1] - TOE - 0.01
            sn = min(max(sm, lo), hi) if lo <= hi else (best[0] + best[1]) / 2 - (TOE - HEEL) / 2
            for k in range(a, b + 1):
                corr[k] = np.array([sn, D[s_][k, 1], best[2] + ANK]) - D[s_][k]
                corr[k, 1] = 0.0
                have[k] = True
        # 振り出しの間: 前後の接地のずれを なめらかにつなぐ(区間の端は 0 へ)
        idx = np.flatnonzero(have)
        out = D[s_].copy()
        sw = np.zeros(N)
        for k in range(N):
            if have[k]:
                out[k] += corr[k]
                continue
            prv = idx[idx < k]
            nxt = idx[idx > k]
            ca, ka = (corr[prv[-1]], prv[-1]) if len(prv) else (np.zeros(3), 0)
            cb, kb = (corr[nxt[0]], nxt[0]) if len(nxt) else (np.zeros(3), N - 1)
            u = (k - ka) / max(kb - ka, 1)
            out[k] += ca + (cb - ca) * smooth(u)
            sw[k] = math.sin(math.pi * u)
            # 段の角より上を通す(出る時・着く時は 0)
            env = smooth(min(u, 1 - u) / 0.2)
            floor = ground_soft(out[k, 0] - HEEL, out[k, 0] + TOE) + ANK + CLEAR
            out[k, 2] += max(0.0, floor - out[k, 2]) * env
        tgt[s_] = out
        stance[s_] = 1.0 - sw
        print("@@ group", round(s_ref, 1), s_, "contacts", len(segs),
              "snap dz cm min/max", round(corr[have, 2].min() * 100, 1), round(corr[have, 2].max() * 100, 1),
              "ds cm max", round(np.abs(corr[have, 0]).max() * 100, 1), flush=True)

    if "--debug" in A:
        for k in range(0, N, 3):
            print("@@ dbg", frames[k], "hip", np.round(Hp[k], 3), *[f"{s_} D {np.round(D[s_][k], 3)} tgt "
                  f"{np.round(tgt[s_][k], 3)} w {W[s_][k]:.2f} st {stance[s_][k]:.2f}" for s_ in "LR"], flush=True)
    # 腰: 両足のずれの高さの平均だけ上下させ、届かない高さにはしない
    dz = (tgt["L"][:, 2] - D["L"][:, 2] + tgt["R"][:, 2] - D["R"][:, 2]) / 2
    zh = Hp[:, 2] + gauss(dz, 3.0)
    for k in range(N):
        for s_ in "LR":
            dh = math.hypot(tgt[s_][k, 0] - Hp[k, 0], tgt[s_][k, 1] - Hp[k, 1])
            zh[k] = min(zh[k], tgt[s_][k, 2] + HIP_UP + math.sqrt(max((0.995 * LEG) ** 2 - dh * dh, 0.01)))
    zh = np.minimum(gauss(zh, 2.0), zh + 0.005)

    for k, fr in enumerate(frames):
        r = ramp[k]
        sc.frame_set(fr)
        Mp = hipb.matrix.copy()
        Mp.translation += AWi.to_3x3() @ (M.to_3x3() @ Vector((0, 0, (zh[k] - Hp[k, 2]) * r)))
        hipb.location = arm.convert_space(pose_bone=hipb, matrix=Mp, from_space='POSE', to_space='LOCAL').translation
        hipb.keyframe_insert("location", frame=fr, group=hipb.name)
        for s_ in "LR":
            pb = ikb[s_]
            base = pb.bone.matrix_local
            old = Vector([fval(f'pose.bones["{pb.name}"].location', i, fr) for i in range(3)])
            old_arm = base.translation + base.to_3x3() @ old
            new_arm = AWi @ (M @ from_line(tgt[s_][k]))
            # 区間の中は効きを 1 にして的 = 置き直した足首。前後のつなぎは的も効きも元へ戻す
            pb.location = base.to_3x3().inverted() @ (old_arm.lerp(new_arm, r) - base.translation)
            pb.keyframe_insert("location", frame=fr, group=pb.name)
            con[s_].influence = W[s_][k] * (1 - r) + r
            con[s_].keyframe_insert("influence", frame=fr)

    # 足の向き: 着いている間は足の裏を平らに(左右の振りは元のまま)
    up_a = (AWi.to_3x3() @ Vector((0, 0, 1))).normalized()
    for k, fr in enumerate(frames):
        sc.frame_set(fr)
        for s_ in "LR":
            pb = ankle[s_]
            R0 = pb.bone.matrix_local.to_3x3()
            Rc = pb.matrix.to_3x3()
            q = (Rc @ R0.inverted()).to_quaternion()
            ax = Vector(q[1:]).project(up_a)
            twist = Quaternion((q.w, ax.x, ax.y, ax.z)).normalized()
            Mp = (twist.to_matrix() @ R0).to_4x4()
            Mp.translation = pb.matrix.translation
            flat = arm.convert_space(pose_bone=pb, matrix=Mp, from_space='POSE', to_space='LOCAL').to_quaternion()
            q_old = pb.rotation_quaternion.copy()
            pb.rotation_quaternion = q_old.slerp(flat, ramp[k] * stance[s_][k])
            pb.keyframe_insert("rotation_quaternion", frame=fr, group=pb.name)
    print("@@ group", round(s_ref, 1), "frames", fa, fb, flush=True)

bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("@@ saved", OUT, flush=True)
