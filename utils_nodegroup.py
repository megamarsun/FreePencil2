"""
utils_nodegroup.py
────────────────────────────────────────────────────────────
• 指定モジュールを import し、ノードグループを返すユーティリティ
• 互換性:
    - 旧   create_node_tree()
    - 新   create_node_tree_<slug>()
• 省略パス対応:
    引数が短縮形 "FreePencil_aov_Group_v1_1_0" の場合でも
    FreePencil.resources.scripts.Exported_<name> を自動補完
"""

from __future__ import annotations
import importlib
import sys

import bpy
from types import ModuleType
from typing import Callable


# ---------------------------------------------------------------------------
#  内部ヘルパー
# ---------------------------------------------------------------------------
def _import_module_flexible(name: str) -> ModuleType:
    """
    • フルパス ('.' 含む) はそのまま import
    • 短縮名        は Exported プレフィックスを補完
    """
    if "." not in name:
        name = f"external_resources.Exported_{name}"

    return importlib.import_module("." + name, __package__)


def _find_create_func(mod: ModuleType) -> Callable | None:
    """
    • 旧式 create_node_tree を優先
    • 見つからなければ create_node_tree_* の先頭を返す
    """
    if hasattr(mod, "create_node_tree"):
        fn = getattr(mod, "create_node_tree")
        if callable(fn):
            return fn

    for attr in dir(mod):
        if attr.startswith("create_node_tree_"):
            fn = getattr(mod, attr)
            if callable(fn):
                return fn
    return None


# ---------------------------------------------------------------------------
#  パブリック API
# ---------------------------------------------------------------------------
def ensure_node_group(module_name: str):
    """
    Parameters
    ----------
    module_name : str
        • 完全修飾パス
            "FreePencil.resources.scripts.Exported_FreePencil_aov_Group_v1_1_0"
        • 旧短縮名
            "FreePencil_aov_Group_v1_1_0"

    Returns
    -------
    bpy.types.NodeTree
        生成されたノードグループオブジェクト

    Raises
    ------
    ImportError
        モジュールが見つからない
    AttributeError
        create_node_tree 関数が見つからない
    """
    # Blender 5.x はコンポジタが作り直され、ColorRamp/Mix/Math が共有ノードへ、
    # Composite が Group Output へ変わった。4.5 で作ったツリーを 5.2 に読ませて
    # Blender 自身に移行させ、その結果を書き出したものが *_5x スクリプト。
    # 5.x ではそちらを優先し、無ければ従来スクリプトへ落ちる。
    mod = None
    if bpy.app.version >= (5, 0, 0) and not module_name.endswith("_5x"):
        try:
            mod = _import_module_flexible(module_name + "_5x")
        except Exception:
            mod = None
    if mod is None:
        mod = _import_module_flexible(module_name)
    fn = _find_create_func(mod)
    if fn is None:
        raise AttributeError(
            f"{module_name} に create_node_tree 関数が見つかりません"
        )
    return fn()


# ---------------------------------------------------------------------------
#  ノードグループの版管理
# ---------------------------------------------------------------------------
# ノードグラフを変更したらこの数字を上げる。既存の .blend に古いグループが
# 残っていても、次に STEP2/STEP3 を実行した時点で作り直される。
NODE_GROUP_VERSION = 2
_VERSION_KEY = "fp_node_version"


def _stamp() -> str:
    """版の刻印。Blender の世代を含める。

    4.x 用と 5.x 用ではノードグラフの作りがそもそも違う。5.2 で保存した
    ファイルを 4.5 で開くと、5.x 用に組まれたグループが残ったまま
    「版は同じ」と判定され、作り直されないまま壊れた絵になっていた
    (実測: 4.5 で開いた直後 ink 0.93、STEP3 を押すと 1.00 の真っ黒)。
    世代を刻んでおけば、世代をまたいだ時点で作り直しになる。
    """
    gen = "5x" if bpy.app.version >= (5, 0, 0) else "4x"
    return f"{NODE_GROUP_VERSION}-{gen}"


def _canonical_name(module_name: str) -> str:
    """モジュール名から、生成されるノードグループの正式名を得る。"""
    name = module_name.rsplit(".", 1)[-1]
    for prefix in ("Exported_", ):
        if name.startswith(prefix):
            name = name[len(prefix):]
    if name.endswith("_5x"):
        name = name[:-3]
    return name


def ensure_node_group_updated(module_name: str, force: bool = False):
    """ノードグループを「必ず最新の内容で」用意する。

    従来は ``if name not in bpy.data.node_groups`` で判定していたため、
    古い .blend やアドオン旧版のグループが残っていると永久に作り直されず、
    ノードの更新が効かなかった(実際に踏んだ)。

    かといって無条件に生成すると Blender が ``名前.001`` という別データ
    ブロックを作り、``bpy.data.node_groups[name]`` は**古い方**を指したまま
    になる。そこで新しい方を作ってから ``user_remap`` で参照を移し替え、
    古い方を削除してから正式名に改名する。
    """
    canonical = _canonical_name(module_name)
    old = bpy.data.node_groups.get(canonical)
    if old is not None and not force \
            and old.get(_VERSION_KEY) == _stamp():
        # 最新版が既にある。何をしたのか呼び出し側が言えるように記録する
        old["fp_last_action"] = "kept"
        return old

    before = {g.name for g in bpy.data.node_groups}
    new = ensure_node_group(module_name)
    if new is None:
        # 生成関数が戻り値を返さない実装でも拾えるようにする
        added = {g.name for g in bpy.data.node_groups} - before
        if not added:
            return old
        new = bpy.data.node_groups[next(iter(added))]
    new[_VERSION_KEY] = _stamp()

    if old is not None and old is not new:
        # 既存ノードの参照を新しいグループへ付け替えてから古い方を捨てる
        try:
            old.user_remap(new)
        except Exception:
            pass
        try:
            bpy.data.node_groups.remove(old)
        except Exception:
            pass
    new.name = canonical  # ".001" が付いていれば正式名に戻す
    new["fp_last_action"] = "updated" if old is not None else "created"
    return new


# ---------------------------------------------------------------------------
#  デバッグ用 CLI 起動
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: blender --python utils_nodegroup.py -- <ModuleName>")
        sys.exit(1)

    # Blender の Python から呼ぶ想定
    name = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else sys.argv[1]
    ng = ensure_node_group(name)
    print(f"✅  NodeGroup '{ng.name}' created with {len(ng.nodes)} nodes.")
