"""手作業の道具の残り: STEP1->2->3 を手で、種を変える、線の強弱を測る、Half Fill、STEP5 一括レンダー。

  blender -b --factory-startup --python audit_tools.py -- [--out out/audit_tools/<版>]
"""
from __future__ import annotations

import json
import math
import sys
import traceback
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d   # noqa: E731
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402
import audit_v29_scene as S       # noqa: E402

OUT = Path(arg("--out", str(HERE / "out" / "audit_tools" / bpy.app.version_string.split()[0]))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
fp_batch.install_addon()
log = {}


def shot(name):
    sc = bpy.context.scene
    sc.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    print("@@@", name, flush=True)


def select_all(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs.values():
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs["Monkey"]


ONLY = arg("--only", "")
# 1) STEP1 -> STEP2 -> STEP3 を手で押す(STEP0 と同じ絵になるか)。仕上がりごと
for style in ("PRECISE", "WEIGHTED", "BACKGROUND"):
    try:
        sc, objs = S.scene_setup(False, 480)
        sc.fp_auto_style = style
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        sc.fp_preview_mode = "WHITE"
        shot(f"manual_{style}_A_step0")
        sc, objs = S.scene_setup(False, 480)
        sc.fp_auto_style = style
        select_all(objs)
        r1 = bpy.ops.freepencil.auto_vertex_color()
        r2 = bpy.ops.freepencil4.link_button()
        r3 = bpy.ops.freepencil2.link_button()
        sc.fp_preview_mode = "WHITE"
        shot(f"manual_{style}_B_step123")
        log[f"manual_{style}"] = [sorted(r1), sorted(r2), sorted(r3), sc.render.resolution_percentage,
                                  sc.fp_line_weight]
    except Exception:                                            # noqa: BLE001
        log[f"manual_{style}"] = traceback.format_exc()
        print("@@@ ERROR", style, traceback.format_exc(), flush=True)

# 2) 種を変える -> STEP1 -> STEP3(線の位置は同じで、塗りの色だけ変わる)
try:
    sc, objs = S.scene_setup(False, 480)
    sc.fp_auto_style = "PRECISE"
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    seed0 = sc.fp_color_seed
    sc.fp_preview_mode = "NONE"
    for o in objs.values():
        o.data.color_attributes.active_color = o.data.color_attributes["mecha_color"]
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light = "FLAT"
    sh.color_type = "VERTEX"
    shot("seed_A_colors")
    select_all(objs)
    bpy.ops.freepencil.randomize_seed()
    bpy.ops.freepencil.auto_vertex_color()
    shot("seed_B_colors")
    sc.render.engine = fp_batch.eevee_engine()
    bpy.ops.freepencil2.link_button()
    sc.fp_preview_mode = "WHITE"
    shot("seed_C_lines")
    log["seed"] = [seed0, sc.fp_color_seed]
except Exception:                                                # noqa: BLE001
    log["seed"] = traceback.format_exc()
    print("@@@ ERROR seed", traceback.format_exc(), flush=True)

# 3) 線の強弱を測る(キャラ): カメラを近づけて測り直すと奥の範囲が変わる
try:
    sc, objs = S.scene_setup(False, 480)
    sc.fp_auto_style = "WEIGHTED"
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_preview_mode = "WHITE"
    before = {k: round(float(getattr(sc, k)), 3) for k in ("fp_lw_density", "fp_lw_e1", "fp_lw_e4")}
    sc.camera.location = (0, -3.5, 1.4)
    shot("measure_A_before")
    res = bpy.ops.freepencil.measure_line_weight()
    after = {k: round(float(getattr(sc, k)), 3) for k in ("fp_lw_density", "fp_lw_e1", "fp_lw_e4")}
    shot("measure_B_after")
    log["measure"] = [sorted(res), before, after]
except Exception:                                                # noqa: BLE001
    log["measure"] = traceback.format_exc()
    print("@@@ ERROR measure", traceback.format_exc(), flush=True)

# 4) Half Fill: 箱の正面の 2 頂点(対角)を選び、片側の面の角を塗る
try:
    sc, objs = S.scene_setup(False, 480)
    sc.fp_auto_style = "PRECISE"
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    sc.fp_preview_mode = "WHITE"
    shot("half_A_before")
    box = objs["Box"]
    bpy.ops.object.select_all(action="DESELECT")
    box.select_set(True)
    bpy.context.view_layer.objects.active = box
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    bpy.ops.object.mode_set(mode="OBJECT")
    vs = sorted(box.data.vertices, key=lambda v: (v.co.y, v.co.x + v.co.z))
    front = [v for v in box.data.vertices if v.co.y < 0]
    a = min(front, key=lambda v: v.co.x + v.co.z)
    b = max(front, key=lambda v: v.co.x + v.co.z)
    a.select = True
    b.select = True
    bpy.ops.object.mode_set(mode="EDIT")
    sc.fp_half_color = (0.9, 0.1, 0.1, 1.0) if len(sc.fp_half_color) == 4 else (0.9, 0.1, 0.1)
    res = bpy.ops.freepencil5.link_button()
    bpy.ops.object.mode_set(mode="OBJECT")
    shot("half_B_after")
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light = "FLAT"
    sh.color_type = "VERTEX"
    box.data.color_attributes.active_color = box.data.color_attributes["mecha_color"]
    sc.fp_preview_mode = "NONE"
    shot("half_C_colors")
    log["half"] = [sorted(res), [tuple(round(c, 2) for c in a.co), tuple(round(c, 2) for c in b.co)]]
except Exception:                                                # noqa: BLE001
    log["half"] = traceback.format_exc()
    print("@@@ ERROR half", traceback.format_exc(), flush=True)

# 5) STEP5: カメラ 2 台のうち 1 台だけチェック、ファイル出力(線・色・セルの 2 枚)
try:
    sc, objs = S.scene_setup(False, 480)
    sc.fp_auto_style = "WEIGHTED"
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    cam2 = bpy.data.objects.new("Cam2", bpy.data.cameras.new("Cam2"))
    cam2.location = (4.5, -4.5, 2.2)
    cam2.rotation_euler = (math.radians(75), 0, math.radians(45))
    sc.collection.objects.link(cam2)
    sc.camera.fp_cam_render = False
    cam2.fp_cam_render = True
    sc.fp_preview_mode = "CEL"
    sc.fp_file_output = True
    for k in ("fp_fo_line", "fp_fo_color", "fp_fo_cel_color", "fp_fo_cel_shadow"):
        setattr(sc, k, True)
    sc.fp_file_output_path = "//step5/"
    sc.render.filepath = "//step5/main_"
    bpy.ops.freepencil2.link_button()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "step5.blend"))     # STEP5 は保存したファイルで使う
    res = bpy.ops.freepencil.render_cameras()
    files = sorted(str(p.relative_to(OUT)) for p in (OUT / "step5").rglob("*.png"))
    log["step5"] = [sorted(res), files, sc.camera.name, sc.render.resolution_percentage]
    print("@@@ step5", files, flush=True)
except Exception:                                                # noqa: BLE001
    log["step5"] = traceback.format_exc()
    print("@@@ ERROR step5", traceback.format_exc(), flush=True)

(OUT / "log.json").write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")
print("@@@ done", flush=True)
