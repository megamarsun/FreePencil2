"""手作業の道具(STEP4 の塗り直し)を、利用者の手順どおりに通して撮る。

  blender -b --factory-startup --python audit_manual.py -- [--out out/audit_manual/<版>] [--styles ...]

手順(仕上がりごとに、白とセルのプレビューで):
  base      STEP0 の直後
  mask_*    箱のマスクカラーを白で塗る(箱の線が消えるはず)
  line_*    サルのラインカラーを 0.2 で塗る(サルの線が薄くなるはず)
  mecha_*   サルの左半分(x < -1)のメカカラーを 1 色で塗る(左半分の線が消え、境目に線が出るはず)
  それぞれ  _paint = 塗っただけ / _s3 = STEP3 を押した後 / _s23 = STEP2 -> STEP3 を押した後
STEP4 の「頂点カラーを塗る」ボタンが、選んだ種類の色属性で頂点ペイントに入るかも確かめる。
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
import numpy as np                # noqa: E402
import fp_batch                   # noqa: E402
import audit_v29_scene as S       # noqa: E402

OUT = Path(arg("--out", str(HERE / "out" / "audit_manual" / bpy.app.version_string.split()[0]))).resolve()
STYLES = arg("--styles", "PRECISE,WEIGHTED,BACKGROUND").split(",")
OUT.mkdir(parents=True, exist_ok=True)
fp_batch.install_addon()
log = []


def paint(obj, layer, rgb, face_pred=None):
    """色属性 layer を、条件に合う面(無ければ全部)の角に rgb で塗る。"""
    me = obj.data
    attr = me.color_attributes.get(layer)
    if attr is None:
        attr = me.color_attributes.new(layer, "BYTE_COLOR", "CORNER")
    if attr.domain == "CORNER":
        cols = np.empty(len(attr.data) * 4, dtype=np.float32)
        attr.data.foreach_get("color", cols)
        cols = cols.reshape(-1, 4)
        for p in me.polygons:
            if face_pred is None or face_pred(obj.matrix_world @ p.center):
                cols[p.loop_start:p.loop_start + p.loop_total, :3] = rgb
                cols[p.loop_start:p.loop_start + p.loop_total, 3] = 1.0
        attr.data.foreach_set("color", cols.ravel())
    else:
        cols = np.empty(len(attr.data) * 4, dtype=np.float32)
        attr.data.foreach_get("color", cols)
        cols = cols.reshape(-1, 4)
        for p in me.polygons:
            if face_pred is None or face_pred(obj.matrix_world @ p.center):
                for vi in p.vertices:
                    cols[vi, :3] = rgb
        attr.data.foreach_set("color", cols.ravel())
    me.update()


def shot(name):
    sc = bpy.context.scene
    sc.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    log.append({"name": name, "mask_aov": sc.fp_mask_color, "line_aov": sc.fp_line_color,
                "aovs": [a.name for a in bpy.context.view_layer.aovs]})
    print("@@@", name, "mask", sc.fp_mask_color, "line", sc.fp_line_color, flush=True)


def select_all(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs.values():
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs["Monkey"]


for style in STYLES:
    for preview in ("WHITE", "CEL"):
        tag = f"{style}_{preview}"
        try:
            for kind in ("mask", "line", "mecha"):
                sc, objs = S.scene_setup(False, 480)
                sc.fp_auto_style = style
                bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
                sc.fp_preview_mode = preview
                if kind == "mask":
                    shot(f"{tag}_base")
                    paint(objs["Box"], "mask_color", (1.0, 1.0, 1.0))
                elif kind == "line":
                    paint(objs["Monkey"], "line_color", (0.2, 0.2, 0.2))
                else:
                    paint(objs["Monkey"], "mecha_color", (0.85, 0.2, 0.6), lambda c: c.x < -1.0)
                    if "fine_color" in objs["Monkey"].data.color_attributes:
                        pass
                shot(f"{tag}_{kind}_paint")
                bpy.ops.freepencil2.link_button()
                shot(f"{tag}_{kind}_s3")
                select_all(objs)
                bpy.ops.freepencil4.link_button()
                bpy.ops.freepencil2.link_button()
                shot(f"{tag}_{kind}_s23")
                if kind == "mecha":
                    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{tag}_mecha.blend"))
        except Exception:                                        # noqa: BLE001
            log.append({"name": tag, "error": traceback.format_exc()})
            print("@@@ ERROR", tag, traceback.format_exc(), flush=True)

# STEP4 の「頂点カラーを塗る」: 種類ごとに頂点ペイントへ入り、その色属性が選ばれるか
sc, objs = S.scene_setup(False, 320)
sc.fp_auto_style = "PRECISE"
bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
for ct in [i.identifier for i in sc.bl_rna.properties["fp_color_type"].enum_items]:
    bpy.ops.object.mode_set(mode="OBJECT")
    select_all(objs)
    sc.fp_color_type = ct
    try:
        res = bpy.ops.freepencil3.link_button()
        o = bpy.context.active_object
        ca = o.data.color_attributes
        rec = {"type": ct, "result": sorted(res), "mode": o.mode,
               "active": ca.active_color.name if ca.active_color else None,
               "has": ct in ca}
    except Exception as e:                                       # noqa: BLE001
        rec = {"type": ct, "error": f"{type(e).__name__}: {e}"}
    log.append(rec)
    print("@@@ paint-op", rec, flush=True)
(OUT / "log.json").write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")
print("@@@ done", flush=True)
