"""UI-independent core logic for FreePencil STEP2 / STEP3.

Both the UI operators (aov_node.py / sample_node.py) and headless
pipelines (dev/batch/fp_batch.py) call these functions, so they must not
touch context.screen, windows, or popups. Anything UI-related stays in
the operators.
"""

import bpy

from . import compat
from . import line_weight
from . import node_layout
from . import render_size
from . import utils_nodegroup
from .utils_nodes import insert_antialiasing_if_needed

AOV_GROUP_NAME = "FreePencil_aov_Group_v1_1_0"
# 細い線(精密の分割)の AOV を材質へ足すときの目印
FINE_AOV_LABEL = "FreePencil_fine_aov"
NODE_GROUP_PREFIX = "FreePencil_v1_1_0_"

# ファイル出力で書き出せるパス。スロット名がそのままファイル名になる。
#
# source:
#   ("group", 出力名)              PROノードグループの出力から取る
#   ("pass", 有効化プロパティ, 候補) レンダーパスから取る。ソケット名は
#                                   バージョンで変わるので候補を順に探す
#
# 影は EEVEE だとノイズが多く実用に耐えないことが多いので既定 OFF。
# 代わりにディフューズの直接光を既定 ON にしている。
FILE_OUTPUT_PASSES = (
    ("fp_fo_line", "line", ("group", "line")),
    # 色はレンダーそのもの(材質の色)から取る。グループの color 出力は
    # Image 入力の素通しで、白/モノクロのプレビュー中はそれが白や灰色に
    # なり、color.png が真っ白で書き出されていた(v2.7 から。v2.8.1 の点検で発見)
    ("fp_fo_color", "color", ("pass", None, ("Image",))),
    ("fp_fo_light", "light",
     ("pass", "use_pass_diffuse_direct", compat.DIFFUSE_DIRECT_SOCKETS)),
    ("fp_fo_shadow", "shadow", ("pass", "use_pass_shadow", ("Shadow",))),
    # v2.9: セルを別のソフトで重ねるためのレイヤー。影を付けない薄い色と、影の所だけの影の色
    # (乗算で重ねる)。プレビューの種類に関係なく書き出す(cel_shade.layer_socket)
    ("fp_fo_cel_color", "cel_color", ("layer", "cel_color")),
    ("fp_fo_cel_shadow", "cel_shadow", ("layer", "cel_shadow")),
)


def selected_file_output_passes(scene) -> list:
    """チェックの入っているパスだけを返す。"""
    return [entry for entry in FILE_OUTPUT_PASSES
            if getattr(scene, entry[0], False)]


# PROノード内のチャンネル別しきい値ランプ(ノード名は v1_1_0_pro 固定)
CHANNEL_RAMP_NODES = {
    "mecha": "ColorRamp",
    "depth": "ColorRamp.001",
    "bone": "ColorRamp.002",
    "gen": "ColorRamp.003",
    "mat": "ColorRamp.006",
}


def _luma4(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def apply_line_tuning(group: bpy.types.NodeTree,
                      sensitivity: float = 1.0,
                      strengths: dict | None = None) -> None:
    """しきい値位置を「全体感度 × チャンネル別強さ」で一括スケールする。

    線の検出は「エッジ検出勾配 → ColorRamp(輝度)」なので、
    position = 元の位置 × sensitivity ÷ strength。
    strength は 1.0 が現状、2.0 でしきい値半分(線が増える)、
    0 でそのチャンネルは実質OFF(しきい値1.0)。
    元の位置は各ノードのカスタムプロパティに保存するので何度でも冪等。
    """
    strengths = strengths or {}
    name_to_channel = {v: k for k, v in CHANNEL_RAMP_NODES.items()}
    sensitivity = max(0.05, min(2.0, sensitivity))
    for node in group.nodes:
        if node.type != "VALTORGB":
            continue
        ramp = node.color_ramp
        if len(ramp.elements) < 2:
            continue
        # 下降ランプ(白→暗 = 勾配が強いほど線)だけが対象。
        # 黒→白の上昇ランプはマスク系で、スケールすると逆効果になる。
        # 注意: OFF は色を白化するため、判定は「バックアップ済みの元の色」で
        # 行う(現在の色で判定すると白化後に復元不能になる — 実バグ)
        orig_cols = node.get("fp_orig_colors")
        if orig_cols is not None and len(orig_cols) != len(ramp.elements):
            orig_cols = None
        first_col = orig_cols[0] if orig_cols else ramp.elements[0].color
        last_col = orig_cols[-1] if orig_cols else ramp.elements[-1].color
        if _luma4(first_col) <= _luma4(last_col):
            continue
        orig = node.get("fp_orig_positions")
        if orig is None or len(orig) != len(ramp.elements):
            orig = [e.position for e in ramp.elements]
            node["fp_orig_positions"] = orig
        if orig_cols is None:
            orig_cols = [list(e.color) for e in ramp.elements]
            node["fp_orig_colors"] = orig_cols
        factor = sensitivity
        channel = name_to_channel.get(node.name)
        if channel is not None:
            s = strengths.get(channel, 1.0)
            if s <= 0.001:
                factor = None  # OFF
            else:
                factor = sensitivity / max(0.05, min(2.0, s))
        for i, (elem, p0) in enumerate(zip(ramp.elements, list(orig))):
            if factor is None:
                # OFF: しきい値には上限1.0があるが Sobel 勾配は 1.0 を
                # 超えるため、位置では消しきれない。色ごと白にして
                # 「どんな勾配でも線ゼロ」を保証する(色は復元可能)
                elem.position = 1.0
                elem.color = (1.0, 1.0, 1.0, 1.0)
            else:
                elem.position = min(1.0, max(0.0, p0 * factor))
                elem.color = list(orig_cols[i])


RELIEF_LABEL = "freepencil_relief"


def apply_far_relief(group: bpy.types.NodeTree,
                     strength: float = 0.0,
                     radius: float = 6.0,
                     threshold: float = 0.35) -> int:
    """遠景で線がつぶれる(黒ベタになる)のを軽減するノードを挿し込む。

    奥へ行くほど画面上の線が詰まり、隣り合う線が繋がって面になる。
    実測(奥へ26列の棚が並ぶ通路、1200px): 3x3 が全部インクで埋まった
    画素の割合が 手前 0.01% に対し 最奥 23.9%。

    距離そのもので薄くすると奥の形まで消えるので、判定には
    「線の局所密度」を使う。つぶれとは密度が飽和した状態そのもので、
    密度の低い遠景の輪郭線は残る。

        density = Blur(線マスク, radius)
        weight  = clamp((density - threshold) / (1 - threshold))
        alpha  *= 1 - strength * weight

    strength=0 で何も挿さない(=従来と1ビットも変わらない)。
    何度呼んでも同じ結果になるよう、既存の挿し込みは毎回外してから作る。
    戻り値は挿し込んだノード数。
    """
    # line 出力から遡って対象を探す。ノード名はバージョンによって
    # 振られ方が変わるので(4.2 と 4.5 で別名だった実例あり)、
    # 名前ではなく配線で特定する
    out_node = next((n for n in group.nodes if n.type == "GROUP_OUTPUT"), None)
    if out_node is None:
        return 0
    line_in = next((s for s in out_node.inputs if s.name == "line"), None)
    if line_in is None or not line_in.links:
        return 0
    sink = line_in.links[0].from_node          # line 出力を作る Set Alpha
    alpha_in = sink.inputs.get("Alpha")
    if alpha_in is None:
        return 0

    # --- 前回の挿し込みを撤去して素の配線に戻す。
    # 撤去前に「軽減ノードでない上流」を控えておく
    src = None
    if alpha_in.links:
        head = alpha_in.links[0].from_node
        if head.label == RELIEF_LABEL:
            # 既に挿さっている: 元の入力は apply ノードの片側にある
            for i in head.inputs:
                for lk in i.links:
                    if lk.from_node.label != RELIEF_LABEL:
                        src = lk.from_node
                        break
                if src is not None:
                    break
        else:
            src = head
    if src is None:
        return 0

    for node in [n for n in group.nodes if n.label == RELIEF_LABEL]:
        group.nodes.remove(node)
    if not alpha_in.links:
        group.links.new(src.outputs[0], alpha_in)

    strength = max(0.0, min(1.0, float(strength)))
    if strength <= 0.0:
        return 0

    x, y = sink.location
    made = []

    def new(idn, name, dx, dy):
        n = compat.new_node(group, idn)
        n.name = name
        n.label = RELIEF_LABEL
        n.location = (x + dx, y + dy)
        n.hide = True
        made.append(n)
        return n

    # 1. 線マスクをぼかして局所密度にする
    blur = new("CompositorNodeBlur", "fp_relief_blur", -520, -190)
    px = int(max(1, round(radius)))
    # 4.x はノードのプロパティ、5.x は入力ソケット。しかも 5.x の Size は
    # (x, y) のベクトルなので、汎用ヘルパーでは書けない
    if hasattr(blur, "filter_type"):
        blur.filter_type = "FAST_GAUSS"
        blur.use_relative = False
        blur.size_x = px
        blur.size_y = px
    else:
        t = blur.inputs.get("Type")
        if t is not None:
            t.default_value = "Fast Gaussian"
        sz = blur.inputs.get("Size")
        if sz is not None:
            try:
                sz.default_value = (px, px)
            except (TypeError, ValueError):
                sz.default_value = float(px)
    group.links.new(src.outputs[0], blur.inputs[0])

    # 2. 密度 -> 重み。threshold 未満は 0(=何もしない)
    ramp = compat.new_node(group, "CompositorNodeValToRGB")
    ramp.name = "fp_relief_ramp"
    ramp.label = RELIEF_LABEL
    ramp.location = (x - 400, y - 190)
    ramp.hide = True
    made.append(ramp)
    e = ramp.color_ramp.elements
    e[0].position = max(0.0, min(0.99, threshold))
    e[0].color = (0.0, 0.0, 0.0, 1.0)
    e[1].position = 1.0
    e[1].color = (1.0, 1.0, 1.0, 1.0)
    group.links.new(blur.outputs[0], ramp.inputs[0])

    # 3. 重み × 強さ
    mul = new("CompositorNodeMath", "fp_relief_mul", -280, -190)
    mul.operation = "MULTIPLY"
    mul.use_clamp = True
    group.links.new(ramp.outputs[0], mul.inputs[0])
    _set_value(mul, 1, strength)

    # 4. 1 - それ = 残す割合
    inv = new("CompositorNodeMath", "fp_relief_inv", -170, -190)
    inv.operation = "SUBTRACT"
    inv.use_clamp = True
    _set_value(inv, 0, 1.0)
    group.links.new(mul.outputs[0], inv.inputs[1])

    # 5. 元のアルファに掛ける
    app = new("CompositorNodeMath", "fp_relief_apply", -70, -190)
    app.operation = "MULTIPLY"
    app.use_clamp = True
    group.links.new(src.outputs[0], app.inputs[0])
    group.links.new(inv.outputs[0], app.inputs[1])
    group.links.new(app.outputs[0], alpha_in)
    return len(made)


def _set_value(node, index, value) -> None:
    if index < len(node.inputs) and hasattr(node.inputs[index],
                                            "default_value"):
        node.inputs[index].default_value = value


def far_relief_from_scene(group: bpy.types.NodeTree,
                          scene: bpy.types.Scene) -> int:
    return apply_far_relief(
        group,
        strength=getattr(scene, "fp_far_relief", 0.0),
        radius=getattr(scene, "fp_far_relief_radius", 6.0),
        threshold=getattr(scene, "fp_far_relief_threshold", 0.35))


def channel_strengths_from_scene(scene: bpy.types.Scene) -> dict:
    """シーンプロパティ fp_ch_* からチャンネル別強さの辞書を作る。"""
    return {ch: getattr(scene, f"fp_ch_{ch}", 1.0)
            for ch in CHANNEL_RAMP_NODES}


def apply_line_sensitivity(group: bpy.types.NodeTree, factor: float) -> None:
    """後方互換ラッパー(チャンネル別強さなしの全体感度のみ)。"""
    apply_line_tuning(group, factor)


WHITE_PREVIEW_MAT = "FP_White_Preview"
_ORIG_MATS_PROP = "fp_orig_mats"


def is_real_glass(mat) -> bool:
    """本物のガラスのみ True。

    Principled の Transmission/低Alpha(定数値)か Glass/Transparent BSDF
    で判定する。blend_method は見ない — トゥーン系が BLEND を多用しており、
    blend_method 判定はキャラ本体まで透明扱いにする誤爆を起こす(実測)。
    """
    if mat is None or not mat.use_nodes or not mat.node_tree:
        return False
    for n in mat.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            tr = n.inputs.get("Transmission Weight") or n.inputs.get("Transmission")
            if tr is not None and not tr.is_linked \
                    and getattr(tr, "default_value", 0.0) > 0.3:
                return True
            al = n.inputs.get("Alpha")
            if al is not None and not al.is_linked and al.default_value < 0.7:
                return True
        elif n.type in {"BSDF_GLASS", "BSDF_TRANSPARENT"}:
            return True
    return False


WHITE_MIX_LABEL = "FP_WhitePreviewMix"
_LEGACY_SHADER_MIX_GROUP = "FreePencil_WhitePreview_Mix"


MONO_LABEL = "FP_MonoLightPreview"


def set_mono_light_preview(scene: bpy.types.Scene, enable: bool,
                           floor: float = 0.25) -> int:
    """モノクロ(ディフューズライト)プレビューの ON/OFF。

    白プレビューと同じ考え方で、PROノードの Image 入力に何を流すかだけ
    変える。白一色ではなく「ディフューズ直接光をグレースケール化した
    もの」を流すので、線はそのまま、面には陰影が乗る。

    ビューティ(Combined)ではなくディフューズ直接光を使うのは、
    テクスチャの模様を持ち込まずに陰影だけを取りたいから。

    floor は影の下限。0 にすると暗部が黒く潰れて線が見えなくなる。

    白プレビューと同時には成立しないので、こちらを立てるときは
    呼び出し側が白を下ろす(props の更新フックがやる)。
    """
    tree = compat.get_compositor_tree(scene)
    if tree is None:
        return 0

    made = [n for n in tree.nodes if n.label == MONO_LABEL]
    grp = next((n for n in tree.nodes
                if n.type == 'GROUP' and n.node_tree
                and n.node_tree.name.startswith(NODE_GROUP_PREFIX)), None)
    if grp is None:
        return 0
    img_in = grp.inputs.get("Image")
    if img_in is None:
        return 0

    if not enable:
        # 立てる前に Image へ入っていた所(白プレビューの Mix か RenderLayers
        # の Image)へ戻してから撤去する。以前は撤去するノードの入力元を
        # 戻していて、それはディフューズ直接光のパスだった。モノクロ ->
        # マテリアルで陰影が残り、そのあと白を選んでも白にならなかった
        # (白の Mix が外れたまま。GUI で確認)
        src = None
        for n in made:
            node = tree.nodes.get(n.get("fp_prev_node", ""))
            idx = int(n.get("fp_prev_out", 0))
            if node is not None and idx < len(node.outputs):
                src = node.outputs[idx]
                break
        if src is None:
            mix = next((n for n in tree.nodes if n.label == WHITE_MIX_LABEL), None)
            rl = next((n for n in tree.nodes if n.type == 'R_LAYERS'), None)
            src = (mix.outputs[0] if mix is not None
                   else rl.outputs.get("Image") if rl is not None else None)
        for n in made:
            tree.nodes.remove(n)
        if src is not None and not img_in.is_linked:
            tree.links.new(src, img_in)
        return 0

    rl = next((n for n in tree.nodes if n.type == 'R_LAYERS'), None)
    if rl is None:
        return 0
    light = compat.render_layer_socket(rl, compat.DIFFUSE_DIRECT_SOCKETS)
    if light is None:
        return 0

    # 立てる前の Image の入力元を覚えておく(下ろすときに戻す)。押し直しでは
    # 自分のノードが入っているので、前回覚えた値を引き継ぐ
    prev = next(((n["fp_prev_node"], n.get("fp_prev_out", 0))
                 for n in made if n.get("fp_prev_node")), None)
    if prev is None and img_in.is_linked:
        lk = img_in.links[0]
        if lk.from_node.label != MONO_LABEL:
            prev = (lk.from_node.name,
                    list(lk.from_node.outputs).index(lk.from_socket))
    for n in made:                      # 何度押しても増やさない
        tree.nodes.remove(n)

    x, y = grp.location.x - 320, grp.location.y + 220

    bw = compat.new_node(tree, "CompositorNodeRGBToBW")
    bw.label = MONO_LABEL
    if prev is not None:
        bw["fp_prev_node"], bw["fp_prev_out"] = prev[0], int(prev[1])
    bw.location = (x, y)
    bw.hide = True
    tree.links.new(light, bw.inputs[0])

    lift = compat.new_node(tree, "CompositorNodeMapRange")
    lift.label = MONO_LABEL
    lift.location = (x + 150, y)
    lift.hide = True
    # クランプ: 4.x の Compositor は use_clamp、5.x の Shader 版は clamp
    compat.set_node_value(lift, "use_clamp" if hasattr(lift, "use_clamp")
                          else "clamp", True)
    for name, val in (("From Min", 0.0), ("From Max", 1.0),
                      ("To Min", max(0.0, min(0.9, floor))), ("To Max", 1.0)):
        sock = lift.inputs.get(name)
        if sock is not None:
            sock.default_value = val
    tree.links.new(bw.outputs[0], lift.inputs[0])
    tree.links.new(lift.outputs[0], img_in)
    return 2


def set_white_preview(scene: bpy.types.Scene, enable: bool,
                      keep_glass: bool = True) -> int:
    """白プレビューの ON/OFF(コンポジタ切替方式・最終形)。

    マテリアルには一切触れない。PROノードは「入力Imageの上に線を描く」
    構造なので、コンポジタで FreePencil グループの Image 入力に入る
    ビューティを Mix(白) 経由にし、その係数だけで
    「白地の線画プレビュー ⇔ マテリアル付き」を切り替える。
    線は AOV 由来なので白背景でもそのまま出る。keep_glass はこの方式では
    不要(ガラスの透過はビューティ側の話で、線はAOVから出るため)。
    OFF 時は過去方式の残骸(シェーダー注入グループ/スロットスワップの
    バックアップ)も掃除して自己修復する。
    """

    # マテリアルスロットを持つ型。コレクションインスタンス
    # (Empty の instance_collection)の中身も再帰的に対象にする
    MAT_TYPES = {"MESH", "CURVE", "SURFACE", "FONT", "META"}

    def _iter_material_objects():
        seen = set()
        stack = list(scene.objects)
        while stack:
            o = stack.pop()
            if o.name in seen:
                continue
            seen.add(o.name)
            if o.instance_type == 'COLLECTION' and o.instance_collection:
                stack.extend(o.instance_collection.all_objects)
            if o.type in MAT_TYPES and o.data is not None:
                yield o

    count = 0
    tree = compat.get_compositor_tree(scene)
    if tree is not None:
        mix = next((n for n in tree.nodes
                    if n.label == WHITE_MIX_LABEL), None)
        if mix is None and enable:
            grp = next((n for n in tree.nodes
                        if n.type == 'GROUP' and n.node_tree
                        and n.node_tree.name.startswith(NODE_GROUP_PREFIX)),
                       None)
            img_in = grp.inputs.get("Image") if grp is not None else None
            if img_in is not None:
                src = img_in.links[0].from_socket if img_in.is_linked else None
                # ソケットは添字で掴む。4.5 の MixRGB は入力が
                # ['Fac','Image','Image'] で **同名が2つある**ため名前引きが
                # できない。両バージョンのランタイムダンプで位置が
                # [0]=係数 [1]=下段 [2]=上段 と一致することを確認済み
                # (5.2 は ['Factor','Color1','Color2'])。t31 で固定している
                mix = compat.new_node(tree, "CompositorNodeMixRGB")
                mix.label = WHITE_MIX_LABEL
                mix.blend_type = 'MIX'
                mix.inputs[2].default_value = (1.0, 1.0, 1.0, 1.0)
                mix.location = (grp.location.x - 200, grp.location.y + 150)
                if src is not None:
                    tree.links.new(src, mix.inputs[1])
                else:
                    mix.inputs[1].default_value = (1.0, 1.0, 1.0, 1.0)
                tree.links.new(mix.outputs[0], img_in)
        if mix is not None:
            mix.inputs[0].default_value = 1.0 if enable else 0.0
            count += 1
    if not enable:
        # --- 過去方式の残骸掃除(自己修復) ---
        # (1) シェーダー注入方式(一時実装)の係数を0に
        sg = bpy.data.node_groups.get(_LEGACY_SHADER_MIX_GROUP)
        if sg is not None and "fp_white_fac" in sg.nodes:
            sg.nodes["fp_white_fac"].outputs[0].default_value = 0.0
        # (2) 旧スロットスワップ方式のバックアップ復元(レガシー)
        for obj in _iter_material_objects():
            data = obj.data
            # リンクデータ/オーバーライド: OBJECTリンク切替の巻き戻し
            if "fp_orig_links" in obj:
                names = list(obj.get(_ORIG_MATS_PROP, []))
                links = list(obj["fp_orig_links"])
                try:
                    for slot, name, link in zip(obj.material_slots,
                                                names, links):
                        if slot.link == 'OBJECT' and link == 'OBJECT':
                            if name != WHITE_PREVIEW_MAT:
                                slot.material = bpy.data.materials.get(name) \
                                    if name else None
                        elif slot.link == 'OBJECT' and link != 'OBJECT':
                            slot.material = None
                            slot.link = link  # データ側の元マテリアルが再表示
                except (AttributeError, RuntimeError):
                    pass
                if _ORIG_MATS_PROP in obj:
                    del obj[_ORIG_MATS_PROP]
                del obj["fp_orig_links"]
                count += 1
                continue
            if data.library is not None:
                continue
            if _ORIG_MATS_PROP in data:
                names = list(data[_ORIG_MATS_PROP])
                if not names:
                    # 元はスロット無し → 追加した白スロットを除去
                    while data.materials and data.materials[-1] \
                            and data.materials[-1].name == WHITE_PREVIEW_MAT:
                        data.materials.pop(index=len(data.materials) - 1)
                else:
                    for i, name in enumerate(names[:len(data.materials)]):
                        if name == WHITE_PREVIEW_MAT:
                            continue  # 汚染バックアップは触らない
                        data.materials[i] = \
                            bpy.data.materials.get(name) if name else None
                del data[_ORIG_MATS_PROP]
                count += 1
            if _ORIG_MATS_PROP in obj:
                names = list(obj[_ORIG_MATS_PROP])
                if not names:
                    # 旧形式(スロット無しメッシュ)の白スロット除去
                    while data.materials and data.materials[-1] \
                            and data.materials[-1].name == WHITE_PREVIEW_MAT:
                        data.materials.pop(index=len(data.materials) - 1)
                for slot, name in zip(obj.material_slots, names):
                    if name in ("<DATA>", WHITE_PREVIEW_MAT):
                        # <DATA>=データ側で復元済み / 白=共有データ由来の
                        # 汚染バックアップ(触らず他の正しい復元を尊重)
                        continue
                    if slot.link == 'OBJECT' or len(names) == len(obj.material_slots):
                        slot.material = \
                            bpy.data.materials.get(name) if name else None
                del obj[_ORIG_MATS_PROP]
                count += 1
    return count


def passthrough_aov_color(group: bpy.types.NodeTree) -> int:
    """mecha_color に頂点カラーをそのまま届ける。

    ノードグループの中で、塗り分けの色は AOV に出る前に2段の Mix を通る。

      頂点カラー(mecha_color)
        -> Mix.002 : mix(頂点カラー, line_texture, 0.5)
        -> Mix.005 : mix(上, 色相180度+彩度2倍+明度2倍+20%反転, Generated.X)
        -> AOV mecha_color

    どちらも塗り分けを壊していた(実測)。

    - line_texture は未接続だと (0,0,0,1) の黒。Mix.002 は blend が MIX で
      Factor が 0.5 固定なので、結果は「頂点カラーの半分」にしかならない。
    - Mix.005 の Factor は Generated 座標の X。オブジェクトのどこにあるかで
      変換の量が変わるため、島ごとに色を変えても位置によって寄ってしまう。

    実測(ロゴ): 頂点カラーに対する AOV の比が場所ごとに 0.54〜1.99 とばらつき、
    単なる減衰ですらなかった。fp_min_neighbor_color_distance は頂点カラーに
    対して保証している(ロゴの隣接397組で最小0.714・違反0)のに、線を検出する
    側にはその色が届いていなかった。

    そこで両方の Factor を 0 にして A(=頂点カラー)を素通しにする。
    line_texture を使いたいときは Mix.002 の Factor を上げれば従来どおり
    効く。配線は残してあるので戻せる。

    mask_texture 側(Mix.004)は blend が ADD で、黒を足しても値が変わらない
    ため触らない。

    戻り値は直したノード数。
    """
    fixed = 0
    for name in ("Mix.002", "Mix.005"):
        nd = group.nodes.get(name)
        if nd is None or nd.type != "MIX":
            continue
        fac = nd.inputs[0]
        for link in list(fac.links):
            group.links.remove(link)
            fixed += 1
        if fac.default_value != 0.0:
            fac.default_value = 0.0
            fixed += 1
    return fixed


def setup_aov(scene: bpy.types.Scene,
              view_layer: bpy.types.ViewLayer) -> dict:
    """STEP2 core: insert the AOV node group into every material and
    configure the view-layer AOV slots and render color settings.

    押しても何も起きていないように見える、という声があったので、
    何をしたのかを辞書で返す(UI 側がそのまま出せる形)。
    """
    # 「無ければ作る」だと古いグループが残っている .blend で永久に
    # 更新されない。版が古ければ作り直して参照を付け替える
    aov_group = utils_nodegroup.ensure_node_group_updated(AOV_GROUP_NAME)
    # 版が同じで作り直されなかった("kept")場合も直す必要があるので、
    # ensure の結果に関わらず毎回通す
    passthrough_aov_color(aov_group)
    result = {"group": aov_group.name,
              "action": aov_group.get("fp_last_action", "created"),
              "materials": 0, "aovs": []}

    mat_total = 0
    if scene.fp_mat_count:
        for m in bpy.data.materials:
            if not m.grease_pencil or m.use_nodes:
                m.pass_index = mat_total
                mat_total += 1

    for mat in bpy.data.materials:
        if mat.grease_pencil and not mat.use_nodes:
            continue
        if not mat.use_nodes or mat.node_tree is None:
            continue

        nt = mat.node_tree
        nodes = nt.nodes

        for nd in list(nodes):
            if nd.type == "GROUP" and nd.node_tree \
               and "FreePencil" in nd.node_tree.name \
               and nd.node_tree.name != AOV_GROUP_NAME:
                nodes.remove(nd)

        # 細い線の AOV。外部リソースのグループは触らず、材質に
        # 「色属性 -> AOV 出力」の2ノードだけ足す(既定OFFでは何も足さない)
        for nd in [n for n in nodes if n.label == FINE_AOV_LABEL]:
            nodes.remove(nd)
        if getattr(scene, "fp_fine_lines", 0.0) > 0.0:
            attr = nodes.new("ShaderNodeVertexColor")
            attr.label = FINE_AOV_LABEL
            attr.layer_name = "fine_color"
            attr.location = (10, 680)
            aov_out = nodes.new("ShaderNodeOutputAOV")
            aov_out.label = FINE_AOV_LABEL
            aov_out.aov_name = "fine_color"
            aov_out.location = (240, 680)
            nt.links.new(attr.outputs["Color"], aov_out.inputs["Color"])

        if not any(nd.type == "GROUP" and nd.node_tree
                   and nd.node_tree.name == AOV_GROUP_NAME
                   for nd in nodes):
            g = nodes.new("ShaderNodeGroup")
            g.node_tree = aov_group
            g.location = (10, 400)
            g.width = 240
            result["materials"] += 1
            if scene.fp_mat_count:
                g.node_tree.nodes["Map Range"].inputs[2].default_value = mat_total

    def ensure_aov(name, enable):
        existing = next((a for a in view_layer.aovs if a.name == name), None)
        if enable and existing is None:
            aov = view_layer.aovs.add()
            aov.name = name
            aov.type = 'COLOR'
        if not enable and existing is not None:
            view_layer.aovs.remove(existing)
        if enable:
            result["aovs"].append(name)

    ensure_aov("mecha_color", True)
    ensure_aov("gen_color", scene.fp_gen_color)
    ensure_aov("mask_color", scene.fp_mask_color)
    ensure_aov("line_color", scene.fp_line_color)
    ensure_aov("mat_color", scene.fp_mat_color)
    ensure_aov("bone_color", scene.fp_bone_color)
    ensure_aov("fine_color", getattr(scene, "fp_fine_lines", 0.0) > 0.0)

    scene.render.film_transparent = True
    scene.view_settings.view_transform = 'Standard'
    return result


def _apply_fine_lines(tree, scene, rl, group_node, comp):
    """fine_color から細い線を作り、最終画像へ薄く乗算する。戻り値はノード数。"""
    label = "FreePencil_fine_line"
    for n in [n for n in tree.nodes if n.label == label]:
        if n.type == "GROUP" and n.node_tree and n.node_tree.users == 1:
            bpy.data.node_groups.remove(n.node_tree)
        tree.nodes.remove(n)
    k = float(getattr(scene, "fp_fine_lines", 0.0))
    src = next((o for o in rl.outputs if o.name == "fine_color"), None)
    if k <= 0.0 or src is None or group_node.node_tree is None:
        return 0
    # 細い線はプロノードの "sample" 出力を使う。テストノード(出力は Image
    # だけ)を選ぶと、手描き背景では STEP3 が KeyError で止まっていた(総当りで発見)
    if "sample" not in group_node.outputs:
        return 0
    if not comp.inputs or not comp.inputs[0].is_linked:
        return 0
    made = []

    fine = tree.nodes.new("CompositorNodeGroup")
    fine.node_tree = group_node.node_tree.copy()
    fine.node_tree.name = group_node.node_tree.name + "_fine"
    fine.label = label
    fine.location = (group_node.location.x, group_node.location.y - 700)
    made.append(fine)
    # 塗り分けの口だけ差し替える。他のチャンネル(深度・ボーン・生成・材質)は
    # つながないので線を出さない = 細い分割の線だけが出る
    if "mecha_color" in fine.inputs:
        tree.links.new(src, fine.inputs["mecha_color"])
    dst_a = group_node.inputs.get("Alpha")
    if dst_a is not None and dst_a.is_linked and "Alpha" in fine.inputs:
        tree.links.new(dst_a.links[0].from_socket, fine.inputs["Alpha"])
    # 奥の扱い(深度)を細い線にも効かせる。コピーしたグループには奥ほど
    # 線を減らす枝が入っているが、深度がつながっておらず効いていなかった
    # (水平線の試験場で、奥の縞がこちらから出続けた)
    dst_d = group_node.inputs.get("Depth")
    if dst_d is not None and dst_d.is_linked and "Depth" in fine.inputs:
        tree.links.new(dst_d.links[0].from_socket, fine.inputs["Depth"])
    # 絵の入口は白に固定する。"line" 出力はほぼ空で(実測: 最大 0.004)、
    # 線は "sample"(絵の上に線を乗せた合成)に出る。ビューティを入れると
    # 陰影まで一緒に乗算されて面が灰色になるので、白を入れて線だけ取る
    white = tree.nodes.new("CompositorNodeRGB")
    white.label = label
    white.hide = True
    white.location = (fine.location.x - 200, fine.location.y)
    white.outputs[0].default_value = (1.0, 1.0, 1.0, 1.0)
    made.append(white)
    if "Image" in fine.inputs:
        tree.links.new(white.outputs[0], fine.inputs["Image"])

    # 薄さ: faint = 1 - k * 線。乗算で最終画像へ
    inv = compat.new_node(tree, "CompositorNodeMixRGB")
    compat.set_node_value(inv, "blend_type", "MIX")
    inv.label = label
    inv.hide = True
    inv.location = (fine.location.x + 320, fine.location.y)
    inv.inputs[0].default_value = k
    inv.inputs[1].default_value = (1.0, 1.0, 1.0, 1.0)
    tree.links.new(fine.outputs["sample"], inv.inputs[2])
    made.append(inv)

    mul = compat.new_node(tree, "CompositorNodeMixRGB")
    compat.set_node_value(mul, "blend_type", "MULTIPLY")
    mul.label = label
    mul.hide = True
    mul.location = (comp.location.x - 160, comp.location.y - 160)
    mul.inputs[0].default_value = 1.0
    made.append(mul)
    lnk = comp.inputs[0].links[0]
    prev = lnk.from_socket
    tree.links.remove(lnk)
    tree.links.new(prev, mul.inputs[1])
    tree.links.new(inv.outputs[0], mul.inputs[2])
    tree.links.new(mul.outputs[0], comp.inputs[0])
    return len(made)


def setup_compositor(scene: bpy.types.Scene,
                     view_layer: bpy.types.ViewLayer) -> str:
    """STEP3 core: build the RenderLayers -> FreePencil group -> Composite
    tree for the node type selected in scene.fp_node_type.

    Returns the node group name that was wired in.
    """
    node_ver_name = f"{NODE_GROUP_PREFIX}{scene.fp_node_type}"

    utils_nodegroup.ensure_node_group_updated(node_ver_name)

    # 線感度(既定1.0=従来挙動)。冪等なので毎回適用してよい。
    # 強弱がONのときは、線を弱め(=減らす)に倒した値になる
    apply_line_tuning(bpy.data.node_groups[node_ver_name],
                      line_weight.effective_sensitivity(scene),
                      channel_strengths_from_scene(scene))
    # 遠景つぶれ軽減(既定0.0=何も挿さない)。これも冪等
    far_relief_from_scene(bpy.data.node_groups[node_ver_name], scene)

    if not view_layer.use_pass_z:
        view_layer.use_pass_z = True
    tree = compat.get_compositor_tree(scene, create=True)

    for node in list(tree.nodes):
        if (
            node.type in {"R_LAYERS", "VIEWER", "REROUTE"}
            or node.type in compat.OUTPUT_NODE_TYPES
            or node.label.startswith("FreePencil")
            or node.label == WHITE_MIX_LABEL
        ):
            tree.nodes.remove(node)

    # 必要なレンダーパスは RenderLayers ノードを作る前に有効化しておく。
    # 後から有効化するとソケットがまだ生えていない
    if getattr(scene, "fp_file_output", False):
        for _prop, _slot, source in selected_file_output_passes(scene):
            if source[0] == "pass" and source[1] is not None:
                setattr(view_layer, source[1], True)
            if source[0] == "layer":
                from . import cel_shade
                cel_shade.ensure_shade_aov(scene, view_layer)
                cel_shade.ensure_light_passes(view_layer)
    from . import line_scale
    if line_scale.needed(scene):            # 物ごとの線の太さ(v2.9)
        line_scale.ensure_aov(scene, view_layer)

    rl = tree.nodes.new("CompositorNodeRLayers")
    rl.label = node_ver_name
    rl.location = (-40, 400)

    group_node = tree.nodes.new("CompositorNodeGroup")
    group_node.label = node_ver_name
    group_node.node_tree = bpy.data.node_groups[node_ver_name]
    group_node.location = (270, 500)

    comp = compat.new_output_node(tree)
    comp.label = node_ver_name
    comp.location = (500, 600)

    # 入力ソケット自動接続（名前の完全一致のみ）
    # 注意: difflib等の曖昧マッチを使うと mecha_color が
    # bone_color/line_color 等にも接続され、未接続時の
    # デフォルト色（黒）を前提とした線抽出が壊れる。
    rl_outputs = {o.name: o for o in rl.outputs}
    for input_sock in group_node.inputs:
        output_sock = rl_outputs.get(input_sock.name)
        if output_sock is not None:
            tree.links.new(output_sock, input_sock)

    # 葉の隙間埋め(手描き背景)。既定 0 で何も挿さない
    from . import gap_fill
    gap_fill.apply(tree, scene, rl, group_node)

    if group_node.outputs:
        insert_antialiasing_if_needed(
            tree,
            group_node.outputs[0],
            comp.inputs[0],
            scene.fp_include_antialiasing,
            threshold=0.1,
            contrast_limit=0.2,
        )

    # STEP2 で film_transparent を有効にしても、PROノード出力の
    # アルファは不透明のままなので背景が塗り潰される（4.5のComposite
    # ノードに Alpha 入力は無い）。Set Alpha ノードでレンダーレイヤーの
    # シルエットアルファを書き戻し、透過背景の線画として出力する。
    # 強弱を挟む先。Set Alpha があればその画像入力、無ければ合成の入力
    weight_target = comp.inputs[0]
    alpha_out = rl_outputs.get("Alpha")
    if group_node.outputs and alpha_out is not None:
        set_alpha = tree.nodes.new("CompositorNodeSetAlpha")
        set_alpha.label = node_ver_name  # 再生成時のクリーンアップ対象
        compat.set_node_value(set_alpha, 'mode', 'REPLACE_ALPHA')
        set_alpha.location = (640, 500)
        for lnk in [l for l in tree.links if l.to_socket == comp.inputs[0]]:
            src = lnk.from_socket
            tree.links.remove(lnk)
            tree.links.new(src, set_alpha.inputs["Image"])
        tree.links.new(alpha_out, set_alpha.inputs["Alpha"])
        tree.links.new(set_alpha.outputs[0], comp.inputs[0])
        comp.location = (860, 600)
        weight_target = set_alpha.inputs["Image"]

    # 線の強弱(入り抜き)。くぼみが深いほど太くする。既定はOFF。
    # 50%縮小(スーパーサンプリング)より前に挟む。縮小が最後でないと
    # 太らせた幅と出力の画素数が合わなくなる
    line_weight.apply(scene, view_layer, tree, weight_target)

    # 細い線(精密の分割)を薄く重ねる。同じ検出の仕組みをもう一度通すため、
    # ノードグループをコピーして fine_color を mecha_color の口へ入れ、出て
    # きた線を強弱の後ろで乗算する(強弱は太い線だけに掛けたいので後ろ)
    _apply_fine_lines(tree, scene, rl, group_node, comp)
    # 物ごとの線の太さ(v2.9)。全部 1 なら何も挿さない
    line_scale.apply(tree, scene, rl, comp)

    # ファイル出力: チェックの入ったパスを個別PNGで書き出す
    selected = selected_file_output_passes(scene)
    if getattr(scene, "fp_file_output", False) and selected:
        fo = tree.nodes.new("CompositorNodeOutputFile")
        fo.label = node_ver_name  # 再生成時のクリーンアップ対象
        fo.location = (640, 150)
        compat.file_output_set_dir(
            fo, getattr(scene, "fp_file_output_path", "//render/"))
        compat.file_output_clear_slots(fo)
        for _prop, slot_name, _source in selected:
            compat.file_output_add_slot(fo, slot_name, 'PNG', 'RGBA')

        # 強弱のある線(キャラ/手描き背景)は、line に強弱を付けた後の線を出す。グループの line は
        # 強弱の前の細い線で、絵と違っていた(v2.9)。強弱のある線は白地に描くので、合成に入る
        # 絵がそのまま線だけの絵になる
        final_line = None
        if (getattr(scene, "fp_line_weight", False) or line_scale.needed(scene)) and comp.inputs[0].is_linked:
            final_line = comp.inputs[0].links[0].from_socket
        for _prop, slot_name, source in selected:
            if source[0] == "layer":
                from . import cel_shade
                src = cel_shade.layer_socket(tree, rl, scene, source[1])
            elif source[0] == "group" and source[1] == "line" and final_line is not None:
                from . import cel_shade
                src = cel_shade.layer_socket(tree, rl, scene, "line_final", line_src=final_line)
            elif source[0] == "group":
                src = next((o for o in group_node.outputs
                            if o.name == source[1]), None)
            elif source[1] is None:          # 常にあるパス(Image)
                src = compat.render_layer_socket(rl, source[2])
            else:
                # パスは有効化した直後だと RenderLayers にソケットが
                # 無いことがあるため、有効化後のノードから引き直す
                src = compat.render_layer_socket(rl, source[2])
            if src is not None:
                tree.links.new(src, fo.inputs[slot_name])

    # 2倍レンダ→50%縮小(細線化): 200%でレンダリングし、コンポジタ出力を
    # 0.5 スケールで戻す。2px の線が 1px のアンチエイリアス線になる。
    #
    # 副作用として、ビューポートコンポジタは同じツリーを評価する一方
    # 200% でレンダリングしないため、プレビューが半分のサイズで表示される。
    # レンダリング中だけ 0.5 にする案を試したが、それだとプレビューの線が
    # 細線化されなくなる。細さの確認こそがプレビューの目的なので、
    # 表示が小さくなる方を受け入れる(常時 0.5 のまま)。
    if getattr(scene, "fp_supersample", False):
        scene.render.resolution_percentage = 200

        def _insert_half_scale(to_socket):
            if not to_socket.is_linked:
                return
            src = to_socket.links[0].from_socket
            sc = tree.nodes.new("CompositorNodeScale")
            sc.label = node_ver_name  # 再生成時のクリーンアップ対象
            compat.set_node_value(sc, 'space', 'RELATIVE')
            sc.inputs['X'].default_value = 0.5
            sc.inputs['Y'].default_value = 0.5
            sc.location = (to_socket.node.location.x - 80,
                           to_socket.node.location.y - 140)
            for lnk in list(to_socket.links):
                tree.links.remove(lnk)
            tree.links.new(src, sc.inputs[0])
            tree.links.new(sc.outputs[0], to_socket)

        # Composite に入る1本だけ目印を付ける。F12 のときはこれを外して
        # 等倍で出す(render_size)。ファイル出力側は 0.5 のままにしないと
        # STEP5 が2倍で出る(テスト t39)
        before = {n.name for n in tree.nodes if n.type == 'SCALE'}
        _insert_half_scale(comp.inputs[0])
        for node in tree.nodes:
            if node.type == 'SCALE' and node.name not in before:
                render_size.mark_composite_scale(node)
        for node in tree.nodes:
            if node.type == 'OUTPUT_FILE':
                for sock in node.inputs:
                    _insert_half_scale(sock)
    else:
        scene.render.resolution_percentage = 100

    # プレビュー中に STEP3 を再生成した場合は掛け直す。白だけ戻していて、
    # モノクロは外れたまま(表示はモノクロなのに材質の色で出た)だった
    # 見るのはプレビューの種類だけ。旧トグル(fp_white_preview)は種類を
    # 切り替えても残っていて、それを見て白を掛け直していた(v2.8.0)
    mode = getattr(scene, "fp_preview_mode", "NONE")
    from . import cel_shade
    # 前の作りの残り(作り直しで外れなかったもの)を外す
    if not cel_shade.wants_underlay(scene):
        cel_shade.set_underlay(scene, None)
    if mode != "CEL":
        cel_shade.set_cel(scene, False)
    if cel_shade.wants_underlay(scene):     # 強弱のある線のマテリアル/モノクロ(v2.9)
        set_white_preview(scene, True)
        cel_shade.set_underlay(scene, mode)
    elif mode == "WHITE":
        set_white_preview(scene, True)
    elif mode == "MONO_LIGHT":
        set_mono_light_preview(scene, True,
                               floor=getattr(scene, "fp_mono_floor", 0.25))
    elif mode == "CEL":                     # セル(影と色): 白地の線に色と影を掛ける(v2.9)
        from . import cel_shade
        set_white_preview(scene, True)
        cel_shade.set_cel(scene, True)

    # 最後に配置を整える。座標はエクスポート元 .blend の手配置がそのまま
    # 入っており、読めない状態だった(PROノード80個で重なり97組)。
    # 挿入・削除を全部終えてからまとめてやる
    node_layout.layout_freepencil_trees(scene)

    group = bpy.data.node_groups.get(node_ver_name)
    fo = next((n for n in compat.get_compositor_tree(scene).nodes
               if n.type == "OUTPUT_FILE"), None)
    return {
        "group": node_ver_name,
        "action": (group.get("fp_last_action", "created")
                   if group is not None else "created"),
        "nodes": len(group.nodes) if group is not None else 0,
        "passes": [slot for _p, slot, _src in selected_file_output_passes(scene)]
                  if fo is not None else [],
        "file_output_dir": compat.file_output_get_dir(fo) if fo else "",
        "relief": getattr(scene, "fp_far_relief", 0.0),
    }
