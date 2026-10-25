"""試作: 保存済みの作例で、葉の材質を持つ物の線の太さ(fp_line_scale)を変えて白を撮る。

  blender -b --factory-startup --python exp_lscale.py -- file.blend out_dir 0.5,0.7
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402

fp_batch.install_addon()
lc = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.leaf_clump"))
src, out, vals = sys.argv[sys.argv.index("--") + 1:][:3]
out = Path(out)
out.mkdir(parents=True, exist_ok=True)
for v in [float(x) for x in vals.split(",")]:
    bpy.ops.wm.open_mainfile(filepath=src)
    sc = bpy.context.scene
    sc.fp_preview_mode = "WHITE"
    for o in sc.objects:
        if o.type == "MESH" and any(s.material and lc.LEAF_RE.search(s.material.name)
                                    for s in o.material_slots):
            o.fp_line_scale = v
            print("@@@", o.name, v)
    sc.render.filepath = str(out / f"lscale_{v:.2f}.png")
    bpy.ops.render.render(write_still=True)
