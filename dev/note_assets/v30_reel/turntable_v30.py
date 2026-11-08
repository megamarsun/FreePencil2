"""v3.0 のデモ用: いろんな作例を v3.0 のセルで回す(カメラが周りを 1 周する)。

  blender -b --factory-startup --python turntable_v30.py -- <出力フォルダ> --models dwarf,taxi,jnr-c62-1-steam-
      [--frames 240] [--only-frames 1,60,120] [--res 1280]

作例の探し方は audit_v30_survey.py と同じ: Scenario(~/hf_data/scenario-3d の名前)/ BlenderKit(名前の頭)。
1 体ごとに <出力>/<名前>/f_0001.png … と <名前>.blend。もうあるコマは飛ばす。

カメラの周回は STEP0 の前にキーにする(手描き背景の「遠い区画をまとめる」はカメラの位置で塗りを決める。
キー無しだと回った先の細かい所が消える。town_pair.py --bake-cam と同じ)。
セルは fp_v30.py と同じ v3.0 の設定: カメラからの日・アニメの影色・顔はいつも日なた・リム(影の側・幅 6・暗め)・2 影(すき間)。
骨で動く物(キャラ)には影の形も入れる。
"""
from __future__ import annotations

import glob
import json
import math
import sys
import time
import traceback
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:]
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d   # noqa: E731
OUT = Path(ARGV[0]).resolve()
N = int(arg("--frames", "240"))
RES = int(arg("--res", "1280"))
ONLY = [int(x) for x in arg("--only-frames").split(",")] if arg("--only-frames") else None
MERGE = "--no-merge" not in ARGV     # glb の頂点を UV の継ぎ目でつなぐ
# つながない物: walker_mech は UV の継ぎ目が板の合わせ目と重なっていて、つなぐと板の線が消えて泥のようになった
NO_MERGE = {"walker_mech"}
# 骨の無い人物に STEP0 が当てる絵の線を外す物。全身に当てると、AI の絵に描いてある汚れ・しわの筆跡が
# 全部短い黒い線になった(medic・girl の腕と前掛け)。頭だけにしても、瞳が黒い塊・口がぎざぎざの縫い目になった。
# 外しても顔は絵の色(セルの色)で出る
TEX_OFF = {"girl", "medic"}
SHAPE_ALL = "--shape-chars-only" not in ARGV
RIM = "--no-rim" not in ARGV
STYLE = arg("--style")                # STEP0 の仕上がり(無ければ自動)
PAINT = arg("--paint-as")             # 物ごとの塗り方(MECHA / CHARA)
BATCH = Path(__file__).resolve().parents[2] / "batch"
sys.path.insert(0, str(BATCH))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402
from mathutils import Vector      # noqa: E402

fp_batch.install_addon()
mod = lambda s: next(m for n, m in sys.modules.items() if n.endswith("freepencil2." + s))   # noqa: E731
ai, cel_light, cel_shade, shade_normal = (mod(s) for s in ("ai", "cel_light", "cel_shade", "shade_normal"))

BK = Path.home() / "blenderkit_data" / "models"
SCN = {Path(s["local"]).parent.name: s["local"] for s in
       json.loads((Path.home() / "hf_data" / "scenario-3d" / "selection.json").read_text(encoding="utf-8"))}
FLOOR_WORDS = ("floor", "ground", "backdrop", "background", "studio", "cyclorama", "sweep", "groundplane")
# 名前ごとの見下ろし(度、水平から)と始めの向き(度)。無ければ 15 / 30
VIEW = {"airplane": (20, 30), "spaceship": (20, 30), "jnr-c62-1-steam-": (22, 40), "dutch_ship_mediu": (15, 50),
        "old_man_bust": (5, 20), "oni_mask": (5, 0), "treehouse": (22, 30), "mushroom_house": (15, 30),
        "spider_robot": (25, 30), "chest": (25, 30), "donut": (35, 30), "sushi": (40, 30)}


def stage(name):
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    path = SCN.get(name) or sorted(glob.glob(str(BK / f"{name}*" / "*.blend")))[0]
    if path.endswith(".glb"):
        # AI 生成(Scenario)の glb は UV がこま切れで、読み込むと頂点が UV の継ぎ目ごとに分かれる。
        # 精密は分かれた部品の境目を線にするので、継ぎ目が全部短い黒い線(ノイズ)になった(medic の腕)
        bpy.ops.import_scene.gltf(filepath=path, merge_vertices=MERGE and name not in NO_MERGE)
        meshes = [o for o in sc.objects if o.type == "MESH"]
        others = [o for o in sc.objects if o.type not in {"MESH", "CAMERA", "LIGHT"}]
        for o in [o for o in sc.objects if o.type in {"CAMERA", "LIGHT"}]:
            bpy.data.objects.remove(o)
    else:
        meshes, others = fp_batch.append_objects(Path(path))
    floor = [o for o in meshes if any(k in o.name.lower() for k in FLOOR_WORDS)]
    for o in floor:
        o.hide_render = True
    meshes = [o for o in meshes if o not in floor]
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
    sc.render.resolution_x, sc.render.resolution_y = RES, RES * 9 // 16
    sc.render.resolution_percentage = 100
    el, yaw0 = (math.radians(v) for v in VIEW.get(name, (15, 30)))
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.data.lens = 50
    sc.collection.objects.link(cam)
    sc.camera = cam

    def dirn(a):
        return Vector((math.sin(a) * math.cos(el), -math.cos(a) * math.cos(el), math.sin(el)))
    # 向きごとに収まる距離を測る(ポーズの付いた形の箱で)
    dg = bpy.context.evaluated_depsgraph_get()
    pts = [o.matrix_world @ Vector(c) for o in vis for c in o.evaluated_get(dg).bound_box]
    ctr = sum(pts, Vector()) / len(pts)
    coords = [v for p in pts for v in p]
    fits = []
    for f in range(1, N + 1):
        d = dirn(yaw0 + 2 * math.pi * (f - 1) / N)
        cam.location = ctr + d * 10
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        bpy.context.view_layer.update()
        loc, _ = cam.camera_fit_coords(dg, coords)
        fits.append((loc, d, cam.rotation_euler.copy()))
    # 回転の軸は箱の真ん中を通る縦の 1 本、距離は全周同じ(一番遠い向きに合わせる)。
    # 向きごとに収めると軸が左右に滑り、寄り引きもした(C62)
    far = max((loc - ctr).dot(d) for loc, d, _ in fits)
    sc.frame_start, sc.frame_end = 1, N
    for f, (loc, d, rot) in enumerate(fits, 1):
        cam.location = ctr + d * far * 1.1
        cam.rotation_euler = rot
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)
    for fc in cam.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy = 4
    sc.collection.objects.link(sun)
    sc.eevee.taa_render_samples = 16
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
        if hasattr(sc, p_):
            setattr(sc, p_, False)
    sc.frame_set(1)
    return sc, vis


for name in arg("--models").split(","):
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    blend = d / f"{name}.blend"
    try:
        if blend.exists():
            bpy.ops.wm.open_mainfile(filepath=str(blend))
            sc = bpy.context.scene
        else:
            sc, vis = stage(name)
            t0 = time.time()
            if PAINT:
                for o in vis:
                    o.fp_paint_as = PAINT
            r = ai.auto(STYLE, [o.name for o in vis])
            print("@@ STEP0", name, round(time.time() - t0, 1), "s", sc.fp_auto_style, r.get("warnings", []), flush=True)
            if name in TEX_OFF:
                for m in bpy.data.materials:
                    if m.node_tree:
                        for n_ in [n_ for n_ in m.node_tree.nodes if n_.label == ai.TEX_LABEL]:
                            m.node_tree.nodes.remove(n_)
                print("@@ tex off", name, flush=True)
            sc.fp_light_mode = "CAMERA"
            sc.fp_preview_mode = "CEL"
            # 影の形は骨の無い物にも入れる(丸い塊は楕円体、ほかは角で切ってならした面の向き)。
            # 骨のある物だけだと、AI 生成のでこぼこの面がそのまま影になり、まだらに割れた(dragon)
            chars = vis if SHAPE_ALL else [o for o in vis if any(m.type == "ARMATURE" for m in o.modifiers)]
            if chars:
                print("@@ shape", shade_normal.bake(sc, bpy.context.view_layer, chars), flush=True)
            sc.fp_cel_rim = RIM
            sc.fp_cel_rim_side = "AUTO"
            sc.fp_cel_rim_width = 6.0
            sc.fp_cel_rim_color = (0.4, 0.5, 0.48)
            # 回転ではリムを「日なたの色」で塗る。光(GLOW)だと赤や橙の物の縁が白っぽい帯になり、
            # 輪郭の横に白いふちが付いたように見えた(red_mecha・medic。4 案を並べて決めた)
            sc.fp_cel_rim_style = arg("--rim-style", "LIT")
            sc.fp_cel_shadow2 = "AO"
            cel_shade.set_cel(sc, True)
            bpy.ops.wm.save_as_mainfile(filepath=str(blend))
        for f in (ONLY or range(1, N + 1)):
            p = d / f"f_{f:04d}.png"
            if p.exists():
                continue
            t = time.time()
            sc.frame_set(f)
            if shade_normal.has_bake(sc):
                shade_normal.follow(sc)
            cel_light.aim_key(sc)
            cel_shade.update_sun(sc)
            sc.render.filepath = str(p)
            bpy.ops.render.render(write_still=True)
            print("@@ shot", name, f, round(time.time() - t, 1), "s", flush=True)
        print("@@ done", name, flush=True)
    except Exception:                                            # noqa: BLE001
        print("@@ ERROR", name, traceback.format_exc(), flush=True)
