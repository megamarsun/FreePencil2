"""UI撮影用の .blend を作る (フェーズ1・バックグラウンド)。

GUI 起動時にファイルを渡すとスプラッシュが出ないので、撮影対象のシーンを
先に .blend にしておく。STEP0 はまだ実行しない (初回起動時のパネルを撮るため)。

  blender -b --factory-startup --python ui_prepare.py -- \
      --blend <asset.blend> --save out/ui_scene.blend
"""
from __future__ import annotations

import sys
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
sys.path.insert(0, str(HERE))

import fp_batch          # noqa: E402
import render_samples    # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
BLEND = ARGV[ARGV.index("--blend") + 1]
SAVE = ARGV[ARGV.index("--save") + 1]
Path(SAVE).parent.mkdir(parents=True, exist_ok=True)

fp_batch.install_addon()
# 起動時の Cube/Camera/Light を消す。残すとモデルと重なって画が読めない
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

objs, others = render_samples.stage_model(Path(BLEND))
for o in bpy.context.scene.objects:
    if o.type == "MESH" and o.hide_render:
        o.hide_viewport = True
fp_batch.apply_white_material(objs)
for o in bpy.context.selected_objects:
    o.select_set(False)
bpy.context.view_layer.objects.active = None

bpy.ops.wm.save_as_mainfile(filepath=SAVE)
print(f"[ui_prepare] saved {SAVE}: {len(objs)} meshes")
