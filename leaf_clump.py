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

眉毛とまつ毛のパーティクルの毛も同じに扱う。毛が 1〜2 画素の筋で、線がかすれた点々にしか
ならず、眉が出なかった(woman_01。AOV では顔とはっきり違う色)。こちらは別の AOV(fp_brow)に書き、
小さく閉じて線の色で塗りつぶす(縁にすると遠目で眉とまつ毛が 1 つの輪になり、ゴーグルのように
見えた)。頭の髪は入れない(かたまりにすると髪の黒い量感が消えて薄くなった。画像で確認)。
"""
from __future__ import annotations

import re

import bpy

from . import compat

LABEL = "FreePencil_leaf_clump"
AOV = "fp_leaf"
MAT_LABEL = "FreePencil_leaf_aov"
LEAF_RE = re.compile(r"leaf|leaves|foliage|needle|bush|shrub|hedge|ivy|fern|grass|葉|草", re.IGNORECASE)
BROW_RE = re.compile(r"brow|lash|眉|まつ毛|睫", re.IGNORECASE)
BROW_AOV = "fp_brow"


def _from_image(sock) -> bool:
    """口の上流に絵があるか。"""
    stack, seen = [lk.from_node for lk in sock.links], set()
    while stack:
        x = stack.pop()
        if x.name in seen:
            continue
        seen.add(x.name)
        if x.type == "TEX_IMAGE" and x.image is not None:
            return True
        stack += [lk.from_node for s in x.inputs for lk in s.links]
    return False


def cutout_by_image(m) -> bool:
    """透明(Transparent BSDF)を絵で混ぜて形を抜いた材質か(葉の板)。

    透明の BSDF があると本物のガラスと見なされて BLEND のまま残り、AOV も光のパスも書かれず、
    木の葉が線画からもセルからも全部消えた(european-maple: 不透明の絵を Mix Shader の Fac に
    つないだ葉)。屈折や一定の値の透けを持つものはガラスとして残す。
    """
    if m is None or not m.use_nodes or m.node_tree is None:
        return False
    nodes = m.node_tree.nodes
    trans = [n for n in nodes if n.type == "BSDF_TRANSPARENT"]
    if not trans or any(n.type == "BSDF_GLASS" for n in nodes):
        return False
    for n in nodes:
        if n.type != "BSDF_PRINCIPLED":
            continue
        tr = n.inputs.get("Transmission Weight") or n.inputs.get("Transmission")
        if tr is not None and not tr.is_linked and tr.default_value > 0.3:
            return False
        al = n.inputs.get("Alpha")
        if al is not None and not al.is_linked and al.default_value < 0.7:
            return False
    for t in trans:
        outs = [lk.to_node for lk in t.outputs[0].links]
        if not outs or any(o.type != "MIX_SHADER" or not _from_image(o.inputs[0]) for o in outs):
            return False
    return True


def cutout_fac_links(m) -> list:
    """絵で透明を混ぜている Mix Shader の Fac へのつなぎ。"""
    if not cutout_by_image(m):
        return []
    return [n.inputs[0].links[0] for n in m.node_tree.nodes
            if n.type == "MIX_SHADER" and n.inputs[0].is_linked
            and any(lk.from_node.type == "BSDF_TRANSPARENT" for s in n.inputs[1:] for lk in s.links)]


def _alpha_from_image(m) -> bool:
    """Principled の Alpha の上流に絵があるか(Color 出力をアルファに使う葉もある)。
    透明の BSDF を絵で混ぜた葉も入れる。"""
    if cutout_by_image(m):
        return True
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


def brow_materials(objs) -> set:
    """眉毛・まつ毛のパーティクルの毛の材質。"""
    names = set()
    for o in objs:
        slots = getattr(o, "material_slots", [])
        for ps in getattr(o, "particle_systems", []):
            st = ps.settings
            if st.type != 'HAIR' or not (BROW_RE.search(ps.name) or BROW_RE.search(st.name)):
                continue
            i = st.material - 1
            if 0 <= i < len(slots) and slots[i].material is not None:
                m = slots[i].material
                if m.get("fp_leaf", True):
                    names.add(m.name)
    return names


def leaf_materials(objs) -> list:
    objs = list(objs)
    brows = brow_materials(objs)
    names = []
    for o in objs:
        for s in getattr(o, "material_slots", []):
            m = s.material
            if m is not None and m.name not in names and (m.name in brows or is_leaf_material(m)):
                names.append(m.name)
    return names


def needed(scene) -> bool:
    return bool(getattr(scene, "fp_leaf_clump", False))


def ensure_aov(scene, view_layer) -> int:
    """葉(と眉・まつ毛)の材質に AOV を足す。足した材質の数を返す。"""
    from .cel_shade import _iter_materials
    brows = brow_materials(scene.objects)
    for name in (AOV, BROW_AOV) if brows else (AOV,):
        if name not in [a.name for a in view_layer.aovs]:
            a = view_layer.aovs.add()
            a.name = name
            a.type = 'VALUE'
    added = 0
    done = set()
    for m in _iter_materials(scene):
        if m.name in done:
            continue
        done.add(m.name)
        nodes = m.node_tree.nodes
        mine = [n for n in nodes if n.label == MAT_LABEL]
        want = BROW_AOV if m.name in brows else AOV if is_leaf_material(m) else None
        if want is None or any(n.type == "OUTPUT_AOV" and n.aov_name != want for n in mine):
            for n in mine:                  # 葉でなくした材質や、行き先の変わった材質からは外す
                nodes.remove(n)
            mine = []
        if want is None or mine:
            continue
        val = nodes.new("ShaderNodeValue")
        val.outputs[0].default_value = 1.0
        out = nodes.new("ShaderNodeOutputAOV")
        out.aov_name = want
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


def _sizes(scene):
    """(閉じる半径, 縁の太さ, 眉を閉じる半径, 中の穴を見分ける半径)。絵の幅 2560px での値を比で直す。"""
    r = scene.render
    width = r.resolution_x * r.resolution_percentage / 100.0
    rad = max(2, int(round(8 * width / 2560.0)))
    return (rad, max(1, int(round(2 * width / 2560.0))), max(1, int(round(3 * width / 2560.0))),
            6 * rad)


def _builders(tree, add):
    """add(型名, dx, dy) でノードを作る関数から、計算・広げる・ぼかすの 3 つを作る。"""
    from . import line_weight

    def math(op, a, b, dx, dy=0, clamp=False):
        n = add("CompositorNodeMath", dx, dy)
        n.operation = op
        n.use_clamp = clamp
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

    def blur(sock, px, dx, dy):
        n = add("CompositorNodeBlur", dx, dy)
        line_weight._set_blur(n, px)
        tree.links.new(sock, n.inputs[0])
        return n.outputs[0]

    return math, grow, blur


FLOOD_STEPS = 24                    # 外から流し込む回数(1 回に r ずつ。幅 2560px で 192px 入る)


def _clump(math, grow, leaf, scene, dx, dy):
    """葉の覆いから (かたまり, 外) を作る。

    かたまり = 葉を半径 r で閉じたもの。外 = 茂みの外から、かたまりを越えずに流し込んで
    届いた所(外側の縁の切れ込みも入る)。届かない所 = かたまりに囲まれた穴で、そのうち
    小さい物(空と枝の先が少し見えるすき間)はかたまりに入れる。穴ごとに縁の輪が出て、
    茂みの中に泡のような丸が浮いた(european-maple)。「奥」を四角く縮めて決めると、
    奥の境で縁の切れ込みが直線に切れた(tree_autumn)ので、流し込みで見分ける。
    """
    rad, _edge, _bro, big = _sizes(scene)
    clump = grow(grow(leaf, rad, dx + 150, dy), -rad, dx + 300, dy)       # 閉じる: 広げてから縮める
    free = math("SUBTRACT", 1.0, clump, dx + 450, dy + 120, clamp=True)
    # 流し込みの種は、大きく閉じた形の外(穴は大きく閉じると埋まるので種にならない)
    big_close = grow(grow(leaf, big, dx + 150, dy + 120, round_=False), -big, dx + 300, dy + 120,
                     round_=False)
    out = math("MULTIPLY", math("SUBTRACT", 1.0, big_close, dx + 450, dy + 160, clamp=True), free,
               dx + 600, dy + 160)
    step = rad
    for i in range(FLOOD_STEPS):
        out = math("MULTIPLY", grow(out, step, dx + 750 + 75 * i, dy + 200, round_=False), free,
                   dx + 750 + 75 * i, dy + 160)
    small = grow(grow(clump, 3 * rad, dx + 450, dy + 40), -3 * rad, dx + 600, dy + 40)
    holes = math("MULTIPLY", math("SUBTRACT", free, out, dx + 2000, dy + 120, clamp=True), small,
                 dx + 2100, dy + 80)
    return math("MAXIMUM", clump, holes, dx + 2200, dy), out


def fill_gaps(tree, add, rl, scene, color, dx, dy):
    """色の絵の、葉のかたまりの中のすき間を、まわりの葉の色で埋める。(色, すき間の覆い) を返す。

    線はかたまりの縁だけにしたのに、セルと材質の色は葉 1 枚ずつのままで、かたまりの中に
    空の色がまだらに透けた(european-maple)。すき間 = かたまり - 葉 に、まわりの葉だけの
    平均の色(ぼかした 色 x 葉 / ぼかした 葉)を置く。葉の無い木や、かたまりを切っていれば
    そのまま返す(すき間の覆いは None)。
    """
    lsock = compat.render_layer_socket(rl, (AOV,)) if needed(scene) else None
    if lsock is None:
        return color, None
    math, grow, blur = _builders(tree, add)
    rad = _sizes(scene)[0]
    leaf = math("GREATER_THAN", lsock, 0.5, dx, dy)
    clump, _out = _clump(math, grow, leaf, scene, dx - 2400, dy + 200)
    gap = math("SUBTRACT", clump, leaf, dx + 225, dy, clamp=True)
    only = add("CompositorNodeMixRGB", dx + 75, dy - 40)
    only.blend_type = "MULTIPLY"
    only.inputs[0].default_value = 1.0
    tree.links.new(color, only.inputs[1])
    tree.links.new(leaf, only.inputs[2])
    # 平均を取る広さは、囲まれた小さい穴(半径 3r まで埋める)の真ん中から葉に届く 6r。葉が
    # ほとんど届かない所は元の色のまま(0 に近い値で割って黒い点になった。tree_autumn)
    blur_leaf = blur(leaf, 6 * rad, dx + 150, dy - 80)
    area = math("MAXIMUM", blur_leaf, 1e-3, dx + 225, dy - 80)
    avg = add("CompositorNodeMixRGB", dx + 300, dy - 40)
    avg.blend_type = "DIVIDE"
    avg.inputs[0].default_value = 1.0
    tree.links.new(blur(only.outputs[0], 6 * rad, dx + 150, dy - 40), avg.inputs[1])
    tree.links.new(area, avg.inputs[2])
    reach = math("MULTIPLY", blur_leaf, 20.0, dx + 225, dy - 120, clamp=True)
    out = add("CompositorNodeMixRGB", dx + 375, dy)
    out.blend_type = "MIX"
    tree.links.new(math("MULTIPLY", gap, reach, dx + 300, dy - 120), out.inputs[0])
    tree.links.new(color, out.inputs[1])
    tree.links.new(avg.outputs[0], out.inputs[2])
    return out.outputs[0], gap


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
    rad, edge, bro, big = _sizes(scene)
    x0, y0 = target.node.location.x - 1800, target.node.location.y - 1000
    made = []

    def add(type_name, dx, dy=0):
        n = compat.new_node(tree, type_name)
        n.label = LABEL
        n.location = (x0 + dx, y0 + dy)
        n.hide = True
        made.append(n)
        return n

    math, grow, _blur = _builders(tree, add)

    leaf = math("GREATER_THAN", lsock, 0.5, 0, 0)
    clump, outside = _clump(math, grow, leaf, scene, -2400, 300)
    zone = grow(clump, edge, 450, 60, round_=False)               # 置き換える所(縁の外側も含む)
    rim = math("SUBTRACT", clump, grow(clump, -edge, 450, 0, round_=False), 600, 0, clamp=True)
    # かたまりに囲まれた大きい穴で、手前の枝や幹が見えている所は縁を描かない。枝の両側に
    # かたまりの縁が出て、枝の線と二重の輪になる。空の見える大きい穴(茂みのすき間)は
    # 縁を残す。茂みの外側の縁は、後ろに建物があっても外から流し込んだ所の隣なので残る
    sil = line_weight.silhouette(tree, rl, scene, x0 + 150, y0 + 200, label=LABEL)
    if sil is not None:
        for n in tree.nodes:
            if n.label == LABEL and n not in made:
                made.append(n)
        # 空は「かたまりの外の空」だけ。葉と葉の小さいすき間の空まで数えると、縁がどこでも
        # 空の隣になって消えなかった
        open_sky = math("MULTIPLY", math("SUBTRACT", 1.0, sil, 300, 200, clamp=True),
                        math("SUBTRACT", 1.0, clump, 300, 240, clamp=True), 400, 200)
        sky = grow(open_sky, edge + 1, 450, 200, round_=False)
        near_out = grow(outside, edge + 1, 450, 240, round_=False)
        seen = math("MAXIMUM", sky, near_out, 600, 220)
        hidden = math("SUBTRACT", 1.0, seen, 750, 160, clamp=True)
        shown = math("SUBTRACT", 1.0, hidden, 900, 160, clamp=True)
        rim = math("MULTIPLY", rim, shown, 1050, 100)
        # 置き換える所も、隠れた穴の側へははみ出さない(枝の輪郭まで白で消えた)
        zone = math("MAXIMUM", clump, math("MULTIPLY", zone, shown, 1050, 140), 1200, 120)
    # 元の線の濃さ
    over_out = on_white(tree, add, src, 0, -150)
    bw = add("CompositorNodeRGBToBW", 150, -150)
    tree.links.new(over_out, bw.inputs[0])
    ink = math("SUBTRACT", 1.0, bw.outputs[0], 300, -150)
    keep = math("SUBTRACT", 1.0, zone, 600, 60, clamp=True)
    out_ink = math("MAXIMUM", math("MULTIPLY", ink, keep, 750, -150), rim, 900, -100)
    dark = math("MULTIPLY", rim, zone, 1050, 0)                   # 線の色で塗る所
    # 眉・まつ毛: 小さく閉じて塗りつぶす(縁にすると遠目で眉と目が 1 つの輪になった)
    bsock = compat.render_layer_socket(rl, (BROW_AOV,))
    if bsock is not None:
        brow = math("GREATER_THAN", bsock, 0.5, 0, -60)
        brow_fill = grow(grow(brow, bro, 150, -60), -bro, 300, -60)
        out_ink = math("MAXIMUM", out_ink, brow_fill, 900, -40)
        dark = math("MAXIMUM", dark, brow_fill, 1100, 30)
    # 葉の所は白地へ置き換え、外は元の絵のまま: 色 = 元 x (1 - zone) + 白 x zone、それに線を掛ける
    white = add("CompositorNodeMixRGB", 1050, -150)
    compat.set_node_value(white, "blend_type", "MIX")
    tree.links.new(zone, white.inputs[0])
    tree.links.new(src, white.inputs[1])
    white.inputs[2].default_value = (1.0, 1.0, 1.0, 1.0)
    f = math("SUBTRACT", 1.0, dark, 1200, 0)
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
