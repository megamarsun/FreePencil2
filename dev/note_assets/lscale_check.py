"""物ごとの線の太さを絵で確かめる。サル 2 / 箱 0.5 / 地面 0、全部 1 との比較。

  blender -b --factory-startup --python lscale_check.py -- <out_dir>
"""
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:]
OUT = Path(ARGV[0]).resolve()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "batch"))
import bpy, fp_batch          # noqa: E402
import math                   # noqa: E402,F401

fp_batch.install_addon()
OUT.mkdir(parents=True, exist_ok=True)
exec(open(Path(__file__).resolve().parent / "mat_fix_check.py", encoding="utf-8").read().split("for style in")[0].split("OUT.mkdir(parents=True, exist_ok=True)")[1])
for style in ("PRECISE", "WEIGHTED"):
    sc = scene_setup()
    sc.fp_auto_style = style
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    objs = {o.name: o for o in sc.objects if o.type == "MESH"}
    for mode in ("WHITE", "NONE"):
        sc.fp_preview_mode = mode
        for o in objs.values():
            o.fp_line_scale = 1.0
        sc.render.filepath = str(OUT / f"{style}_{mode}_all1.png")
        bpy.ops.render.render(write_still=True)
        objs["Suzanne"].fp_line_scale = 2.0
        objs["Cube"].fp_line_scale = 0.5
        objs["Plane"].fp_line_scale = 0.0
        sc.render.filepath = str(OUT / f"{style}_{mode}_mixed.png")
        bpy.ops.render.render(write_still=True)
        objs["Suzanne"].fp_line_scale = 3.0                 # 値だけ変える(作り直さずに効くか)
        sc.render.filepath = str(OUT / f"{style}_{mode}_monkey3.png")
        bpy.ops.render.render(write_still=True)
        print("@@@", style, mode, flush=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{style}.blend"))
