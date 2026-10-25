"""試作 B案: 決まりはそのままにして、卵を AI の窓口の道具で手直しする(保存済みの作例に当てて撮る)。

  blender -b --factory-startup --python exp_eggs_b.py -- file.blend out_dir

卵(名前が ovo の物)に ai.merge を当てる。merge は塗り分け(mecha_color / bone_color)を 1 色に
そろえる道具で、手描き背景の「細い線」(fine_color)は触らない。
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402

fp_batch.install_addon()
ai = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.ai"))
src, out = sys.argv[sys.argv.index("--") + 1:][:2]
out = Path(out)
out.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=src)
sc = bpy.context.scene
eggs = [o.name for o in sc.objects if o.type == "MESH" and o.name.startswith("ovo")]
print("@@@", ai.merge({"objects": eggs}).get("done"))
for i, mode in enumerate(("WHITE", "NONE", "CEL"), 1):
    sc.fp_preview_mode = mode
    sc.render.filepath = str(out / f"{i}_{mode}.png")
    bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=str(out / "eggs_bowl.blend"))
