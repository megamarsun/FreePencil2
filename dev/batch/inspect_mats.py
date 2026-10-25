"""保存済みの作例 .blend を開いて、材質ごとの描画方法・葉/眉の判定・面数を出す(調べもの用)。

  blender -b --factory-startup --python inspect_mats.py -- a.blend b.blend
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402

fp_batch.install_addon()
lc = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.leaf_clump"))
files = sys.argv[sys.argv.index("--") + 1:]
for f in files:
    bpy.ops.wm.open_mainfile(filepath=f)
    sc = bpy.context.scene
    objs = [o for o in sc.objects if o.type == "MESH" and not o.hide_render]
    brows = lc.brow_materials(objs)
    leaves = lc.leaf_materials(objs)
    print("=====", Path(f).name, "style", sc.fp_auto_style, "leaf_clump", sc.fp_leaf_clump,
          "aovs", [a.name for a in bpy.context.view_layer.aovs])
    used = {}
    for o in objs:
        for s in o.material_slots:
            if s.material:
                used.setdefault(s.material.name, []).append(o.name)
    for name, os_ in sorted(used.items()):
        m = bpy.data.materials[name]
        imgs = [n.image.name for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image] if m.use_nodes else []
        print(f"  {name[:34]:34} blend={getattr(m, 'blend_method', '?'):7} surf={getattr(m, 'surface_render_method', '-'):9}"
              f" leaf={'Y' if name in leaves else '-'} brow={'Y' if name in brows else '-'}"
              f" objs={len(os_)} {os_[0][:20]} imgs={imgs[:2]}")
