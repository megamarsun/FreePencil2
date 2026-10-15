"""v2.9 を実モデルで: STEP0 -> 白 / マテリアル / モノクロ / セル / セル + 線の太さ、とファイル出力。

  blender -b --factory-startup --python audit_v29_models.py -- [--out out/audit_v29_models/<版>] [--res 720]
      [--only anime-girl]

モデルは BlenderKit の取り込み(材質は元のまま。発光・テクスチャ・透過の材質が混ざる)。
"""
from __future__ import annotations

import glob
import math
import sys
import time
import traceback
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d   # noqa: E731
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402
from mathutils import Vector      # noqa: E402

OUT = Path(arg("--out", str(HERE / "out" / "audit_v29_models" / bpy.app.version_string.split()[0]))).resolve()
RES = int(arg("--res", "720"))
ROOT = Path.home() / "blenderkit_data" / "models"
MODELS = [  # (名前, 仕上がり, カメラの向き(度)、太くする物の名前の一部)
    ("anime-girl", "WEIGHTED", 20, "body"),
    ("stylized-male-ch", "WEIGHTED", 25, ""),
    ("robot-kuka-quant", "PRECISE", 35, ""),
    ("jnr-c58-steam-lo", "PRECISE", 55, ""),
    ("japan-apartment", "BACKGROUND", 30, ""),
    ("tank", "PRECISE", 40, ""),
]
if arg("--only"):
    MODELS = [m for m in MODELS if m[0] in arg("--only").split(",")]
OUT.mkdir(parents=True, exist_ok=True)
fp_batch.install_addon()


def stage(name, yaw):
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    blend = glob.glob(str(ROOT / f"{name}*" / "*.blend"))[0]
    meshes, others = fp_batch.append_objects(Path(blend))
    fp_batch.normalize(meshes + others, meshes)
    # 主要な塊の自動選びは、ロボット(リグの部品)や家(屋根だけ)で一部しか選ばなかったので、
    # キャラ(リグ付き)だけに使う。使わないとアニメ少女が遠くの小物と一緒に写って豆粒になった
    if any(m.type == "ARMATURE" for o in meshes for m in o.modifiers):
        keep = fp_batch.dominant_cluster(meshes)
        for o in meshes:
            if o not in keep and o.name not in keep:
                o.hide_render = True
    vis = [o for o in meshes if not o.hide_render]
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in vis for c in o.bound_box]
    ctr = sum(pts, Vector()) / len(pts)
    cd = bpy.data.cameras.new("Cam")
    cd.lens = 50
    cam = bpy.data.objects.new("Cam", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.rotation_euler = (math.radians(78), 0, math.radians(yaw))
    sc.render.resolution_x, sc.render.resolution_y = RES, RES * 9 // 16
    bpy.context.view_layer.update()
    loc, _ = cam.camera_fit_coords(bpy.context.evaluated_depsgraph_get(), [v for p in pts for v in p])
    cam.location = ctr + (loc - ctr) * 1.1
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy = 4
    sun.rotation_euler = (math.radians(50), 0, math.radians(yaw + 35))     # カメラの側から斜めに
    sc.collection.objects.link(sun)
    sc.eevee.taa_render_samples = 16
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
        setattr(sc, p_, False)
    bpy.ops.object.select_all(action="DESELECT")
    for o in vis:
        o.select_set(True)
    bpy.context.view_layer.objects.active = vis[0]
    return sc, vis


for name, style, yaw, thick in MODELS:
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    try:
        t0 = time.time()
        sc, vis = stage(name, yaw)
        sc.fp_auto_style = style
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        t_step0 = time.time() - t0
        times = {}
        for mode in ("WHITE", "NONE", "MONO_LIGHT", "CEL"):
            sc.fp_preview_mode = mode
            t1 = time.time()
            sc.render.filepath = str(d / f"{mode}.png")
            bpy.ops.render.render(write_still=True)
            times[mode] = round(time.time() - t1, 1)
        # 線の太さ: 一番大きい物を 2、ほかを 0.5
        big = max(vis, key=lambda o: o.dimensions.length * (1 + len(o.data.polygons)) ** 0.1)
        for o in vis:
            o.fp_line_scale = 0.5
        big.fp_line_scale = 2.0
        sc.render.filepath = str(d / "CEL_scale.png")
        bpy.ops.render.render(write_still=True)
        for o in vis:
            o.fp_line_scale = 1.0
        sc.fp_file_output = True
        for k in ("fp_fo_line", "fp_fo_cel_color", "fp_fo_cel_shadow"):
            setattr(sc, k, True)
        sc.fp_file_output_path = str(d / "fo") + "/"
        bpy.ops.freepencil2.link_button()
        sc.render.filepath = str(d / "CEL_fo.png")
        bpy.ops.render.render(write_still=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(d / f"{name}.blend"))
        print("@@@", name, style, f"STEP0 {t_step0:.1f}s", times, "big", big.name,
              sorted(p.name for p in (d / "fo").glob("*.png")), flush=True)
    except Exception:                                            # noqa: BLE001
        print("@@@ ERROR", name, traceback.format_exc(), flush=True)
