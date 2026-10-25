"""保存済みの作例で、線のチャンネルを 1 つずつ止めて白を撮る(どの線が悪さをしているかを見る)。

  blender -b --factory-startup --python exp_channels.py -- file.blend out_dir
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402

fp_batch.install_addon()
src, out = sys.argv[sys.argv.index("--") + 1:][:2]
out = Path(out)
out.mkdir(parents=True, exist_ok=True)
CASES = [("all", {}), ("no_depth", {"fp_ch_depth": 0.0}), ("no_bone", {"fp_ch_bone": 0.0}),
         ("no_mecha", {"fp_ch_mecha": 0.0}), ("no_mat", {"fp_ch_mat": 0.0}),
         ("no_weight", {"fp_line_weight": False})]
for name, props in CASES:
    bpy.ops.wm.open_mainfile(filepath=src)
    sc = bpy.context.scene
    sc.fp_preview_mode = "WHITE"
    for k, v in props.items():
        setattr(sc, k, v)
    sc.render.filepath = str(out / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    print("@@@", name, {k: getattr(sc, k) for k in props})
