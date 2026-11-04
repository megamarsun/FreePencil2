"""ひざのガタつきを取る: 脚の IK を切り、通しで もも・すねを三角形で解き直す(ソフト IK)。

  blender -b <city.blend> --python knee_soft.py -- <出力.blend> [--start 1] [--end 5400] [--soft 0.015]

stairs_feet.py の後に回す。ガタつきの元は 3 つあった:
  1. 脚が伸びきる所: 足首の的が届かないと ひざが一直線(3 度)に張り付き、届いた瞬間に折れる(V の字の折れ目)
  2. 足の接地の IK(retarget_terrain.py --footlock)は向きの的が無く、効き(influence)を上げ下げする所で
     FK と IK の回転が混ざって ひざが揺れる
  3. 階段・パイプの足の的が着く・離れる 1 コマで跳ぶ(これは stairs_feet.py 側で直した)
ここでは 1 と 2 を直す:
  - 足首の的 = FK の足首と IK の的を効きで混ぜた位置(位置で混ぜる。回転で混ぜない)
  - ひざの向き = FK のひざの向き(股関節-足首の線から ひざへ)を 1.5 コマでならし、前へ少し寄せる
    (脚が伸びている所で向きが決まらず、後ろへ回らないように)。後ろ向きの分は消す
  - 届く長さはソフト IK: 脚の長さ L の (1 - soft) を超えたら指数で L に近づける(伸びきって張り付かない)
  - 足の向きは FK のまま(世界での向きを保つ。足首の回転はすねに対する値なので、すねを動かすと足が傾く)
"""
import math
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

A = sys.argv[sys.argv.index("--") + 1:]
arg = lambda n, d=None: A[A.index(n) + 1] if n in A else d   # noqa: E731
OUT = A[0]
SOFT = float(arg("--soft", "0.015"))
BIAS = 0.05                   # ひざを前へ寄せる量(m)。曲がっている所では FK の向きがずっと大きい
sc = bpy.context.scene
F0, F1 = int(arg("--start", sc.frame_start)), int(arg("--end", sc.frame_end))
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE" and "Armature" in o.name)
HUM = arm.data["fp_humanoid"]
TN = lambda n: HUM.get(n, n)  # noqa: E731
AW = arm.matrix_world.copy()
AWi = AW.inverted()
osc = AW.to_scale()[0]
fc = arm.animation_data.action.fcurves
SIDES = "LR"
thigh = {s: arm.pose.bones[TN(f"足.{s}")] for s in SIDES}
shin = {s: arm.pose.bones[TN(f"ひざ.{s}")] for s in SIDES}
ankle = {s: arm.pose.bones[TN(f"足首.{s}")] for s in SIDES}
ikb = {s: arm.pose.bones[TN(f"足ＩＫ.{s}")] for s in SIDES}
con = {s: next(c for c in shin[s].constraints if c.type == "IK") for s in SIDES}
for s in SIDES:
    assert shin[s].parent == thigh[s] and ankle[s].parent == shin[s], "脚の骨の親子が想定と違う"
L1 = {s: (shin[s].bone.head_local - thigh[s].bone.head_local).length for s in SIDES}
L2 = {s: (ankle[s].bone.head_local - shin[s].bone.head_local).length for s in SIDES}
frames = list(range(F0, F1 + 1))
N = len(frames)


def infl(s, f):
    cu = fc.find(f'pose.bones["{shin[s].name}"].constraints["{con[s].name}"].influence')
    return cu.evaluate(f) if cu else con[s].influence


# 1 回目: IK を切った FK の姿勢と、IK の的・効きを読む
for s in SIDES:
    con[s].mute = True
rec = {s: dict(H=np.zeros((N, 3)), K=np.zeros((N, 3)), A=np.zeros((N, 3)), T=np.zeros((N, 3)), w=np.zeros(N),
               Mth=[], Msh=[], Mft=[], Mpar=[]) for s in SIDES}
for i, f in enumerate(frames):
    sc.frame_set(f)
    for s in SIDES:
        r = rec[s]
        r["H"][i], r["K"][i], r["A"][i] = thigh[s].head, shin[s].head, ankle[s].head
        r["T"][i] = ikb[s].head
        r["w"][i] = infl(s, f)
        r["Mth"].append(thigh[s].matrix.copy())
        r["Msh"].append(shin[s].matrix.copy())
        r["Mft"].append(ankle[s].matrix.copy())
        r["Mpar"].append(thigh[s].parent.matrix.copy())
    if i % 600 == 0:
        print("@@ read", f, flush=True)


def gauss(a, sig):
    r = int(3 * sig)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sig) ** 2)
    k /= k.sum()
    return np.stack([np.convolve(np.pad(a[:, j], r, mode="edge"), k, mode="valid") for j in range(a.shape[1])], 1)


# 前の向き(アーマチュアの座標): 上 × 右。ひざは平均すると前に出るので、その向きで符号を決める
up = np.array(AWi.to_3x3() @ Vector((0, 0, 1)))
up /= np.linalg.norm(up)
right = rec["R"]["H"] - rec["L"]["H"]
fw = np.cross(up, right)
fw /= np.linalg.norm(fw, axis=1)[:, None]
if np.mean([((rec[s]["K"] - rec[s]["H"]) * fw).sum(1).mean() for s in SIDES]) < 0:
    fw = -fw
fw = gauss(fw, 4.0)
fw /= np.linalg.norm(fw, axis=1)[:, None]

sol = {}
for s in SIDES:
    r = rec[s]
    D = r["A"] + (r["T"] - r["A"]) * r["w"][:, None]          # 足首の的(位置で混ぜる)
    dv = D - r["H"]
    d = np.linalg.norm(dv, axis=1)
    u = dv / d[:, None]
    L = L1[s] + L2[s]
    sw = SOFT * L
    da = L - sw
    d2 = np.where(d > da, da + sw * (1 - np.exp(-(d - da) / sw)), d)
    d2 = np.clip(d2, abs(L1[s] - L2[s]) + 1e-4, L * 0.9999)
    # ひざの向き
    p = r["K"] - r["H"]
    p -= u * (p * u).sum(1)[:, None]
    pf = (p * fw).sum(1)
    p -= fw * np.minimum(pf, 0)[:, None]                     # 後ろ向きの分は消す
    p += fw * (BIAS / osc)
    p = gauss(p, 1.5)
    p -= u * (p * u).sum(1)[:, None]
    p /= np.linalg.norm(p, axis=1)[:, None]
    a_ = (L1[s] ** 2 - L2[s] ** 2 + d2 ** 2) / (2 * d2)
    h_ = np.sqrt(np.maximum(L1[s] ** 2 - a_ ** 2, 0))
    K = r["H"] + u * a_[:, None] + p * h_[:, None]
    An = r["H"] + u * d2[:, None]
    sol[s] = (K, An)
    short = (d - d2) * osc * 100
    straight = (d > da).sum()
    print(f"@@ {s} soft frames {straight}  ankle short of target max {short.max():.1f} cm  p99 {np.percentile(short, 99):.1f} cm"
          f"  IK on {(r['w'] > 0.01).sum()}", flush=True)


def aim(Mold, head, frm, to):
    """Mold(ポーズの座標の行列)を、head→frm の向きが head→to になるよう最小の回しで回した行列(位置は head)。
    ボーンの Y でなく子の付け根への向きで合わせる(ひざ・足首の付け根は親のボーンの Y の上に無い)。"""
    R = Mold.to_3x3().normalized()
    q = R.to_quaternion()
    q.rotate((frm - head).normalized().rotation_difference((to - head).normalized()))
    M_ = q.to_matrix().to_4x4()
    M_.translation = head
    return M_


def basis(pb, Mpose, Mparent):
    """親のポーズの行列から、ボーンのローカルの回転(四元数)を出す。"""
    off = pb.parent.bone.matrix_local.inverted() @ pb.bone.matrix_local
    return ((Mparent @ off).inverted() @ Mpose).to_quaternion()


# 2 回目: もも・すね・足首の回転を打ち直す
prev = {}
for s in SIDES:
    r = rec[s]
    K, An = sol[s]
    for i, f in enumerate(frames):
        Hh, Kn, Aa = Vector(r["H"][i]), Vector(K[i]), Vector(An[i])
        Mth = aim(r["Mth"][i], Hh, Vector(r["K"][i]), Kn)
        # すねは、ももを回した後の付け根の位置で、もとの すね→足首 の向きを回して合わせる
        Rd = Mth.to_3x3() @ r["Mth"][i].to_3x3().normalized().inverted()
        Msh0 = (Rd @ r["Msh"][i].to_3x3().normalized()).to_4x4()
        Msh0.translation = Kn
        Msh = aim(Msh0, Kn, Kn + Rd @ (Vector(r["A"][i]) - Vector(r["K"][i])), Aa)
        Mft = r["Mft"][i].to_3x3().normalized().to_4x4()
        Mft.translation = Aa
        for pb, Mp, Mpar in ((thigh[s], Mth, r["Mpar"][i]), (shin[s], Msh, Mth), (ankle[s], Mft, Msh)):
            q = basis(pb, Mp, Mpar)
            if pb.name in prev and prev[pb.name].dot(q) < 0:
                q.negate()
            prev[pb.name] = q
            pb.rotation_quaternion = q
            pb.keyframe_insert("rotation_quaternion", frame=f, group=pb.name)
    con[s].mute = True
print("@@ keyed", len(frames), "frames", flush=True)

# 確かめ: いくつかのコマで、打った回転から出るひざ・足首が解いた位置に来ているか
err = 0.0
for i in range(0, N, max(1, N // 12)):
    sc.frame_set(frames[i])
    for s in SIDES:
        K, An = sol[s]
        err = max(err, (shin[s].head - Vector(K[i])).length * osc, (ankle[s].head - Vector(An[i])).length * osc)
print(f"@@ check max error {err * 100:.2f} cm", flush=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("@@ saved", OUT, flush=True)
