# FreePencil – node_io.py
# Blender ノードグループ ⇄ Python スクリプト変換ユーティリティ
# ──────────────────────────────────────────────────────────
# ■ 主な仕様
#   • Compositor/Shader グループを *.py にエクスポート & インポート
#   • ユニーク関数名  create_node_tree_<slug>()
#   • 後方互換 alias   create_node_tree も自動付与
#   • AOV 出力の有無を尊重:
#         - 元ツリーに Group Output があれば保持
#         - AOV 専用で元に Output が無ければ自動追加しない
#   • ColorRamp 完整形、二重 register ガード   …etc.

from __future__ import annotations
import bpy
import keyword
import pathlib
import re
import traceback
import importlib.util
from typing import Optional
from bpy.types import Operator, Panel
from bpy_extras.io_utils import ExportHelper, ImportHelper

# =============================================================================
# 共通ユーティリティ
# =============================================================================
def _slug(name: str) -> str:
    s = re.sub(r'\W|^(?=\d)', '_', name.lower())
    return f"{s}_grp" if keyword.iskeyword(s) else s


# =============================================================================
# Switch ノード互換ユーティリティ
# =============================================================================
IS_45_PLUS = bpy.app.version >= (4, 5, 0)


def switch_socket_indices() -> dict[str, Optional[int]]:
    """Switch 入力のインデックスをバージョンごとに返す"""
    if IS_45_PLUS:
        return {"Check": 0, "Off": 1, "On": 2}
    return {"Check": None, "Off": 0, "On": 1}


def get_switch_input(sw: bpy.types.Node, name: str) -> Optional[bpy.types.NodeSocket]:
    """名前で入力ソケットを取得し、無ければインデックスでフォールバック"""
    sock = sw.inputs.get(name)
    if sock is not None:
        return sock
    idx = switch_socket_indices().get(name)
    if idx is not None and len(sw.inputs) > idx:
        return sw.inputs[idx]
    return None


def unlink_all(sock: bpy.types.NodeSocket) -> None:
    """ソケットの既存リンクをすべて削除"""
    for lk in list(getattr(sock, "links", [])):
        lk.id_data.links.remove(lk)


def is_image_like(sock: bpy.types.NodeSocket) -> bool:
    """色/ベクタ等の画像系ソケットかの簡易判定"""
    idname = getattr(sock, "bl_socket_idname", "")
    return any(k in idname for k in ("Color", "Vector", "Image", "RGBA"))


def sanitize_switch_check(sw: bpy.types.Node) -> list[bpy.types.NodeSocket]:
    """Check 側のリンクを除去し、既定値を設定。削除したリンク元を返す"""
    sources: list[bpy.types.NodeSocket] = []
    check_sock = None
    if IS_45_PLUS:
        check_sock = get_switch_input(sw, "Check")
        if check_sock and check_sock.is_linked:
            sources = [lk.from_socket for lk in check_sock.links]
            unlink_all(check_sock)
        if check_sock and hasattr(check_sock, "default_value"):
            try:
                check_sock.default_value = 1.0
            except Exception:
                pass
    try:
        if hasattr(sw, "check"):
            sw.check = True
        elif hasattr(sw, "switch"):
            sw.switch = True
    except Exception:
        pass
    return sources


def repair_switch_links(
    ng: bpy.types.NodeTree,
    sw: bpy.types.Node,
    off_src: Optional[bpy.types.NodeSocket] = None,
    on_src: Optional[bpy.types.NodeSocket] = None,
    move_from_check: bool = True,
) -> None:
    """Switch ノードの配線を整備"""
    sources = sanitize_switch_check(sw)
    if move_from_check:
        for src in sources:
            if not is_image_like(src):
                continue
            off = get_switch_input(sw, "Off")
            on = get_switch_input(sw, "On")
            if off and not off.is_linked:
                ng.links.new(src, off)
            elif on and not on.is_linked:
                ng.links.new(src, on)
    if off_src:
        off = get_switch_input(sw, "Off")
        if off:
            unlink_all(off)
            ng.links.new(off_src, off)
    if on_src:
        on = get_switch_input(sw, "On")
        if on:
            unlink_all(on)
            ng.links.new(on_src, on)


def fix_all_switches(ng: bpy.types.NodeTree, mapping: dict[str, dict]) -> None:
    """複数の Switch ノードをまとめて修正"""
    for name, opts in mapping.items():
        sw = ng.nodes.get(name)
        if sw is None:
            continue
        kwargs = {
            k: v for k, v in opts.items() if k in {"off_src", "on_src", "move_from_check"}
        }
        repair_switch_links(ng, sw, **kwargs)

# =============================================================================
# ノードツリーのクリーニング
# =============================================================================
def remove_frames(cp):
    for f in [n for n in cp.nodes if n.type == 'FRAME']:
        cp.nodes.remove(f)

def keep_one_used_group_input(cp):
    gis = [n for n in cp.nodes if n.bl_idname == 'NodeGroupInput']
    used = [g for g in gis if any(o.is_linked for o in g.outputs)]
    for g in gis:
        if g not in used:
            cp.nodes.remove(g)
    if len(used) > 1:
        for g in used[1:]:
            cp.nodes.remove(g)

def keep_one_used_group_output(cp):
    """未使用 GroupOutput を削除、使用中は 1 個残す（AOV 有無を問わず）"""
    gos = [n for n in cp.nodes if n.bl_idname == 'NodeGroupOutput']
    used = [g for g in gos if any(i.is_linked for i in g.inputs)]
    for g in gos:
        if g not in used:
            cp.nodes.remove(g)
    if len(used) > 1:
        for g in used[1:]:
            cp.nodes.remove(g)

def copy_node_tree_keep_used_groupio(orig):
    """
    ノードツリーをコピーし、使用中の GroupInput/GroupOutput のみを残す
    リンクの整合性が取れないもの（None を含むリンクや、ノードが存在しないリンク）は除去する
    """
    tmp_name = orig.name + "_ExportTemp"
    if tmp_name in bpy.data.node_groups:
        bpy.data.node_groups.remove(bpy.data.node_groups[tmp_name], do_unlink=True)
    cp = orig.copy()
    cp.name = tmp_name

    remove_frames(cp)
    keep_one_used_group_input(cp)
    keep_one_used_group_output(cp)

    # リンクの整合性をチェック
    invalid_links = []
    for link in cp.links:
        # from_node または to_node が None のケース
        if not link.from_node or not link.to_node:
            invalid_links.append(link)
            continue
        # ノード名をキーとして cp.nodes に含まれないケースを除外
        names = [n.name for n in cp.nodes]
        if (link.from_node.name not in names) or (link.to_node.name not in names):
            invalid_links.append(link)

    if invalid_links:
        for link in invalid_links:
            cp.links.remove(link)

    return cp

# =============================================================================
# ColorRamp 処理（完全修正版）
# =============================================================================
def export_color_ramp(node_var: str, nd) -> list[str]:
    """ColorRamp の正確なエクスポート（Blender の仕様に対応）"""
    elements = list(nd.color_ramp.elements)
    is_compositor = nd.bl_idname.startswith("Compositor")
    node_type = "Compositor" if is_compositor else "Shader"

    L = [
        f"# ===== {node_type} ColorRamp for {node_var} =====",
        f"# Original: {len(elements)} elements",
        f"ramp = {node_var}.color_ramp",
        "",
        "# Blender の仕様: ColorRamp は最低 2 要素が必要",
        "# 戦略: デフォルト要素を直接上書きする",
        "",
    ]

    # position 順にソート
    sorted_elements = sorted(elements, key=lambda e: e.position)

    # 要素が 2 つの場合：デフォルト要素を上書き
    if len(sorted_elements) == 2:
        L.extend([
            "# 2 要素の場合: デフォルト要素を直接上書き",
            f"ramp.elements[0].position = {sorted_elements[0].position:.10f}",
            f"ramp.elements[0].color = ({sorted_elements[0].color[0]:.6f}, {sorted_elements[0].color[1]:.6f}, {sorted_elements[0].color[2]:.6f}, {sorted_elements[0].color[3]:.6f})",
            "",
            f"ramp.elements[1].position = {sorted_elements[1].position:.10f}",
            f"ramp.elements[1].color = ({sorted_elements[1].color[0]:.6f}, {sorted_elements[1].color[1]:.6f}, {sorted_elements[1].color[2]:.6f}, {sorted_elements[1].color[3]:.6f})",
        ])

    # 要素が 3 つ以上の場合：手動削除 → 再構築
    else:
        L.extend([
            f"# {len(sorted_elements)} 要素の場合: 手動削除後に再構築",
            "# Blender 4.3 対応: clear() の代わりに手動削除",
            "elements_to_remove = list(ramp.elements)",
            "for elem in elements_to_remove:",
            "    try:",
            "        ramp.elements.remove(elem)",
            "    except:",
            "        pass",
            "",
        ])

        for i, e in enumerate(sorted_elements):
            L.extend([
                f"elem_{i} = ramp.elements.new({e.position:.10f})",
                f"elem_{i}.color = ({e.color[0]:.6f}, {e.color[1]:.6f}, {e.color[2]:.6f}, {e.color[3]:.6f})",
                "",
            ])

    # ColorRamp の設定
    L.extend([
        "# ColorRamp 設定",
        f"ramp.interpolation = {nd.color_ramp.interpolation!r}",
        f"ramp.color_mode = {nd.color_ramp.color_mode!r}",
        f"ramp.hue_interpolation = {nd.color_ramp.hue_interpolation!r}",
        "",
    ])

    return L

# =============================================================================
# ノードプロパティのエクスポート（改善版）
# =============================================================================
def export_node_properties(node_var: str, nd) -> list[str]:
    """ノードの全プロパティを詳細にエクスポート"""
    L = []

    # ソケットの型/本数を決めるセレクタは、必ず default_value より先に
    # 出す。ShaderNodeMix の data_type や GeometryNodeSwitch の input_type
    # がこれで、後から設定するとソケットが作り直されて値が飛ぶ
    # (5.x で Switch の False ソケットに色を入れて型エラーになった)
    for sel in ("data_type", "input_type", "domain", "clamp_factor",
                "factor_mode"):
        if hasattr(nd, sel):
            try:
                L.append(f"    {node_var}.{sel} = {getattr(nd, sel)!r}")
            except Exception:
                pass

    # 基本プロパティ
    L.extend([
        f"    {node_var}.name = {nd.name!r}",
        f"    {node_var}.label = {nd.label!r}",
        f"    {node_var}.location = ({nd.location[0]}, {nd.location[1]})",
        f"    {node_var}.hide = {nd.hide}",
    ])

    # width と height は変更されている場合のみ保存
    if hasattr(nd, 'width') and hasattr(nd, 'bl_width_default') and nd.width != nd.bl_width_default:
        L.append(f"    {node_var}.width = {nd.width}")
    if hasattr(nd, 'height') and hasattr(nd, 'bl_height_default') and nd.height != nd.bl_height_default:
        L.append(f"    {node_var}.height = {nd.height}")

    # ノードタイプ別の特別な処理
    if nd.bl_idname == "ShaderNodeMix":
        if hasattr(nd, 'blend_type'):
            L.append(f"    {node_var}.blend_type = {nd.blend_type!r}")
        if hasattr(nd, 'data_type'):
            L.append(f"    {node_var}.data_type = {nd.data_type!r}")

    elif nd.bl_idname == "ShaderNodeMath":
        L.append(f"    {node_var}.operation = {nd.operation!r}")

    elif nd.bl_idname == "ShaderNodeVectorMath":
        L.append(f"    {node_var}.operation = {nd.operation!r}")

    elif nd.bl_idname == "CompositorNodeFilter":
        # 5.x は filter_type プロパティが無く、Type メニュー入力ソケットに
        # 移っている。ソケット側は default_value 出力で拾われるのでここでは
        # 書かない(4.x のみプロパティとして出力する)
        if hasattr(nd, "filter_type"):
            L.append(f"    {node_var}.filter_type = {nd.filter_type!r}")

    elif nd.bl_idname in ("CompositorNodeMixRGB", "ShaderNodeMixRGB"):
        L.append(f"    {node_var}.blend_type = {nd.blend_type!r}")
        if hasattr(nd, 'use_alpha'):
            L.append(f"    {node_var}.use_alpha = {nd.use_alpha}")
        if hasattr(nd, 'use_clamp'):
            L.append(f"    {node_var}.use_clamp = {nd.use_clamp}")

    elif nd.bl_idname == "ShaderNodeOutputAOV":
        # AOV ノードの name プロパティは特別
        if hasattr(nd, 'aov_name') and nd.aov_name:
            L.append(f"    {node_var}.aov_name = {nd.aov_name!r}")

    elif nd.bl_idname == "CompositorNodeSwitch":
        val = nd.check if hasattr(nd, 'check') else getattr(nd, 'switch', False)
        L.extend([
            f"    if hasattr({node_var}, 'check'):",
            f"        {node_var}.check = {val}",
            f"    elif hasattr({node_var}, 'switch'):",
            f"        {node_var}.switch = {val}",
        ])

    elif nd.bl_idname == "CompositorNodeDilateErode":
        L.append(f"    {node_var}.mode = {nd.mode!r}")
        L.append(f"    {node_var}.distance = {nd.distance}")
        if hasattr(nd, 'edge'):
            L.append(f"    {node_var}.edge = {nd.edge}")

    elif nd.bl_idname == "CompositorNodeInpaint":
        L.append(f"    {node_var}.distance = {nd.distance}")

    elif nd.bl_idname == "CompositorNodeColorMatte":
        L.append(f"    {node_var}.color_hue = {nd.color_hue}")
        L.append(f"    {node_var}.color_saturation = {nd.color_saturation}")
        L.append(f"    {node_var}.color_value = {nd.color_value}")

    elif nd.bl_idname == "ShaderNodeTexImage":
        # Image Texture ノードの処理
        if nd.image:
            L.extend([
                f"    img_path = bpy.path.abspath({nd.image.filepath!r})",
                f"    img = bpy.data.images.get({nd.image.name!r})",
                "    if img is None:",
                "        try:",
                "            img = bpy.data.images.load(img_path, check_existing=True)",
                "        except Exception:",
                "            img = None",
                "    if img is not None:",
                f"        {node_var}.image = img",
            ])
        L.append(f"    {node_var}.interpolation = {nd.interpolation!r}")
        L.append(f"    {node_var}.projection = {nd.projection!r}")

    elif nd.bl_idname == "ShaderNodeVertexColor":
        # 頂点カラーノードの重要なプロパティ
        L.append(f"    {node_var}.layer_name = {nd.layer_name!r}")

    elif nd.bl_idname == "ShaderNodeAttribute":
        # Attribute ノードの属性名
        L.append(f"    {node_var}.attribute_name = {nd.attribute_name!r}")
        L.append(f"    {node_var}.attribute_type = {nd.attribute_type!r}")

    elif nd.bl_idname == "ShaderNodeUVMap":
        # UV Map ノードの UV 名
        if hasattr(nd, 'uv_map') and nd.uv_map:
            L.append(f"    {node_var}.uv_map = {nd.uv_map!r}")

    elif nd.bl_idname == "CompositorNodeRGB":
        # RGB ノードの色値
        if hasattr(nd, 'color'):
            color = nd.color
            L.append(f"    {node_var}.color = ({color[0]:.6f}, {color[1]:.6f}, {color[2]:.6f})")

    elif nd.bl_idname == "CompositorNodeValue":
        # Value ノードの値
        if hasattr(nd, 'outputs') and len(nd.outputs) > 0:
            val = nd.outputs[0].default_value
            L.append(f"    {node_var}.outputs[0].default_value = {val:.6f}")

    elif nd.bl_idname in ["CompositorNodeGroup", "ShaderNodeGroup"]:
        # Group ノードのノードツリー参照
        if nd.node_tree:
            L.extend([
                f"    grp = bpy.data.node_groups.get({nd.node_tree.name!r})",
                "    if grp:",
                f"        {node_var}.node_tree = grp",
                "    else:",
                f"        print('Warning: Node group {nd.node_tree.name!r} not found')",
            ])
        else:
            L.append("    # Warning: Group node has no node_tree assigned")

    # 入力ソケットのデフォルト値
    for input_socket in nd.inputs:
        if nd.bl_idname == "CompositorNodeSwitch" and input_socket.name == "Check":
            continue
        if hasattr(input_socket, 'default_value') and not input_socket.is_linked:
            try:
                val = input_socket.default_value
                if isinstance(val, str):
                    # 5.x の NodeSocketMenu(Filter の Type など)。文字列だが
                    # __len__ を持つので、先に判定しないと1文字ずつの
                    # タプルに分解されてしまう
                    value_repr = repr(val)
                elif isinstance(val, (int, float)):
                    value_repr = f"{val}"
                elif hasattr(val, '__len__'):
                    if len(val) == 3:  # Vector
                        value_repr = f"({val[0]}, {val[1]}, {val[2]})"
                    elif len(val) == 4:  # Color
                        value_repr = f"({val[0]}, {val[1]}, {val[2]}, {val[3]})"
                    else:
                        continue
                else:
                    continue
                sock_name = input_socket.name
                sock_idx = list(nd.inputs).index(input_socket)
                L.append(
                    f"    _s = _in({node_var}, {sock_idx}, {sock_name!r})")
                L.append("    if _s is not None:")
                L.append(f"        _s.default_value = {value_repr}")
            except (AttributeError, TypeError):
                # 一部のソケットは default_value にアクセスできない場合がある
                pass

    return L

# =============================================================================
# Python スクリプト生成（改善版）
# =============================================================================
def make_python_script(node_tree, group_name, tree_type='CompositorNodeTree'):
    """
    戻り値: (script_text:str, func_name:str)
    """
    func_name = f"create_node_tree_{_slug(group_name)}"
    # ソケット解決はインデックス優先・名前フォールバック。
    # Blender 5.x の ShaderNodeMix のように同名ソケットが型違いで多重定義
    # される(Factor/Factor/A/B/A/B...)ため、名前だけで引くと誤った型を
    # 掴んで default_value の代入が型エラーになる。
    L: list[str] = [
        "import bpy",
        "",
        "",
        "def _sock(coll, idx, name):",
        "    if 0 <= idx < len(coll) and coll[idx].name == name:",
        "        return coll[idx]",
        "    for s in coll:",
        "        if s.name == name:",
        "            return s",
        "    return None",
        "",
        "",
        "def _in(node, idx, name):",
        "    return _sock(node.inputs, idx, name)",
        "",
        "",
        f"def {func_name}():",
    ]
    L.append(f"    ng = bpy.data.node_groups.new({group_name!r}, {tree_type!r})")

    # --- インターフェイス ------------------------------------------------
    if hasattr(node_tree, "interface"):
        for it in node_tree.interface.items_tree:
            if it.item_type == 'SOCKET':
                L.append(
                    f"    ng.interface.new_socket(name={it.name!r}, in_out={it.in_out!r}, socket_type={it.socket_type!r})"
                )

    # AOV ノードに対応したソケットを自動生成
    for nd in node_tree.nodes:
        if nd.bl_idname == 'ShaderNodeOutputAOV':
            aov_name = getattr(nd, 'aov_name', nd.name)
            L.append(
                f"    ng.interface.new_socket(name={aov_name!r}, in_out='OUTPUT', socket_type='NodeSocketColor')"
            )

    # --- ノード定義 ------------------------------------------------------
    idx_map: dict[object, str] = {}
    for idx, nd in enumerate(node_tree.nodes):
        v = f"n_{idx}"
        idx_map[nd] = v
        if nd.bl_idname == 'CompositorNodeAntiAliasing':
            # RNA を覗く方式(bpy.types.Node.bl_rna.functions['new'])は
            # 5.x で通らない。単純に作ってみて失敗したら諦める
            L.append("    try:")
            L.append(f"        {v} = ng.nodes.new('CompositorNodeAntiAliasing')")
            for line in export_node_properties(v, nd):
                # lstrip すると "if idx is not None:" の本体まで同じ深さに
                # 潰れて IndentationError になる。相対インデントは保つこと
                L.append("    " + line)
            L.append("    except Exception:")
            L.append(f"        {v} = None  # Anti-Aliasing node not available; skipping")
            L.append("")
        else:
            L.append(f"    {v} = ng.nodes.new({nd.bl_idname!r})")
            try:
                L.extend(export_node_properties(v, nd))
            except AttributeError as exc:
                # Blender 5.x では多くのノードプロパティが入力ソケットへ移った
                # (filter_type, color_hue など)。移った値は下の default_value
                # 出力で拾われるので、プロパティとしては出力しないのが正しい。
                L.append(f"    # skipped node properties ({exc})")
            # ColorRamp ノードは特別に要素を出力
            if nd.bl_idname in ["CompositorNodeValToRGB", "ShaderNodeValToRGB"]:
                L.extend([f"    {r}" for r in export_color_ramp(v, nd)])
            L.append("")

    # --- リンク ----------------------------------------------------------
    L.append("    def _link(f, fi, fsock, t, ti, tsock):")
    L.append("        a = _sock(f.outputs, fi, fsock)")
    L.append("        b = _in(t, ti, tsock)")
    L.append("        if a is not None and b is not None:")
    L.append("            ng.links.new(a, b)")
    L.append("")
    L.append("    # links:")
    for ln in node_tree.links:
        # ノードが idx_map に存在するかチェック
        if ln.from_node not in idx_map or ln.to_node not in idx_map:
            continue

        fvar = idx_map[ln.from_node]
        tvar = idx_map[ln.to_node]

        f_name = ln.from_socket.name
        t_name = ln.to_socket.name

        # MixRGB ノードは「下段画像入力」を必ず inputs[2] とする
        if ln.to_node.bl_idname in ('CompositorNodeMixRGB', 'ShaderNodeMixRGB'):
            # GroupInput の mecha_color は必ず下段（Color2）へ
            if ln.from_node.bl_idname == 'NodeGroupInput' and ln.from_socket.name == 'mecha_color':
                t_name = 'Color2'
            # GroupInput の alpha は必ず係数（Fac）へ
            elif ln.from_node.bl_idname == 'NodeGroupInput' and ln.from_socket.name == 'alpha':
                t_name = 'Fac'

        # CompositorNodeFilter は常に「画像」（下段）を使う
        if ln.to_node.bl_idname == 'CompositorNodeFilter':
            for sock in ln.to_node.inputs:
                if sock.name.lower() == 'image':
                    t_name = sock.name
                    break

        f_idx = list(ln.from_node.outputs).index(ln.from_socket)
        if t_name == ln.to_socket.name:
            # 実際に繋がっているソケットの位置をそのまま使う。名前引きだと
            # ShaderNodeMix のように同名ソケットが型違いで並ぶノードで
            # 誤った型に繋がり、リンクが無効になる
            t_idx = list(ln.to_node.inputs).index(ln.to_socket)
        else:
            # 上の MixRGB/Filter 特例で宛先名を差し替えた場合は名前引き
            t_idx = next((i for i, s in enumerate(ln.to_node.inputs)
                          if s.name == t_name), 0)
        L.append(f"    _link({fvar}, {f_idx}, {f_name!r}, "
                 f"{tvar}, {t_idx}, {t_name!r})")

    # --- 終端 ------------------------------------------------------------
    L += ["", "    return ng", "",
          f"# usage: ng = {func_name}()", "",
          f"create_node_tree = {func_name}  # backward-compat alias"]

    return "\n".join(L), func_name

# =============================================================================
# Export / Import Operators & Panels（Compositor + Shader）
# =============================================================================
def _export_impl(ctx, nt_type: str, tree_type: str, operator_self):
    nt = ctx.space_data.edit_tree
    if not nt or nt.bl_idname != nt_type:
        operator_self.report({'ERROR'}, bpy.app.translations.pgettext(f"Not in a {nt_type}."))
        return None
    sel = [n for n in nt.nodes if n.select and n.type == 'GROUP']
    if len(sel) != 1:
        operator_self.report({'ERROR'}, bpy.app.translations.pgettext("Select exactly one GROUP node."))
        return None
    grp = sel[0].node_tree
    if grp is None or any(n.type == 'GROUP' for n in grp.nodes):
        operator_self.report({'ERROR'}, bpy.app.translations.pgettext("Nested / empty group not supported."))
        return None

    # Blender 4.4+ のネイティブ出力を試す
    try:
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp:
            grp.write(filepath=tmp.name)
            tmp_path = tmp.name
        with open(tmp_path, 'r', encoding='utf-8') as f:
            script = f.read()
        import os
        os.unlink(tmp_path)
        return script
    except AttributeError:
        # Blender 4.3 以前のフォールバック
        cp = copy_node_tree_keep_used_groupio(grp)
        script, _ = make_python_script(cp, grp.name, tree_type)
        bpy.data.node_groups.remove(cp, do_unlink=True)
        return script

def _import_impl(ctx, nt_type: str, operator_self, filepath):
    nt = ctx.space_data.edit_tree
    if not nt or nt.bl_idname != nt_type:
        operator_self.report({'ERROR'}, bpy.app.translations.pgettext(f"Not in a {nt_type}."))
        return None
    spec = importlib.util.spec_from_file_location("_fp2_imported", filepath)
    if not spec or not spec.loader:
        operator_self.report({'ERROR'}, bpy.app.translations.pgettext("Failed to load module."))
        return None
    module = importlib.util.module_from_spec(spec)
    module.__dict__.update({"bpy": bpy, "__builtins__": __builtins__})
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        operator_self.report({'ERROR'}, str(e))
        traceback.print_exc()
        return None
    ct_funcs = [getattr(module, name) for name in dir(module)
                if callable(getattr(module, name)) and name.startswith("create_node_tree")]
    if not ct_funcs:
        operator_self.report({'ERROR'}, bpy.app.translations.pgettext("create_node_tree_*() not found."))
        return None
    try:
        newg = ct_funcs[0]()
    except Exception as e:
        operator_self.report({'ERROR'}, str(e))
        traceback.print_exc()
        return None
    newg.name = "Imported_" + newg.name
    return newg

# --- Compositor
class NODE_OT_export_group_to_python(Operator, ExportHelper):
    bl_idname = "node.export_group_to_python"
    bl_label = "Export Group to Python"
    filename_ext = ".py"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def description(cls, context, properties):
        return bpy.app.translations.pgettext("Export Group to Python")

    def execute(self, ctx):
        script = _export_impl(ctx, "CompositorNodeTree", "CompositorNodeTree", self)
        if script:
            pathlib.Path(self.filepath).write_text(script, encoding='utf-8')
            msg = f"{bpy.app.translations.pgettext('Exported to')} {self.filepath}"
            self.report({'INFO'}, msg)
            return {'FINISHED'}
        return {'CANCELLED'}

class NODE_OT_import_group_from_python(Operator, ImportHelper):
    bl_idname = "node.import_group_from_python"
    bl_label = "Import Group from Python"
    filename_ext = ".py"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def description(cls, context, properties):
        return bpy.app.translations.pgettext("Import Group from Python")

    def execute(self, ctx):
        newg = _import_impl(ctx, "CompositorNodeTree", self, self.filepath)
        if newg:
            msg = f"{bpy.app.translations.pgettext('Imported as')} '{newg.name}'"
            self.report({'INFO'}, msg)
            return {'FINISHED'}
        return {'CANCELLED'}

class NODE_PT_export_python_panel(Panel):
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Node Tools"
    bl_label = "Export/Import Python"

    @classmethod
    def poll(cls, ctx):
        return ctx.space_data and ctx.space_data.edit_tree and ctx.space_data.edit_tree.bl_idname == "CompositorNodeTree"

    def draw(self, ctx):
        col = self.layout.column(align=True)
        col.operator(
            "node.export_group_to_python",
            text=bpy.app.translations.pgettext("Export Group to Python"),
            icon='EXPORT',
        )
        col.operator(
            "node.import_group_from_python",
            text=bpy.app.translations.pgettext("Import Group from Python"),
            icon='IMPORT',
        )

    def draw_header(self, context):
        self.layout.label(text="", icon='NODE')

# --- Shader
class SHADER_OT_export_group_to_python(Operator, ExportHelper):
    bl_idname = "shader.export_group_to_python"
    bl_label = "Export Shader Group to Python"
    filename_ext = ".py"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def description(cls, context, properties):
        return bpy.app.translations.pgettext("Export Shader Group to Python")

    def execute(self, ctx):
        script = _export_impl(ctx, "ShaderNodeTree", "ShaderNodeTree", self)
        if script:
            pathlib.Path(self.filepath).write_text(script, encoding='utf-8')
            msg = f"{bpy.app.translations.pgettext('Exported to')} {self.filepath}"
            self.report({'INFO'}, msg)
            return {'FINISHED'}
        return {'CANCELLED'}

class SHADER_OT_import_group_from_python(Operator, ImportHelper):
    bl_idname = "shader.import_group_from_python"
    bl_label = "Import Shader Group to Python"
    filename_ext = ".py"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def description(cls, context, properties):
        return bpy.app.translations.pgettext("Import Shader Group to Python")

    def execute(self, ctx):
        newg = _import_impl(ctx, "ShaderNodeTree", self, self.filepath)
        if newg:
            msg = f"{bpy.app.translations.pgettext('Imported as')} '{newg.name}'"
            self.report({'INFO'}, msg)
            return {'FINISHED'}
        return {'CANCELLED'}

class SHADER_PT_export_python_panel(Panel):
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Node Tools"
    bl_label = "Export/Import Shader Python"

    @classmethod
    def poll(cls, ctx):
        return ctx.space_data and ctx.space_data.edit_tree and ctx.space_data.edit_tree.bl_idname == "ShaderNodeTree"

    def draw(self, ctx):
        col = self.layout.column(align=True)
        col.operator(
            "shader.export_group_to_python",
            text=bpy.app.translations.pgettext("Export Group to Python"),
            icon='EXPORT',
        )
        col.operator(
            "shader.import_group_from_python",
            text=bpy.app.translations.pgettext("Import Group from Python"),
            icon='IMPORT',
        )

    def draw_header(self, context):
        self.layout.label(text="", icon='NODE')


