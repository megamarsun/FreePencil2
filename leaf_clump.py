"""木の葉をかたまりで描く(v3.0)。シーンの fp_leaf_clump。STEP0 が葉の材質を見つけたら入れる。

葉を透明の模様(葉の形に抜いた絵)で描いた木は、葉が数画素の大きさで何千枚も重なり、
どのチャンネルでも葉 1 枚ごとに線が出て、木が真っ黒な影絵になった(tree_autumn。チャンネルを
1 つずつ止めても黒いまま、全部止めると白)。線の密な所を薄める「遠景つぶれ軽減」を全体に
かけると木は直るが、人物や建物の太い線まで薄くなった(画像で確認)。

そこで葉の材質の所だけを扱う。葉の材質は AOV(fp_leaf)に 1 を書き、合成で
  かたまり = 葉の覆いを半径 r で閉じたもの(葉と葉の小さいすき間を埋める)
  線      = かたまりの縁(2 画素)
とし、かたまりの中の元の線は消して白にする。手で描く木の「茂みの輪郭」の描き方。
r は絵の幅に比例させる(試作: 幅 2560px で 8px)。

葉の材質: 絵がアルファへつながっていて、名前が葉らしいもの。材質の "fp_leaf"(True/False)が
あればそちらを使う。
"""
from __future__ import annotations

import re

import bpy

from . import compat

LABEL = "FreePencil_leaf_clump"
AOV = "fp_leaf"
MAT_LABEL = "FreePencil_leaf_aov"
LEAF_RE = re.compile(r"leaf|leaves|foliage|needle|bush|shrub|hedge|ivy|fern|grass|葉|草", re.IGNORECASE)


def _alpha_from_image(m) -> bool:
    """Principled の Alpha の上流に絵があるか(Color 出力をアルファに使う葉もある)。"""
    for n in m.node_tree.nodes:
        if n.type != "BSDF_PRINCIPLED" or "Alpha" not in n.inputs or not n.inputs["Alpha"].is_linked:
            continue
        stack, seen = [n.inputs["Alpha"].links[0].from_node], set()
        while stack:
            x = stack.pop()
            if x.name in seen:
                continue
            seen.add(x.name)
            if x.type == "TEX_IMAGE" and x.image is not None:
                return True
            stack += [lk.from_node for s in x.inputs for lk in s.links]
    return False


def is_leaf_material(m) -> bool:
    if m is None or not m.use_nodes or m.node_tree is None:
        return False
    if "fp_leaf" in m:
        return bool(m["fp_leaf"])
    return bool(LEAF_RE.search(m.name)) and _alpha_from_image(m)


def leaf_materials(objs) -> list:
    names = []
    for o in objs:
        for s in getattr(o, "material_slots", []):
            if s.material is not None and s.material.name not in names and is_leaf_material(s.material):
                names.append(s.material.name)
    return names


def needed(scene) -> bool:
    return bool(getattr(scene, "fp_leaf_clump", False))


def ensure_aov(scene, view_layer) -> int:
    """葉の材質に AOV を足す。足した材質の数を返す。"""
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
        mine = [n for n in nodes if n.label == MAT_LABEL]
        if not is_leaf_material(m):
            for n in mine:                  # 葉でなくした材質からは外す
                nodes.remove(n)
            continue
        if mine:
            continue
        val = nodes.new("ShaderNodeValue")
        val.outputs[0].default_value = 1.0
        out = nodes.new("ShaderNodeOutputAOV")
        out.aov_name = AOV
        for i, n in enumerate((val, out)):
            n.label = MAT_LABEL
            n.location = (10 + 180 * i, 1350)
            n.hide = True
        m.node_tree.links.new(val.outputs[0], out.inputs["Value"])
        added += 1
    if added:
        view_layer.update()
    return added


def remove_material_nodes() -> None:
    for m in bpy.data.materials:
        if m.use_nodes and m.node_tree is not None:
            for n in [n for n in m.node_tree.nodes if n.label == MAT_LABEL]:
                m.node_tree.nodes.remove(n)


def _set_round(node, px):
    """丸く広げる/縮める(負で縮める)。4.x はプロパティ、5.x はソケット。"""
    from . import line_weight
    if hasattr(node, "distance"):
        node.mode = "DISTANCE"
        node.distance = px
        return
    line_weight._set_num_socket(node, "Size", px)
    line_weight._set_enum_socket(node, "Type", "DISTANCE", "Distance")


def apply(tree, scene, rl, target) -> int:
    """target へ入る線の絵の、葉の所を「かたまりの縁」に置き換える。挿したノードの数を返す。"""
    from . import line_weight
    from .cel_shade import on_white
    for n in [n for n in tree.nodes if n.label == LABEL]:
        tree.nodes.remove(n)
    if not needed(scene) or target is None or not target.is_linked:
        return 0
    lsock = compat.render_layer_socket(rl, (AOV,))
    if lsock is None:
        return 0
    src = target.links[0].from_socket
    r = scene.render
    width = r.resolution_x * r.resolution_percentage / 100.0
    rad = max(2, int(round(8 * width / 2560.0)))
    edge = max(1, int(round(2 * width / 2560.0)))
    x0, y0 = target.node.location.x - 1800, target.node.location.y - 1000
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

    def grow(sock, px, dx, dy, round_=True):
        n = add("CompositorNodeDilateErode", dx, dy)
        if round_:
            _set_round(n, px)
        else:
            line_weight._set_dilate(n, px)
        tree.links.new(sock, n.inputs[0])
        return n.outputs[0]

    leaf = math("GREATER_THAN", lsock, 0.5, 0, 0)
    clump = grow(grow(leaf, rad, 150, 0), -rad, 300, 0)          # 閉じる: 広げてから縮める
    zone = grow(clump, edge, 450, 60, round_=False)               # 置き換える所(縁の外側も含む)
    rim = math("SUBTRACT", clump, grow(clump, -edge, 450, 0, round_=False), 600, 0, clamp=True)
    # 元の線の濃さ
    over_out = on_white(tree, add, src, 0, -150)
    bw = add("CompositorNodeRGBToBW", 150, -150)
    tree.links.new(over_out, bw.inputs[0])
    ink = math("SUBTRACT", 1.0, bw.outputs[0], 300, -150)
    keep = math("SUBTRACT", 1.0, zone, 600, 60, clamp=True)
    out_ink = math("MAXIMUM", math("MULTIPLY", ink, keep, 750, -150), rim, 900, -100)
    # 葉の所は白地へ置き換え、外は元の絵のまま: 色 = 元 x (1 - zone) + 白 x zone、それに線を掛ける
    white = add("CompositorNodeMixRGB", 1050, -150)
    compat.set_node_value(white, "blend_type", "MIX")
    tree.links.new(zone, white.inputs[0])
    tree.links.new(src, white.inputs[1])
    white.inputs[2].default_value = (1.0, 1.0, 1.0, 1.0)
    f = math("SUBTRACT", 1.0, math("MULTIPLY", rim, zone, 1050, 0), 1200, 0)
    rgb = add("CompositorNodeCombineColor", 1350, 0)
    for i in range(3):
        tree.links.new(f, rgb.inputs[i])
    rgb.inputs[3].default_value = 1.0
    mul = add("CompositorNodeMixRGB", 1500, -150)
    compat.set_node_value(mul, "blend_type", "MULTIPLY")
    mul.inputs[0].default_value = 1.0
    tree.links.new(white.outputs[0], mul.inputs[1])
    tree.links.new(rgb.outputs[0], mul.inputs[2])
    # アルファ: 葉の所は元の線の分を外し、縁の線を足す(透過の背景でも縁が消えない)
    sep_a = add("CompositorNodeSeparateColor", 1350, 80)
    tree.links.new(src, sep_a.inputs[0])
    alpha = math("MAXIMUM", sep_a.outputs[3], out_ink, 1500, 80)
    sa = add("CompositorNodeSetAlpha", 1650, -150)
    compat.set_node_value(sa, "mode", "REPLACE_ALPHA")
    tree.links.new(mul.outputs[0], sa.inputs["Image"])
    tree.links.new(alpha, sa.inputs["Alpha"])
    for lk in list(target.links):
        tree.links.remove(lk)
    tree.links.new(sa.outputs[0], target)
    return len(made)
