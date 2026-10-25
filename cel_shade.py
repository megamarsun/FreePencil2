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

import re

import bpy

from . import compat
import logging

logger = logging.getLogger(__name__)

CEL_LABEL = "FP_CelShade"
SHADE_AOV = "fp_shade"
# 材質に足すノードの目印。「FreePencil を外す」がこれで見つけて消す
SHADE_NODE_LABEL = "FreePencil_shade_aov"
# 金属・ガラスの色(拡散の色のパスに入らない分)を書く AOV
METAL_AOV = "fp_metal"
METAL_NODE_LABEL = "FreePencil_metal_aov"
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


FACE_RE = re.compile(r"(?<![a-z])face|顔|かお|フェイス|(?<![a-z])cheek|チーク|頬|ほほ", re.IGNORECASE)


def is_face_material(m) -> bool:
    """顔の材質か。材質の "fp_face"(True/False)があればそれ、無ければ名前で見る。

    "Surface" などに当たらないよう、face / cheek の前が英字のときは数えない。
    """
    if "fp_face" in m:
        return bool(m["fp_face"])
    return bool(FACE_RE.search(m.name))


def ensure_shade_aov(scene, view_layer) -> int:
    """影の AOV を材質とビューレイヤーに用意する。足した材質の数を返す。

    AOV は色で、R = 白い拡散面の光、G = 1(物がある印)、B = 顔の材質なら 1。物のある所を深度や
    アルファで取ると、背景が不透明で遠景の大きい場面で空まで物と見なした
    (C62 の場面で空が暗い灰色になった)。材質が書く印なら背景の設定に左右されない。

    R の光(Shader to RGB)は材質の中で光をもう一度計算するので重い。手続きテクスチャの多い材質
    (ろうそくの蝋: ノイズ 5 個と凹凸)ではシェーダーが GPU の命令数を超えてコンパイルできず、
    材質の表示が紫、セルでは物が透明になった(halloween_pumpkin)。日があれば光は法線と影の
    パスから取れるので、重い材質(_heavy)だけ作らずに R = -1 の印を書く(light_socket が見る)。
    ほかの材質は今までどおり作る: 拡散の色が 0 の材質(金属・ガラス・真っ黒・発光だけ)は
    影のパスがずれた三日月になり(4.5 で確認)、R の光が要る。日を足したり外したりしたら、
    次にセルを作り直すときに合わせる。
    """
    has_sun = key_sun(scene) is not None
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
        face = 1.0 if is_face_material(m) else 0.0
        comb = next((n for n in mine if n.type == "COMBINE_COLOR"), None)
        has_light = any(n.type == "SHADERTORGB" for n in mine)
        want_light = not (has_sun and _heavy(m))
        if comb is not None and has_light == want_light:
            comb.inputs[2].default_value = face     # 名前や fp_face を後から変えても効く
            continue
        for n in mine:                          # 前の形(光だけ / 日の有無が違う)は作り直す
            nodes.remove(n)
        comb = nodes.new("ShaderNodeCombineColor")
        comb.inputs[0].default_value = NO_LIGHT
        comb.inputs[1].default_value = 1.0
        comb.inputs[2].default_value = face
        out = nodes.new("ShaderNodeOutputAOV")
        out.aov_name = SHADE_AOV
        chain = [comb, out]
        links = m.node_tree.links
        if want_light:
            dif = nodes.new("ShaderNodeBsdfDiffuse")
            dif.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
            s2r = nodes.new("ShaderNodeShaderToRGB")
            bw = nodes.new("ShaderNodeRGBToBW")
            links.new(dif.outputs[0], s2r.inputs[0])
            links.new(s2r.outputs["Color"], bw.inputs[0])
            links.new(bw.outputs[0], comb.inputs[0])
            chain = [dif, s2r, bw] + chain
        for i, n in enumerate(chain):
            n.label = SHADE_NODE_LABEL
            n.location = (10 + 180 * i, 900)
            n.hide = True
        links.new(comb.outputs[0], out.inputs["Color"])
        added += 1
    added += ensure_metal_aov(scene, view_layer)
    if added:
        view_layer.update()
    return added


def _surface_bsdfs(m):
    """材質の出力の Surface から上流にある BSDF(ノードグループの中は見ない)。"""
    out = next((n for n in m.node_tree.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output), None)         or next((n for n in m.node_tree.nodes if n.type == "OUTPUT_MATERIAL"), None)
    if out is None or not out.inputs["Surface"].is_linked:
        return []
    found, stack, seen = [], [lk.from_node for lk in out.inputs["Surface"].links], set()
    while stack:
        x = stack.pop()
        if x.name in seen:
            continue
        seen.add(x.name)
        if x.type in ("BSDF_PRINCIPLED", "BSDF_DIFFUSE", "BSDF_GLASS", "BSDF_GLOSSY", "BSDF_REFRACTION"):
            found.append(x)
        elif x.type in ("MIX_SHADER", "ADD_SHADER"):
            stack += [lk.from_node for s in x.inputs for lk in s.links if s.type == "SHADER"]
    return found


def ensure_metal_aov(scene, view_layer) -> int:
    """金属とガラスの色を AOV(fp_metal)に書く。足した材質の数を返す。

    セルの色は「拡散の色 + 発光」のパスから取るが、金属とガラスは拡散の色が 0 で、銀の包丁も
    ガラスのコップも黒から持ち上げた暗い灰色になった(cleaver_knife, baccarat の調査)。
    反射の色のパスには金属の色が入るが、普通の材質の縁にも明るく入る。そこで Principled の
    地の色 x (1 - (1 - 金属)(1 - 透過)) を書く。拡散の色のパスは 地の色 x (1 - 金属)(1 - 透過)
    なので、足すと地の色になる。金属でも透過でもない材質には何も足さない(絵は変わらない)。
    """
    def num(sock):
        return None if sock is None or sock.is_linked else float(sock.default_value)

    added = 0
    want_any = False
    done = set()
    for m in _iter_materials(scene):
        if m.name in done:
            continue
        done.add(m.name)
        nodes, links = m.node_tree.nodes, m.node_tree.links
        # Principled があればそれ。拡散の BSDF と混ぜた反射(つや)は足さない(拡散の色が入っている)。
        # ガラス・反射だけの材質はその色
        bs = _surface_bsdfs(m)
        b = next((x for x in bs if x.type == "BSDF_PRINCIPLED"), None)
        if b is None and bs and not any(x.type == "BSDF_DIFFUSE" for x in bs):
            b = bs[0]
        if b is not None and b.type == "BSDF_PRINCIPLED":
            met = b.inputs.get("Metallic")
            tr = b.inputs.get("Transmission Weight") or b.inputs.get("Transmission")
            need = not (num(met) == 0.0 and num(tr) == 0.0)
            color = b.inputs.get("Base Color")
        else:
            met = tr = None
            need = b is not None
            color = b.inputs.get("Color") if b is not None else None
        mine = [n for n in nodes if n.label == METAL_NODE_LABEL]
        if mine and need and mine[0].get("fp_src") == b.name:
            want_any = True
            continue
        for n in mine:
            nodes.remove(n)
        if not need or color is None:
            continue
        want_any = True

        def node(t, i):
            n = nodes.new(t)
            n.label = METAL_NODE_LABEL
            n.location = (10 + 180 * i, 1000)
            n.hide = True
            return n

        def feed(sock, dst):
            if sock is None:
                dst.default_value = 0.0
            elif sock.is_linked:
                links.new(sock.links[0].from_socket, dst)
            else:
                dst.default_value = sock.default_value

        # k = 1 - (1 - 金属)(1 - 透過)。金属だけ/透過だけの BSDF(ガラス・反射)は 1
        k_out = None
        if met is not None:
            a = node("ShaderNodeMath", 0)
            a.operation = "SUBTRACT"
            a.inputs[0].default_value = 1.0
            feed(met, a.inputs[1])
            c = node("ShaderNodeMath", 1)
            c.operation = "SUBTRACT"
            c.inputs[0].default_value = 1.0
            feed(tr, c.inputs[1])
            mul = node("ShaderNodeMath", 2)
            mul.operation = "MULTIPLY"
            links.new(a.outputs[0], mul.inputs[0])
            links.new(c.outputs[0], mul.inputs[1])
            k = node("ShaderNodeMath", 3)
            k.operation = "SUBTRACT"
            k.use_clamp = True
            k.inputs[0].default_value = 1.0
            links.new(mul.outputs[0], k.inputs[1])
            k_out = k.outputs[0]
        sc_ = node("ShaderNodeVectorMath", 4)
        sc_.operation = "SCALE"
        if color.is_linked:
            links.new(color.links[0].from_socket, sc_.inputs[0])
        else:
            sc_.inputs[0].default_value = tuple(color.default_value)[:3]
        if k_out is not None:
            links.new(k_out, sc_.inputs["Scale"])
        else:
            sc_.inputs["Scale"].default_value = 1.0
        out = node("ShaderNodeOutputAOV", 5)
        out.aov_name = METAL_AOV
        out["fp_src"] = b.name
        for n in nodes:
            if n.label == METAL_NODE_LABEL:
                n["fp_src"] = b.name
        links.new(sc_.outputs[0], out.inputs["Color"])
        added += 1
    aov = next((a for a in view_layer.aovs if a.name == METAL_AOV), None)
    if want_any and aov is None:
        aov = view_layer.aovs.add()
        aov.name = METAL_AOV
        aov.type = 'COLOR'
    return added


NO_LIGHT = -1.0                    # AOV の R: この材質は光を書いていない(パスから取る)
_PROCEDURAL = {"TEX_NOISE", "TEX_VORONOI", "TEX_MUSGRAVE", "TEX_WAVE", "TEX_MAGIC", "TEX_GABOR"}


def _heavy(m) -> bool:
    """手続きテクスチャが 6 以上ある材質(凹凸は上流を 3 回計算するので 2 を足す)。
    ろうそくの蝋はノイズ 5 個 + 凹凸で 7。"""
    def walk(tree, seen):
        n_ = 0
        for n in tree.nodes:
            if n.type in _PROCEDURAL:
                n_ += 1
            elif n.type == "BUMP" and n.inputs["Height"].is_linked:
                n_ += 2
            elif n.type == "GROUP" and n.node_tree is not None and n.node_tree.name not in seen:
                seen.add(n.node_tree.name)
                n_ += walk(n.node_tree, seen)
        return n_
    return walk(m.node_tree, set()) >= 6


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


def on_white(tree, add, src, dx, dy=0):
    """線の絵を白の上に重ね、0..1 に収めた出口を返す(add はノードを作る関数)。

    白プレビューで背景が透過だと、線の絵の物の外は「色は白、アルファ 0」(足し合わせの光)になる。
    白に重ねると 1 + 1 = 2 になり、空の色やマテリアルの色を掛けると白に飛んだ(v2.9 の総当りと
    ビューポートで発見)。Alpha Over の「ストレートアルファ」はビューポートのコンポジタで効かなかった
    ので、重ねたあと 1 で切る(プリマルチプライの縁 0.5 + 0.5 = 1 も正しく白になる)。
    """
    over = add("CompositorNodeAlphaOver", dx, dy)
    ci = _color_inputs(over)
    ci[0].default_value = (1.0, 1.0, 1.0, 1.0)
    tree.links.new(src, ci[1])
    clamp = add("CompositorNodeMixRGB", dx + 75, dy)
    clamp.blend_type = "MIX"
    clamp.use_clamp = True
    clamp.inputs[0].default_value = 0.0
    tree.links.new(over.outputs[0], clamp.inputs[1])
    return clamp.outputs[0]


def smooth_light(tree, add, light, present, scene, dx, dy):
    """2 階調に切る前の光。ふつうは少しぼかすだけ、細かい凹凸のある所だけ大きくぼかす。

    銃のグリップの粒や屋根瓦は、粒ごとに光がしきい値をまたいで、影がざらざらのまだらになった
    (v3.0 の作例調査)。全体を大きくぼかすと消えるが、滑らかな面の影の形まで丸くなる。
    そこで「光 - 少しぼかした光」の揺れを広く平均し、揺れの多い所だけ大きいぼかしに替える。
    大きいぼかしは物の中だけで平均する(縁で空の 0 と混ざって影の縁取りが出ないように)。
    """
    from . import line_weight
    ss = 2.0 if scene.render.resolution_percentage == 200 else 1.0
    big_px = int(round(12 * ss))

    def blur(sock, px, x, y):
        n = add("CompositorNodeBlur", dx + x, dy + y)
        line_weight._set_blur(n, px)
        tree.links.new(sock, n.inputs[0])
        return n.outputs[0]

    def math(op, a, b, x, y, clamp=False):
        n = add("CompositorNodeMath", dx + x, dy + y)
        n.operation = op
        n.use_clamp = clamp
        for i, v in enumerate((a, b)):
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            elif v is not None:
                tree.links.new(v, n.inputs[i])
        return n.outputs[0]

    small = blur(light, max(0, int(round(getattr(scene, "fp_cel_softness", 3.0) * ss))), 0, 0)
    inner = add("CompositorNodeDilateErode", dx, dy - 60)       # 縁の段差は揺れに数えない
    line_weight._set_dilate(inner, -max(1, int(round(2 * ss))))
    tree.links.new(present, inner.inputs[0])
    wiggle = math("MULTIPLY", math("ABSOLUTE", math("SUBTRACT", light, small, 150, -60), None, 300, -60),
                  inner.outputs[0], 450, -60)
    area = math("MAXIMUM", blur(inner.outputs[0], big_px, 600, -120), 1e-3, 750, -120)
    rough = math("DIVIDE", blur(wiggle, big_px, 600, -60), area, 900, -60)
    k = math("MULTIPLY", math("SUBTRACT", rough, ROUGH_FROM, 1050, -60), 1 / ROUGH_SPAN, 1200, -60, clamp=True)
    p_area = math("MAXIMUM", blur(present, big_px, 600, -180), 1e-3, 750, -180)
    big = math("DIVIDE", blur(math("MULTIPLY", light, present, 450, -180), big_px, 600, -240), p_area, 900, -180)
    return math("ADD", small, math("MULTIPLY", k, math("SUBTRACT", big, small, 1050, -180), 1200, -150), 1350, -100)


ROUGH_FROM = 0.01                           # 揺れの平均がこれを超えると大きいぼかしへ寄せ始める
ROUGH_SPAN = 0.02                           # この幅で大きいぼかしに替わりきる


def pale_color(tree, add, base, scene, dx, dy):
    """セルの地の色: 材質の色を白へ寄せたもの。

    寄せるのは見た目の明るさ(ガンマ 2.2)の上で。リニアのまま寄せると小さい成分が大きく
    持ち上がり、橙がサーモン色に、影の青みと合わさって藤色にくすんだ(KUKA のロボット、車)。
    ただそれだけだと暗い材質がほぼ黒のままで、日なたと影の区別が見えなかった(ギター、銃、電話)。
    そこで暗い色ほど余分に白へ寄せる: 量 = 薄め x 2 x (1 - 明るさ)^3。黒は薄め 0.15 で
    明るさ 0.3 の灰色になり、橙などはほとんど動かない(2 乗では車の橙が少しサーモン寄りに
    戻った)。薄め 0 なら何もしない。
    """
    p = float(getattr(scene, "fp_cel_pale", 0.15))

    def mixw(fac, col, x):
        n = add("CompositorNodeMixRGB", dx + x, dy)
        n.blend_type = "MIX"
        if isinstance(fac, float):
            n.inputs[0].default_value = fac
        else:
            tree.links.new(fac, n.inputs[0])
        tree.links.new(col, n.inputs[1])
        n.inputs[2].default_value = (1.0, 1.0, 1.0, 1.0)
        return n.outputs[0]

    def math(op, a, b, x, y):
        n = add("CompositorNodeMath", dx + x, dy + y)
        n.operation = op
        n.use_clamp = True                  # 1 を超える色で負の数の累乗にならないように
        for i, v in enumerate((a, b)):
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            else:
                tree.links.new(v, n.inputs[i])
        return n.outputs[0]

    m = mixw(p, _gamma(tree, add, base, 1 / 2.2, dx, dy), 75)
    bw = add("CompositorNodeRGBToBW", dx + 100, dy - 40)
    tree.links.new(m, bw.inputs[0])
    dark = math("POWER", math("SUBTRACT", 1.0, bw.outputs[0], 120, -40), 3.0, 140, -40)
    lift = math("MINIMUM", math("MULTIPLY", dark, 2.0 * p, 160, -40), 1.0, 180, -40)
    return _gamma(tree, add, mixw(lift, m, 200), 2.2, dx + 220, dy)


def _gamma(tree, add, sock, g, dx, dy):
    """色の 3 成分をそれぞれ g 乗する。5.x には Gamma ノードが無いので、分けて累乗して戻す。"""
    sep = add("CompositorNodeSeparateColor", dx, dy)
    tree.links.new(sock, sep.inputs[0])
    comb = add("CompositorNodeCombineColor", dx + 40, dy)
    for i in range(3):
        p = add("CompositorNodeMath", dx + 20, dy - 20 * i)
        p.operation = "POWER"
        tree.links.new(sep.outputs[i], p.inputs[0])
        p.inputs[1].default_value = g
        tree.links.new(p.outputs[0], comb.inputs[i])
    comb.inputs[3].default_value = 1.0
    return comb.outputs[0]


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


SUN_LABEL = "FP_CelSun"            # 日の向き(x, y, z)を入れた掛け算のノード。日を回すと書き換える
NORMAL_SOCKETS = ("Normal",)
SHADOW_SOCKETS = ("Shadow",)


def key_sun(scene):
    """一番強い日(サン)。無ければ None(点光源などは材質の光で取る)。"""
    suns = [o for o in scene.objects if o.type == 'LIGHT' and o.data.type == 'SUN'
            and not o.hide_render]
    return max(suns, key=lambda o: o.data.energy, default=None)


def sun_vector(sun):
    """日の来る向き(ワールド、単位ベクトル)。"""
    v = sun.matrix_world.to_3x3() @ __import__("mathutils").Vector((0.0, 0.0, 1.0))
    return v.normalized()


def light_socket(tree, rl, scene, new_node, x0, y0, label):
    """0..1 の光(1 = 日に正面から当たっている)の出口と、物のある印の出口を返す。

    日があれば「法線のパス・日の向き(内積)x 影のパス」で取る。どちらも材質に関係しない。
    材質に足した「白い拡散面の光」(Shader to RGB)は、表面下散乱や地の色の暗い材質で
    光り方が変わり(同じ球でも陰の位置がずれた)、5.2 では材質の拡散と混ざって、服だけ
    明るく出た(v2.9 の実モデルの総当りで発見)。日が無い場面だけ、その光を正規化して使う。
    """
    from . import line_weight
    shade = compat.render_layer_socket(rl, (SHADE_AOV,))
    sep = new_node("CompositorNodeSeparateColor", x0, y0)
    tree.links.new(shade, sep.inputs[0])
    present = sep.outputs[1]
    sun = key_sun(scene)
    nrm = compat.render_layer_socket(rl, NORMAL_SOCKETS)
    shd = compat.render_layer_socket(rl, SHADOW_SOCKETS)
    # R = -1 は「光を書いていない材質」の印(ensure_shade_aov)。正規化の前に 0 に戻す
    lit_r = line_weight._math(tree, "MAXIMUM", x0 + 75, y0 + 30)
    lit_r.label = label
    lit_r.hide = True
    tree.links.new(sep.outputs[0], lit_r.inputs[0])
    lit_r.inputs[1].default_value = 0.0
    if sun is None or nrm is None or shd is None:
        norm = new_node("CompositorNodeNormalize", x0 + 150, y0)
        tree.links.new(lit_r.outputs[0], norm.inputs[0])
        return norm.outputs[0], present
    L = sun_vector(sun)
    ns = new_node("CompositorNodeSeparateColor", x0, y0 - 60)
    tree.links.new(nrm, ns.inputs[0])

    def m(op, a, b, dx, dy):
        n = line_weight._math(tree, op, x0 + dx, y0 + dy)
        n.label = label
        n.hide = True
        for i, v in enumerate((a, b)):
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            elif v is not None:
                tree.links.new(v, n.inputs[i])
        return n
    terms = []
    for i in range(3):
        t = m("MULTIPLY", ns.outputs[i], float(L[i]), 150, -60 - 30 * i)
        t[SUN_LABEL] = i                    # 日を回したらこの値を書き換える
        terms.append(t.outputs[0])
    dot = m("ADD", m("ADD", terms[0], terms[1], 300, -60).outputs[0], terms[2], 450, -60)
    dot.use_clamp = True
    sbw = new_node("CompositorNodeRGBToBW", x0 + 300, y0 - 150)
    tree.links.new(shd, sbw.inputs[0])
    geo = m("MULTIPLY", dot.outputs[0], sbw.outputs[0], 600, -60)
    # 拡散の色が無い材質(発光だけ・トゥーン・ガラス)は、4.x の影のパスが 0 になり全部影に
    # なった(4.5 で確認、5.2 は出る)。そこは材質の「白い拡散面の光」を使う。拡散の無い材質は
    # 表面下散乱も無いので、こちらで正しく出る
    dcol = compat.render_layer_socket(rl, DIFFUSE_COLOR_SOCKETS)
    if dcol is None:
        return geo.outputs[0], present
    norm = new_node("CompositorNodeNormalize", x0 + 150, y0 + 60)
    tree.links.new(lit_r.outputs[0], norm.inputs[0])
    cbw = new_node("CompositorNodeRGBToBW", x0 + 300, y0 - 200)
    tree.links.new(dcol, cbw.inputs[0])
    # 光を書いていない重い材質(R < 0)もパスの光を使う
    has = m("MAXIMUM", m("GREATER_THAN", cbw.outputs[0], 0.001, 450, -200).outputs[0],
            m("LESS_THAN", sep.outputs[0], 0.0, 450, -240).outputs[0], 600, -220)
    d = m("SUBTRACT", geo.outputs[0], norm.outputs[0], 750, -60)
    light = m("ADD", norm.outputs[0], m("MULTIPLY", d.outputs[0], has.outputs[0], 750, -100).outputs[0], 900, -60)
    # 顔(AOV の B = 1)だけ光の取り方を変える。髪や帽子の落とす影が顔にまだらに落ち、
    # 面の向きだけでも頬や鼻に崩れた形の影が出た(v3.0 の作例調査)
    face_mode = getattr(scene, "fp_cel_face", 'SHADOW')
    if face_mode == 'SHADOW':
        return light.outputs[0], present
    face_light = dot.outputs[0] if face_mode == 'NO_CAST' else 1.0
    fd = m("SUBTRACT", face_light, light.outputs[0], 1050, -60)
    out = m("ADD", light.outputs[0], m("MULTIPLY", fd.outputs[0], sep.outputs[2], 1050, -100).outputs[0],
            1200, -60)
    return out.outputs[0], present


def update_sun(scene) -> bool:
    """コンポジタの日の向きを、いまの日に合わせる。変えたら True。"""
    tree = compat.get_compositor_tree(scene)
    if tree is None:
        return False
    nodes = [n for n in tree.nodes if SUN_LABEL in n]
    if not nodes:
        return False
    sun = key_sun(scene)
    if sun is None:
        return False
    L = sun_vector(sun)
    changed = False
    for n in nodes:
        v = float(L[int(n[SUN_LABEL])])
        if abs(n.inputs[1].default_value - v) > 1e-5:
            n.inputs[1].default_value = v
            changed = True
    return changed


def ensure_light_passes(view_layer) -> None:
    for k in ("use_pass_normal", "use_pass_shadow"):
        if not getattr(view_layer, k):
            setattr(view_layer, k, True)


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
    ensure_light_passes(vl)
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

    # 光(0..1)-> ぼかし -> しきい値 = 日なた
    light, present = light_socket(tree, rl, scene, lambda t, dx, dy: add(t, dx, dy), -300, 0, CEL_LABEL)
    for n in tree.nodes:
        if n.label == CEL_LABEL and n not in nodes:
            nodes.append(n)
    soft = smooth_light(tree, add, light, present, scene, 150, -300)
    lit = math("GREATER_THAN", soft, float(getattr(scene, "fp_cel_threshold", 0.55)), 300, 0)

    white = (1.0, 1.0, 1.0)

    def opaque(sock, dx, dy):
        # パスは物の外でアルファ 0。ビューポートのコンポジタは Mix にそのアルファを持ち込み、
        # 空の色が透けて白く出た(F12 では出ない)。先にアルファを 1 にしてから混ぜる
        n = add("CompositorNodeSetAlpha", dx, dy)
        compat.set_node_value(n, "mode", "REPLACE_ALPHA")
        tree.links.new(sock, n.inputs["Image"])
        n.inputs["Alpha"].default_value = 1.0
        return n.outputs[0]
    base = opaque(dcol, 75, 160)
    if emit is not None:
        base = mix(1.0, base, opaque(emit, 75, 200), "ADD", 150, 120)
        base.node.use_clamp = True
    metal = compat.render_layer_socket(rl, (METAL_AOV,))
    if metal is not None:                   # 金属・ガラスの色(ensure_metal_aov)
        base = mix(1.0, base, opaque(metal, 75, 240), "ADD", 190, 160)
        base.node.use_clamp = True
    pale = pale_color(tree, add, base, scene, 225, 140)
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

    # 線の絵は物の外が透過のことがある。白の上に重ねてから掛ける。掛けるときは線の絵を
    # 1 番目の口に入れる(ビューポートの乗算は 1 番目のアルファを持ち込み、細い線が消えた)
    over_out = on_white(tree, add, src, 600, 220)
    from . import leaf_clump
    if getattr(scene, "fp_cel_sky", True):
        # 物の外は空の色。線の絵(物の外にはみ出した輪郭)はその上に掛ける
        sky = tuple(getattr(scene, "fp_cel_sky_color", (0.6, 0.76, 0.93)))
        body = mix(sil, sky, colored, "MIX", 900, 60)
        # 葉のかたまりの中に空がまだらに透けないよう、すき間を葉の色で埋める
        body, _gap = leaf_clump.fill_gaps(tree, add, rl, scene, body, 900, -400)
        out = mix(1.0, over_out, body, "MULTIPLY", 1050, 100)
        opaque = add("CompositorNodeSetAlpha", 1200, 100)
        compat.set_node_value(opaque, "mode", "REPLACE_ALPHA")
        tree.links.new(out, opaque.inputs["Image"])
        opaque.inputs["Alpha"].default_value = 1.0
        result = opaque.outputs[0]
    else:
        # 空なし: 物の中だけ色を付け、元の線の絵(透過)の上に重ねる
        colored, gap = leaf_clump.fill_gaps(tree, add, rl, scene, colored, 900, -400)
        if gap is not None:                 # 葉のかたまりのすき間も物の中として塗る
            sil = math("MAXIMUM", sil, gap, 1050, 180)
        inside = mix(1.0, over_out, colored, "MULTIPLY", 900, 120)
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


# ---------------------------------------------------------------- 強弱のある線の下に敷く(マテリアル / モノクロ)

UNDER_LABEL = "FP_Underlay"


def wants_underlay(scene) -> bool:
    """強弱のある線(キャラ / 手描き背景)で、マテリアルかモノクロを選んでいるとき。

    強弱の処理は、合成に入る絵の暗い所をすべて線として扱う。マテリアル/モノクロでは
    その絵が「材質の色や陰影の上に線」なので、陰影まで黒い線になり、色も消えて灰色に
    なった(v2.8.0 から。v2.9 のデモを作っていて見つけた)。線は白地に描いて強弱を付け、
    材質の色や陰影はその後で下に掛ける。精密は今までどおり(v2.7 と同じ絵のまま)。
    木の葉のかたまりと内側(丸み)も入ってくる絵を白地の線として扱うので同じ。精密の木で
    材質を選ぶと、葉のかたまりの中が白く塗られた(european-maple)。
    """
    from . import inner_line, leaf_clump, line_scale
    return ((bool(getattr(scene, "fp_line_weight", False)) or line_scale.needed(scene)
             or leaf_clump.needed(scene) or inner_line.needed(scene))
            and getattr(scene, "fp_preview_mode", "NONE") in ("NONE", "MONO_LIGHT"))


def set_underlay(scene, kind) -> int:
    """kind: "NONE"(材質の色)/ "MONO_LIGHT"(陰影)/ None(外す)。作ったノードの数を返す。"""
    tree = compat.get_compositor_tree(scene)
    if tree is None:
        return 0
    made = [n for n in tree.nodes if n.label == UNDER_LABEL]
    target = _target_socket(tree)
    if made:
        _remove(tree, made, target)
        target = _target_socket(tree)
    if kind is None or target is None or not target.is_linked:
        return 0
    rl = next((n for n in tree.nodes if n.type == 'R_LAYERS'), None)
    if rl is None:
        return 0
    src = target.links[0].from_socket
    prev = (src.node.name, list(src.node.outputs).index(src))
    x0, y0 = target.node.location.x - 700, target.node.location.y - 500
    nodes = []

    def add(type_name, dx, dy):
        n = compat.new_node(tree, type_name)
        n.label = UNDER_LABEL
        n.location = (x0 + dx, y0 + dy)
        n.hide = True
        nodes.append(n)
        return n

    if kind == "MONO_LIGHT":
        light = compat.render_layer_socket(rl, compat.DIFFUSE_DIRECT_SOCKETS)
        if light is None:
            return 0
        bw = add("CompositorNodeRGBToBW", 0, 0)
        tree.links.new(light, bw.inputs[0])
        lift = add("CompositorNodeMapRange", 150, 0)
        compat.set_node_value(lift, "use_clamp" if hasattr(lift, "use_clamp") else "clamp", True)
        floor = max(0.0, min(0.9, float(getattr(scene, "fp_mono_floor", 0.25))))
        for name, val in (("From Min", 0.0), ("From Max", 1.0), ("To Min", floor), ("To Max", 1.0)):
            sock = lift.inputs.get(name)
            if sock is not None:
                sock.default_value = val
        tree.links.new(bw.outputs[0], lift.inputs[0])
        base = lift.outputs[0]
    else:
        base = rl.outputs.get("Image")
        if base is None:
            return 0
    # 葉のかたまりの中のすき間を葉の色で埋める(線はかたまりの縁なのに、色は葉 1 枚ずつで
    # 後ろが透けた)
    from . import leaf_clump
    base, _gap = leaf_clump.fill_gaps(tree, add, rl, scene, base, 0, -300)

    # 線の絵(物の外は透過のことがある)を白の上に重ね、下の絵に掛ける。アルファは線の絵のまま
    over_out = on_white(tree, add, src, 300, 100)
    mul = add("CompositorNodeMixRGB", 450, 60)
    mul.blend_type = "MULTIPLY"
    mul.inputs[0].default_value = 1.0
    # 線の絵を上の口(1 番目)に入れる。ビューポートのコンポジタの乗算は 1 番目の口のアルファを
    # 持ち込み、色の絵を先に入れると細い線が消えた(F12 では出る。窓のある Blender で発見)
    tree.links.new(over_out, mul.inputs[1])
    tree.links.new(base, mul.inputs[2])
    sep = add("CompositorNodeSeparateColor", 300, -60)
    tree.links.new(src, sep.inputs[0])
    alpha = add("CompositorNodeSetAlpha", 600, 60)
    compat.set_node_value(alpha, "mode", "REPLACE_ALPHA")
    tree.links.new(mul.outputs[0], alpha.inputs["Image"])
    tree.links.new(sep.outputs[3], alpha.inputs["Alpha"])
    for lk in list(target.links):
        tree.links.remove(lk)
    tree.links.new(alpha.outputs[0], target)
    nodes[0]["fp_prev_node"], nodes[0]["fp_prev_out"] = prev[0], int(prev[1])
    logger.info(f"Underlay {kind}: {len(nodes)} nodes")
    return len(nodes)


# ---------------------------------------------------------------- 書き出し用のレイヤー(v2.9)

LAYER_LABEL = "FreePencil_layers"       # STEP3 の作り直しで消える名前("FreePencil" で始まる)


def layer_socket(tree, rl, scene, which, line_src=None):
    """ファイル出力に出すレイヤーの絵を作り、出口のソケットを返す。プレビューの種類に左右されない。

    which:
      "cel_color"  影を付けない薄い色(セルの色の薄さ)。物の外は透過
      "cel_shadow" 影の所だけ影の色、日なたは透過(乗算のレイヤーとして重ねる)
      "line_final" line_src(白地に黒線の絵)を、黒い線 + 透過に直したもの
    """
    from . import line_weight
    ss = 2.0 if scene.render.resolution_percentage == 200 else 1.0
    x0, y0 = rl.location.x + 400, rl.location.y - 1400 - 300 * ["cel_color", "cel_shadow", "line_final"].index(which)

    def add(type_name, dx, dy=0):
        n = compat.new_node(tree, type_name)
        n.label = LAYER_LABEL
        n.location = (x0 + dx, y0 + dy)
        n.hide = True
        return n

    def set_alpha(img, alpha, dx):
        sa = add("CompositorNodeSetAlpha", dx)
        compat.set_node_value(sa, "mode", "REPLACE_ALPHA")
        if isinstance(img, tuple):
            sa.inputs["Image"].default_value = (*img[:3], 1.0)
        else:
            tree.links.new(img, sa.inputs["Image"])
        tree.links.new(alpha, sa.inputs["Alpha"])
        return sa.outputs[0]

    if which == "line_final":
        if line_src is None:
            return None
        over_out = on_white(tree, add, line_src, 0)
        bw = add("CompositorNodeRGBToBW", 150)
        tree.links.new(over_out, bw.inputs[0])
        inv = line_weight._math(tree, "SUBTRACT", x0 + 300, y0, a=1.0)
        inv.label = LAYER_LABEL
        tree.links.new(bw.outputs[0], inv.inputs[1])
        return set_alpha((0.0, 0.0, 0.0), inv.outputs[0], 450)

    shade = compat.render_layer_socket(rl, (SHADE_AOV,))
    if shade is None:
        return None
    sep = add("CompositorNodeSeparateColor", 0)
    tree.links.new(shade, sep.inputs[0])
    present = sep.outputs[1]
    if which == "cel_color":
        dcol = compat.render_layer_socket(rl, DIFFUSE_COLOR_SOCKETS)
        emit = compat.render_layer_socket(rl, EMIT_SOCKETS)
        if dcol is None:
            return None
        base = dcol
        if emit is not None:
            add_ = add("CompositorNodeMixRGB", 150)
            add_.blend_type = "ADD"
            add_.use_clamp = True
            add_.inputs[0].default_value = 1.0
            tree.links.new(dcol, add_.inputs[1])
            tree.links.new(emit, add_.inputs[2])
            base = add_.outputs[0]
        metal = compat.render_layer_socket(rl, (METAL_AOV,))
        if metal is not None:               # 金属・ガラスの色(ensure_metal_aov)
            add_ = add("CompositorNodeMixRGB", 190)
            add_.blend_type = "ADD"
            add_.use_clamp = True
            add_.inputs[0].default_value = 1.0
            tree.links.new(base, add_.inputs[1])
            tree.links.new(metal, add_.inputs[2])
            base = add_.outputs[0]
        return set_alpha(pale_color(tree, add, base, scene, 225, 0), present, 450)
    # cel_shadow: 影 = 物の中で日なたでない所(光はセルと同じ取り方)
    light, present = light_socket(tree, rl, scene, lambda t, dx, dy: add(t, dx, dy), 150, -200,
                                  LAYER_LABEL)
    soft = smooth_light(tree, add, light, present, scene, 300, -300)
    dark = line_weight._math(tree, "LESS_THAN", x0 + 450, y0, b=float(getattr(scene, "fp_cel_threshold", 0.55)))
    dark.label = LAYER_LABEL
    tree.links.new(soft, dark.inputs[0])
    mask = line_weight._math(tree, "MULTIPLY", x0 + 600, y0)
    mask.label = LAYER_LABEL
    tree.links.new(dark.outputs[0], mask.inputs[0])
    tree.links.new(present, mask.inputs[1])
    return set_alpha(tuple(getattr(scene, "fp_cel_shadow_color", (0.62, 0.62, 0.80))), mask.outputs[0], 750)
