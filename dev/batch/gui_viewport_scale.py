"""ビューポートで、合成の最後の縮小(細線化の 0.5)を通した絵と、1 にした絵を撮る。

  blender <file.blend> --python gui_viewport_scale.py -- <out_dir>
"""
import sys
from pathlib import Path

import bpy

ARGV = sys.argv[sys.argv.index("--") + 1:]
OUT = Path(ARGV[0]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
sc = bpy.context.scene
sc.fp_cel_shadow_line = False
sc.fp_cel_sky = True
for o in sc.objects:
    if o.type == 'MESH':
        o.fp_line_scale = 1.0
STEPS = [("WHITE", 0.5), ("NONE", 0.5), ("MONO_LIGHT", 0.5), ("CEL", 0.5), ("CEL", 1.0)]
state = {"i": -1, "wait": 0}


def view3d():
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                return win, area
    return None, None


def scale_node():
    tree = sc.node_tree
    return next(n for n in tree.nodes if n.type == 'SCALE' and n.get("fp_composite_scale"))


def tick():
    if state["wait"] > 0:
        state["wait"] -= 1
        return 0.5
    win, area = view3d()
    if state["i"] >= 0:
        mode, k = STEPS[state["i"]]
        with bpy.context.temp_override(window=win, area=area):
            bpy.ops.screen.screenshot_area(filepath=str(OUT / f"{state['i']:02d}_{mode}_{k}.png"))
        print("@@@ shot", mode, k, flush=True)
    state["i"] += 1
    if state["i"] >= len(STEPS):
        bpy.ops.wm.quit_blender()
        return None
    mode, k = STEPS[state["i"]]
    sc.fp_preview_mode = mode
    n = scale_node()
    n.inputs["X"].default_value = k
    n.inputs["Y"].default_value = k
    state["wait"] = 10
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
