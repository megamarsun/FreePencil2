"""blend の材質のノードとつなぎを出す(調べもの用)。

  blender -b --factory-startup --python dump_nodes.py -- file.blend 材質名の一部 [材質名の一部 ...]
"""
import sys

import bpy

args = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.open_mainfile(filepath=args[0])
for m in bpy.data.materials:
    if not any(k.lower() in m.name.lower() for k in args[1:]):
        continue
    print("=====", m.name, "blend", getattr(m, "blend_method", "?"),
          "surf", getattr(m, "surface_render_method", "-"), "users", m.users)
    if not m.use_nodes:
        continue
    for n in m.node_tree.nodes:
        extra = ""
        if n.type == "TEX_IMAGE" and n.image:
            extra = f" img={n.image.name} cs={n.image.colorspace_settings.name} alpha={n.image.alpha_mode}"
        if n.type == "BSDF_PRINCIPLED":
            vals = {s.name: (round(s.default_value, 3) if isinstance(s.default_value, float) else None)
                    for s in n.inputs if not s.is_linked and s.name in
                    ("Metallic", "Alpha", "Transmission Weight", "Roughness", "Subsurface Weight", "IOR")}
            bc = n.inputs["Base Color"]
            extra = f" {vals} base={'linked' if bc.is_linked else tuple(round(v, 2) for v in bc.default_value)}"
        if n.type == "GROUP" and n.node_tree:
            extra = f" group={n.node_tree.name}"
        print(f"  [{n.type}] {n.name}{extra}")
    for lk in m.node_tree.links:
        print(f"    {lk.from_node.name}.{lk.from_socket.name} -> {lk.to_node.name}.{lk.to_socket.name}")
