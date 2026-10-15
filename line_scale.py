"""物ごとの線の太さ(v2.9)。オブジェクトの「線の太さ(倍)」fp_line_scale。

  0    その物の線を出さない
  0..1 薄くする(細く見える)
  1    今までどおり(既定。全部 1 なら何も挿さず、絵は 1 画素も変わらない)
  1..3 太くする(1 で +1px、2 で +2px。2 倍レンダでは 2px / 4px)

値は材質から AOV(fp_lscale、R = 倍率 / 4、G = 物がある印)で取り出す。オブジェクトの値は
属性ノード(オブジェクト)で読むので、値を変えてもノードを作り直さずに絵が変わる。

線の絵(白地に黒線)を受け取り、物ごとに太らせ/薄めた線へ置き換える。細線化の縮小の手前
(2 倍の大きさ)で掛ける(縮小の後ろだと AOV と線の大きさがずれ、線が欠けた)。
  太くする量: 周りへ広げる(太い方が勝つ。輪郭の外側にも効く)
  薄くする量: 周りの一番小さい値を使う(物の外は「どちらでもない」= 1 として数えない)。
             広い方が勝つようにすると、地面 0 がサルの輪郭まで消した(画像で確認)
"""
from __future__ import annotations

import bpy

from . import compat

LABEL = "FreePencil_line_scale"
AOV = "fp_lscale"
MAT_LABEL = "FreePencil_lscale_aov"


def _objects(scene):
    seen = set()
    stack = list(scene.objects)
    while stack:
        o = stack.pop()
        if o.name in seen:
            continue
        seen.add(o.name)
        if o.instance_type == 'COLLECTION' and o.instance_collection:
            stack.extend(o.instance_collection.all_objects)
        yield o


def needed(scene) -> bool:
    """1 以外の物があるときだけ挿す(全部 1 なら今までと同じ絵のまま)。"""
    return any(abs(float(getattr(o, "fp_line_scale", 1.0)) - 1.0) > 1e-4
               for o in _objects(scene) if o.type == 'MESH')


def ensure_aov(scene, view_layer) -> int:
    """材質とビューレイヤーに AOV を用意する。足した材質の数を返す。"""
    if AOV not in [a.name for a in view_layer.aovs]:
        a = view_layer.aovs.add()
        a.name = AOV
        a.type = 'COLOR'
    added = 0
    done = set()
    for o in _objects(scene):
        for slot in getattr(o, "material_slots", []):
            m = slot.material
            if m is None or m.name in done or not m.use_nodes or m.node_tree is None:
                continue
            done.add(m.name)
            nodes = m.node_tree.nodes
            if any(n.label == MAT_LABEL for n in nodes):
                continue
            attr = nodes.new("ShaderNodeAttribute")
            attr.attribute_type = 'OBJECT'
            attr.attribute_name = "fp_line_scale"
            div = nodes.new("ShaderNodeMath")
            div.operation = 'DIVIDE'
            div.inputs[1].default_value = 4.0
            comb = nodes.new("ShaderNodeCombineColor")
            comb.inputs[1].default_value = 1.0
            comb.inputs[2].default_value = 0.0
            out = nodes.new("ShaderNodeOutputAOV")
            out.aov_name = AOV
            for i, n in enumerate((attr, div, comb, out)):
                n.label = MAT_LABEL
                n.location = (10 + 180 * i, 1050)
                n.hide = True
            links = m.node_tree.links
            links.new(attr.outputs["Fac"], div.inputs[0])
            links.new(div.outputs[0], comb.inputs[0])
            links.new(comb.outputs[0], out.inputs["Color"])
            added += 1
    if added:
        view_layer.update()
    return added


def remove_material_nodes() -> None:
    for m in bpy.data.materials:
        if m.use_nodes and m.node_tree is not None:
            for n in [n for n in m.node_tree.nodes if n.label == MAT_LABEL]:
                m.node_tree.nodes.remove(n)


def present(tree) -> bool:
    return tree is not None and any(n.label == LABEL for n in tree.nodes)


def apply(tree, scene, rl, comp) -> int:
    """Composite へ入る線の絵を、物ごとの太さに置き換える。挿したノードの数を返す。"""
    from . import line_weight
    for n in [n for n in tree.nodes if n.label == LABEL]:
        tree.nodes.remove(n)
    if not needed(scene) or not comp.inputs[0].is_linked:
        return 0
    lsc = compat.render_layer_socket(rl, (AOV,))
    if lsc is None:
        return 0
    target = comp.inputs[0]
    up = target.links[0].from_node
    if up.type == "SCALE" and up.inputs[0].is_linked:          # 細線化の縮小の手前で掛ける
        target = up.inputs[0]
    src = target.links[0].from_socket
    ss = 2.0 if scene.render.resolution_percentage == 200 else 1.0
    x0, y0 = comp.location.x - 600, comp.location.y - 900
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

    def grow(sock, px, dx, dy):
        n = add("CompositorNodeDilateErode", dx, dy)
        line_weight._set_dilate(n, px)          # 負の値で縮める(周りの一番小さい値)
        tree.links.new(sock, n.inputs[0])
        return n.outputs[0]

    # 線の濃さ(0..1)
    from .cel_shade import on_white
    over_out = on_white(tree, add, src, 0)
    bw = add("CompositorNodeRGBToBW", 150)
    tree.links.new(over_out, bw.inputs[0])
    ink = math("SUBTRACT", 1.0, bw.outputs[0], 300)
    # 倍率: 物の中は値、物の外は 1
    sep = add("CompositorNodeSeparateColor", 0, -120)
    tree.links.new(lsc, sep.inputs[0])
    # R は縁で覆い(G)の分だけ薄まっているので、そのまま 4 倍して、物の外の分(1 - G)を足す
    s_obj = math("MULTIPLY", sep.outputs[0], 4.0, 150, -120)
    s = math("ADD", s_obj, math("SUBTRACT", 1.0, sep.outputs[1], 300, -180), 450, -120)
    # 太くする量 b(0..2)と薄くする量 a(0..1)。輪郭の外側にも届くよう周りへ広げる
    reach = max(2, int(round(3 * ss)))
    b = grow(math("MAXIMUM", math("SUBTRACT", s, 1.0, 600, -120), 0.0, 750, -120), reach, 900, -120)
    # 薄くする量: 物の中は 1 - 倍率、物の外は 1(数えない)。周りの一番小さい値へ縮める
    # 覆い G・倍率 k の画素は G*(1-k) + (1-G)*1 = 1 - G*k = 1 - 4R(縁の画素でも地面 0 の
    # 地平線が薄く残らない)
    a_bg = math("SUBTRACT", 1.0, s_obj, 900, -200, clamp=True)
    a = grow(a_bg, -reach, 1050, -200)
    ink1 = grow(ink, max(1, int(round(1 * ss))), 450, 60)
    ink2 = grow(ink, max(1, int(round(2 * ss))), 450, 120)
    t1 = math("MINIMUM", b, 1.0, 1050, -120)
    t2 = math("MAXIMUM", math("SUBTRACT", b, 1.0, 1050, -160), 0.0, 1200, -160, clamp=True)

    def lerp(x, y, t, dx, dy):
        d = math("SUBTRACT", y, x, dx, dy)
        return math("ADD", x, math("MULTIPLY", d, t, dx + 75, dy), dx + 150, dy)
    thick = lerp(lerp(ink, ink1, t1, 1050, 60), ink2, t2, 1350, 60)
    out_ink = math("MULTIPLY", thick, math("SUBTRACT", 1.0, a, 1350, -200), 1500, 60, clamp=True)
    # 白地に黒線へ戻す。アルファは元の線の絵と線の濃さの大きい方(太らせた分が透過で消えない)
    gray = math("SUBTRACT", 1.0, out_ink, 1650, 60)
    rgb = add("CompositorNodeCombineColor", 1800, 60)
    for i in range(3):
        tree.links.new(gray, rgb.inputs[i])
    rgb.inputs[3].default_value = 1.0
    sep_a = add("CompositorNodeSeparateColor", 1650, 140)
    tree.links.new(src, sep_a.inputs[0])
    alpha = math("MAXIMUM", sep_a.outputs[3], out_ink, 1800, 140)
    sa = add("CompositorNodeSetAlpha", 1950, 60)
    compat.set_node_value(sa, "mode", "REPLACE_ALPHA")
    tree.links.new(rgb.outputs[0], sa.inputs["Image"])
    tree.links.new(alpha, sa.inputs["Alpha"])
    for lk in list(target.links):
        tree.links.remove(lk)
    tree.links.new(sa.outputs[0], target)
    return len(made)
