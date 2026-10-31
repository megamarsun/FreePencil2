"""キャラと背景で光を分ける(v3.0)。セルの「カメラから」の日をキャラだけに当て、背景は動かない日で描く。

カメラから当てる日を背景にも使うと、カメラが曲がるたびに壁の明暗が一斉に入れ替わってパカパカした
(迷路を歩くデモ、212→213 コマ)。キャラの影は画面の同じ側に置きたいが、背景は世界に固定の
光でないと、カメラの動きがそのまま壁のちらつきになる。

  - キャラ = 骨で動く物(humanoid.armature_of)。それ以外が背景
  - キャラの日: 「カメラから」の日(cel_shade.key_sun)。光のリンクでキャラだけを照らす
  - 背景の日: FP_BgSun(向きは fp_light_bg_dir、ワールドに固定)。キャラを照らさない。
    キャラの落とす影も背景にはこの日から落ちる
  - コンポジタ: キャラの所はキャラの日の光、ほかは「法線・背景の日 x 落ちる影」
    (材質の AOV fp_char でキャラの所を見分ける。EEVEE は物の番号のパスを出さない)
  - リムはキャラだけ(斜めから見た平らな壁が丸ごとリムで白く飛んだ)
"""

import bpy
from mathutils import Vector

BG_SUN = "FP_BgSun"
CHAR_LIT = "FP_CharLit"          # キャラの日が照らす物(キャラ)
CHAR_OUT = "FP_CharUnlit"        # 背景の日が照らさない物(キャラ。光のリンクの「外す」で使う)
MASK_AOV = "fp_char"
MASK_LABEL = "FreePencil_char_aov"
BG_SUN_LABEL = "FP_BgSun"        # 背景の日の向き(x, y, z)を入れた掛け算のノード
BG_ENERGY = 0.5                  # 背景の日はキャラの日の半分(一番強い日はキャラの日のまま。アドオンはそれを回す)


def enabled(scene) -> bool:
    return bool(getattr(scene, "fp_light_split", False)) and \
        getattr(scene, "fp_light_mode", 'CAMERA') == 'CAMERA'


def char_objects(scene) -> list:
    from . import humanoid
    return [o for o in scene.objects if o.type == "MESH" and not o.hide_render
            and humanoid.armature_of(o) is not None]


def bg_direction(scene) -> Vector:
    v = Vector(tuple(getattr(scene, "fp_light_bg_dir", (0.68, -0.30, 0.67))))
    return v.normalized() if v.length > 1e-6 else Vector((0.0, 0.0, 1.0))


def _collection(name, objs, state):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
    for o in list(c.objects):
        if o not in objs:
            c.objects.unlink(o)
    for o in objs:
        if o.name not in c.objects:
            c.objects.link(o)
    for co in c.collection_objects:
        co.light_linking.link_state = state
    return c


def _bg_sun(scene, key):
    o = bpy.data.objects.get(BG_SUN)
    if o is None:
        d = bpy.data.lights.new(BG_SUN, 'SUN')
        o = bpy.data.objects.new(BG_SUN, d)
    if o.name not in scene.collection.objects:
        scene.collection.objects.link(o)
    o.data.use_shadow = True
    o.data.energy = (key.data.energy if key is not None else 3.0) * BG_ENERGY
    o.hide_render = False
    aim_bg(scene, o)
    return o


def aim_bg(scene, o=None) -> None:
    o = o or bpy.data.objects.get(BG_SUN)
    if o is None:
        return
    q = bg_direction(scene).to_track_quat('Z', 'Y')        # 日の +Z が光の来る向き
    m = q.to_matrix().to_4x4()
    m.translation = o.matrix_world.translation
    o.matrix_world = m


def ensure(scene, view_layer) -> bool:
    """光のリンク・背景の日・キャラのマスクを用意する。分けられなければ False(片付ける)。"""
    from . import cel_shade
    chars = char_objects(scene)
    if not enabled(scene) or not chars:
        clear(scene)
        return False
    key = cel_shade.key_sun(scene)
    if key is not None and key.name == BG_SUN:
        key = None
    if key is None:
        from . import cel_light
        cel_light.aim_key(scene, create=True)
        key = next((o for o in scene.objects if o.type == 'LIGHT' and o.data.type == 'SUN'
                    and o.name != BG_SUN and not o.hide_render), None)
    lit = _collection(CHAR_LIT, chars, 'INCLUDE')
    out = _collection(CHAR_OUT, chars, 'EXCLUDE')
    if key is not None:
        key.light_linking.receiver_collection = lit
    sun = _bg_sun(scene, key)
    sun.light_linking.receiver_collection = out
    # キャラのマスク: キャラの材質から AOV に 1 を書く
    if MASK_AOV not in [a.name for a in view_layer.aovs]:
        a = view_layer.aovs.add()
        a.name, a.type = MASK_AOV, 'VALUE'
    mats = {s.material for o in chars for s in o.material_slots
            if s.material is not None and s.material.use_nodes}
    for m in bpy.data.materials:
        if not m.use_nodes or m.node_tree is None:
            continue
        mine = [n for n in m.node_tree.nodes if n.label == MASK_LABEL]
        if m in mats and not mine:
            n = m.node_tree.nodes.new("ShaderNodeOutputAOV")
            n.aov_name = MASK_AOV
            n.inputs["Value"].default_value = 1.0
            n.label = MASK_LABEL
            n.location = (10, 1000)
            n.hide = True
        elif m not in mats:
            for n in mine:
                m.node_tree.nodes.remove(n)
    return True


def clear(scene) -> None:
    """分けるのをやめる(「FreePencil を外す」からも呼ぶ)。"""
    for o in scene.objects:
        if o.type == 'LIGHT' and o.light_linking.receiver_collection is not None and \
                o.light_linking.receiver_collection.name in (CHAR_LIT, CHAR_OUT):
            o.light_linking.receiver_collection = None
    o = bpy.data.objects.get(BG_SUN)
    if o is not None:
        d = o.data
        bpy.data.objects.remove(o)
        if d is not None and d.users == 0:
            bpy.data.lights.remove(d)
    for name in (CHAR_LIT, CHAR_OUT):
        c = bpy.data.collections.get(name)
        if c is not None:
            bpy.data.collections.remove(c)
    for m in bpy.data.materials:
        if m.use_nodes and m.node_tree is not None:
            for n in [n for n in m.node_tree.nodes if n.label == MASK_LABEL]:
                m.node_tree.nodes.remove(n)


def light_socket(tree, rl, scene, m, new_node, light, x0, y0, label):
    """キャラの光(light)を、背景の所だけ「法線・背景の日 x 落ちる影」に差し替えた出口。

    m(op, a, b, dx, dy) は cel_shade.light_socket の掛け算を作る関数、new_node(型, dx, dy) は x0, y0 からの位置で置く。マスクのパスが無ければ light のまま。
    """
    from . import compat, line_weight
    from .cel_shade import NORMAL_SOCKETS, SHADOW_SOCKETS
    mask = compat.render_layer_socket(rl, (MASK_AOV,))
    nrm = compat.render_layer_socket(rl, NORMAL_SOCKETS)
    shd = compat.render_layer_socket(rl, SHADOW_SOCKETS)
    if mask is None or nrm is None or shd is None:
        return light
    L = bg_direction(scene)
    ns = new_node("CompositorNodeSeparateColor", 0, -500)
    tree.links.new(nrm, ns.inputs[0])
    terms = []
    for i in range(3):
        t = m("MULTIPLY", ns.outputs[i], float(L[i]), 150, -500 - 30 * i)
        t[BG_SUN_LABEL] = i
        terms.append(t.outputs[0])
    dot = m("ADD", m("ADD", terms[0], terms[1], 300, -500).outputs[0], terms[2], 450, -500)
    dot.use_clamp = True
    # 背景の落ち影: キャラの落ち影(60 px ぼかしてから半分で切る)では細い人の影が消えた。軽く 8 px
    sbw = new_node("CompositorNodeRGBToBW", 300, -600)
    tree.links.new(shd, sbw.inputs[0])
    ss = 2.0 if scene.render.resolution_percentage == 200 else 1.0
    cb = new_node("CompositorNodeBlur", 375, -600)
    cb.label = label
    cb.hide = True
    line_weight._set_blur(cb, max(1, int(round(8 * ss))))
    tree.links.new(sbw.outputs[0], cb.inputs[0])
    cast = m("GREATER_THAN", cb.outputs[0], 0.5, 450, -600).outputs[0]
    bg = m("MULTIPLY", dot.outputs[0], cast, 600, -500).outputs[0]
    out = m("ADD", bg, m("MULTIPLY", m("SUBTRACT", light, bg, 750, -520).outputs[0], mask,
                         900, -520).outputs[0], 1050, -500)
    return out.outputs[0]


def mask_socket(rl):
    from . import compat
    return compat.render_layer_socket(rl, (MASK_AOV,))


def update_nodes(scene, tree) -> bool:
    """背景の日の向きを、ノードと日に合わせる。"""
    nodes = [n for n in tree.nodes if BG_SUN_LABEL in n and n.type == "MATH"]
    if not nodes:
        return False
    aim_bg(scene)
    L = bg_direction(scene)
    changed = False
    for n in nodes:
        v = float(L[int(n[BG_SUN_LABEL])])
        if abs(n.inputs[1].default_value - v) > 1e-5:
            n.inputs[1].default_value = v
            changed = True
    return changed
