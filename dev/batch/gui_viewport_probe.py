"""ビューポートのコンポジタに、どのパスがどう届いているかを撮る(窓のある Blender)。

  blender <file.blend> --python gui_viewport_probe.py -- <out_dir>
Composite の入力を、Render Layers の各出力へ順につなぎ替えて 3D ビューを撮る。
"""
import sys
from pathlib import Path

import bpy

ARGV = sys.argv[sys.argv.index("--") + 1:]
OUT = Path(ARGV[0]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
sc = bpy.context.scene
MODE = ARGV[1] if len(ARGV) > 1 else "CEL"
sc.fp_preview_mode = MODE
if "--sky" in ARGV:
    sc.fp_cel_shadow_line = False
    sc.fp_cel_sky = True
for o in sc.objects:
    if o.type == 'MESH':
        o.fp_line_scale = 1.0
bpy.data.objects["Monkey"].fp_line_scale = 2.0
tree = sc.node_tree
rl = next(n for n in tree.nodes if n.type == 'R_LAYERS')
comp = next(n for n in tree.nodes if n.type == 'COMPOSITE')
LBL = {"CEL": "FP_CelShade", "NONE": "FP_Underlay"}[MODE]
mine = [n for n in tree.nodes if n.label == LBL and n.outputs]
PROBES = [None, "Image"] + ["node:" + n.name for n in mine]
if "--present" in ARGV:
    sh = tree.nodes.new("CompositorNodeSeparateColor"); sh.name = "P_sep"
    tree.links.new(rl.outputs["fp_shade"], sh.inputs[0])
    g = tree.nodes.new("CompositorNodeCombineColor"); g.name = "P_G"
    tree.links.new(sh.outputs[1], g.inputs[0]); tree.links.new(sh.outputs[1], g.inputs[1]); tree.links.new(sh.outputs[1], g.inputs[2])
    a = tree.nodes.new("CompositorNodeSeparateColor"); a.name = "P_sepA"
    tree.links.new(rl.outputs["fp_shade"], a.inputs[0])
    ga = tree.nodes.new("CompositorNodeCombineColor"); ga.name = "P_A"
    for i in range(3):
        tree.links.new(a.outputs[3], ga.inputs[i])
    dz = tree.nodes.new("CompositorNodeMath"); dz.name = "P_depth"; dz.operation = "LESS_THAN"; dz.inputs[1].default_value = 1000.0
    tree.links.new(rl.outputs["Depth"], dz.inputs[0])
    for n in (g, ga, dz):
        n.label = "probe"
    PROBES = ["node:P_G", "node:P_A", "node:P_depth", "Image", "Alpha"]
print("@@@ outputs", [s.name for s in rl.outputs if s.enabled], flush=True)
state = {"i": -1, "wait": 0, "orig": comp.inputs[0].links[0].from_socket}


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
    win, area = view3d()
    if state["i"] >= 0:
        name = (PROBES[state["i"]] or "final").replace("node:", "")
        n_ = tree.nodes.get(name)
        if n_ is not None:
            name += "_" + n_.type
        with bpy.context.temp_override(window=win, area=area):
            bpy.ops.screen.screenshot_area(filepath=str(OUT / f"{state['i']:02d}_{name}.png"))
        print("@@@ shot", name, flush=True)
    state["i"] += 1
    if state["i"] >= len(PROBES):
        bpy.ops.wm.quit_blender()
        return None
    p = PROBES[state["i"]]
    for lk in list(comp.inputs[0].links):
        tree.links.remove(lk)
    if p is None:
        src = state["orig"]
    elif p.startswith("node:"):
        src = tree.nodes[p[5:]].outputs[0]
    else:
        src = rl.outputs[p]
    tree.links.new(src, comp.inputs[0])
    state["wait"] = 10
    return 0.5


def start():
    win, area = view3d()
    sp = area.spaces[0]
    # 利用者と同じ手順: STEP3 の「コンポジタープレビューを有効化」で入れる
    with bpy.context.temp_override(window=win, area=area, screen=win.screen):
        bpy.context.scene.fp_enable_compositor_view = False
        bpy.context.scene.fp_enable_compositor_view = True
    print("@@@ render_pass", sp.shading.render_pass, flush=True)
    sp.region_3d.view_perspective = 'CAMERA'
    sp.overlay.show_overlays = False
    bpy.app.timers.register(tick, first_interval=3.0)


bpy.app.timers.register(start, first_interval=2.0)
