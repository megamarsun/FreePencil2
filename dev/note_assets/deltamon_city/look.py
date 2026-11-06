"""プリビズの見た目を明るく・フラットにする(ワークベンチ)。build_city.py の暗い谷の色を持ち上げる。

  blender -b <city.blend> --python look.py -- <flat|studio> [--save <出力.blend>] [--snap <フォルダ> --frames 870,2399,...]

flat:   光の向きを使わない平らな塗り。形はくぼみの影(キャビティ)と輪郭で見せる
studio: スタジオの光のまま、背景と色を明るく、落ち影なし
"""
import sys
from pathlib import Path

import bpy

A = sys.argv[sys.argv.index("--") + 1:]
arg = lambda n, d=None: A[A.index(n) + 1] if n in A else d   # noqa: E731
MODE = A[0]
LIFT = 0.68                  # 色 c → 1 - (1 - c) * LIFT(暗い色ほど持ち上がる)。道(足場・手すり)の分
LIFT_BG = 0.86               # 谷の機械・パイプ・ケーブルの分(道より持ち上げない。道と背景を分ける)
BG = (0.62, 0.68, 0.76)      # 背景(明るい灰青)

sc = bpy.context.scene
for m in bpy.data.materials:
    if m.name.startswith("city_") and "lamp" not in m.name:
        if "fp_orig_color" not in m:
            m["fp_orig_color"] = list(m.diffuse_color)[:3]
        c = m["fp_orig_color"]
        k = LIFT if any(t in m.name for t in ("deck", "rail")) else LIFT_BG
        m.diffuse_color = (*[1 - (1 - v) * k for v in c], 1)
sc.world.color = BG


def setup(sh):
    sh.light = "FLAT" if MODE == "flat" else "STUDIO"
    sh.color_type = "TEXTURE"
    sh.background_type = "WORLD"
    sh.show_shadows = False
    sh.show_cavity = True
    sh.cavity_type = "WORLD"      # 画面の奥行きからの影(SCREEN)は顔の口・鼻・頬に灰色のしみを作った。形から付ける WORLD だけ
    sh.cavity_ridge_factor = 1.0
    sh.cavity_valley_factor = 1.0 if MODE == "flat" else 0.6
    sh.curvature_ridge_factor = 0.6
    sh.curvature_valley_factor = 1.0 if MODE == "flat" else 0.6
    sh.show_object_outline = MODE == "flat"
    sh.object_outline_color = (0.12, 0.14, 0.2)


setup(sc.display.shading)
for scr in bpy.data.screens:
    for ar in scr.areas:
        if ar.type == "VIEW_3D":
            for sp in ar.spaces:
                if sp.type == "VIEW_3D":
                    setup(sp.shading)
if arg("--save"):
    bpy.ops.wm.save_as_mainfile(filepath=arg("--save"))
    print("@@ saved", arg("--save"), flush=True)
if arg("--snap"):
    out = Path(arg("--snap"))
    out.mkdir(parents=True, exist_ok=True)
    mks = sorted([m for m in sc.timeline_markers if m.camera], key=lambda m: m.frame)
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    for f in [int(x) for x in arg("--frames").split(",")]:
        m = max((m for m in mks if m.frame <= f), key=lambda m: m.frame)
        sc.camera = m.camera
        sc.frame_set(f)
        sc.render.filepath = str(out / f"{m.name}_{f:04d}.png")
        bpy.ops.render.render(write_still=True)
    print("@@ snap", out, flush=True)
