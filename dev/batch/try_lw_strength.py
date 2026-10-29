"""キャラの線の強さ(fp_lw_strength)を変えて白で撮る。STEP0 済みの .blend から。

  blender -b --factory-startup --python try_lw_strength.py -- <.blend> <出力フォルダ> [0.6,0.45,0.35]
出力: lw_<強さ>.png(白のプレビュー)
"""
import sys
from pathlib import Path

import bpy

ARGV = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = Path(ARGV[0]), Path(ARGV[1])
VALUES = [float(v) for v in ARGV[2].split(",")] if len(ARGV) > 2 else [0.6, 0.45, 0.35]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fp_batch  # noqa: E402

fp_batch.install_addon()
bpy.ops.wm.open_mainfile(filepath=str(SRC))
sc = bpy.context.scene
OUT.mkdir(parents=True, exist_ok=True)
sc.fp_preview_mode = "WHITE"
print("@@ file", SRC.name, sc.fp_auto_style, sc.fp_line_weight, round(sc.fp_lw_strength, 2), flush=True)
for v in VALUES:
    sc.fp_lw_strength = v
    bpy.context.view_layer.update()
    sc.render.filepath = str(OUT / f"lw_{v:.2f}.png")
    bpy.ops.render.render(write_still=True)
    print("@@ shot", v, flush=True)
