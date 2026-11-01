"""キャラと背景を分ける(v3.0)。セルはキャラだけに掛け、背景は通常の陰影のまま出す。

カメラから当てる日を背景にも使うと、カメラが曲がるたびに壁の明暗が一斉に入れ替わってパカパカした
(迷路を歩くデモ、212→213 コマ)。キャラの影は画面の同じ側に置きたいが、背景は場面の光のままで
ないと、カメラの動きがそのまま壁のちらつきになる。

分けるだけで、背景には陰影の簡易化(日の向きとの内積、影のしきい値)を一切入れない。

  - キャラ = 骨で動く物(humanoid.armature_of)。それ以外が背景
  - キャラの日: FreePencil の日(cel_light.SUN_NAME)。「カメラから」で回り、光のリンクでキャラだけを
    照らし、影もキャラだけが落とす。場面に元からある日は回さない(回すと背景がその日を失う)
  - 場面の光はキャラを照らさない。迷路の天井がキャラの日を遮り、天井の照明が影のパスを灰色に薄めて、
    しきい値を越えた所だけが白い斑点としてコマごとに出入りした(迷路のデモ、255 コマ〜)。
    元から光のリンクを付けてある光は触らない
  - 背景: レンダーの絵(場面の光の通常の陰影)のまま。キャラの落ち影も場面の光から落ちる
  - コンポジタ: キャラの所だけセルの絵、ほかはレンダーの絵(cel_shade.set_cel)。
    キャラの所は材質の AOV fp_char で見分ける(EEVEE は物の番号のパスを出さない)
  - リムと影の境界の線はキャラだけ
"""

import bpy

CHAR_LIT = "FP_CharLit"          # キャラの日が照らす物・影を落とす物(キャラ)
CHAR_OUT = "FP_CharUnlit"        # 場面の光が照らさない物(キャラ)
OUT_MARK = "fp_split_out"        # キャラから外した場面の光の印(外すときに戻す)
MASK_AOV = "fp_char"
MASK_LABEL = "FreePencil_char_aov"
OWN_SUN = "fp_split_own"         # 分けるときに作った日の印(外すときに消す)
# 前の開発版が作っていた背景の日。開いたファイルに残っていれば片付ける
OLD_BG_SUN = "FP_BgSun"


def enabled(scene) -> bool:
    return bool(getattr(scene, "fp_light_split", False)) and \
        getattr(scene, "fp_light_mode", 'CAMERA') == 'CAMERA'


def char_objects(scene) -> list:
    from . import humanoid
    return [o for o in scene.objects if o.type == "MESH" and not o.hide_render
            and humanoid.armature_of(o) is not None]


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


def _own_sun(scene):
    """キャラの日(FreePencil の日)。無ければ作る。場面の日はそのまま背景を照らす。"""
    from . import cel_light
    o = bpy.data.objects.get(cel_light.SUN_NAME)
    if o is None or o.type != 'LIGHT':
        d = bpy.data.lights.new(cel_light.SUN_NAME, 'SUN')
        d.energy = 3.0
        o = bpy.data.objects.new(cel_light.SUN_NAME, d)
        o[OWN_SUN] = True
    if o.name not in scene.objects:
        scene.collection.objects.link(o)
    o.hide_render = False
    return o


def _clear_old(scene) -> None:
    o = bpy.data.objects.get(OLD_BG_SUN)
    if o is not None:
        d = o.data
        bpy.data.objects.remove(o)
        if d is not None and d.users == 0:
            bpy.data.lights.remove(d)


def ensure(scene, view_layer) -> bool:
    """光のリンク・キャラの日・キャラのマスクを用意する。分けられなければ False(片付ける)。"""
    chars = char_objects(scene)
    if not enabled(scene) or not chars:
        clear(scene)
        return False
    _clear_old(scene)
    key = _own_sun(scene)
    from . import cel_light
    cel_light.aim_key(scene)
    lit = _collection(CHAR_LIT, chars, 'INCLUDE')
    key.light_linking.receiver_collection = lit
    key.light_linking.blocker_collection = lit
    out = _collection(CHAR_OUT, chars, 'EXCLUDE')
    for o in scene.objects:
        if o.type != 'LIGHT' or o is key:
            continue
        if o.light_linking.receiver_collection is None:
            o.light_linking.receiver_collection = out
            o[OUT_MARK] = True
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
        if o.type != 'LIGHT':
            continue
        ll = o.light_linking
        if ll.receiver_collection is not None and ll.receiver_collection.name in (CHAR_LIT, CHAR_OUT):
            ll.receiver_collection = None
        if ll.blocker_collection is not None and ll.blocker_collection.name == CHAR_LIT:
            ll.blocker_collection = None
        if OUT_MARK in o:
            del o[OUT_MARK]
    from . import cel_light
    o = bpy.data.objects.get(cel_light.SUN_NAME)
    # 分けるときに作った日は消す。ただし場面にほかの日が無ければ、それがセルの日なので残す
    if o is not None and o.get(OWN_SUN):
        others = [s for s in scene.objects if s.type == 'LIGHT' and s.data.type == 'SUN'
                  and s is not o and not s.hide_render]
        if others:
            d = o.data
            bpy.data.objects.remove(o)
            if d is not None and d.users == 0:
                bpy.data.lights.remove(d)
        else:
            del o[OWN_SUN]
    _clear_old(scene)
    for name in (CHAR_LIT, CHAR_OUT):
        c = bpy.data.collections.get(name)
        if c is not None:
            bpy.data.collections.remove(c)
    for m in bpy.data.materials:
        if m.use_nodes and m.node_tree is not None:
            for n in [n for n in m.node_tree.nodes if n.label == MASK_LABEL]:
                m.node_tree.nodes.remove(n)


def mask_socket(rl):
    from . import compat
    return compat.render_layer_socket(rl, (MASK_AOV,))
