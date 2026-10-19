"""v2.9 デモのメカの場面: BlenderKit のモデルを明るいスタジオに置き、ゆっくり回り込むカメラで撮る。

  blender -b --factory-startup --python mech_orbit.py -- --model tank --out <dir>
          [--frames 234] [--res 1920] [--yaw0 25] [--yaw1 70] [--pitch 76] [--zoom 1.05]
          [--modes model,line,cel] [--only 1,117,234] [--samples 16] [--style PRECISE]

カメラは STEP0 の前にキーを打つ(手描き背景の遠い区画をまとめる、と同じ理由で、動きを先に決める)。
日はカメラの向きから 10° 上・左へ 15°(正面から。回り込みに合わせて日もついて行く)。
4K(--res 3840)は 2倍レンダを使わない(デモで画像で比べて決めた)。
"""
import glob
import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:]
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d   # noqa: E731
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
import fp_batch                                   # noqa: E402
fp_batch.install_addon()
import bpy                                        # noqa: E402
from mathutils import Matrix, Vector              # noqa: E402

MODEL = arg("--model")
OUT = Path(arg("--out")).resolve()
OUT.mkdir(parents=True, exist_ok=True)
N = int(arg("--frames", "234"))
RES = int(arg("--res", "1920"))
Y0, Y1 = float(arg("--yaw0", "25")), float(arg("--yaw1", "70"))
PITCH = float(arg("--pitch", "76"))
ZOOM = float(arg("--zoom", "1.05"))
MODES = arg("--modes", "model,line,cel").split(",")
ONLY = [int(v) for v in arg("--only", "").split(",") if v]
STYLE = arg("--style", "PRECISE")

bpy.ops.wm.read_homefile(use_empty=True)
sc = bpy.context.scene
blend = glob.glob(str(Path.home() / "blenderkit_data" / "models" / f"{MODEL}*" / "*.blend"))[0]
meshes, others = fp_batch.append_objects(Path(blend))
fp_batch.normalize(meshes + others, meshes)
vis = [o for o in meshes if not o.hide_render]
bpy.context.view_layer.update()
pts = [o.matrix_world @ Vector(c) for o in vis for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
ctr = (lo + hi) / 2
size = (hi - lo).length
# 床(影を受ける。線は出さない)
bpy.ops.mesh.primitive_plane_add(size=size * 40, location=(ctr.x, ctr.y, lo.z))
floor = bpy.context.object
floor.name = "StudioFloor"
fm = bpy.data.materials.new("StudioFloor")
fm.use_nodes = True
fm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.82, 0.83, 0.86, 1)
fm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
floor.data.materials.append(fm)
floor.fp_line_scale = 0.0
w = bpy.data.worlds.new("Studio")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.86, 0.87, 0.90, 1)   # 床と同じくらいの明るさ
w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
sc.world = w
cd = bpy.data.cameras.new("Cam")
cd.lens = 50
cam = bpy.data.objects.new("Cam", cd)
sc.collection.objects.link(cam)
sc.camera = cam
sc.render.resolution_x, sc.render.resolution_y = RES, RES * 9 // 16
sc.render.fps = 30
sc.frame_start, sc.frame_end = 1, N
sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
sun.data.energy = 3.5
sc.collection.objects.link(sun)
# 回り込み: 全体が入る距離を始めと終わりで測って大きい方
dg = bpy.context.evaluated_depsgraph_get()
flat = [v for p in pts for v in p]


def place(yaw):
    cam.rotation_euler = (math.radians(PITCH), 0, math.radians(yaw))
    bpy.context.view_layer.update()
    loc, _s = cam.camera_fit_coords(dg, flat)
    return loc


d0 = (place(Y0) - ctr).length
d1 = (place(Y1) - ctr).length
dist = max(d0, d1) * ZOOM
for f in range(1, N + 1):
    u = (f - 1) / max(1, N - 1)
    u = u * u * (3 - 2 * u)
    yaw = Y0 + (Y1 - Y0) * u
    rot = Matrix.Rotation(math.radians(yaw), 3, "Z") @ Matrix.Rotation(math.radians(PITCH), 3, "X")
    cam.location = ctr - (rot @ Vector((0, 0, -1))) * dist
    cam.rotation_euler = rot.to_euler()
    cam.keyframe_insert("location", frame=f)
    cam.keyframe_insert("rotation_euler", frame=f)
    sun.rotation_euler = (rot @ Matrix.Rotation(math.radians(-10), 3, "X")
                          @ Matrix.Rotation(math.radians(-15), 3, "Y")).to_euler()
    sun.keyframe_insert("rotation_euler", frame=f)
sc.view_settings.view_transform = "Standard"
sc.eevee.taa_render_samples = int(arg("--samples", "16"))
for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
    setattr(sc, p_, False)
sc.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{MODEL}_clean.blend"))
frames = ONLY or list(range(1, N + 1))


# 見せ方ごとに撮るコマの範囲(例 model:1-80,line:50-140,cel:110-234)。映る所だけ撮る
RANGES = {}
for item in [v for v in arg("--ranges", "").split(",") if v]:
    k, r = item.split(":")
    a_, b_ = (int(x) for x in r.split("-"))
    RANGES[k] = list(range(a_, b_ + 1))


def shoot(mode):
    d = OUT / mode
    d.mkdir(exist_ok=True)
    for f in (RANGES.get(mode, frames) if not ONLY else frames):
        p = d / f"{f:04d}.png"
        if p.exists() and "--resume" in ARGV:
            continue
        sc.frame_set(f)
        sc.render.filepath = str(p)
        bpy.ops.render.render(write_still=True)
    print("@@@ seq", mode, len(frames), flush=True)


if "model" in MODES:
    sc.render.use_compositing = False
    shoot("model")
    sc.render.use_compositing = True
fp = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.ai"))
for o in sc.objects:
    o.select_set(o.type == "MESH" and o is not floor and not o.hide_render)
bpy.context.view_layer.objects.active = vis[0]
sc.frame_set(N // 2)
fp.auto(STYLE, objects=[o.name for o in vis])
floor.fp_line_scale = 0.0
bpy.ops.freepencil2.link_button()
if "line" in MODES:
    fp.preview("WHITE")
    shoot("line")
if "cel" in MODES:
    # 空の色は床に合わせる(地平線の上に青い帯が出ないように)
    fp.cel(threshold=0.2, cast_shadows=True, pale=float(arg("--pale", "0.15")),
           sky=True, sky_color=(0.86, 0.87, 0.90))
    shoot("cel")
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{MODEL}_fp.blend"))
print("@@@ done", MODEL, flush=True)
