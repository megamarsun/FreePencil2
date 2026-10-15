"""v2.9 の総当り: 仕上がり x プレビュー x 線の太さ x 背景 x 細線化 を撮る(リリース前の点検)。

  blender -b --factory-startup --python audit_v29.py -- [--out out/audit_v29/<版>] [--res 480]

場面: 赤いサル(滑らか)・黄色い箱・青い地面・日。線の太さ「混ぜ」はサル 2 / 箱 0.5 / 地面 0。
1 枚ずつ <仕上がり>_<プレビュー>_<太さ>_<背景>_<細線化>.png。ログに例外と所要時間を出す。
判定は audit_v29_sheet.py のシートを目で見る(透過は市松で見せる)。
"""
from __future__ import annotations

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

OUT = Path(arg("--out", str(HERE / "out" / "audit_v29" / bpy.app.version_string))).resolve()
RES = int(arg("--res", "480"))
STYLES = arg("--styles", "PRECISE,WEIGHTED,BACKGROUND").split(",")
MODES = ("NONE", "WHITE", "MONO_LIGHT", "CEL")
OUT.mkdir(parents=True, exist_ok=True)
fp_batch.install_addon()
log = []


def scene_setup(transparent):
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene

    def mat(name, col):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*col, 1)
        return m
    bpy.ops.mesh.primitive_monkey_add(size=1.6, location=(-1.0, 0, 0.9))
    bpy.ops.object.shade_smooth()
    monkey = bpy.context.object
    monkey.name = "Monkey"
    monkey.data.materials.append(mat("Red", (0.8, 0.15, 0.1)))
    bpy.ops.mesh.primitive_cube_add(size=1.2, location=(1.0, 0.3, 0.6))
    cube = bpy.context.object
    cube.name = "Box"
    cube.data.materials.append(mat("Yellow", (0.9, 0.75, 0.2)))
    bpy.ops.mesh.primitive_plane_add(size=12, location=(0, 2, 0))
    ground = bpy.context.object
    ground.name = "Ground"
    ground.data.materials.append(mat("Blue", (0.2, 0.4, 0.8)))
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.location = (0, -6, 1.8)
    cam.rotation_euler = (math.radians(80), 0, 0)
    sc.collection.objects.link(cam)
    sc.camera = cam
    lt = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    lt.data.energy = 4
    lt.rotation_euler = (math.radians(50), 0, math.radians(-40))
    sc.collection.objects.link(lt)
    sc.render.resolution_x, sc.render.resolution_y = RES, RES * 9 // 16
    sc.eevee.taa_render_samples = 8
    sc.render.film_transparent = transparent
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
        setattr(sc, p_, False)
    bpy.ops.object.select_all(action="DESELECT")
    for o in (monkey, cube, ground):
        o.select_set(True)
    bpy.context.view_layer.objects.active = monkey
    return sc, {"Monkey": monkey, "Box": cube, "Ground": ground}


def shot(sc, name):
    t0 = time.time()
    sc.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    return round(time.time() - t0, 2)


for style in STYLES:
    for transparent in (False, True):
        for ss in (True, False):
            try:
                sc, objs = scene_setup(transparent)
                sc.fp_auto_style = style
                bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
                # STEP0 は背景を透過にする。利用者が後で不透明に戻した場合も見る
                sc.render.film_transparent = transparent
                if sc.fp_supersample != ss:
                    sc.fp_supersample = ss
                    bpy.ops.freepencil2.link_button()          # 細線化は STEP3 で効く
                for scale in ("all1", "mixed"):
                    for o in objs.values():
                        o.fp_line_scale = 1.0
                    if scale == "mixed":
                        objs["Monkey"].fp_line_scale = 2.0
                        objs["Box"].fp_line_scale = 0.5
                        objs["Ground"].fp_line_scale = 0.0
                    for mode in MODES:
                        sc.fp_preview_mode = mode
                        name = f"{style}_{mode}_{scale}_{'clear' if transparent else 'opaque'}_{'ss' if ss else 'x1'}"
                        sec = shot(sc, name)
                        log.append({"name": name, "ok": True, "sec": sec, "pct": sc.render.resolution_percentage})
                        print("@@@", name, sec, flush=True)
            except Exception:                                   # noqa: BLE001
                log.append({"name": f"{style}_{transparent}_{ss}", "ok": False, "error": traceback.format_exc()})
                print("@@@ ERROR", style, transparent, ss, traceback.format_exc(), flush=True)
(OUT / "log.json").write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")
print("@@@ done", len(log), "errors", sum(1 for r in log if not r["ok"]), flush=True)
