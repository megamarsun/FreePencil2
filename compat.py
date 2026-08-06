"""Blender バージョン差の吸収層。

Blender 5.0 でコンポジタが作り直され、次が変わった(5.2 で実測):

- ``scene.node_tree`` が廃止され ``scene.compositing_node_group`` へ。
  4.x の ``use_nodes = True`` のような自動生成は無く、CompositorNodeTree の
  ノードグループを自分で作って割り当てる必要がある
  (``scene.use_nodes`` は残っているが 6.0 で削除予定の警告が出る)
- コンポジタがノードグループになったため ``CompositorNodeComposite`` が
  消え、最終出力は ``NodeGroupOutput`` で受ける
- ColorRamp / MixRGB / Math がシェーダ側の共有ノードに統合された。
  ``ShaderNodeValToRGB`` は ``color_ramp`` API まで同じなので置き換えるだけ

``CompositorNodeInvert`` や ``CompositorNodeSeparateColor`` などは 5.2 にも
残っているので、対象は下の 4 種だけ。
"""

import bpy

IS_5_PLUS = bpy.app.version >= (5, 0, 0)

# ビューポート(リアルタイム)コンポジタが AOV 出力を評価できるか。
#
# 実測(4.2.3 / 4.3.2 / 4.5.2 / 5.2.0、同一シーン・同一設定):
#   RenderLayers.Image -> Invert -> 出力        4.2 でも表示される
#   RenderLayers.Image -> [ノードグループ] -> 出力  4.2 でも表示される
#   RenderLayers.mecha_color(AOV) -> 出力       4.2 だけ何も出ない
#
# FreePencil の線は AOV の色境界から作るので、AOV が空だとプレビューが
# 真っ白になる。ビューポートコンポジタ自体もノードグループも動くため、
# アドオン側の組み方では回避できない。4.2 ではプレビューへ切り替えない。
HAS_AOV_IN_VIEWPORT_COMPOSITOR = bpy.app.version >= (4, 3, 0)

# 4.x の型名 -> 5.x の型名
_NODE_TYPE_5X = {
    "CompositorNodeValToRGB": "ShaderNodeValToRGB",
    "CompositorNodeMixRGB": "ShaderNodeMixRGB",
    "CompositorNodeMath": "ShaderNodeMath",
    # Composite は「グループ出力」に置き換わる。ソケット構成が異なるため
    # 呼び出し側で扱いを分ける必要がある(new_output_node を使うこと)
    "CompositorNodeComposite": "NodeGroupOutput",
}

# 「最終出力ノード」の判定に使う型名(バージョン非依存で探すため)
OUTPUT_NODE_TYPES = ("COMPOSITE", "GROUP_OUTPUT")

# Render Layers のディフューズ直接光パスのソケット名。
# 4.x は 'DiffDir'、5.x で 'Diffuse Direct' に変わった(実測)。
DIFFUSE_DIRECT_SOCKETS = ("Diffuse Direct", "DiffDir")


def render_layer_socket(rl_node, names):
    """名前候補の順に Render Layers の出力ソケットを探す。

    パスを有効化した直後はソケットがまだ生えていないことがあるので、
    呼ぶ側は有効化 -> ノード作成 の順にすること。
    """
    for name in names:
        sock = next((o for o in rl_node.outputs if o.name == name), None)
        if sock is not None:
            return sock
    return None

# Filter ノードの種類。5.x はメニューソケット化に伴い、値が識別子から
# 表示名に変わった('SOBEL' -> 'Sobel')
FILTER_TYPE_5X = {
    "SOFTEN": "Soften",
    "SHARPEN": "Box Sharpen",
    "SHARPEN_DIAMOND": "Diamond Sharpen",
    "LAPLACE": "Laplace",
    "SOBEL": "Sobel",
    "PREWITT": "Prewitt",
    "KIRSCH": "Kirsch",
    "SHADOW": "Shadow",
}


def node_type(name: str) -> str:
    """4.x の型名を、動作中の Blender で有効な型名に読み替える。"""
    if IS_5_PLUS:
        return _NODE_TYPE_5X.get(name, name)
    return name


def new_node(tree, type_name: str):
    """バージョン差を吸収してノードを作る。"""
    return tree.nodes.new(node_type(type_name))


def get_compositor_tree(scene, create: bool = False):
    """シーンのコンポジタツリーを返す。無ければ create=True で作る。"""
    if IS_5_PLUS:
        ng = scene.compositing_node_group
        if ng is None and create:
            ng = bpy.data.node_groups.new(
                "FreePencil Compositor", "CompositorNodeTree")
            # 5.x はノードグループなので出力ソケットを自前で用意する
            ng.interface.new_socket("Image", in_out="OUTPUT",
                                    socket_type="NodeSocketColor")
            scene.compositing_node_group = ng
        return ng
    if create and not scene.use_nodes:
        scene.use_nodes = True
    return scene.node_tree


def clear_compositor_tree(scene) -> None:
    """コンポジタツリーの参照を外す(4.x の use_nodes=False 相当)。"""
    if IS_5_PLUS:
        scene.compositing_node_group = None
    else:
        scene.use_nodes = False


def new_output_node(tree):
    """最終出力ノードを作る。4.x は Composite、5.x は Group Output。"""
    if IS_5_PLUS:
        node = tree.nodes.new("NodeGroupOutput")
        # interface に Image が無いツリーだと入力ソケットが生えない
        if not node.inputs:
            tree.interface.new_socket("Image", in_out="OUTPUT",
                                      socket_type="NodeSocketColor")
            tree.nodes.remove(node)
            node = tree.nodes.new("NodeGroupOutput")
        return node
    return tree.nodes.new("CompositorNodeComposite")


def set_filter_type(node, value: str) -> None:
    """Filter ノードの種類(SOBEL等)を設定する。

    5.x では node.filter_type というプロパティが無くなり、``Type`` という
    メニュー入力ソケットに移った。ついでに入力の並びも
    4.x ``[Fac, Image]`` -> 5.x ``[Image, Factor, Type]`` と変わっている。
    """
    if IS_5_PLUS:
        sock = node.inputs.get("Type")
        if sock is not None:
            sock.default_value = FILTER_TYPE_5X.get(value, value)
        return
    node.filter_type = value


def filter_image_input(node):
    """Filter ノードの画像入力ソケット(バージョン差あり)。"""
    return node.inputs.get("Image") or node.inputs[1]


def filter_factor_input(node):
    """Filter ノードの係数入力ソケット(4.x は Fac, 5.x は Factor)。"""
    return (node.inputs.get("Factor") or node.inputs.get("Fac")
            or node.inputs[0])


def set_node_value(node, name: str, value) -> None:
    """ノードの設定値を、プロパティでもソケットでも受け付けて設定する。

    5.x では多くのノード設定が入力ソケットへ移った
    (SetAlpha.mode, AntiAliasing.threshold など)。呼び出し側が
    バージョンを気にせず済むように、まずプロパティを試し、無ければ
    同名の入力ソケットへ書く。
    """
    if hasattr(node, name):
        setattr(node, name, value)
        return
    # 'contrast_limit' -> 'Contrast Limit' のようにソケット名へ寄せる
    candidates = (name, name.replace("_", " ").title())
    for cand in candidates:
        sock = node.inputs.get(cand)
        if sock is not None:
            try:
                sock.default_value = value
            except TypeError:
                # 'REPLACE_ALPHA' のような識別子はメニュー表示名と異なる
                sock.default_value = value.replace("_", " ").title()
            return


def file_output_set_dir(fo, path: str) -> None:
    """File Output の出力先。5.x は base_path が directory になった。"""
    if IS_5_PLUS:
        fo.directory = path
        # file_name の既定 "{blend_name}" が各スロット名の前に付いてしまい、
        # line0001.png ではなく Unsavedline.png のような名前になる。
        # 4.x と揃えるため接頭辞は空にする
        fo.file_name = ""
    else:
        fo.base_path = path


def file_output_get_dir(fo) -> str:
    """File Output の出力先を読む(4.x base_path / 5.x directory)。"""
    return fo.directory if IS_5_PLUS else fo.base_path


def file_output_slot_names(fo) -> list:
    """スロット名の一覧。5.x は file_output_items、4.x は file_slots.path。"""
    if IS_5_PLUS:
        return [it.name for it in fo.file_output_items]
    return [s.path for s in fo.file_slots]


def file_output_add_slot(fo, name: str, file_format: str = 'PNG',
                         color_mode: str = 'RGBA'):
    """File Output にスロットを1本足し、フォーマットを設定する。

    4.x はノード単位のフォーマット(fo.format)+ file_slots。
    5.x は file_slots が消えて file_output_items になり、ノード側の
    format は OPEN_EXR_MULTILAYER 固定(スロット数に関係なく変えられない)。
    PNG などはスロット単位に override_node_format で設定する。
    """
    if IS_5_PLUS:
        # 5.x は format.media_type が新設され、既定が MULTI_LAYER_IMAGE。
        # そのままだと file_format の候補が OPEN_EXR_MULTILAYER だけになり
        # PNG を代入できない(=多層EXR1本しか出ない)。IMAGE へ切り替えると
        # 4.x と同じくスロットごとの個別ファイルになる。
        if fo.format.media_type != 'IMAGE':
            fo.format.media_type = 'IMAGE'
        fo.format.file_format = file_format
        fo.format.color_mode = color_mode
        return fo.file_output_items.new('RGBA', name)
    fo.format.file_format = file_format
    fo.format.color_mode = color_mode
    return fo.file_slots.new(name)


def file_output_clear_slots(fo) -> None:
    """既存スロットを空にする。"""
    (fo.file_output_items if IS_5_PLUS else fo.file_slots).clear()


def find_output_node(tree):
    """最終出力ノードを探す(無ければ None)。"""
    if tree is None:
        return None
    for n in tree.nodes:
        if n.type in OUTPUT_NODE_TYPES:
            return n
    return None
