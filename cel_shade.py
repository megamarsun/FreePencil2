"""セル調の影と薄い色(プレビューの種類「セル(影と色)」)。v2.9。

線画(白プレビューの絵 = 白地に黒線)の下に、
    材質の色を白へ寄せた薄い色  x  2 階調の影(日なた / 影の色)
を敷く。物の外は空の色(切れば透過のまま)。

影は材質の光からは取らない。アニメ調のモデルは発光や Shader to RGB の材質が
多く、ディフューズの光のパスが 0 になる(試作で実測: 真っ黒)。代わりに、
すべての材質に「白い拡散面が受けた光(影込み)-> Shader to RGB -> AOV」を足し、
材質がどう作られていても同じ光と影を取る。

コンポジタでは Composite(細線化の縮小があればその手前)へ入る線の絵を受け取り、
合成した絵を同じ所へ戻す。白/モノクロと同じく、種類を切り替えると挿したり外したりする。
"""
from __future__ import annotations

import bpy

from . import compat
import logging

logger = logging.getLogger(__name__)

CEL_LABEL = "FP_CelShade"
SHADE_AOV = "fp_shade"
# 材質に足すノードの目印。「FreePencil を外す」がこれで見つけて消す
SHADE_NODE_LABEL = "FreePencil_shade_aov"
DIFFUSE_COLOR_SOCKETS = ("Diffuse Color", "DiffCol")
EMIT_SOCKETS = ("Emission", "Emit")


# ---------------------------------------------------------------- 材質と AOV

def _iter_materials(scene):
    seen = set()
    stack = list(scene.objects)
    while stack:
        o = stack.pop()
        if o.name in seen:
            continue
        seen.add(o.name)
        if o.instance_type == 'COLLECTION' and o.instance_collection:
            stack.extend(o.instance_collection.all_objects)
        for slot in getattr(o, "material_slots", []):
            m = slot.material
            if m is not None and m.use_nodes and m.node_tree is not None \
                    and not getattr(m, "grease_pencil", None):
                yield m


def ensure_shade_aov(scene, view_layer) -> int:
    """影の AOV を材質とビューレイヤーに用意する。足した材質の数を返す。

    AOV は色で、R = 白い拡散面の光、G = 1(物がある印)。物のある所を深度や
    アルファで取ると、背景が不透明で遠景の大きい場面で空まで物と見なした
    (C62 の場面で空が暗い灰色になった)。材質が書く印なら背景の設定に左右されない。
    """
    aov = next((a for a in view_layer.aovs if a.name == SHADE_AOV), None)
    if aov is None:
        aov = view_layer.aovs.add()
        aov.name = SHADE_AOV
    aov.type = 'COLOR'
    # 色は「拡散の色 + 発光」から取る。発光の材質(アニメ調のモデルに多い)は
    # 拡散の色が 0 で、灰色になった(テスト 81 で発見)
    if not view_layer.use_pass_diffuse_color:
        view_layer.use_pass_diffuse_color = True
    if not view_layer.use_pass_emit:
        view_layer.use_pass_emit = True
    added = 0
    done = set()
    for m in _iter_materials(scene):
        if m.name in done:
            continue
        done.add(m.name)
        nodes = m.node_tree.nodes
        mine = [n for n in nodes if n.label == SHADE_NODE_LABEL]
        if any(n.type == "COMBINE_COLOR" for n in mine):
            continue
        for n in mine:                          # 前の形(光だけ)は作り直す
            nodes.remove(n)
        dif = nodes.new("ShaderNodeBsdfDiffuse")
        dif.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
        s2r = nodes.new("ShaderNodeShaderToRGB")
        bw = nodes.new("ShaderNodeRGBToBW")
        comb = nodes.new("ShaderNodeCombineColor")
        comb.inputs[1].default_value = 1.0
        comb.inputs[2].default_value = 0.0
        out = nodes.new("ShaderNodeOutputAOV")
        out.aov_name = SHADE_AOV
        for i, n in enumerate((dif, s2r, bw, comb, out)):
            n.label = SHADE_NODE_LABEL
            n.location = (10 + 180 * i, 900)
            n.hide = True
        links = m.node_tree.links
        links.new(dif.outputs[0], s2r.inputs[0])
        links.new(s2r.outputs["Color"], bw.inputs[0])
        links.new(bw.outputs[0], comb.inputs[0])
        links.new(comb.outputs[0], out.inputs["Color"])
        added += 1
    if added:
        view_layer.update()
    return added


# ---------------------------------------------------------------- コンポジタ

def _target_socket(tree):
    """線の絵が入る口: Composite の入力。細線化の縮小があればその入力(等倍で合成する)。"""
    comp = next((n for n in tree.nodes if n.type in compat.OUTPUT_NODE_TYPES
                 and n.inputs and n.inputs[0].is_linked), None)
    if comp is None:
        return None
    target = comp.inputs[0]
    src_node = target.links[0].from_node
    if src_node.type == "SCALE" and src_node.inputs[0].is_linked:
        target = src_node.inputs[0]
    return target


def _color_inputs(node):
    return [s for s in node.inputs if s.type == 'RGBA']


def _remove(tree, made, target):
    """挿したノードを外し、挿す前の入力元を target へ戻す。"""
    src = None
    for n in made:
        prev = tree.nodes.get(n.get("fp_prev_node", ""))
        idx = int(n.get("fp_prev_out", 0))
        if prev is not None and idx < len(prev.outputs):
            src = prev.outputs[idx]
            break
    for n in made:
        tree.nodes.remove(n)
    if src is not None and target is not None and not target.is_linked:
        tree.links.new(src, target)


def set_cel(scene, enable: bool) -> int:
    """セル(影と色)を立てる/下ろす。作ったノードの数を返す。"""
    from . import line_weight
    tree = compat.get_compositor_tree(scene)
    if tree is None:
        return 0
    made = [n for n in tree.nodes if n.label == CEL_LABEL]
    target = _target_socket(tree)
    if made:
        _remove(tree, made, target)
        target = _target_socket(tree)
    if not enable or target is None or not target.is_linked:
        return 0
    rl = next((n for n in tree.nodes if n.type == 'R_LAYERS'), None)
    if rl is None:
        return 0
    vl = bpy.context.view_layer
    ensure_shade_aov(scene, vl)
    shade = compat.render_layer_socket(rl, (SHADE_AOV,))
    dcol = compat.render_layer_socket(rl, DIFFUSE_COLOR_SOCKETS)
    if shade is None or dcol is None:
        logger.warning("Cel: the shade AOV or the diffuse color pass is missing")
        return 0
    emit = compat.render_layer_socket(rl, EMIT_SOCKETS)

    src = target.links[0].from_socket
    prev = (src.node.name, list(src.node.outputs).index(src))
    ss = 2.0 if scene.render.resolution_percentage == 200 else 1.0
    x0, y0 = target.node.location.x - 900, target.node.location.y - 700
    nodes = []

    def add(type_name, dx, dy):
        n = compat.new_node(tree, type_name)
        n.label = CEL_LABEL
        n.location = (x0 + dx, y0 + dy)
        n.hide = True
        nodes.append(n)
        return n

    def math(op, a, b, dx, dy):
        n = add("CompositorNodeMath", dx, dy)
        n.operation = op
        for i, v in enumerate((a, b)):
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            else:
                tree.links.new(v, n.inputs[i])
        return n.outputs[0]

    def mix(fac, c1, c2, blend, dx, dy):
        n = add("CompositorNodeMixRGB", dx, dy)
        n.blend_type = blend
        for i, v in ((0, fac), (1, c1), (2, c2)):
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            elif isinstance(v, tuple):
                n.inputs[i].default_value = (*v[:3], 1.0)
            else:
                tree.links.new(v, n.inputs[i])
        return n.outputs[0]

    # AOV を分ける: R = 光、G = 物のある印
    sep = add("CompositorNodeSeparateColor", -150, 0)
    tree.links.new(shade, sep.inputs[0])
    light, present = sep.outputs[0], sep.outputs[1]
    # 光 -> 正規化(一番明るい所が 1)-> ぼかし -> しきい値 = 日なた
    norm = add("CompositorNodeNormalize", 0, 0)
    tree.links.new(light, norm.inputs[0])
    blur = add("CompositorNodeBlur", 150, 0)
    line_weight._set_blur(blur, max(0, int(round(getattr(scene, "fp_cel_softness", 3.0) * ss))))
    tree.links.new(norm.outputs[0], blur.inputs[0])
    lit = math("GREATER_THAN", blur.outputs[0], float(getattr(scene, "fp_cel_threshold", 0.7)), 300, 0)

    white = (1.0, 1.0, 1.0)
    base = dcol
    if emit is not None:
        base = mix(1.0, dcol, emit, "ADD", 150, 120)
        base.node.use_clamp = True
    pale = mix(float(getattr(scene, "fp_cel_pale", 0.15)), base, white, "MIX", 300, 120)
    cel = mix(lit, tuple(getattr(scene, "fp_cel_shadow_color", (0.62, 0.62, 0.80))), white, "MIX", 450, 60)
    colored = mix(1.0, pale, cel, "MULTIPLY", 600, 100)

    sil = present

    if getattr(scene, "fp_cel_shadow_line", False):
        # 影の境界: 日なたを広げた所 - 日なた。物の中だけ
        dil = add("CompositorNodeDilateErode", 450, -60)
        line_weight._set_dilate(dil, max(1, int(round(getattr(scene, "fp_cel_shadow_line_width", 1.0) * ss))))
        tree.links.new(lit, dil.inputs[0])
        edge = math("SUBTRACT", dil.outputs[0], lit, 600, -60)
        edge = math("MULTIPLY", edge, sil, 750, -60)
        colored = mix(edge, colored, tuple(getattr(scene, "fp_cel_shadow_line_color", (0.05, 0.2, 0.8))),
                      "MIX", 750, 100)

    # 線の絵は物の外が透過のことがある。白の上に重ねてから掛ける
    over = add("CompositorNodeAlphaOver", 600, 220)
    ci = _color_inputs(over)
    ci[0].default_value = (1.0, 1.0, 1.0, 1.0)
    tree.links.new(src, ci[1])
    if getattr(scene, "fp_cel_sky", True):
        # 物の外は空の色。線の絵(物の外にはみ出した輪郭)はその上に掛ける
        sky = tuple(getattr(scene, "fp_cel_sky_color", (0.6, 0.76, 0.93)))
        body = mix(sil, sky, colored, "MIX", 900, 60)
        out = mix(1.0, body, over.outputs[0], "MULTIPLY", 1050, 100)
        opaque = add("CompositorNodeSetAlpha", 1200, 100)
        compat.set_node_value(opaque, "mode", "REPLACE_ALPHA")
        tree.links.new(out, opaque.inputs["Image"])
        opaque.inputs["Alpha"].default_value = 1.0
        result = opaque.outputs[0]
    else:
        # 空なし: 物の中だけ色を付け、元の線の絵(透過)の上に重ねる
        inside = mix(1.0, colored, over.outputs[0], "MULTIPLY", 900, 120)
        inside_a = add("CompositorNodeSetAlpha", 1050, 140)
        compat.set_node_value(inside_a, "mode", "REPLACE_ALPHA")
        tree.links.new(inside, inside_a.inputs["Image"])
        tree.links.new(sil, inside_a.inputs["Alpha"])
        top = add("CompositorNodeAlphaOver", 1200, 100)
        ct = _color_inputs(top)
        tree.links.new(src, ct[0])
        tree.links.new(inside_a.outputs[0], ct[1])
        result = top.outputs[0]

    for lk in list(target.links):
        tree.links.remove(lk)
    tree.links.new(result, target)
    nodes[0]["fp_prev_node"], nodes[0]["fp_prev_out"] = prev[0], int(prev[1])
    logger.info(f"Cel shading: {len(nodes)} nodes")
    return len(nodes)
