"""滑らかな形の内側の線(v3.0)。チャンネル「内側(丸み)」fp_ch_inner、既定 0(何も挿さない)。

折れ目も色の境目も無い所(猫の前足の付け根、あご、皿のくぼみ、鼻の脇)は、どのチャンネルにも
線が出なかった。面がこちらを向く度合い N·V を材質から AOV(fp_ndv)で書き出し、その「谷」
(まわりより急にこちらを向かなくなる所)を線にする。DeCarlo の示唆輪郭を画像で近似したもの。

  d = ぼかした N·V - N·V(物の中だけで平均する。物の縁はぼかし幅だけ削る)
  谷 = d が t を超え、しかも d の尾根(d - ぼかした d > 0)の所。尾根だけ取るので帯にならない
  今の線のそば(ぼかし幅の 2 倍)は消す。皿のふちが二重になった(試作の画像で確認)
  t = 0.08 / 強さ。強さ 1 で試作の既定、2 で谷の浅い所まで出る

N·V は材質の Geometry の法線から取る(スムーズの法線。ノーマルマップの凹凸は入らない)。
線の絵(白地に黒線)へ黒で掛ける。強弱の後ろ、細線化の縮小の手前(2 倍の大きさ)で掛ける。
"""
from __future__ import annotations

import bpy

from . import compat

LABEL = "FreePencil_inner_line"
AOV = "fp_ndv"
MAT_LABEL = "FreePencil_ndv_aov"
INK = 0.8                   # 線の濃さ(試作の見た目に合わせた)


def strength(scene) -> float:
    return float(getattr(scene, "fp_ch_inner", 0.0))


def needed(scene) -> bool:
    return strength(scene) > 1e-3


def ensure_aov(scene, view_layer) -> int:
    """材質とビューレイヤーに N·V の AOV を用意する。足した材質の数を返す。"""
    from .cel_shade import _iter_materials
    if AOV not in [a.name for a in view_layer.aovs]:
        a = view_layer.aovs.add()
        a.name = AOV
        a.type = 'VALUE'
    added = 0
    done = set()
    for m in _iter_materials(scene):
        if m.name in done:
            continue
        done.add(m.name)
        nodes = m.node_tree.nodes
        if any(n.label == MAT_LABEL for n in nodes):
            continue
        geo = nodes.new("ShaderNodeNewGeometry")
        dot = nodes.new("ShaderNodeVectorMath")
        dot.operation = 'DOT_PRODUCT'
        ab = nodes.new("ShaderNodeMath")
        ab.operation = 'ABSOLUTE'
        out = nodes.new("ShaderNodeOutputAOV")
        out.aov_name = AOV
        for i, n in enumerate((geo, dot, ab, out)):
            n.label = MAT_LABEL
            n.location = (10 + 180 * i, 1200)
            n.hide = True
        links = m.node_tree.links
        links.new(geo.outputs["Normal"], dot.inputs[0])
        links.new(geo.outputs["Incoming"], dot.inputs[1])
        links.new(dot.outputs["Value"], ab.inputs[0])
        links.new(ab.outputs[0], out.inputs["Value"])
        added += 1
    if added:
        view_layer.update()
    return added


def remove_material_nodes() -> None:
    for m in bpy.data.materials:
        if m.use_nodes and m.node_tree is not None:
            for n in [n for n in m.node_tree.nodes if n.label == MAT_LABEL]:
                m.node_tree.nodes.remove(n)


def apply(tree, scene, rl, target) -> int:
    """target へ入る線の絵に内側の線を足す。挿したノードの数を返す。"""
    from . import line_weight
    from .cel_shade import on_white
    for n in [n for n in tree.nodes if n.label == LABEL]:
        tree.nodes.remove(n)
    if not needed(scene) or target is None or not target.is_linked:
        return 0
    nsock = compat.render_layer_socket(rl, (AOV,))
    asock = rl.outputs.get("Alpha")
    if nsock is None or asock is None:
        return 0
    src = target.links[0].from_socket
    # ぼかし幅は絵の幅に比例させる(試作: 幅 2560px で 8px)
    r = scene.render
    width = r.resolution_x * r.resolution_percentage / 100.0
    s = max(2, int(round(8 * width / 2560.0)))
    t = 0.08 / max(0.05, min(2.0, strength(scene)))
    x0, y0 = target.node.location.x - 1800, target.node.location.y - 700
    made = []

    def add(type_name, dx, dy=0):
        n = compat.new_node(tree, type_name)
        n.label = LABEL
        n.location = (x0 + dx, y0 + dy)
        n.hide = True
        made.append(n)
        return n

    def math(op, a, b, dx, dy=0, clamp=False):
        n = line_weight._math(tree, op, x0 + dx, y0 + dy)
        n.label = LABEL
        n.use_clamp = clamp
        made.append(n)
        for i, v in enumerate((a, b)):
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            elif v is not None:
                tree.links.new(v, n.inputs[i])
        return n.outputs[0]

    def blur(sock, px, dx, dy):
        n = add("CompositorNodeBlur", dx, dy)
        line_weight._set_blur(n, px)
        tree.links.new(sock, n.inputs[0])
        return n.outputs[0]

    def grow(sock, px, dx, dy):
        n = add("CompositorNodeDilateErode", dx, dy)
        line_weight._set_dilate(n, px)
        tree.links.new(sock, n.inputs[0])
        return n.outputs[0]

    # 物の中(アルファがあって N·V が書かれている所)
    inside = math("MULTIPLY", math("GREATER_THAN", asock, 0.5, 0, 0),
                  math("GREATER_THAN", nsock, 0.001, 0, 60), 150, 30)
    nv = math("MULTIPLY", nsock, inside, 300, 0)
    # Blender のガウスぼかしは半径で指定する。試作の sigma に合わせて 3 倍にする
    g = math("DIVIDE", blur(nv, 3 * s, 450, 0),
             math("MAXIMUM", blur(inside, 3 * s, 450, 60), 0.001, 600, 60), 750, 0)
    core = grow(inside, -s, 450, 120)
    d = math("MULTIPLY", math("SUBTRACT", g, nv, 900, 0), core, 1050, 0)
    ridge = math("SUBTRACT", d, blur(d, 3 * 2, 1200, 60), 1350, 60)
    k = math("MULTIPLY",
             math("DIVIDE", math("SUBTRACT", d, t, 1200, 0), t, 1350, 0, clamp=True),
             math("DIVIDE", math("SUBTRACT", ridge, 0.004, 1500, 60), 0.004, 1650, 60, clamp=True),
             1800, 0)
    # 今の線のそばは消す
    over_out = on_white(tree, add, src, 0, -150)
    bw = add("CompositorNodeRGBToBW", 150, -150)
    tree.links.new(over_out, bw.inputs[0])
    have = math("LESS_THAN", bw.outputs[0], 0.6, 300, -150)
    near = grow(have, 2 * s, 450, -150)
    k = math("MULTIPLY", k, math("SUBTRACT", 1.0, near, 600, -150, clamp=True), 1950, 0)
    ink = math("MULTIPLY", k, INK, 2100, 0)
    # 白地に黒線へ掛ける。アルファは元の線の絵と線の濃さの大きい方(透過背景でも消えない)
    f = math("SUBTRACT", 1.0, ink, 2250, 0)
    rgb = add("CompositorNodeCombineColor", 2400, 0)
    for i in range(3):
        tree.links.new(f, rgb.inputs[i])
    rgb.inputs[3].default_value = 1.0
    mul = add("CompositorNodeMixRGB", 2550, 0)
    compat.set_node_value(mul, "blend_type", "MULTIPLY")
    mul.inputs[0].default_value = 1.0
    tree.links.new(src, mul.inputs[1])
    tree.links.new(rgb.outputs[0], mul.inputs[2])
    sep_a = add("CompositorNodeSeparateColor", 2400, 80)
    tree.links.new(src, sep_a.inputs[0])
    alpha = math("MAXIMUM", sep_a.outputs[3], ink, 2550, 80)
    sa = add("CompositorNodeSetAlpha", 2700, 0)
    compat.set_node_value(sa, "mode", "REPLACE_ALPHA")
    tree.links.new(mul.outputs[0], sa.inputs["Image"])
    tree.links.new(alpha, sa.inputs["Alpha"])
    for lk in list(target.links):
        tree.links.remove(lk)
    tree.links.new(sa.outputs[0], target)
    return len(made)
