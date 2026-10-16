"""ビューポートのセルで細い線がどこで消えるか: セルの中の各段を Composite へつないで撮る(等倍の領域)。
  blender <file.blend> --python gui_cel_thin.py -- <out_dir>
"""
import sys
from pathlib import Path
import bpy

OUT = Path(sys.argv[sys.argv.index("--") + 1:][0]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
sc = bpy.context.scene
sc.fp_cel_shadow_line = False
sc.fp_cel_sky = True
for o in sc.objects:
    if o.type == 'MESH':
        o.fp_line_scale = 1.0
state = {"i": -1, "wait": 0, "probes": None}


def view3d():
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                return win, area
    return None, None


def tick():
    if state["wait"] > 0:
        state["wait"] -= 1
        return 0.5
    tree = sc.node_tree
    comp = next(n for n in tree.nodes if n.type == 'COMPOSITE')
    if state["probes"] is None:
        sc.fp_preview_mode = "CEL"
        sc_node = comp.inputs[0].links[0].from_node
        sc_node.inputs["X"].default_value = 1.0
        sc_node.inputs["Y"].default_value = 1.0
        final = sc_node.inputs[0].links[0].from_socket
        cel = [n for n in tree.nodes if n.label == "FP_CelShade"]
        over = next(n for n in cel if n.type == "ALPHAOVER")
        src = next(s for s in over.inputs if s.is_linked).links[0].from_socket
        clamp = next(n for n in cel if n.type == "MIX_RGB" and n.inputs[1].is_linked
                     and n.inputs[1].links[0].from_node == over)
        mul = next(n for n in cel if n.type == "MIX_RGB" and n.blend_type == "MULTIPLY"
                   and any(i.is_linked and i.links[0].from_node == clamp for i in n.inputs))
        body = next(i for i in mul.inputs[1:3] if i.is_linked and i.links[0].from_node != clamp).links[0].from_socket
        t1 = tree.nodes.new("CompositorNodeMixRGB"); t1.blend_type = "MULTIPLY"; t1.inputs[0].default_value = 1.0
        tree.links.new(clamp.outputs[0], t1.inputs[1]); tree.links.new(body, t1.inputs[2])
        bw = tree.nodes.new("CompositorNodeRGBToBW"); tree.links.new(clamp.outputs[0], bw.inputs[0])
        inv = tree.nodes.new("CompositorNodeMath"); inv.operation = "SUBTRACT"; inv.inputs[0].default_value = 1.0
        tree.links.new(bw.outputs[0], inv.inputs[1])
        t2 = tree.nodes.new("CompositorNodeMixRGB"); t2.blend_type = "MIX"
        tree.links.new(inv.outputs[0], t2.inputs[0]); tree.links.new(body, t2.inputs[1]); t2.inputs[2].default_value = (0, 0, 0, 1)
        state["probes"] = [("0_src", src), ("2_clamp", clamp.outputs[0]), ("4_mul", mul.outputs[0]),
                           ("5_body", body), ("6_mul_swapped", t1.outputs[0]), ("7_mix_by_ink", t2.outputs[0]),
                           ("3_final", final)]
        state["comp"] = comp
        state["wait"] = 8
        return 0.5
    win, area = view3d()
    if state["i"] >= 0:
        with bpy.context.temp_override(window=win, area=area):
            bpy.ops.screen.screenshot_area(filepath=str(OUT / f"{state['probes'][state['i']][0]}.png"))
    state["i"] += 1
    if state["i"] >= len(state["probes"]):
        bpy.ops.wm.quit_blender()
        return None
    for lk in list(state["comp"].inputs[0].links):
        tree.links.remove(lk)
    tree.links.new(state["probes"][state["i"]][1], state["comp"].inputs[0])
    state["wait"] = 8
    return 0.5


def start():
    win, area = view3d()
    sp = area.spaces[0]
    with bpy.context.temp_override(window=win, area=area, screen=win.screen):
        sc.fp_enable_compositor_view = False
        sc.fp_enable_compositor_view = True
    sp.region_3d.view_perspective = 'CAMERA'
    sp.overlay.show_overlays = False
    bpy.app.timers.register(tick, first_interval=3.0)


bpy.app.timers.register(start, first_interval=2.0)
