"""保存済みの作例で、塗り分けの頂点カラーを Attribute -> Emission で素通しにして撮る(調べもの用)。

  blender -b --factory-startup --python probe_vcol.py -- file.blend out.png [mecha_color] [--hide-leaves]

--hide-leaves: 葉の材質(fp_leaf の AOV がある材質)を透明にして、枝だけを見る。
"""
import sys
from pathlib import Path

import bpy

args = sys.argv[sys.argv.index("--") + 1:]
src, out = args[0], Path(args[1]).resolve()
layer = next((a for a in args[2:] if not a.startswith("--")), "mecha_color")
hide = "--hide-leaves" in args
bpy.ops.wm.open_mainfile(filepath=src)
sc = bpy.context.scene
sc.use_nodes = False
if hasattr(sc, "compositing_node_group"):
    sc.compositing_node_group = None
sc.render.film_transparent = True
for m in bpy.data.materials:
    if not m.use_nodes or m.node_tree is None:
        continue
    nt = m.node_tree
    leaf = any(n.type == "OUTPUT_AOV" and n.aov_name == "fp_leaf" for n in nt.nodes)
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    if leaf and hide:
        t = nt.nodes.new("ShaderNodeBsdfTransparent")
        nt.links.new(t.outputs[0], o.inputs["Surface"])
        m.blend_method = "HASHED" if hasattr(m, "blend_method") else None
        continue
    a = nt.nodes.new("ShaderNodeAttribute")
    a.attribute_name = layer
    e = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(a.outputs["Color"], e.inputs["Color"])
    nt.links.new(e.outputs[0], o.inputs["Surface"])
sc.view_settings.view_transform = "Standard"
sc.render.filepath = str(out)
bpy.ops.render.render(write_still=True)
print("@@@ wrote", out)
