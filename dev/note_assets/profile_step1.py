"""STEP1 のどこで時間を使っているかを測る。

実測(v2.5.0):
    メカ    155パーツ /   50k面 ->   8.6秒
    戦車     43パーツ /  421k面 ->  19.4秒
    C62       1パーツ / 1279k面 ->  28.0秒
    霊柩馬車 138パーツ /  889k面 -> 191.0秒   <- 明らかに外れている
パーツ数が効いている疑いがあるが、推測しない。進捗ジェネレータの
yield 間隔と cProfile の両方で内訳を出す。

  blender -b --factory-startup --python profile_step1.py -- --blend <asset.blend>
"""
from __future__ import annotations

import cProfile
import json
import pstats
import sys
import time
from io import StringIO
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
TOP = int(ARGV[ARGV.index("--top") + 1]) if "--top" in ARGV else 18

bpy.ops.wm.read_homefile(use_empty=True)
fp_batch.install_addon()
from freepencil2 import vertex_color  # noqa: E402

preset = json.loads((HERE.parent / "batch" / "presets.json").read_text(
    encoding="utf-8"))["auto"]        # STEP0 の実挙動に近い方を使う
scene = bpy.context.scene
objs, others = render_samples.stage_model(Path(BLEND))
has_arm = any(o.type == "ARMATURE" for o in others)
fp_batch.apply_white_material(objs)
render_samples.apply_preset(scene, preset, 42, has_arm)
fp_batch.select_meshes()

# --- yield 間隔の内訳 -------------------------------------------------
marks: list[tuple[float, str]] = []
t0 = time.perf_counter()
gen, _state = vertex_color.make_vertex_color_gen(bpy.context, quiet=True)
for done, total, name in gen:
    marks.append((time.perf_counter() - t0, f"{done:.2f}/{total} {name}"))
wall = time.perf_counter() - t0

gaps = []
prev = 0.0
for at, label in marks:
    gaps.append((round(at - prev, 3), label))
    prev = at
gaps.sort(reverse=True)

# --- 関数単位 ---------------------------------------------------------
bpy.ops.wm.read_homefile(use_empty=True)
objs, others = render_samples.stage_model(Path(BLEND))
fp_batch.apply_white_material(objs)
render_samples.apply_preset(bpy.context.scene, preset, 42, has_arm)
fp_batch.select_meshes()

prof = cProfile.Profile()
prof.enable()
_gen, _st = vertex_color.make_vertex_color_gen(bpy.context, quiet=True)
for _ in _gen:
    pass
prof.disable()

buf = StringIO()
pstats.Stats(prof, stream=buf).sort_stats("cumulative").print_stats(TOP)
rows = []
for line in buf.getvalue().splitlines():
    parts = line.split()
    if len(parts) >= 6 and parts[0].replace(".", "").isdigit():
        rows.append({"ncalls": parts[0], "tottime": parts[1],
                     "cumtime": parts[3], "where": " ".join(parts[5:])[:70]})

print("[profile] " + json.dumps({
    "name": NAME,
    "objects": len(objs),
    "faces": int(sum(len(o.data.polygons) for o in objs)),
    "wall_seconds": round(wall, 2),
    "yields": len(marks),
    "slowest_gaps": gaps[:10],
    "top_functions": rows[:TOP],
}, ensure_ascii=False))
