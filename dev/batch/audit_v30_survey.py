"""v3.0 の出発点: いろんな作例に今の STEP0 をそのままかけて、欠点を探す。

  blender -b --factory-startup --python audit_v30_survey.py -- [--out out/v30_survey] [--res 1280]
      [--only tank,bridge] [--blends a_clean.blend,b_clean.blend] [--props fp_auto_shells=0]

--blends を付けると、BlenderKit の代わりにカメラと日が置いてある場面(MMD の *_clean.blend など)を開く。

1 体ごとに: 元の 3D → AI の窓口の auto()(仕上がりは窓口に選ばせる) → 白 / 材質 / セル を撮る。
手直しはしない(AI や人が手を入れる前の、素の出来を見るため)。窓口の warnings も控える。
絵は make_v30_sheet.py で 1 体 1 行に並べて、目で見る。
"""
from __future__ import annotations

import glob
import json
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

OUT = Path(arg("--out", str(HERE / "out" / "v30_survey"))).resolve()
RES = int(arg("--res", "1280"))
ROOT = Path.home() / "blenderkit_data" / "models"
MODELS = [  # (名前の頭, カメラの向き(度), 見下ろし(度))  作例の種類がばらけるように選んだ
    # 人・キャラ
    ("loli_anime_girl", 20, 82), ("anime-girl", 20, 82), ("kaino-school-mil", 25, 82), ("woman_01", 20, 82),
    ("zombie_riot_poli", 25, 82), ("full-skeleton-human", 30, 82), ("stylized-male-ch", 25, 82),
    # メカ・機械
    ("heavy-zaku-mkll-", 30, 80), ("space_scavenger", 40, 70), ("robot-kuka-quant", 35, 75),
    ("portable-generat", 35, 65),
    # 乗り物
    ("lamborghini-revu", 40, 72), ("airbus_a320", 35, 65), ("dutch_ship_mediu", 50, 75),
    ("toy_train-02", 40, 65),
    # 建物・大きい物
    ("modern-house", 35, 75), ("eiffel_tower_189", 30, 85), ("bridge", 40, 70), ("japan-apartment", 30, 78),
    # 有機・自然
    ("tree_autumn", 20, 85), ("squid_with_proce", 30, 60), ("cat_figurine", 30, 75), ("butterfly-wings", 0, 40),
    # 小物
    ("tea_set_01", 30, 60), ("hollowbody_elect", 20, 75), ("sushi", 30, 50), ("cupcakes", 30, 60),
    ("basketball", 0, 80), ("books-pack", 30, 65), ("chair", 35, 70), ("pistol", 90, 85),
]
# 2 巡目: 1 巡目で直すのに使っていない作例。直したことが 1 巡目の作例にだけ効いていないかを見る
HOLDOUT = [
    # 人・キャラ
    ("man_01", 20, 82), ("man_308", 20, 82), ("fredy", 25, 82), ("mozo", 25, 82), ("terna", 25, 82),
    # メカ・乗り物
    ("tank", 35, 72), ("heavy-light-carg", 35, 72), ("jnr-c62-1-steam-", 40, 75), ("batmobile", 40, 72),
    ("audi_r8_v10", 40, 72), ("80-s-cartoon-wag", 40, 70), ("cartoon-car-cabr", 40, 70),
    ("futuristic_ct", 35, 72), ("distressed-sci-f", 35, 70),
    # 建物
    ("arched_hangar", 35, 75), ("rausch_funeral_h", 35, 78),
    # 植物
    ("european-maple-a", 20, 85), ("coconut-tree", 20, 85), ("manchester-acaci", 20, 85),
    ("baccarat-dahlia-", 30, 60), ("halloween_pumpki", 30, 70),
    # 小物・家具・家電
    ("clay-vase", 30, 70), ("eggs_bowl", 30, 55), ("kallax-ikea", 35, 75), ("standard_bathtub", 35, 65),
    ("ps3-dualshock-co", 20, 50), ("camera_", 35, 70), ("43-inch-tv", 30, 80), ("formal-shoe", 40, 70),
    ("cleaver_knife", 30, 60), ("generic_wall_clo", 20, 85),
]
if arg("--set") == "holdout":
    MODELS = HOLDOUT
if arg("--blends"):
    MODELS = [(str(Path(b).resolve()), None, None) for b in arg("--blends").split(",")]
elif arg("--only"):
    MODELS = [m for m in MODELS if any(m[0].startswith(k) for k in arg("--only").split(","))]
OUT.mkdir(parents=True, exist_ok=True)
fp_batch.install_addon()
ai = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.ai"))


def stage(name, yaw, pitch):
    if yaw is None:              # カメラと日が置いてある場面
        bpy.ops.wm.open_mainfile(filepath=name)
        sc = bpy.context.scene
        sc.render.resolution_x, sc.render.resolution_y = RES, RES * 9 // 16
        sc.render.resolution_percentage = 100
        for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
            setattr(sc, p_, False)
        return sc, [o for o in sc.objects if o.type == "MESH" and not o.hide_render and len(o.data.polygons)]
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    blend = sorted(glob.glob(str(ROOT / f"{name}*" / "*.blend")))[0]
    meshes, others = fp_batch.append_objects(Path(blend))
    fp_batch.normalize(meshes + others, meshes)
    if any(m.type == "ARMATURE" for o in meshes for m in o.modifiers):
        keep = fp_batch.dominant_cluster(meshes)
        for o in meshes:
            if o not in keep and o.name not in keep:
                o.hide_render = True
    vis = [o for o in meshes if not o.hide_render]
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in vis for c in o.bound_box]
    ctr = sum(pts, Vector()) / len(pts)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.data.lens = 50
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.rotation_euler = (math.radians(pitch), 0, math.radians(yaw))
    sc.render.resolution_x, sc.render.resolution_y = RES, RES * 9 // 16
    bpy.context.view_layer.update()
    loc, _ = cam.camera_fit_coords(bpy.context.evaluated_depsgraph_get(), [v for p in pts for v in p])
    cam.location = ctr + (loc - ctr) * 1.1
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy = 4
    sun.rotation_euler = (math.radians(50), 0, math.radians(yaw + 35))
    sc.collection.objects.link(sun)
    sc.eevee.taa_render_samples = 16
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
        setattr(sc, p_, False)
    return sc, vis


def shot(sc, path):
    sc.render.filepath = str(path)
    t = time.time()
    bpy.ops.render.render(write_still=True)
    return round(time.time() - t, 1)


for name, yaw, pitch in MODELS:
    d = OUT / (Path(name).stem.replace("_clean", "") if yaw is None else name)
    d.mkdir(parents=True, exist_ok=True)
    rec = {"name": d.name}
    try:
        sc, vis = stage(name, yaw, pitch)
        rec["objects"], rec["faces"] = len(vis), sum(len(o.data.polygons) for o in vis)
        rec["t_3d"] = shot(sc, d / "0_3d.png")
        t0 = time.time()
        for kv in filter(None, (arg("--props") or "").split(",")):   # 例 fp_auto_shells=0
            k_, v_ = kv.split("=")
            setattr(sc, k_, type(getattr(sc, k_))(float(v_)) if not isinstance(getattr(sc, k_), str) else v_)
        r = ai.auto(None, [o.name for o in vis])
        rec["t_step0"] = round(time.time() - t0, 1)
        rec["style"] = sc.fp_auto_style
        rec["warnings"] = r.get("warnings", [])
        for i, mode in enumerate(("WHITE", "NONE", "CEL"), 1):
            sc.fp_preview_mode = mode
            rec[f"t_{mode}"] = shot(sc, d / f"{i}_{mode}.png")
        bpy.ops.wm.save_as_mainfile(filepath=str(d / f"{d.name}.blend"))
    except Exception:                                            # noqa: BLE001
        rec["error"] = traceback.format_exc()
    (d / "rec.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print("@@@", json.dumps({k: v for k, v in rec.items() if k != "error"}, ensure_ascii=False),
          "ERROR" if "error" in rec else "", flush=True)
