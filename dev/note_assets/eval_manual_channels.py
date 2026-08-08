"""STEP4 の手動チャンネル(mask_color / line_color)の実効果を測る。

ユーザー報告:
  1. mask_color は白(1.0)だとほぼ効かず、0.6 付近が最も効く
  2. line_color は線の無い場所に塗っても線が出ず、既存線の色が変わるだけ

マニュアルの記述は UI ラベルからの推測で書かれており、ノードの実装を
確認していない。塗る明度を振って実際のレンダー結果で確かめる。

  blender -b --factory-startup --python eval_manual_channels.py -- \
      --channel mask_color --out <abs dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))

import fp_batch  # noqa: E402

fp_batch.install_addon()

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
CHANNEL = ARGV[ARGV.index("--channel") + 1]
OUT = Path(ARGV[ARGV.index("--out") + 1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
LEVELS = [0.0, 0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]


def paint(obj, attr_name: str, value: float) -> None:
    """指定の色属性を一様な明度で塗りつぶす。"""
    attr = obj.data.color_attributes.get(attr_name)
    assert attr is not None, attr_name
    n = len(attr.data)
    attr.data.foreach_set("color", [value, value, value, 1.0] * n)
    obj.data.update()


def build(paint_value):
    """立方体を塗り分けて STEP0 まで通す。paint_value が None なら素のまま。"""
    bpy.ops.wm.read_homefile(use_empty=True)
    # 面ごとに向きが違う立方体は mecha_color が複数島になり線が出る
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.active_object
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    scene = bpy.context.scene
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 1234
    scene.fp_enable_compositor_view = False
    scene.fp_supersample = False
    scene.fp_auto_white_preview = True
    # 自動検出だと「まだ塗っていない」チャンネルのAOVが作られないので、
    # 対象チャンネルは明示的に有効化する(STEP4の実運用では塗ってから
    # STEP0/STEP2 をやり直すか、STEP2でチェックを入れる形になる)
    scene.fp_auto_detect_aov = False
    scene.fp_mask_color = True
    scene.fp_line_color = True
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")

    if paint_value is not None:
        paint(obj, CHANNEL, paint_value)

    fp_batch.setup_camera_and_light()
    scene.render.engine = fp_batch.eevee_engine()
    scene.eevee.taa_render_samples = 8
    scene.render.resolution_x = scene.render.resolution_y = 400
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    png = OUT / f"{CHANNEL}_{'base' if paint_value is None else paint_value}.png"
    fp_batch.render_still(scene, png, 1)
    return fp_batch.lineart_metrics(png)


rows = []
base = build(None)
rows.append({"paint": "none", "ink_ratio": base["ink_ratio"],
             "components": base["components"]})
for v in LEVELS:
    m = build(v)
    delta = (m["ink_ratio"] - base["ink_ratio"]) / max(base["ink_ratio"], 1e-9)
    rows.append({"paint": v, "ink_ratio": m["ink_ratio"],
                 "components": m["components"],
                 "vs_base_pct": round(delta * 100, 1)})

print("[channels] " + json.dumps({"channel": CHANNEL, "rows": rows},
                                 ensure_ascii=False))
