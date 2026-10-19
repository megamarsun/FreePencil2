"""v2.9 デモのキャラの場面: anime-girl を回り込みで撮る。3D → STEP0 だけの線画 → 手直しの後の線画 → セル。

  blender -b --factory-startup --python girl_orbit.py -- <girl_clean.blend> <out_dir>
          [--frames 585] [--res 3840] [--yaw 18] [--ranges model:1-135,step0:100-252,fixed:220-370,cel:340-585]
          [--only 1,293,585]

手直しは girl_4k_states.py と同じ(殻を切る・目のまわりを merge・ボタンは服の絵の線・日は正面から)。
目とボタンの四角は、カメラが正面(回り込みの真ん中)にあるコマで選ぶ(選んだ面は形に残るので、
回り込んでもそのまま効く)。日はカメラについて行く(カメラの向きから 25° 上・左へ 15°)。
"""
import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:]
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d   # noqa: E731
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "batch"))
import fp_batch                                   # noqa: E402
fp_batch.install_addon()
import bpy                                        # noqa: E402
from mathutils import Matrix, Vector              # noqa: E402

SRC, OUT = Path(ARGV[0]).resolve(), Path(ARGV[1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
N = int(arg("--frames", "585"))
RES = int(arg("--res", "3840"))
YAW = float(arg("--yaw", "18"))
ONLY = [int(v) for v in arg("--only", "").split(",") if v]
RANGES = {}
for item in arg("--ranges", "model:1-135,step0:100-252,fixed:220-370,cel:340-585").split(","):
    k, r = item.split(":")
    a_, b_ = (int(x) for x in r.split("-"))
    RANGES[k] = list(range(a_, b_ + 1))

bpy.ops.wm.open_mainfile(filepath=str(SRC))
sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = RES, RES * 9 // 16
sc.render.fps = 30
sc.frame_start, sc.frame_end = 1, N
sc.eevee.taa_render_samples = int(arg("--samples", "32"))
cam = sc.camera
sun = bpy.data.objects["Sun"]
arm = bpy.data.objects["Armature"]
bpy.context.view_layer.update()
# 回る中心: カメラの視線上で、首にいちばん近い点
neck = arm.matrix_world @ arm.pose.bones["mixamorig:Neck"].head
c0 = cam.matrix_world.translation.copy()
fwd = (cam.matrix_world.to_3x3() @ Vector((0, 0, -1))).normalized()
target = c0 + fwd * (neck - c0).dot(fwd)
rel = (c0 - target) * float(arg("--back", "1.10"))   # 少し引く(頭の上が切れていた)
rot0 = cam.matrix_world.to_3x3()
for f in range(1, N + 1):
    u = (f - 1) / max(1, N - 1)
    u = u * u * (3 - 2 * u)
    yaw = math.radians(-YAW + 2 * YAW * u)
    R = Matrix.Rotation(yaw, 3, "Z")
    cam.location = target + R @ rel
    m = R @ rot0
    cam.rotation_euler = m.to_euler()
    cam.keyframe_insert("location", frame=f)
    cam.keyframe_insert("rotation_euler", frame=f)
    sun.rotation_euler = (m @ Matrix.Rotation(math.radians(25), 3, "X")
                          @ Matrix.Rotation(math.radians(-15), 3, "Y")).to_euler()
    sun.keyframe_insert("rotation_euler", frame=f)
MID = (N + 1) // 2
sc.frame_set(MID)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "girl_orbit.blend"))
fp = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.ai"))


def shoot(mode):
    d = OUT / mode
    d.mkdir(exist_ok=True)
    for f in (ONLY or RANGES[mode]):
        p = d / f"{f:04d}.png"
        if p.exists() and "--resume" in ARGV:
            continue
        sc.frame_set(f)
        sc.render.filepath = str(p)
        bpy.ops.render.render(write_still=True)
    sc.frame_set(MID)
    print("@@@ seq", mode, flush=True)


fp.preview("NONE")
keep = sc.render.use_compositing
sc.render.use_compositing = False
shoot("model")
sc.render.use_compositing = keep
fp.auto("WEIGHTED")                              # 4K なので 2倍レンダは auto() が切る
fp.preview("WHITE")
shoot("step0")
fp.shells()
fp.merge({"objects": ["Face"], "rect": (0.39, 0.33, 0.51, 0.49)})
fp.texture_lines({"objects": ["Clothes"], "rect": (0.40, 0.62, 0.50, 0.84)}, strength=0.3)
fp.preview("WHITE")
shoot("fixed")
fp.cel(threshold=0.25)
shoot("cel")
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "girl_orbit_fp.blend"))
print("@@@ done", flush=True)
