"""STEP0(全自動セットアップ)の実時間を測る。

記事に書く「処理時間」は、ユーザーがボタンを押してから終わるまで =
freepencil.auto_setup 1回分。STEP1 単体ではない。

  blender -b --factory-startup --python time_step0.py -- --blend <asset.blend> --name mecha
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
sys.path.insert(0, str(HERE))

import fp_batch          # noqa: E402
import render_samples    # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
BLEND = ARGV[ARGV.index("--blend") + 1]
NAME = ARGV[ARGV.index("--name") + 1] if "--name" in ARGV else Path(BLEND).stem

bpy.ops.wm.read_homefile(use_empty=True)
fp_batch.install_addon()

objs, _others = render_samples.stage_model(Path(BLEND))
fp_batch.apply_white_material(objs)
fp_batch.select_meshes()

t0 = time.perf_counter()
res = bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
elapsed = time.perf_counter() - t0

print("[time_step0] " + json.dumps({
    "name": NAME,
    "blender": bpy.app.version_string,
    "mesh_objects": len(objs),
    "faces_total": int(sum(len(o.data.polygons) for o in objs)),
    "result": list(res),
    "step0_seconds": round(elapsed, 2),
}, ensure_ascii=False))
