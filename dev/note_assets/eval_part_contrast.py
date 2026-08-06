"""実モデルで「パーツごとの隣接輝度差」を測る。

vertex_color.py に残っていた既知の弱点:
  「メカ155体中50体が窓幅0.26側に入り、隣接輝度差の中央値が
    0.417 -> 0.225 と半減する = そのパーツの線が薄い」
これを実測で再現し、窓の作り方を変えた効果を比べる。

--scheme old を渡すと v2.5.0 の窓ずらし(幅 0.50/0.43/0.26)に戻して測る。

  blender -b --factory-startup --python eval_part_contrast.py -- \
      --blend <asset.blend> [--scheme old|new]
"""
from __future__ import annotations

import json
import statistics
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
SCHEME = ARGV[ARGV.index("--scheme") + 1] if "--scheme" in ARGV else "new"

bpy.ops.wm.read_homefile(use_empty=True)
fp_batch.install_addon()
from freepencil2 import utils  # noqa: E402

if SCHEME == "old":
    # v2.5.0 の窓: 上へずらすだけ。上限 0.85 でクランプされる
    def _old_window(part_class: int):
        tint = (part_class % 3) * 0.17
        return 0.25 + tint, min(0.85, 0.75 + tint)
    utils.part_luma_window = _old_window

objs, _others = render_samples.stage_model(Path(BLEND))
fp_batch.apply_white_material(objs)
fp_batch.select_meshes()
bpy.ops.freepencil.auto_vertex_color()

# 塗り終わった頂点カラーから、オブジェクトごとに使われている輝度を集める
per_obj: dict[str, list[float]] = {}
for obj in bpy.context.scene.objects:
    if obj.type != "MESH":
        continue
    vcols = utils.get_vertex_colors(obj)
    if "mecha_color" not in vcols:
        continue
    idx = list(vcols).index("mecha_color") if not isinstance(vcols, dict) else None
    attr = obj.data.color_attributes.get("mecha_color")
    if attr is None:
        continue
    seen = set()
    for d in attr.data:
        c = tuple(round(v, 3) for v in d.color[:3])
        seen.add(c)
    per_obj[obj.name] = sorted(utils._luma(c) for c in seen)

widths, inner_gaps, part_levels = [], [], []
for name, lumas in per_obj.items():
    if not lumas:
        continue
    widths.append(round(max(lumas) - min(lumas), 4))
    part_levels.append(lumas)
    if len(lumas) >= 2:
        gaps = [lumas[i + 1] - lumas[i] for i in range(len(lumas) - 1)]
        inner_gaps.append(statistics.median(gaps))


def stats(xs):
    if not xs:
        return None
    xs = sorted(xs)
    return {"n": len(xs), "min": round(xs[0], 4),
            "median": round(statistics.median(xs), 4),
            "max": round(xs[-1], 4)}


# 幅の分布(どれだけ潰れたパーツがあるか)
buckets: dict[str, int] = {}
for w in widths:
    key = f"{round(w, 1):.1f}"
    buckets[key] = buckets.get(key, 0) + 1

print("[contrast] " + json.dumps({
    "scheme": SCHEME,
    "blend": Path(BLEND).name,
    "objects_painted": len(per_obj),
    "window_width": stats(widths),
    "width_buckets": dict(sorted(buckets.items())),
    "inner_luma_gap": stats(inner_gaps),
    "multi_island_objects": len(inner_gaps),
}, ensure_ascii=False))
