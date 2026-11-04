"""ひざのガタつきを探す: 通しで もも・ひざ・足首の位置を取って npz に書く。

  blender -b <city.blend> --python knee_scan.py -- <out.npz> [--start 1] [--end 5400] [--fk]

--fk はひざの IK を切って もう一度取る(ガタつきが IK から来るのか元の動きから来るのかを分ける)。
"""
import sys

import bpy
import numpy as np

A = sys.argv[sys.argv.index("--") + 1:]
arg = lambda n, d=None: A[A.index(n) + 1] if n in A else d   # noqa: E731
OUT = A[0]
F0, F1 = int(arg("--start", "1")), int(arg("--end", "5400"))
sc = bpy.context.scene
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE" and "Armature" in o.name)
HUM = arm.data["fp_humanoid"]
TN = lambda n: HUM.get(n, n)  # noqa: E731
pbs = arm.pose.bones


def grab(fk):
    cons = [c for s in "LR" for c in pbs[TN(f"ひざ.{s}")].constraints if c.type == "IK"]
    old = [c.mute for c in cons]
    if fk:
        for c in cons:
            c.mute = True
    P, W, H = [], [], []
    for f in range(F0, F1 + 1):
        sc.frame_set(f)
        mw = arm.matrix_world
        row = []
        for s in "LR":
            for n in ("足", "ひざ", "足首"):
                row.append(tuple(mw @ pbs[TN(f"{n}.{s}")].head))
            row.append(tuple(mw @ pbs[TN(f"足首.{s}")].tail))
        P.append(row)
        W.append([c.influence for c in cons])
        H.append(np.array(mw @ pbs[TN("下半身")].matrix))
    for c, m in zip(cons, old):
        c.mute = m
    return np.array(P), np.array(W), np.array(H)


P, W, H = grab(False)
d = dict(frames=np.arange(F0, F1 + 1), P=P, W=W, H=H)
if "--fk" in A:
    d["P_fk"] = grab(True)[0]
np.savez(OUT, **d)
print("@@ saved", OUT, P.shape, flush=True)
