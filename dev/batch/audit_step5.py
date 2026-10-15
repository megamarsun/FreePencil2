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

(OUT / "log_step5.json").write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")
print("@@@ done", flush=True)
