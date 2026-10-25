"""試作: 保存済みの作例で、シーンのプロパティを変えて STEP3 を作り直し、白を撮る。

  blender -b --factory-startup --python exp_props.py -- file.blend out_dir "name:k=v;k=v" ["name2:..."]
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402

fp_batch.install_addon()
props = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.props"))
args = sys.argv[sys.argv.index("--") + 1:]
src, out = args[0], Path(args[1])
out.mkdir(parents=True, exist_ok=True)
for case in args[2:]:
    name, _, kvs = case.partition(":")
    bpy.ops.wm.open_mainfile(filepath=src)
    sc = bpy.context.scene
    vals = {}
    for kv in filter(None, kvs.split(";")):
        k, v = kv.split("=")
        cur = getattr(sc, k)
        vals[k] = type(cur)(float(v)) if not isinstance(cur, str) else v
    props._write_quiet(sc, vals)
    sc.fp_preview_mode = "WHITE"
    props._rebuild_step3(bpy.context)
    sc.render.filepath = str(out / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    print("@@@", name, {k: getattr(sc, k) for k in vals})
