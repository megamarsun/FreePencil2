"""ライトの当て方(v3.0 試作): セルの日をカメラから向ける、縁を光らせる(リム)。

いまのセルは場面にある日(サン)の向きをそのまま使う。作例の日はワールドに固定で、カメラを
回すと影の量が変わり、正面から当たって影が無い、真後ろからで全部影、ということが起きた
(dev/batch/out/report_shade_survey の 6 章)。アニメの光は「画面のどちらから、どれだけ影を
入れるか」で決めるので、カメラを基準に日を向ける。

  - 側: 画面の左 / 右のどちらから当てるか
  - 影の量: 0 = カメラの向きから(影がほぼ無い)、0.5 = 真横、1 = 真後ろ(ほぼ全部影)
  - 高さ: 画面の上へどれだけ傾けるか

カメラを動かすと日もついて行く(render_size._follow_sun)。

リム: 縁(物の輪郭)が後ろからの光で光る帯。しきい値 1 本の今の光では、後ろからの日を当てても
全部影になるだけで縁は光らなかった(同 6 章)。そこで奥行きのパスを画面上で数画素ずらし、
「その向きの隣が自分よりはっきり奥」の所だけを帯にする。幅は画面の画素で一定になり、
腕が胴の前にある所のような、物の中の重なりの縁にも出る。帯は「光る」(日なたの色にリムの色を
スクリーンで重ねる、逆光のハイライト)か「日なたの色」(影の側だけで見える)で塗る。側は影の側か、
左右・上下の「ぐるり」。
"""
from __future__ import annotations

import logging
import math

import bpy
from mathutils import Vector

logger = logging.getLogger(__name__)

SUN_NAME = "FP_KeySun"
RIM_SHIFT = "FP_RimShift"   # 奥行きをずらすノードの印(値 = 幅 px)。カメラや日を回したら向きを書き換える
RIM_FACING = "FP_RimFacing"  # 面の向きを測る掛け算の印(値 = x, y, z)
RIM_DIR = "FP_RimDir"        # 上の 2 つが何番目の向き(rim_sides)のものか
RIM_DEPTH = 0.03            # 隣の奥行きがこれ(自分の奥行きに対する割合)より奥なら縁と見る


def _cam_axes(cam):
    m = cam.matrix_world.to_3x3()
    right = (m @ Vector((1.0, 0.0, 0.0))).normalized()
    up = (m @ Vector((0.0, 1.0, 0.0))).normalized()
    back = (m @ Vector((0.0, 0.0, 1.0))).normalized()        # カメラの +Z は見ている人の側
    return right, up, back


def key_direction(scene):
    """カメラ基準の日の来る向き(ワールド、単位)。カメラが無ければ None。"""
    cam = scene.camera
    if cam is None:
        return None
    right, up, back = _cam_axes(cam)
    side = -right if getattr(scene, "fp_light_side", 'LEFT') == 'LEFT' else right
    a = math.pi * float(getattr(scene, "fp_light_amount", 0.3))
    h = float(getattr(scene, "fp_light_height", math.radians(35.0)))
    flat = back * math.cos(a) + side * math.sin(a)
    return (flat * math.cos(h) + up * math.sin(h)).normalized()


def aim_key(scene, create=False) -> bool:
    """「カメラから」のとき、一番強い日をカメラ基準の向きに回す。回したら True。

    日が無ければ create のときだけ作る(ハンドラの中では作らない)。"""
    if getattr(scene, "fp_light_mode", 'CAMERA') != 'CAMERA':
        return False
    # セルを見ていない場面の日は回さない(既定がカメラからなので、線だけの場面の材質の光を変えないように)
    if getattr(scene, "fp_preview_mode", 'NONE') != 'CEL':
        return False
    d = key_direction(scene)
    if d is None:
        return False
    from . import cel_shade
    sun = cel_shade.key_sun(scene)
    if sun is None:
        if not create:
            return False
        data = bpy.data.lights.new(SUN_NAME, 'SUN')
        data.energy = 3.0
        sun = bpy.data.objects.new(SUN_NAME, data)
        scene.collection.objects.link(sun)
    if (cel_shade.sun_vector(sun) - d).length < 1e-4:
        return False
    # 日の +Z が光の来る向き(cel_shade.sun_vector)。親があれば親の向きを外す
    q = d.to_track_quat('Z', 'Y')
    world = q.to_matrix().to_4x4()
    world.translation = sun.matrix_world.translation
    sun.matrix_world = world
    return True


def rim_sides(scene, light_dir):
    """リムの帯を付ける画面の向き (x, y) の並び。既定は日の反対の横(影の側の縁)。

    「ぐるり」は上下左右の 4 つ(逆光のハイライトは頭の上や腕の下の縁にも乗る)。"""
    mode = getattr(scene, "fp_cel_rim_side", 'AUTO')
    if mode == 'ALL':
        return [Vector((1.0, 0.0)), Vector((-1.0, 0.0)), Vector((0.0, 1.0)), Vector((0.0, -1.0))]
    if mode == 'LEFT':
        sx = -1.0
    elif mode == 'RIGHT':
        sx = 1.0
    else:
        sx = 1.0
        cam = scene.camera
        if cam is not None and light_dir is not None:
            right, _up, _back = _cam_axes(cam)
            sx = -1.0 if light_dir.dot(right) > 0.0 else 1.0
    v = Vector((sx, 0.35))                  # 少し上の縁にも(アニメのリムは肩や頭の上に乗る)
    return [v.normalized()]


RIM_SAMPLING = (("Interpolation", "Nearest"), ("Extension X", "Extend"), ("Extension Y", "Extend"))


def _rim_sampling(node) -> bool:
    """5.x の Translate は絵の外を切り(Clip)、なめらかに補間するのが既定。そのままだと画面の端に
    触れる物の、ずらした側の端に幅 w の黒い帯が出た(5.2、端で切れた髪)。4.x と同じく、最寄りの画素を
    使い、絵の外は端の値を延ばす。4.x にはこのソケットが無いので何もしない。変えたら True。"""
    changed = False
    for name, value in RIM_SAMPLING:
        sock = node.inputs.get(name)
        if sock is None or sock.default_value == value:
            continue
        try:
            sock.default_value = value
            changed = True
        except (TypeError, ValueError):
            pass
    return changed


def rim_socket(tree, rl, scene, add, normal, dx, dy):
    """リムの帯(0/1)の出口。奥行きのパスが無ければ None。

    add(type, x, y) はノードを作る関数、normal は光に使った法線(x, y, z の 3 つの出口)。
    向きが複数(ぐるり)なら、向きごとの帯の最大を返す。
    """
    from . import compat, line_weight, cel_shade
    depth = compat.render_layer_socket(rl, line_weight.DEPTH_SOCKETS)
    if depth is None:
        return None
    ss = 2.0 if scene.render.resolution_percentage == 200 else 1.0
    w = max(1.0, float(getattr(scene, "fp_cel_rim_width", 10.0)) * ss)
    sun = cel_shade.key_sun(scene)
    L = cel_shade.sun_vector(sun) if sun is not None else None
    cam = scene.camera

    def math_(op, a, b, x, y):
        n = add("CompositorNodeMath", dx + x, dy + y)
        n.operation = op
        for i, v in enumerate((a, b)):
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            elif v is not None:
                tree.links.new(v, n.inputs[i])
        return n.outputs[0]

    out = None
    for k, sd in enumerate(rim_sides(scene, L)):
        oy = -200 * k
        # 出口の (p) に、その向きへ w 画素先の奥行きを持ってくる(Translate は絵を t だけ動かす)
        t = add("CompositorNodeTranslate", dx, dy + oy)
        tree.links.new(depth, t.inputs["Image"])
        t[RIM_SHIFT] = w
        t[RIM_DIR] = k
        t.inputs["X"].default_value = -round(w * sd.x)
        t.inputs["Y"].default_value = -round(w * sd.y)
        _rim_sampling(t)
        gap =math_("SUBTRACT", t.outputs[0], depth, 150, oy)
        edge = math_("GREATER_THAN", gap, math_("MULTIPLY", depth, RIM_DEPTH, 150, oy - 40), 300, oy)
        # 面の向きがその側を向いている所だけ(平らな正面の縁は光らせない)
        if cam is not None and normal is not None:
            right, up, _back = _cam_axes(cam)
            dw = right * sd.x + up * sd.y
            terms = [math_("MULTIPLY", normal[i], float(dw[i]), 150, oy - 80 - 30 * i) for i in range(3)]
            for i, s_ in enumerate(terms):
                s_.node[RIM_FACING] = i
                s_.node[RIM_DIR] = k
            facing = math_("ADD", math_("ADD", terms[0], terms[1], 300, oy - 80), terms[2], 450, oy - 80)
            edge = math_("MULTIPLY", edge, math_("GREATER_THAN", facing, 0.1, 600, oy - 80), 600, oy)
        out = edge if out is None else math_("MAXIMUM", out, edge, 750, oy)
    # 透ける髪(ディザ)は奥行きが画素ごとに飛び、帯が細かい点々になった(woman_01)。
    # 少しぼかして半分で切り、孤立した点を消す
    b = add("CompositorNodeBlur", dx + 900, dy)
    line_weight._set_blur(b, max(1, int(round(2 * ss))))
    tree.links.new(out, b.inputs[0])
    return math_("GREATER_THAN", b.outputs[0], 0.5, 1000, 0)


def update_rim(scene, tree) -> bool:
    """リムの向き(画面の側と、面の向きを測るワールドの向き)を、いまのカメラと日に合わせる。"""
    from . import cel_shade
    shifts = [n for n in tree.nodes if RIM_SHIFT in n]
    facing = [n for n in tree.nodes if RIM_FACING in n]
    if not shifts and not facing:
        return False
    sun = cel_shade.key_sun(scene)
    sides = rim_sides(scene, cel_shade.sun_vector(sun) if sun is not None else None)
    changed = False
    for n in shifts:
        changed = _rim_sampling(n) or changed      # 前の版で作ったノードも直す
        k = int(n.get(RIM_DIR, 0))
        if k >= len(sides):
            continue
        w = float(n[RIM_SHIFT])
        for key, v in (("X", -round(w * sides[k].x)), ("Y", -round(w * sides[k].y))):
            if n.inputs[key].default_value != v:
                n.inputs[key].default_value = v
                changed = True
    cam = scene.camera
    if cam is not None:
        right, up, _back = _cam_axes(cam)
        for n in facing:
            k = int(n.get(RIM_DIR, 0))
            if k >= len(sides):
                continue
            dw = right * sides[k].x + up * sides[k].y
            v = float(dw[int(n[RIM_FACING])])
            if abs(n.inputs[1].default_value - v) > 1e-5:
                n.inputs[1].default_value = v
                changed = True
    return changed


# ---------------------------------------------------------------- 値を変えたとき

def update_light(self, context):
    """光の向きの値を変えたら日を回す(ノードは作り直さない)。"""
    scene = context.scene
    from . import light_split
    light_split.aim_bg(scene)
    if aim_key(scene, create=True) or light_split.enabled(scene):
        from . import cel_shade
        context.view_layer.update()
        cel_shade.update_sun(scene)
