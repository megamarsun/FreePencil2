"""材質ごとに、拡散の色・反射の色・発光のパスに何が入るかを見る(調べもの用)。

  blender -b --factory-startup --python probe_passes.py -- out_dir

球を 6 つ(白プラ / 黒プラ / 銀 / 金 / ガラス / 赤の半金属)並べ、パスごとに PNG を書く。
"""
import math
import sys
from pathlib import Path

import bpy

OUT = Path(sys.argv[sys.argv.index("--") + 1])
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_homefile(use_empty=True)
sc = bpy.context.scene
SPECS = [  # 名前, 地の色, 金属, 透過
    ("white", (0.8, 0.8, 0.8), 0.0, 0.0), ("black", (0.02, 0.02, 0.02), 0.0, 0.0),
    ("silver", (0.9, 0.9, 0.9), 1.0, 0.0), ("gold", (1.0, 0.7, 0.3), 1.0, 0.0),
    ("glass", (1.0, 1.0, 1.0), 0.0, 1.0), ("pure_black", (0.0, 0.0, 0.0), 0.0, 0.0),
]
for i, (name, col, met, tr) in enumerate(SPECS):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.9, location=(i * 2.0 - 5.0, 0, 0))
    o = bpy.context.object
    bpy.ops.object.shade_smooth()
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*col, 1)
    p.inputs["Metallic"].default_value = met
    p.inputs["Transmission Weight"].default_value = tr
    p.inputs["Roughness"].default_value = 0.3
    o.data.materials.append(m)
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
cam.location = (0, -14, 0)
cam.rotation_euler = (math.radians(90), 0, 0)
sc.collection.objects.link(cam)
sc.camera = cam
lt = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
lt.data.energy = 4
lt.rotation_euler = (math.radians(50), 0, math.radians(30))
sc.collection.objects.link(lt)
w = bpy.data.worlds.new("W")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.05, 0.05, 1)
sc.world = w
sc.render.resolution_x, sc.render.resolution_y = 1200, 220
sc.eevee.taa_render_samples = 8
vl = sc.view_layers[0]
vl.use_pass_diffuse_color = vl.use_pass_glossy_color = vl.use_pass_emit = True
vl.use_pass_glossy_direct = vl.use_pass_diffuse_direct = True
if hasattr(vl, "use_pass_shadow"):
    vl.use_pass_shadow = True
elif hasattr(vl.eevee, "use_pass_shadow"):
    vl.eevee.use_pass_shadow = True
if hasattr(vl, "use_pass_transmission_color"):
    vl.use_pass_transmission_color = True
sc.use_nodes = True
tree = sc.compositing_node_group if hasattr(sc, "compositing_node_group") else sc.node_tree
if tree is None:
    tree = bpy.data.node_groups.new("comp", "CompositorNodeTree")
    sc.compositing_node_group = tree
for n in list(tree.nodes):
    tree.nodes.remove(n)
rl = tree.nodes.new("CompositorNodeRLayers")
print("SOCKETS", [s.name for s in rl.outputs if s.enabled])
try:
    comp = tree.nodes.new("CompositorNodeComposite")
    inp = comp.inputs[0]
except RuntimeError:
    comp = tree.nodes.new("NodeGroupOutput")
    tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    inp = comp.inputs[0]
for s in rl.outputs:
    if not s.enabled or s.name in ("Alpha", "Depth", "Normal", "Vector", "Image", "Emit", "GlossDir"):
        continue
    for lk in list(inp.links):
        tree.links.remove(lk)
    tree.links.new(s, inp)
    sc.render.filepath = str(OUT / f"pass_{s.name.replace(' ', '_')}.png")
    bpy.ops.render.render(write_still=True)
