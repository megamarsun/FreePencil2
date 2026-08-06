"""UI-independent core logic for FreePencil STEP2 / STEP3.

Both the UI operators (aov_node.py / sample_node.py) and headless
pipelines (dev/batch/fp_batch.py) call these functions, so they must not
touch context.screen, windows, or popups. Anything UI-related stays in
the operators.
"""

import bpy

from . import compat
from . import node_layout
from . import utils_nodegroup
from .utils_nodes import insert_antialiasing_if_needed

AOV_GROUP_NAME = "FreePencil_aov_Group_v1_1_0"
NODE_GROUP_PREFIX = "FreePencil_v1_1_0_"

# ファイル出力の3枚目。v2.5.0 までは影パス("Shadow")だったが、EEVEE の
# 影パスはノイズが多く実用に耐えないことが多いため、ディフューズの
# 直接光に差し替えた。書き出されるファイル名もこの名前になる
FILE_OUTPUT_LIGHT_SLOT = "light"


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


def setup_aov(scene: bpy.types.Scene, view_layer: bpy.types.ViewLayer) -> None:
    """STEP2 core: insert the AOV node group into every material and
    configure the view-layer AOV slots and render color settings."""
    # 「無ければ作る」だと古いグループが残っている .blend で永久に
    # 更新されない。版が古ければ作り直して参照を付け替える
    aov_group = utils_nodegroup.ensure_node_group_updated(AOV_GROUP_NAME)

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

        if not any(nd.type == "GROUP" and nd.node_tree
                   and nd.node_tree.name == AOV_GROUP_NAME
                   for nd in nodes):
            g = nodes.new("ShaderNodeGroup")
            g.node_tree = aov_group
            g.location = (10, 400)
            g.width = 240
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

    ensure_aov("mecha_color", True)
    ensure_aov("gen_color", scene.fp_gen_color)
    ensure_aov("mask_color", scene.fp_mask_color)
    ensure_aov("line_color", scene.fp_line_color)
    ensure_aov("mat_color", scene.fp_mat_color)
    ensure_aov("bone_color", scene.fp_bone_color)

    scene.render.film_transparent = True
    scene.view_settings.view_transform = 'Standard'


def setup_compositor(scene: bpy.types.Scene,
                     view_layer: bpy.types.ViewLayer) -> str:
    """STEP3 core: build the RenderLayers -> FreePencil group -> Composite
    tree for the node type selected in scene.fp_node_type.

    Returns the node group name that was wired in.
    """
    node_ver_name = f"{NODE_GROUP_PREFIX}{scene.fp_node_type}"

    utils_nodegroup.ensure_node_group_updated(node_ver_name)

    # 線感度(既定1.0=従来挙動)。冪等なので毎回適用してよい
    apply_line_tuning(bpy.data.node_groups[node_ver_name],
                      getattr(scene, "fp_line_sensitivity", 1.0),
                      channel_strengths_from_scene(scene))

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

    # ファイル出力の3枚目はディフューズの直接光。以前は影パスだったが、
    # EEVEE の影パスはノイズが乗って使える絵にならないことが多い(実測)。
    # ディフューズ・ライトの方が後段で乗算しやすい
    if getattr(scene, "fp_file_output", False):
        view_layer.use_pass_diffuse_direct = True

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

    # ファイル出力: line / color / light を個別PNGで書き出す
    if getattr(scene, "fp_file_output", False):
        if not view_layer.use_pass_diffuse_direct:
            view_layer.use_pass_diffuse_direct = True
        fo = tree.nodes.new("CompositorNodeOutputFile")
        fo.label = node_ver_name  # 再生成時のクリーンアップ対象
        fo.location = (640, 150)
        compat.file_output_set_dir(
            fo, getattr(scene, "fp_file_output_path", "//render/"))
        compat.file_output_clear_slots(fo)
        for slot_name in ("line", "color", FILE_OUTPUT_LIGHT_SLOT):
            compat.file_output_add_slot(fo, slot_name, 'PNG', 'RGBA')
        for out_name, slot_name in (("line", "line"), ("color", "color")):
            src = next((o for o in group_node.outputs if o.name == out_name), None)
            if src is not None:
                tree.links.new(src, fo.inputs[slot_name])
        # パスは STEP3 実行時に有効化した直後だと RenderLayers にまだ
        # ソケットが無いことがあるため、有効化後のノードから引き直す。
        # 名前は 4.x が 'DiffDir'、5.x が 'Diffuse Direct'
        light_out = compat.render_layer_socket(rl, compat.DIFFUSE_DIRECT_SOCKETS)
        if light_out is not None:
            tree.links.new(light_out, fo.inputs[FILE_OUTPUT_LIGHT_SLOT])

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

        _insert_half_scale(comp.inputs[0])
        for node in tree.nodes:
            if node.type == 'OUTPUT_FILE':
                for sock in node.inputs:
                    _insert_half_scale(sock)
    else:
        scene.render.resolution_percentage = 100

    # 白プレビュー中に STEP3 を再生成した場合は Mix(白) を挿入し直す
    if getattr(scene, "fp_white_preview", False):
        set_white_preview(scene, True)

    # 最後に配置を整える。座標はエクスポート元 .blend の手配置がそのまま
    # 入っており、読めない状態だった(PROノード80個で重なり97組)。
    # 挿入・削除を全部終えてからまとめてやる
    node_layout.layout_freepencil_trees(scene)

    return node_ver_name
