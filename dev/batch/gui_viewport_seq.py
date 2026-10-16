"""ビューポートで プレビューを順に切り替えた後、セルの途中のノードを撮る(線が消える順番の調べ)。

  blender <file.blend> --python gui_viewport_seq.py -- <out_dir> NONE,MONO_LIGHT,CEL
"""
import sys
from pathlib import Path

import bpy

ARGV = sys.argv[sys.argv.index("--") + 1:]
OUT = Path(ARGV[0]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
SEQ = ARGV[1].split(",")
sc = bpy.context.scene
sc.fp_cel_shadow_line = False
sc.fp_cel_sky = True
for o in sc.objects:
    if o.type == 'MESH':
        o.fp_line_scale = 1.0
state = {"phase": "seq", "i": 0, "wait": 0, "probes": [], "orig": None}


def view3d():
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                return win, area
    return None, None


def shot(name):
    win, area = view3d()
    with bpy.context.temp_override(window=win, area=area):
        bpy.ops.screen.screenshot_area(filepath=str(OUT / f"{name}.png"))


def tick():
    if state["wait"] > 0:
        state["wait"] -= 1
        return 0.5
    tree = sc.node_tree
    comp = next(n for n in tree.nodes if n.type == 'COMPOSITE')
    if state["phase"] == "seq":
        if state["i"] > 0:
            shot(f"s{state['i'] - 1:02d}_{SEQ[state['i'] - 1]}")
        if state["i"] < len(SEQ):
            sc.fp_preview_mode = SEQ[state["i"]]
            state["i"] += 1
            state["wait"] = 10
            return 0.5
        mine = [n for n in tree.nodes if n.label == "FP_CelShade" and n.outputs]
        state["probes"] = [n.name for n in mine if n.type in ("ALPHAOVER", "MIX_RGB", "SETALPHA")]
        state["orig"] = comp.inputs[0].links[0].from_socket
        state["phase"] = "probe"
        state["i"] = -1
        sc_node = comp.inputs[0].links[0].from_node
        final = sc_node.inputs[0].links[0].from_socket
        ns = tree.nodes.new("CompositorNodeScale")
        ns.space = "RELATIVE"
        ns.inputs["X"].default_value = 0.5
        ns.inputs["Y"].default_value = 0.5
        tree.links.new(final, ns.inputs[0])
        print("@@@ old scale", sc_node.space, getattr(sc_node, "frame_method", None),
              [(i.name, getattr(i, "default_value", None)) for i in sc_node.inputs][1:], flush=True)
        print("@@@ new scale", ns.space, getattr(ns, "frame_method", None),
              [(i.name, getattr(i, "default_value", None)) for i in ns.inputs][1:], flush=True)
        state["acts"] = [("a_old_scale", None), ("b_new_scale", ns.outputs[0]), ("c_direct", final)]
        state["phase"] = "acts"
        state["i"] = 0
        state["wait"] = 10
        return 0.5
    if state["phase"] == "acts":
        name, sock = state["acts"][state["i"]]
        if sock is not None:
            for lk in list(comp.inputs[0].links):
                tree.links.remove(lk)
            tree.links.new(sock, comp.inputs[0])
            state["acts"][state["i"]] = (name, None)
            state["wait"] = 10
            return 0.5
        shot(name)
        state["i"] += 1
        if state["i"] >= len(state["acts"]):
            bpy.ops.wm.quit_blender()
            return None
        state["wait"] = 2 if state["acts"][state["i"]][1] is None else 0
        if state["acts"][state["i"]][0] == "d_wait_more":
            state["wait"] = 30
        return 0.5
    if state["i"] >= 0:
        shot(f"p{state['i']:02d}_{state['probes'][state['i']]}")
    state["i"] += 1
    if state["i"] >= len(state["probes"]):
        bpy.ops.wm.quit_blender()
        return None
    for lk in list(comp.inputs[0].links):
        tree.links.remove(lk)
    tree.links.new(tree.nodes[state["probes"][state["i"]]].outputs[0], comp.inputs[0])
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
