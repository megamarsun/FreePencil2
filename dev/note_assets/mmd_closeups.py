"""4 体のダンスの、キャラごとの顔のアップ(胸から上)を撮る。カメラは頭を追う(動きはならす)。

  blender -b --factory-startup --python mmd_closeups.py -- <dir> [--frames 300-449] [--res 1920] [--mode cel]

<dir>/Four_dance_fp.blend(FreePencil を当てた後)を開き、<dir>/Four_close<k>_<mode>/ に連番を書く。
各キャラのカメラで、線の強弱のしきい値を測り直す(カメラを変えたら測る)。
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "batch"))
import fp_batch                                   # noqa: E402
fp_batch.install_addon()
import bpy                                        # noqa: E402
from mathutils import Matrix, Vector              # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:]
D = Path(ARGV[0]).resolve()
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d   # noqa: E731
F0, F1 = (int(x) for x in arg("--frames", "300-449").split("-"))
RES = int(arg("--res", "1920"))
MODE = arg("--mode", "cel")
bpy.ops.wm.open_mainfile(filepath=str(D / "Four_dance_fp.blend"))
sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = RES, RES * 9 // 16
sc.fp_supersample = True                        # 1920 は 2倍レンダで細い線(anime-girl で決めた)
fp = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.ai"))
sun = next(o for o in sc.objects if o.type == "LIGHT")
arms = sorted([o for o in sc.objects if o.type == "ARMATURE"], key=lambda o: o.matrix_world.translation.x)


def head_track(a):
    pb = a.pose.bones
    hd = next(pb[n] for n in ("頭", "head") if n in pb)
    nk = next(pb[n] for n in ("首", "neck") if n in pb)
    ub = next((pb[n] for n in ("上半身2", "上半身", "upper body") if n in pb), None)
    hs, ns, fw = [], [], []
    for f in range(F0 - 10, F1 + 11):
        sc.frame_set(f)
        hs.append(a.matrix_world @ hd.head)
        ns.append(a.matrix_world @ nk.head)
        if ub is not None:
            rot = ub.matrix.to_3x3() @ ub.bone.matrix_local.to_3x3().inverted()
            v = a.matrix_world.to_3x3() @ rot @ Vector((0, -1, 0))
        else:
            v = Vector((0, -1, 0))
        v.z = 0
        fw.append(v.normalized())
    return hs, ns, fw


def smooth(seq, k):
    out = []
    for i in range(len(seq)):
        lo, hi = max(0, i - k), min(len(seq), i + k + 1)
        s = Vector((0, 0, 0))
        for v in seq[lo:hi]:
            s += v
        out.append(s / (hi - lo))
    return out


for k, a in enumerate(arms):
    hs, ns, fw = head_track(a)
    hs, ns = smooth(hs, 6), smooth(ns, 6)
    hlen = sum(((h - n).length for h, n in zip(hs, ns)), 0.0) / len(hs)
    cd = bpy.data.cameras.new(f"Close{k}")
    cd.lens = 85
    cd.sensor_fit = "VERTICAL"
    cam = bpy.data.objects.new(f"Close{k}", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    height = hlen * 6.0                          # 胸から頭の上まで
    dist = height / (2 * math.tan(cd.angle_y / 2))
    for i, f in enumerate(range(F0 - 10, F1 + 11)):
        aim = hs[i] + (hs[i] - ns[i]) * 0.2 - Vector((0, 0, hlen * 0.8))
        # 正面(-Y)から見る。キャラが回っても追わない(並んだ全員と同じ向きのまま)
        d = Vector((0.15, -1.0, 0.12)).normalized()
        cam.location = aim + d * dist
        cam.rotation_euler = (aim - cam.location).to_track_quat("-Z", "Y").to_euler()
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)
    sc.frame_set((F0 + F1) // 2)               # カメラの向きが決まってから日を合わせる
    bpy.context.view_layer.update()
    sun.rotation_euler = (cam.matrix_world.to_3x3() @ Matrix.Rotation(math.radians(-10), 3, "X")
                          @ Matrix.Rotation(math.radians(-15), 3, "Y")).to_euler()
    sun.data.use_shadow = False
    bpy.context.view_layer.update()
    bpy.ops.freepencil2.link_button()
    bpy.ops.freepencil.measure_line_weight()
    if MODE == "cel":
        fp.cel(threshold=0.2, cast_shadows=False)
    else:
        fp.preview("WHITE")
    out = D / f"Four_close{k}_{MODE}"
    out.mkdir(exist_ok=True)
    for f in range(F0, F1 + 1):
        if (out / f"{f:04d}.png").exists() and "--resume" in ARGV:
            continue
        sc.frame_set(f)
        sc.render.filepath = str(out / f"{f:04d}.png")
        bpy.ops.render.render(write_still=True)
    print("@@@ close", k, a.name, flush=True)
print("@@@ done", flush=True)
