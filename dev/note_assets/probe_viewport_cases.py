"""4.2 のビューポートコンポジタが何を評価できないかを切り分ける (GUI)。

FreePencil のプレビューは 4.2 で真っ白になる。原因が
(A) ビューポートコンポジタ自体 / (B) ノードグループ / (C) AOV入力
のどれかを、最小グラフを差し替えながら撮って特定する。

  blender --factory-startup -p 0 0 1600 1000 <prepared.blend> \
      --python probe_viewport_cases.py -- --out <abs dir> --tag 4.2.3
"""
from __future__ import annotations

import sys
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))

import fp_batch  # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = Path(ARGV[ARGV.index("--out") + 1])
TAG = ARGV[ARGV.index("--tag") + 1]
OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / f"cases_{TAG}.log"
LOG.write_text("", encoding="utf-8")


def log(msg) -> None:
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(str(msg) + "\n")


def main_window():
    return bpy.context.window_manager.windows[0]


def view3d():
    for area in main_window().screen.areas:
        if area.ui_type == "VIEW_3D":
            return area
    return None


def comp_tree():
    scene = bpy.context.scene
    if hasattr(scene, "compositing_node_group"):
        return scene.compositing_node_group
    return scene.node_tree


def clear_tree(tree):
    for n in list(tree.nodes):
        tree.nodes.remove(n)


def out_node(tree):
    """このバージョンでの最終出力ノードを作る。"""
    name = "CompositorNodeComposite" if hasattr(
        bpy.types, "CompositorNodeComposite") else "NodeGroupOutput"
    return tree.nodes.new(name)


def rlayers(tree):
    return tree.nodes.new("CompositorNodeRLayers")


# ---------------------------------------------------------------- 各ケース
def case_a(tree):
    """素の合成: RenderLayers.Image -> Invert -> 出力"""
    clear_tree(tree)
    rl, inv, co = rlayers(tree), tree.nodes.new("CompositorNodeInvert"), out_node(tree)
    inv.location, co.location = (300, 0), (600, 0)
    tree.links.new(rl.outputs["Image"], inv.inputs[1])
    tree.links.new(inv.outputs[0], co.inputs[0])
    return "A_plain_invert"


def case_b(tree):
    """ノードグループ経由: RenderLayers.Image -> [Group: Invert] -> 出力"""
    clear_tree(tree)
    grp = bpy.data.node_groups.new("FP_ProbeGroup", "CompositorNodeTree")
    gin = grp.nodes.new("NodeGroupInput")
    gout = grp.nodes.new("NodeGroupOutput")
    ginv = grp.nodes.new("CompositorNodeInvert")
    gin.location, ginv.location, gout.location = (-300, 0), (0, 0), (300, 0)
    if hasattr(grp, "interface"):
        grp.interface.new_socket("Image", in_out="INPUT",
                                 socket_type="NodeSocketColor")
        grp.interface.new_socket("Image", in_out="OUTPUT",
                                 socket_type="NodeSocketColor")
    else:
        grp.inputs.new("NodeSocketColor", "Image")
        grp.outputs.new("NodeSocketColor", "Image")
    grp.links.new(gin.outputs[0], ginv.inputs[1])
    grp.links.new(ginv.outputs[0], gout.inputs[0])

    rl, node, co = rlayers(tree), tree.nodes.new("CompositorNodeGroup"), out_node(tree)
    node.node_tree = grp
    node.location, co.location = (300, 0), (600, 0)
    tree.links.new(rl.outputs["Image"], node.inputs[0])
    tree.links.new(node.outputs[0], co.inputs[0])
    return "B_node_group"


def case_c(tree):
    """AOV入力: RenderLayers.mecha_color -> 出力"""
    clear_tree(tree)
    rl, co = rlayers(tree), out_node(tree)
    co.location = (600, 0)
    sock = rl.outputs.get("mecha_color")
    if sock is None:
        log("case C: mecha_color 出力が無い / available=" +
            str([s.name for s in rl.outputs]))
        sock = rl.outputs["Image"]
    tree.links.new(sock, co.inputs[0])
    return "C_aov_direct"


CASES = [case_a, case_b, case_c]
_state = {"phase": 0, "i": 0, "label": ""}


def shoot(name: str) -> None:
    area, win = view3d(), main_window()
    region = next((r for r in area.regions if r.type == "WINDOW"), None)
    with bpy.context.temp_override(window=win, screen=win.screen,
                                   area=area, region=region):
        bpy.ops.screen.screenshot_area(filepath=str(OUT / f"case_{TAG}_{name}.png"))
    log(f"shot case_{TAG}_{name}.png")


def tick():
    try:
        area = view3d()
        space = area.spaces.active
        win = main_window()
        region = next((r for r in area.regions if r.type == "WINDOW"), None)

        if _state["phase"] == 0:
            meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
            for o in meshes:
                o.select_set(True)
            if meshes:
                bpy.context.view_layer.objects.active = meshes[0]
            bpy.context.scene.fp_enable_compositor_view = True
            log("auto_setup: " + str(list(
                bpy.ops.freepencil.auto_setup("EXEC_DEFAULT"))))
            space.shading.type = "RENDERED"
            space.shading.use_compositor = "ALWAYS"
            space.overlay.show_overlays = False
            with bpy.context.temp_override(window=win, screen=win.screen,
                                           area=area, region=region):
                bpy.ops.view3d.view_all()
            _state["phase"] = 1
            return 5.0

        if _state["phase"] == 1:
            if _state["i"] >= len(CASES):
                log("done")
                bpy.ops.wm.quit_blender()
                return None
            tree = comp_tree()
            _state["label"] = CASES[_state["i"]](tree)
            log(f"built {_state['label']} nodes={[n.type for n in tree.nodes]}")
            area.tag_redraw()
            _state["phase"] = 2
            return 5.0

        if _state["phase"] == 2:
            shoot(_state["label"])
            _state["i"] += 1
            _state["phase"] = 1
            return 0.5
    except Exception:
        import traceback
        log("ERROR\n" + traceback.format_exc())
        bpy.ops.wm.quit_blender()
        return None


try:
    log(f"start {bpy.app.version_string}")
    fp_batch.install_addon()
    bpy.app.timers.register(tick, first_interval=1.5)
except Exception:
    import traceback
    log("SETUP ERROR\n" + traceback.format_exc())
