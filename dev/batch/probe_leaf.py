"""保存済みの作例で、プレビューごとに葉のかたまりのノードが挿さっているか、target の上流を出す(調べもの用)。

  blender -b --factory-startup --python probe_leaf.py -- a.blend ...
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402

fp_batch.install_addon()
for f in sys.argv[sys.argv.index("--") + 1:]:
    bpy.ops.wm.open_mainfile(filepath=f)
    sc = bpy.context.scene
    tree = sc.compositing_node_group if hasattr(sc, "compositing_node_group") and sc.compositing_node_group else sc.node_tree
    print("=====", Path(f).name, "leaf_clump", sc.fp_leaf_clump, "film_transparent", sc.render.film_transparent)
    for mode in ("WHITE", "NONE", "CEL"):
        sc.fp_preview_mode = mode
        n_leaf = len([n for n in tree.nodes if n.label == "FreePencil_leaf_clump"])
        sa = [n for n in tree.nodes if n.label == "FreePencil_leaf_clump" and n.bl_idname == "CompositorNodeSetAlpha"]
        down = [f"{lk.to_node.name}.{lk.to_socket.name}" for n in sa for lk in n.outputs[0].links]
        print(f"  {mode}: leaf nodes={n_leaf} setalpha->{down}")


def chain(tree, node, depth=0, seen=None):
    seen = seen if seen is not None else set()
    if node.name in seen or depth > 12:
        return
    seen.add(node.name)
    for o in node.outputs:
        for lk in o.links:
            print("    " * 1 + "  " * depth + f"{node.name}[{node.bl_idname[13:]}].{o.name} -> {lk.to_node.name}.{lk.to_socket.name}")
            chain(tree, lk.to_node, depth + 1, seen)


for f in sys.argv[sys.argv.index("--") + 1:]:
    bpy.ops.wm.open_mainfile(filepath=f)
    sc = bpy.context.scene
    tree = sc.compositing_node_group if hasattr(sc, "compositing_node_group") and sc.compositing_node_group else sc.node_tree
    sc.fp_preview_mode = "NONE"
    sa = [n for n in tree.nodes if n.label == "FreePencil_leaf_clump" and n.bl_idname == "CompositorNodeSetAlpha"][0]
    print("##### NONE downstream", Path(f).name)
    chain(tree, sa)
    src = [n for n in tree.nodes if n.label == "FreePencil_leaf_clump" and n.bl_idname == "CompositorNodeSeparateColor"][0]
    lk = src.inputs[0].links[0]
    print("  src from", lk.from_node.name, lk.from_node.bl_idname, lk.from_socket.name)
