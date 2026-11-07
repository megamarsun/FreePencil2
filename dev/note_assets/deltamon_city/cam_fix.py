"""ショットのカメラを横へ寄せる(手すりの柱・手すりがレンズの前に来るのを避ける)。

  blender -b <previz.blend> --python cam_fix.py -- <出力.blend> --shot S10 --lat 0.55

build_city.py のカメラは キャラの腰 + 前・左・上のずれ(shots.json の o0→o1)。S10 は左 1.6 m で手すりの線の上を走り、
柱・手すりに 12 cm まで寄って画面を ふさいだ(2880・2937)。腰の進む向き(前後 ±15 コマで ならす)から左を出し、
カメラの左のずれを --lat m にして、向きは 腰 + 上 0.2 m(ならし 4 コマ。build_city.py と同じ)を見るように付け直す。
"""
import sys

import bpy
import numpy as np
from mathutils import Vector

A = sys.argv[sys.argv.index("--") + 1:]
OUT = A[0]
arg = lambda n, d: A[A.index(n) + 1] if n in A else d   # noqa: E731
SHOT = arg("--shot", "S10")
LAT = float(arg("--lat", "0.55"))
LOOK_UP = float(arg("--look-up", "0.2"))


def smooth(a, s):
    r = int(3 * s)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / s) ** 2)
    k /= k.sum()
    p = np.pad(a, ((r, r), (0, 0)), mode="edge")
    return np.stack([np.convolve(p[:, i], k, mode="valid") for i in range(a.shape[1])], 1)


sc = bpy.context.scene
arm = bpy.data.objects["Armature"]
mks = sorted([m for m in sc.timeline_markers if m.camera], key=lambda m: m.frame)
i = [m.name for m in mks].index(SHOT)
f0 = mks[i].frame
f1 = (mks[i + 1].frame - 1) if i + 1 < len(mks) else sc.frame_end
cam = mks[i].camera
fr = list(range(f0 - 15, f1 + 16))
H, C = [], []
for f in fr:
    sc.frame_set(f)
    H.append(tuple(arm.matrix_world @ arm.pose.bones["root.x"].head))
    C.append(tuple(cam.matrix_world.translation))
H, C = np.array(H), np.array(C)
V = np.gradient(smooth(H, 15), axis=0)
fw = V.copy()
fw[:, 2] = 0
fw /= np.linalg.norm(fw, axis=1, keepdims=True) + 1e-9
lf = np.stack([-fw[:, 1], fw[:, 0], np.zeros(len(fw))], 1)
lat = np.einsum("ij,ij->i", C - H, lf)
newC = C - lf * (lat - LAT * np.sign(lat))[:, None]
look = smooth(H + np.array([0, 0, LOOK_UP]), 4)
fc = cam.animation_data.action.fcurves
for c in [c for c in fc if c.data_path in ("location", "rotation_euler")]:
    for j in reversed(range(len(c.keyframe_points))):
        if f0 <= c.keyframe_points[j].co[0] <= f1:
            c.keyframe_points.remove(c.keyframe_points[j])
    if len(c.keyframe_points):
        c.update()
for k, f in enumerate(fr):
    if not f0 <= f <= f1:
        continue
    p, tg = Vector(newC[k]), Vector(look[k])
    cam.location = p
    cam.rotation_euler = (tg - p).to_track_quat("-Z", "Y").to_euler()
    cam.keyframe_insert("location", frame=f)
    cam.keyframe_insert("rotation_euler", frame=f)
print("@@ moved", SHOT, f0, f1, "lat", round(float(lat[15]), 2), "->", LAT, flush=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("@@ wrote", OUT, flush=True)
