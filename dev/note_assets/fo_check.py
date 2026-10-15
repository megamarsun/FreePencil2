"""ファイル出力(線・色・光・影)を書き出して、1 枚ずつ並べる。

  blender -b --factory-startup --python fo_check.py -- <out_dir> [--style BACKGROUND] [--cel]
"""
import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:]
OUT = Path(ARGV[0]).resolve()
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "batch"))
STYLE_ARG = None
import bpy, fp_batch          # noqa: E402

fp_batch.install_addon()
OUT.mkdir(parents=True, exist_ok=True)
exec(open(Path(__file__).resolve().parent / "mat_fix_check.py", encoding="utf-8").read().split("for style in")[0].split("OUT.mkdir(parents=True, exist_ok=True)")[1])
sc = scene_setup()
sc.fp_auto_style = arg("--style", "WEIGHTED")
bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
if "--cel" in ARGV:
    sc.fp_preview_mode = "CEL"
sc.fp_file_output = True
for k in [p for p in dir(sc) if p.startswith("fp_fo_")]:
    setattr(sc, k, True)
sc.fp_file_output_path = str(OUT) + "/"
bpy.ops.freepencil2.link_button()
sc.render.filepath = str(OUT / "composite.png")
bpy.ops.render.render(write_still=True)
print("@@@ wrote", sorted(p.name for p in OUT.iterdir()), flush=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "fo.blend"))
