"""細線化したときの F12 の出力サイズを、筋の通ったものにする。

Blender の Composite 出力はレンダー解像度に固定される。細線化は
「200%でレンダして、コンポジタの中で 0.5 に縮める」ので、F12 で保存すると
2倍のキャンバスに半分の大きさの絵が入る。実測(1920x1080 を指定):

    細線化OFF  出力 1920x1080  被写体の幅 1236
    細線化ON   出力 3840x2160  被写体の幅 1236   <- 絵は面積で4分の1

ファイル出力(STEP5)はバッファの大きさで書くので 1920x1080 で正しく出る。
つまり F12 と STEP5 で出る絵が食い違っていた。

コンポジタの中で縮める限り、F12 を最終サイズにすることはできない
(Composite のキャンバスがレンダー解像度に固定されるため)。そこで
「レンダーの間だけ Composite 側の縮小を外す」ことにした。

    F12          3840x2160 に等倍の絵。ふつうのスーパーサンプリング画像で、
                 半分に縮めれば細い線になる
    ビューポート  0.5 のまま。細さをその場で確認するという本来の目的を保つ
    ファイル出力  0.5 のまま。STEP5 は今までどおり最終サイズで出る

縮小ノードを外す対象は Composite に入る1本だけ。ファイル出力側の縮小まで
外すと STEP5 が2倍で出てしまう(テスト t39 が固定している)。
"""

import bpy
from bpy.app.handlers import persistent

# Composite に入る縮小ノードだけに付ける目印。ファイル出力側と区別する
MARK = "fp_composite_scale"
# 退避した縮小率の置き場
SAVED_X = "fp_saved_scale_x"
SAVED_Y = "fp_saved_scale_y"


def mark_composite_scale(node) -> None:
    """fp_core が Composite の手前に挿した縮小ノードへ目印を付ける。"""
    node[MARK] = True


def _composite_scales(scene):
    """このシーンの Composite 側の縮小ノードを返す。"""
    from . import compat
    tree = compat.get_compositor_tree(scene)
    if tree is None:
        return []
    return [n for n in tree.nodes
            if n.type == "SCALE" and n.get(MARK, False)]


def _set_scale(node, x, y) -> None:
    for name, value in (("X", x), ("Y", y)):
        sock = node.inputs.get(name)
        if sock is not None:
            sock.default_value = value


@persistent
def _follow_sun(scene, _depsgraph=None):
    """セル(影と色)の日の向きを、日を回したらついて行かせる(v2.9)。動かす値は 3 つだけ。"""
    try:
        from . import cel_shade
        cel_shade.update_sun(scene)
    except Exception:            # noqa: BLE001  ハンドラで例外を出さない
        pass


@persistent
def _render_pre(scene, _depsgraph=None):
    """レンダー(F12 / アニメーション)の開始時に縮小を外す。値は控えておく。"""
    _follow_sun(scene)
    for node in _composite_scales(scene):
        sx = node.inputs.get("X")
        sy = node.inputs.get("Y")
        if sx is None or sy is None:
            continue
        node[SAVED_X] = sx.default_value
        node[SAVED_Y] = sy.default_value
        _set_scale(node, 1.0, 1.0)


@persistent
def _render_post(scene, _depsgraph=None):
    """レンダーが終わったら戻す。中断されたときも同じ処理でよい。"""
    for node in _composite_scales(scene):
        if SAVED_X not in node:
            continue
        _set_scale(node, node[SAVED_X], node[SAVED_Y])
        del node[SAVED_X]
        del node[SAVED_Y]


# render_pre/post(フレームごと)だとアニメーションで効かなかった。
# フレームの手前で外してもコンポジタが見る評価済みツリーには届かず、
# 2倍のキャンバスに半分の絵が入った(実測: 被写体の幅 0.50)。
# render_init/complete(レンダー全体の前後)なら F12 もアニメーションも
# 等倍で出る(実測: 幅 1.00)
@persistent
def _migrate_preview_mode(_dummy=None):
    """v2.7 以前のファイルを開いたら、白プレビューを「プレビューの種類」へ移す。

    v2.7 までは白プレビューを ON/OFF の1つで持っていて、種類は無かった。
    2.8.1 は種類だけを見るので、白プレビュー中の v2.7 のファイルを開いて
    STEP3 か STEP0 を押すと、白が外れて材質の色で出た(上書きインストールの
    点検で発見)。種類が一度も書かれていないファイルだけを移す。
    """
    from .props import _write_quiet
    for scene in bpy.data.scenes:
        if not hasattr(scene, "fp_preview_mode"):
            return
        if scene.is_property_set("fp_preview_mode"):
            continue
        if getattr(scene, "fp_white_preview", False):
            _write_quiet(scene, {"fp_preview_mode": "WHITE"})


_HANDLERS = (
    ("depsgraph_update_post", _follow_sun),
    ("frame_change_post", _follow_sun),
    ("load_post", _migrate_preview_mode),
    ("render_init", _render_pre),
    ("render_complete", _render_post),
    ("render_cancel", _render_post),
)


def register_handlers() -> None:
    for name, fn in _HANDLERS:
        lst = getattr(bpy.app.handlers, name, None)
        if lst is None:
            continue
        # 再読み込みで二重に入らないよう、同名のものを外してから足す
        for old in [h for h in lst if getattr(h, "__name__", "") == fn.__name__]:
            lst.remove(old)
        lst.append(fn)


def unregister_handlers() -> None:
    for name, fn in _HANDLERS:
        lst = getattr(bpy.app.handlers, name, None)
        if lst is None:
            continue
        for old in [h for h in lst if getattr(h, "__name__", "") == fn.__name__]:
            lst.remove(old)
