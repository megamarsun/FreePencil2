"""Scene properties used by FreePencil operators."""

import bpy
import logging
from bpy.props import (
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    EnumProperty,
    BoolProperty,
)

logger = logging.getLogger(__name__)

def _update_line_tuning(self, context):
    """線の感度/チャンネル強さスライダーの即時反映。

    生成済みの FreePencil ノードグループのランプ位置を直接更新する
    (ノードエディタを開かずにサイドバーだけで調整できる)。
    """
    if _QUIET[0]:
        return
    from . import fp_core
    from . import line_weight
    scene = context.scene
    for ng in bpy.data.node_groups:
        if ng.name.startswith(fp_core.NODE_GROUP_PREFIX):
            fp_core.apply_line_tuning(
                ng,
                line_weight.effective_sensitivity(scene),
                fp_core.channel_strengths_from_scene(scene))


def _update_far_relief(self, context):
    """遠景つぶれ軽減のスライダーを、生成済みノードへ即時反映する。"""
    if _QUIET[0]:
        return
    from . import fp_core
    from . import line_weight
    scene = context.scene
    for ng in bpy.data.node_groups:
        if ng.name.startswith(fp_core.NODE_GROUP_PREFIX):
            fp_core.far_relief_from_scene(ng, scene)


def _update_fine_lines(self, context):
    """細い線のスライダーを、生成済みのコンポジタへ即時反映する。

    STEP3 を押し直さなくても割合を変えられる(塗り分けは STEP0 が 2 枚
    作ってあるので、変わるのは合成だけ)。
    """
    if _QUIET[0]:
        return
    # 細い線の合成だけを後から差し直すと、強弱や奥の扱いを挿し終えた
    # あとのグループを複製・配線することになり、動かした直後に線が
    # ほとんど消えた(STEP3 を押すと戻る。総当りで発見)。STEP3 ごと作り直す
    _rebuild_step3(context)


def _rebuild_step3(context) -> None:
    """生成済みの STEP3 を作り直す(ボタンと同じ処理)。無いシーンでは何もしない。"""
    from . import compat, fp_core
    scene = context.scene
    tree = compat.get_compositor_tree(scene)
    if tree is None:
        return
    if not any(n.type == "GROUP" and n.node_tree is not None
               and n.node_tree.name.startswith(fp_core.NODE_GROUP_PREFIX)
               for n in tree.nodes):
        return
    fp_core.setup_compositor(scene, context.view_layer)


def _update_auto_style(self, context):
    """仕上がりを変えたら、キャラの塗り方の目印(fp_rig_coarse)も合わせる。

    目印は STEP0 を押したときにしか変わらず、仕上がりを「精密」に戻してから
    STEP1 だけ押し直すと、古い目印のままキャラの塗り方になった(パネルでは
    「塗り方」の欄が精密で灰色になっていて、表示と動きが食い違った)。
    """
    scene = context.scene
    if getattr(scene, "fp_auto_style", "PRECISE") == "PRECISE":
        if "fp_rig_coarse" in scene:
            del scene["fp_rig_coarse"]
    else:
        scene["fp_rig_coarse"] = True


# まとめたつまみ 1 本 -> 中の値。1.0 で手描き背景の既定(v2.8.0 と同じ値)
def far_values(k: float) -> dict:
    """「奥の扱い」k から、奥ほど細く/線を減らす/薄く の3つ。"""
    k = max(0.0, float(k))
    return {"fp_lw_far": min(1.0, k), "fp_lw_far_sens": min(4.0, 1.0 + k),
            "fp_lw_far_fade": min(1.0, 0.15 * k)}


def relief_values(c: float) -> dict:
    """「つぶれ軽減」c から、詰まった線を薄く。

    v2.8.3 で「細かすぎる縞を薄く」はここから外した(既定 0・詳細の別のつまみ)。
    動くと遠景が灰色のまだらでちらついたため
    """
    c = max(0.0, float(c))
    return {"fp_lw_dense": min(1.0, 0.3 * c)}


_QUIET = [False]


def _write_quiet(scene, values: dict) -> None:
    """更新フックを動かさずに書く(1つずつ STEP3 を作り直さない)。

    scene["名前"] = 値 で書くと、5.x では登録したプロパティとは別の
    カスタムプロパティになり、本当の値が変わらなかった(総当りで発見:
    5.2 でまとめたつまみを動かしても中の値が変わらず、白の旧トグルも
    種類に合わせられていなかった)。ふつうに setattr し、フックは
    _QUIET の間は何もしない。
    """
    _QUIET[0] = True
    try:
        for k, v in values.items():
            setattr(scene, k, v)
    finally:
        _QUIET[0] = False


def _update_far_amount(self, context):
    if _QUIET[0]:
        return
    _write_quiet(context.scene, far_values(context.scene.fp_lw_far_amount))
    _rebuild_step3(context)


def _update_relief(self, context):
    if _QUIET[0]:
        return
    _write_quiet(context.scene, relief_values(context.scene.fp_lw_relief))
    _rebuild_step3(context)


def _update_line_weight_toggle(self, context):
    """強弱の ON/OFF。感度の実効値も変わるので STEP3 ごと作り直す。
    以前は感度だけ書き換えていて、STEP3 を押すまで絵が変わらなかった。"""
    if _QUIET[0]:
        return
    _rebuild_step3(context)


def _update_line_scale(self, context):
    """物ごとの線の太さ。値そのものは材質の属性で読むので、作り直すのは
    「1 以外の物が出た / 無くなった」ときだけ(挿す / 外す)。"""
    if _QUIET[0]:
        return
    from . import compat, line_scale
    tree = compat.get_compositor_tree(context.scene)
    if line_scale.needed(context.scene) != line_scale.present(tree):
        _rebuild_step3(context)


def _update_compositor_view(self, context):
    """「コンポジタープレビューを有効化」をその場で効かせる(v2.8.3)。

    以前は STEP3 を押したときにしか見なかったので、チェックしても何も起きず、
    外してもビューポートのコンポジタが「常に」のまま残った。チェックを入れたら
    ビューポートをレンダー表示 + コンポジタ「常に」に、外したらコンポジタを切る
    (レンダー表示はそのまま)。4.2 はビューポートのコンポジタが AOV を出さないので触らない
    """
    if _QUIET[0]:
        return
    from . import compat
    if not compat.HAS_AOV_IN_VIEWPORT_COMPOSITOR or context.screen is None:
        return
    on = bool(context.scene.fp_enable_compositor_view)
    for area in context.screen.areas:
        if area.type != 'VIEW_3D':
            continue
        sh = area.spaces[0].shading
        if on:
            sh.type = 'RENDERED'
            sh.use_compositor = 'ALWAYS'
            # STEP2 は塗り分けの確認のため表示を mecha_color にする。そのままコンポジタを
            # 有効にすると、コンポジタに入る絵(Image)がそのパスになり、マテリアルの色が白く、
            # セルの空も出なかった(v2.9 のビューポートの点検で発見)。STEP3 のボタンと同じく戻す
            sh.render_pass = 'COMBINED'
        else:
            sh.use_compositor = 'DISABLED'


def _update_line_weight_live(self, context):
    """線の強弱の見た目のつまみ(強さ・濃さ・縁)を、生成済みの STEP3 へ即時反映する。

    太さの段・届く距離・詰まりの判定まで変わるので、値の書き換えでは済まず
    STEP3 を作り直す(ボタンと同じ処理、0.1〜0.3 秒)。STEP3 がまだ無い
    シーンでは何もしない(勝手にコンポジタを作らない)。
    """
    if _QUIET[0]:
        return
    from . import compat, fp_core
    scene = context.scene
    tree = compat.get_compositor_tree(scene)
    if tree is None or not getattr(scene, "fp_line_weight", False):
        return
    if not any(n.type == "GROUP" and n.node_tree is not None
               and n.node_tree.name.startswith(fp_core.NODE_GROUP_PREFIX)
               for n in tree.nodes):
        return
    fp_core.setup_compositor(scene, context.view_layer)


def _apply_preview_mode(scene) -> None:
    """プレビューの種類を1か所で反映する。

    どちらも「PROノードの Image 入力に何を流すか」を変えるだけなので、
    同時には成立しない。片方を立てるときは必ずもう片方を下ろす。
    """
    from . import fp_core
    mode = getattr(scene, "fp_preview_mode", "NONE")
    # 旧トグル(白)を種類に合わせる。更新フックを通さずに書く(通すと種類を
    # NONE に戻してしまう)。ずれたままだと、STEP3 の作り直しやスライダーで
    # 古い方の値を見て掛け直し、「白」を選んでいるのに材質の色で出た
    if bool(getattr(scene, "fp_white_preview", False)) != (mode == "WHITE"):
        _write_quiet(scene, {"fp_white_preview": mode == "WHITE"})
    if mode == "MONO_LIGHT":
        # 陰影の素になるパスが無いと真っ黒になる。つなぐ前に立てる。後で
        # 立てていたので、5.2 ではつなぐ時点でパスの口が無く、最初に
        # モノクロを選んだときだけ材質の色で出た(画像で確認)
        vl = bpy.context.view_layer
        if not vl.use_pass_diffuse_direct:
            vl.use_pass_diffuse_direct = True
            vl.update()
            logger.info("Enabled the Diffuse Direct pass for mono preview")
    # セル(影と色)は線を白地に描いてから色と影を掛けるので、白も立てる。
    # 強弱のある線のマテリアル/モノクロも同じ(線は白地、色や陰影は後で下に掛ける)
    from . import cel_shade
    under = cel_shade.wants_underlay(scene)
    # 先に、前の種類で挿したもの(セル/下に掛ける形)を外す。セルを挿してから下に掛ける形を外すと、
    # セルの入力が外したノードを指したままになり、線が全部消えた(総当りで発見)
    cel_shade.set_cel(scene, False)
    cel_shade.set_underlay(scene, None)
    fp_core.set_white_preview(
        scene, mode in ("WHITE", "CEL") or under,
        keep_glass=getattr(scene, "fp_white_keep_glass", True))
    fp_core.set_mono_light_preview(
        scene, mode == "MONO_LIGHT" and not under,
        floor=getattr(scene, "fp_mono_floor", 0.25))
    cel_shade.set_cel(scene, mode == "CEL")
    cel_shade.set_underlay(scene, mode if under else None)
    logger.info(f"Preview mode: {mode}")


def _update_preview_mode(self, context):
    if _QUIET[0]:
        return
    _apply_preview_mode(context.scene)


def _update_white_preview(self, context):
    """旧トグル。種類へ橋渡しして、古いスクリプトでも動くようにする。"""
    if _QUIET[0]:
        return
    scene = context.scene
    want = "WHITE" if scene.fp_white_preview else "NONE"
    if getattr(scene, "fp_preview_mode", "NONE") != want:
        scene.fp_preview_mode = want   # 種類側の更新フックが実処理をする
    else:
        _apply_preview_mode(scene)


def _update_white_keep_glass(self, context):
    """プレビュー中にガラス維持を切り替えたら復元→再適用で反映する。"""
    if _QUIET[0]:
        return
    from . import fp_core
    scene = context.scene
    if scene.fp_white_preview:
        fp_core.set_white_preview(scene, False)
        fp_core.set_white_preview(scene, True,
                                  keep_glass=scene.fp_white_keep_glass)


def register_props():
    """プロパティを登録する関数"""
    scene = bpy.types.Scene

    t = bpy.app.translations.pgettext
    color_type_items = [
        ('mecha_color', t("Mecha Color"), t("Mecha Color")),
        ('mask_color',  t("Mask Color(paint to erase lines)"),
         t("Lines vanish where painted. The brightness does not matter")),
        ('line_color',  t("Line Color(line darkness)"),
         t("Sets how dark the line is. White makes it invisible")),
    ]
    node_type_items = [
        ('test', t("Test Node"), t("Test Node")),
        ('pro',  t("Pro Node"),  t("Pro Node")),
    ]

    props_to_register = {
        "fp_sharp_clear": BoolProperty(
            name="clear sharp",
            description="Erase outline's sharp edges",
            default=False
        ),
        "fp_mat_count": BoolProperty(
            name="material ID",
            description="Add the material ID",
            default=False
        ),
        "fp_sharp_auto": BoolProperty(
            name="Auto edge angle",
            description=(
                "Choose the sharp-edge angle automatically from the mesh's "
                "dihedral-angle distribution (per object)"
            ),
            # 既定OFF: 既存ワークフロー(特にボーン系キャラ)の挙動を変えない。
            # 一括評価パイプラインはプリセットで明示的にONにする。
            default=False
        ),
        "fp_auto_split_floor": FloatProperty(
            name="Artificial split floor",
            description=(
                "Lowest angle the auto threshold may pick for a model that "
                "has no structural edges at all. Too low and a smoothly "
                "curving surface gets cut across at an arbitrary place"
            ),
            # 既定 5.0 = v2.7 と同じ。STEP0 が仕上がり(fp_auto_style)ごとに
            # 入れる: 精密 5.0 / 強弱 14.0。14 の根拠は utils.py の
            # ARTIFICIAL_SPLIT_FLOOR
            default=5.0, min=1.0, max=45.0, step=0.5, precision=1
        ),
        "fp_sharp_edges": FloatProperty(
            name="Line sharp edges",
            description="Outline's angle threshold.",
            default=30.0,
            min=0.0,
            max=180.0
        ),
        "fp_seam_boundaries": BoolProperty(
            name="Seam/material boundaries",
            description=(
                "Treat UV seams and material borders as island boundaries "
                "in addition to the edge angle"
            ),
            default=False
        ),
        "fp_min_island_area_pct": FloatProperty(
            name="Min island area %",
            description=(
                "Merge islands smaller than this % of total mesh area "
                "into their largest neighbor (0 = off)"
            ),
            # 既定OFF(0): 既存挙動を変えない。バッチはプリセットで0.02を指定
            #
            # 上限は 5% だったが、これは「小島の掃除」しか想定していない値。
            # 実測では 1〜2% で塗りが広くまとまり(スザンヌ 429色 -> 6色)、
            # メカは 5% でパネルごとに1色になる。有機的な形はさらに上まで
            # 上げると最終的にルースパーツ単位の1色に行き着くので、
            # そこまで動かせるようにする
            default=0.0,
            min=0.0,
            max=100.0,
            step=0.01,
            precision=3
        ),
        "fp_ridge_amount": FloatProperty(
            name="Ridge relief",
            description=(
                "Add a faint normal-based relief inside each island so that "
                "smooth ridges (a brow, a fold) get a line. 0 = off"
            ),
            # 島の色は面ごとに一定なので、足しても島境界の段差は残る。
            # 隣接島の色距離の契約(既定0.5)を割らないよう小さく保つ
            default=0.0,
            min=0.0,
            max=0.5,
            step=0.01,
            precision=3
        ),
        "fp_ridge_radius": FloatProperty(
            name="Ridge scale",
            description=(
                "How far to look when deciding the 'overall direction' of a "
                "surface, as a fraction of the object size. Smaller = thinner "
                "lines on finer features"
            ),
            default=0.08,
            min=0.005,
            max=0.5,
            step=0.005,
            precision=3
        ),
        "fp_color_type": EnumProperty(
            name="Vertex color type",
            description="Select vertex color type.",
            items=color_type_items,
            default='mecha_color'
        ),
        "fp_node_type": EnumProperty(
            name="Select node type",
            description="Select Node Type",
            items=node_type_items,
            default='test'
        ),
        # Requires Blender 4.3+ for Real-Time Compositor preview
        "fp_enable_compositor_view": BoolProperty(
            name="Enable Compositor Preview",
            description="Enable Compositor Preview",
            default=True,
            update=_update_compositor_view
        ),
        "fp_far_relief": FloatProperty(
            name="Far crush relief",
            description=(
                "Thin out lines where they have merged into solid black "
                "(typically the far background of a large set). "
                "0 = off, no change to the image"
            ),
            default=0.0, min=0.0, max=1.0, step=0.05, precision=2,
            update=_update_far_relief
        ),
        "fp_far_relief_radius": FloatProperty(
            name="Relief radius",
            description=(
                "How far to look when measuring how crowded the lines are, "
                "in pixels. Larger = only wide black areas are thinned"
            ),
            default=6.0, min=1.0, max=32.0, step=100, precision=0,
            update=_update_far_relief
        ),
        "fp_far_relief_threshold": FloatProperty(
            name="Relief threshold",
            description=(
                "How crowded an area must be before it is thinned. "
                "Lower = starts working on sparser lines"
            ),
            default=0.35, min=0.05, max=0.95, step=0.05, precision=2,
            update=_update_far_relief
        ),
        "fp_line_sensitivity": FloatProperty(
            name="Line sensitivity",
            description=(
                "Scale the line-detection thresholds inside the node group. "
                "Lower = weaker edges also become solid lines (1.0 = raw node)"
            ),
            # 既定を 0.5 にする。1.0 はノードの素の値で、塗り分けは
            # できているのに検出しきい値に届かず線が出ない境界が多かった。
            # 線が出るかは RGB距離で決まり、境目は実測で 0.05〜0.14。
            # 明度の近い隣接色(水色と白など)がここを越えられていない。
            #
            # 実測(1920等倍・4モデルのインク):
            #   戦車 0.0855 -> 0.0919 / メカ 0.1048 -> 0.1110
            #   帆船 0.0482 -> 0.0534 / カメラ 0.0894 -> 0.1004
            # 目視でも索具が点線から実線になり、ノイズは増えなかった。
            # 0.35 まで下げてもメカは破綻しないので余裕を残して 0.5。
            default=0.5,
            min=0.05,
            max=2.0,
            step=0.05,
            precision=2,
            update=_update_line_tuning
        ),
        # --- 線の強弱(入り抜き) -------------------------------------
        # くぼみ(AO)が深いほど線を太くする。詳細と実測は line_weight.py
        "fp_line_weight": BoolProperty(
            name="Line weight from cavities",
            description=(
                "Thicken the line where the shape is recessed and thin it "
                "where it is open, using the ambient-occlusion pass. "
                "Updates the drawing right away"
            ),
            # 既定OFF。既存ファイルの絵を勝手に変えない
            default=False,
            # 切り替えたら STEP3 ごと作り直す(感度の実効値も変わる)
            update=_update_line_weight_toggle
        ),
        "fp_lw_strength": FloatProperty(
            name="Weight strength",
            description=(
                "Multiplier on the step widths. 1.0 = 12/8/5/3/2 px before "
                "the 50% shrink. Updates the drawing right away"
            ),
            default=1.0, min=0.2, max=3.0, step=0.05, precision=2,
            update=_update_line_weight_live
        ),
        "fp_lw_density": FloatProperty(
            name="Measured line density",
            description=(
                "Share of the silhouette covered by lines, read by the "
                "threshold measurement. Dense models get a lower maximum "
                "width automatically"
            ),
            default=0.0, min=0.0, max=1.0, precision=3
        ),
        # 奥ほど線を細く・少なく・薄く(深度パス)。町のように奥へ続く
        # セットで、遠くの線が詰まって黒い塊になるのを防ぐ。既定は全部OFF
        "fp_lw_far": FloatProperty(
            name="Thin far lines",
            description=(
                "Shrink the line weight with distance so far objects keep "
                "the thin base line only. 0 = off"
            ),
            default=0.0, min=0.0, max=1.0, step=5, precision=2
        ),
        "fp_lw_far_sens": FloatProperty(
            name="Fewer far lines",
            description=(
                "Raise the line threshold with distance so weak lines drop "
                "out far away. 1 = off, 3 = far threshold x3"
            ),
            default=1.0, min=1.0, max=4.0, step=10, precision=1
        ),
        "fp_lw_far_fade": FloatProperty(
            name="Lighten far lines",
            description=(
                "Fade far lines toward the paper, like aerial perspective. "
                "0 = off"
            ),
            default=0.0, min=0.0, max=1.0, step=5, precision=2
        ),
        "fp_lw_dense": FloatProperty(
            name="Fade dense lines",
            description=(
                "Lighten lines where they are packed together on screen "
                "(shutters, railings, fire escapes), so dense detail reads as "
                "fine texture instead of a black blob. 0 = off. Updates the "
                "drawing right away"
            ),
            default=0.0, min=0.0, max=1.0, step=5, precision=2,
            update=_update_line_weight_live
        ),
        "fp_lw_stripe_fade": FloatProperty(
            name="Fade fine stripes",
            description=(
                "Far away, blur rows of lines that are packed finer than the "
                "pixels (shutters, louvers, railings seen from a low angle) "
                "into a light haze, keeping floor bands and outlines. Only rows "
                "running one way are touched, not leaves. Stops the far end from "
                "crushing and flickering. 0 = off. Updates the drawing right away"
            ),
            default=0.0, min=0.0, max=1.0, step=5, precision=2,
            update=_update_line_weight_live
        ),
        # パネルに出すのはこの2本。中の5つはまとめて動かす(v2.8.1 で整理。
        # 5つとも組で動かすもので、1つずつ触る理由が無かった)
        "fp_lw_far_amount": FloatProperty(
            name="Far lines",
            description=(
                "How much to hold back far lines: thinner, fewer and lighter "
                "with distance. 1 = the Background default, 0 = off. Updates "
                "the drawing right away"
            ),
            default=0.0, min=0.0, max=1.5, step=5, precision=2,
            update=_update_far_amount
        ),
        "fp_lw_relief": FloatProperty(
            name="Crush relief",
            description=(
                "Keep packed detail from crushing into black: fade lines that "
                "are packed together (railings, shutters) and blur rows of "
                "stripes that get finer than the pixels far away. Outlines stay. "
                "1 = the Background default, 0 = off. Updates the drawing right away"
            ),
            default=0.0, min=0.0, max=1.5, step=5, precision=2,
            update=_update_relief
        ),
        "fp_lw_far_start": FloatProperty(
            name="Far start",
            description=(
                "Camera distance where the far treatment begins. Measured "
                "with the thresholds (5th percentile of line depth)"
            ),
            default=0.0, min=0.0, precision=1
        ),
        "fp_lw_far_end": FloatProperty(
            name="Far end",
            description=(
                "Camera distance where the far treatment is full. Measured "
                "with the thresholds (95th percentile of line depth)"
            ),
            default=0.0, min=0.0, precision=1
        ),
        # 手描き背景モードの特殊処理。既定 0 = 通らない
        "fp_fine_lines": FloatProperty(
            name="Fine lines",
            description=(
                "Also paint a second, finer split (the precise/mech one) and "
                "lay those lines over the drawing at this strength. "
                "0 = off. Needs STEP0 again (it paints twice)"
            ),
            default=0.0, min=0.0, max=1.0, step=5, precision=2,
            update=_update_fine_lines
        ),
        "fp_foliage_clumps": IntProperty(
            name="Foliage clumps",
            description=(
                "Paint small islands (leaf cards) in this many spatial "
                "clumps instead of one colour per leaf. 0 = off. Needs "
                "STEP1 again. Maple 4-8, palm 1"
            ),
            default=0, min=0, max=16
        ),
        "fp_far_lod_px": FloatProperty(
            name="Merge far islands (px)",
            description=(
                "Islands that look smaller than this on screen (pixels of a "
                "1920-wide picture, seen from the camera, nearest point of its animation) are "
                "painted together with the nearest bigger island, so far "
                "buildings keep their outline and big bands instead of a black "
                "block of windows. 0 = off. Needs STEP1 again"
            ),
            default=0.0, min=0.0, max=5000.0, step=1000, precision=0
        ),
        "fp_gap_fill": IntProperty(
            name="Fill leaf gaps",
            description=(
                "Fill holes narrower than this (pixels at 200%) before "
                "detecting lines, so sky seen between leaves does not "
                "outline every leaf. 0 = off. Needs STEP3 again"
            ),
            default=0, min=0, max=32
        ),
        "fp_lw_ink": FloatProperty(
            name="Ink darkness",
            description=(
                "How dark the darkest line is, as seen on screen. 1 = black, "
                "0.75 = dark grey. Updates the drawing right away"
            ),
            default=1.0, min=0.2, max=1.0, step=5, precision=2,
            update=_update_line_weight_live
        ),
        "fp_lw_soften": FloatProperty(
            name="Soften edges",
            description=(
                "Blur the line edges by this many pixels (at 200%) after "
                "anti-aliasing, before the 50% downscale. 0 = SMAA only"
            ),
            # 1px(1080pで0.5px)では SMAA だけとほぼ同じで、2px で段が消えた
            # (実測: 町のデモ4倍拡大)
            default=2.0, min=0.0, max=4.0, step=10, precision=1,
            update=_update_line_weight_live
        ),
        # 段の境目。d = 1 - AO の分位点。モデルごとに15倍ひらくので
        # 「しきい値を測る」ボタンでカットごとに入れ直す
        **{
            f"fp_lw_e{i}": FloatProperty(
                name=f"Weight edge {i}",
                description="Step boundary on 1 - AO. Measure it per cut",
                default=d, min=0.0, max=1.0, step=0.001, precision=4
            )
            for i, d in enumerate((0.0019, 0.0147, 0.0453, 0.1051), start=1)
        },
        **{
            f"fp_ch_{ch}": FloatProperty(
                name=f"{label} strength",
                description=(
                    f"Line strength of the {label} channel. "
                    "1.0 = current, higher = more/stronger lines, 0 = off"
                ),
                default=1.0,
                min=0.0,
                max=2.0,
                step=0.05,
                precision=2,
                subtype='FACTOR',
                update=_update_line_tuning
            )
            for ch, label in (
                ("mecha", "Mecha"), ("depth", "Depth"), ("bone", "Bone"),
                ("gen", "Generate"), ("mat", "Material"),
            )
        },
        # STEP0 の仕上がり。v2.7 の挙動を「精密」として残し、AO の強弱は
        # 別のスタイルとして選ぶ。既定は精密(既存ファイルの出力を変えない)
        "fp_auto_style": EnumProperty(
            name="Finish",
            description="What STEP0 aims for",
            items=[
                ('PRECISE', "Precise (mech)",
                 "Uniform lines, every panel edge. Same output as v2.7"),
                ('WEIGHTED', "Character (hand-drawn)",
                 "Line weight from cavities (AO): the outline is thick and "
                 "lines thin as they enter a crease. Smooth surfaces are "
                 "split less (14 deg floor, ridge 0.45) and the AO "
                 "thresholds are measured for this shot"),
                ('BACKGROUND', "Background (hand-drawn)",
                 "Character plus special handling for sets: far lines get "
                 "thin, fewer and lighter with distance, and foliage is "
                 "painted in clumps instead of leaf by leaf"),
            ],
            default='PRECISE',
            update=_update_auto_style
        ),
        # STEP0 全自動が適用する項目の個別ON/OFF
        **{
            name: BoolProperty(name=label, description=desc, default=default)
            for name, label, desc, default in (
                ("fp_auto_sharp", "Auto: edge angle",
                 "Full auto sets the sharp-edge angle automatically", True),
                ("fp_auto_seam", "Auto: seam/material boundaries",
                 "Full auto splits islands at UV seams and material borders", True),
                ("fp_auto_merge", "Auto: merge small islands",
                 "Full auto merges tiny islands (0.02%)", True),
                ("fp_auto_part_tint", "Auto: part tint",
                 "Full auto separates touching parts by brightness bands", True),
                ("fp_auto_bone", "Auto: bone AOV by rig detection",
                 "Full auto enables the bone AOV when an armature is found", True),
                ("fp_auto_aa", "Auto: anti-aliasing",
                 "Full auto includes the anti-aliasing node", True),
                ("fp_auto_hashed", "Auto: BLEND to HASHED",
                 "Full auto converts BLEND materials (except real glass) to "
                 "HASHED so AOVs render", True),
                ("fp_auto_supersample", "Auto: 2x supersampling",
                 "Full auto enables 2x render + 50% output scaling. "
                 "Near-essential: FreePencil lines are too thick without it",
                 True),
                ("fp_auto_detect_aov", "Auto: AOVs from scene",
                 "Full auto owns the AOV setup: gen/mask/line follow whether "
                 "those vertex colors are painted, mat follows material ID. "
                 "STEP2 manual toggles are overridden while this is on", True),
                ("fp_auto_file_output", "Auto: enable File Output",
                 "Full auto also enables the STEP3 File Output node", False),
                ("fp_auto_white_preview", "Auto: white material preview",
                 "Full auto turns on the white material preview so the line "
                 "art is visible right after setup. Materials are untouched "
                 "(the compositor is switched); turn it off to see the "
                 "original materials", True),
            )
        },
        "fp_supersample": BoolProperty(
            name="2x supersampling (thin lines)",
            description=(
                "Render at 200% resolution and scale the compositor output "
                "back to 50%, turning 2px lines into crisp 1px lines. "
                "Applies to the Composite output and File Output slots"
            ),
            default=False
        ),
        "fp_preview_mode": EnumProperty(
            name="Preview",
            description=(
                "What to show under the lines. Both work the same way: "
                "they change what feeds the node group, so materials are "
                "never touched"
            ),
            items=[
                ('NONE', t("Materials"),
                 t("Show the scene as it is, with lines on top")),
                ('WHITE', t("White"),
                 t("Flat white under the lines. Pure line art")),
                ('MONO_LIGHT', t("Mono (diffuse light)"),
                 t("Grey shading from the diffuse light, with lines on "
                   "top. Texture patterns are not carried over")),
                ('CEL', t("Cel (shadow and color)"),
                 t("Two-tone cel shadow and pale material colors under the "
                   "lines, with a sky color behind. Works whatever the "
                   "materials are (the light is taken from a white surface)")),
            ],
            default='NONE',
            update=_update_preview_mode
        ),
        "fp_cel_threshold": FloatProperty(
            name="Shadow threshold",
            description=(
                "Where light turns into shadow (1 = the brightest spot). "
                "Raise it for more shadow"
            ),
            # 0.7 では、日に斜めの面(既定の地面で 0.6)まで影になった。C62 の場面は影 0.45 / 日なた 0.87
            default=0.55, min=0.05, max=0.98, step=2, precision=2,
            update=_update_preview_mode
        ),
        "fp_cel_softness": FloatProperty(
            name="Smooth shadow edges",
            description=(
                "Blur the light before cutting it into two tones (px). "
                "Removes speckled shadows and wavy edges"
            ),
            default=3.0, min=0.0, max=12.0, step=50, precision=1,
            update=_update_preview_mode
        ),
        "fp_cel_shadow_color": FloatVectorProperty(
            name="Shadow color",
            description="Color multiplied into the shadow side",
            subtype='COLOR', size=3, min=0.0, max=1.0,
            default=(0.62, 0.62, 0.80),
            update=_update_preview_mode
        ),
        "fp_cel_pale": FloatProperty(
            name="Paleness",
            description=(
                "How far the material colors are pushed toward white. "
                "0 keeps the material color"
            ),
            default=0.15, min=0.0, max=1.0, step=5, precision=2,
            update=_update_preview_mode
        ),
        "fp_cel_sky": BoolProperty(
            name="Sky color",
            description=(
                "Fill the background with a sky color. Off keeps it "
                "transparent (for compositing elsewhere)"
            ),
            default=True,
            update=_update_preview_mode
        ),
        "fp_cel_sky_color": FloatVectorProperty(
            name="Sky",
            description="Background color behind the objects",
            subtype='COLOR', size=3, min=0.0, max=1.0,
            default=(0.6, 0.76, 0.93),
            update=_update_preview_mode
        ),
        "fp_cel_shadow_line": BoolProperty(
            name="Shadow line",
            description="Draw a colored line along the shadow edge",
            default=False,
            update=_update_preview_mode
        ),
        "fp_cel_shadow_line_color": FloatVectorProperty(
            name="Shadow line color",
            description="Color of the line along the shadow edge",
            subtype='COLOR', size=3, min=0.0, max=1.0,
            default=(0.05, 0.2, 0.8),
            update=_update_preview_mode
        ),
        "fp_cel_shadow_line_width": FloatProperty(
            name="Shadow line width",
            description="Width of the shadow line (px)",
            default=1.0, min=1.0, max=6.0, step=50, precision=1,
            update=_update_preview_mode
        ),
        "fp_mono_floor": FloatProperty(
            name="Shadow floor",
            description=(
                "How dark the shadows may get in mono preview. "
                "0 crushes them to black and the lines disappear"
            ),
            default=0.25, min=0.0, max=0.9, step=5, precision=2,
            update=_update_preview_mode
        ),
        "fp_white_preview": BoolProperty(
            name="White material preview",
            description=(
                "Temporarily replace all materials with a flat white "
                "emission (AOV-enabled) to preview pure line art. "
                "Original materials are backed up per object and fully "
                "restored when turned off"
            ),
            default=False,
            update=_update_white_preview
        ),
        "fp_white_keep_glass": BoolProperty(
            name="Keep glass transparent",
            description=(
                "While white preview is on, leave real glass materials "
                "(Transmission / low Alpha) untouched so you can still "
                "see through windows"
            ),
            default=True,
            update=_update_white_keep_glass
        ),
        "fp_file_output": BoolProperty(
            name="File Output",
            description=(
                "Add a File Output node to the generated compositor tree "
                "that writes the selected passes as PNGs"
            ),
            default=False
        ),
        # どのパスを書き出すかは個別に選ぶ。影は EEVEE だとノイズが多く
        # 使えないことが多いので既定 OFF、ディフューズ直接光を既定 ON。
        "fp_fo_line": BoolProperty(
            name="Write line pass",
            description="Write the line art to line.png",
            default=True
        ),
        "fp_fo_color": BoolProperty(
            name="Write color pass",
            description="Write the flat color output to color.png",
            default=True
        ),
        "fp_fo_light": BoolProperty(
            name="Write light pass",
            description=(
                "Write the diffuse direct light pass to light.png. "
                "Easier to composite than the shadow pass"
            ),
            default=True
        ),
        "fp_fo_shadow": BoolProperty(
            name="Write shadow pass",
            description=(
                "Write the shadow pass to shadow.png. "
                "EEVEE's shadow pass is often noisy"
            ),
            default=False
        ),
        "fp_fo_cel_color": BoolProperty(
            name="Write cel color",
            description=(
                "Write flat, pale material colors without shading to "
                "cel_color.png (transparent outside the objects)"
            ),
            default=False
        ),
        "fp_fo_cel_shadow": BoolProperty(
            name="Write cel shadow",
            description=(
                "Write the two-tone cel shadow to cel_shadow.png: shadow "
                "color where it is in shadow, transparent elsewhere. Stack "
                "it as a multiply layer"
            ),
            default=False
        ),
        "fp_file_output_path": bpy.props.StringProperty(
            name="File Output path",
            description="Base path for the File Output node",
            default="//render/",
            subtype='DIR_PATH'
        ),
        "fp_include_antialiasing": BoolProperty(
            name="Include Anti-Aliasing Node",
            description="Insert Anti-Aliasing node before Composite",
            default=False,
        ),
        "fp_gen_color": BoolProperty(
            name="generator color",
            description="AOV Generator Color",
            default=False
        ),
        "fp_mask_color": BoolProperty(
            name="mask color",
            description="AOV Mask Color(White erases lines)",
            default=False
        ),
        "fp_line_color": BoolProperty(
            name="line color",
            description="AOV Line Color",
            default=False
        ),
        "fp_mat_color": BoolProperty(
            name="material color",
            description="AOV Material Boundary Color",
            default=False
        ),
        "fp_bone_color": BoolProperty(
            name="bone color",
            description="AOV Bone Color",
            default=False
        ),
        "fp_color_noise_scale": FloatProperty(
            name="Color noise scale",
            description="Increasing the scale scatters island colors more randomly.",
            default=1.0,
            min=0.01,
            max=10.0,
            step=0.1,
            precision=2,
            subtype='FACTOR'
        ),
        "fp_min_neighbor_color_distance": FloatProperty(
            name="Min color distance",
            description="Minimum RGB distance between neighboring islands (0–1.732). Lower values allow similar colors.",
            default=0.5,
            min=0.0,
            max=1.732,
            step=0.01,
            precision=2
        ),
        "fp_max_color_retries": IntProperty(
            name="Max color retries",
            description="How many times to retry when a color already exists",
            default=30,
            min=1,
            max=200
        ),
        "fp_use_random_seed": BoolProperty(
            name="Random seed each run",
            description=(
                "Generate a new random seed every run. "
                "Turn this off to reproduce exactly the same island colors."
            ),
            default=True
        ),
        "fp_color_seed": IntProperty(
            name="Color seed",
            description=(
                "Seed for island color generation. "
                "The same seed with the same mesh reproduces the same colors."
            ),
            default=0,
            min=0,
            max=2147483647
        ),
        "fp_bone_grouping_mode": EnumProperty(
            name=t("Bone color grouping"),
            description=t("How to group bone names when coloring bone_color"),
            items=[
                ('exact', t("Exact"), t("Use the bone/vertex-group name as-is")),
                ('basename', t("Basename (.###)"), t("Treat suffix like .001 as the same")),
                ('stripdigits', t("Strip trailing digits"), t("Ignore trailing digits even without dot")),
            ],
            default='basename',
        ),
        "fp_part_tint": BoolProperty(
            name="Part tint (mecha color)",
            description=(
                "Give touching parts (objects) different brightness bands "
                "in mecha_color so part boundaries (hairline, collar) become "
                "lines; bone_color stays a pure weight blend and the node "
                "composites both channels"
            ),
            default=True
        ),
        "fp_bone_hard_names": bpy.props.StringProperty(
            name="Hard boundary bones",
            description=(
                "Comma-separated bone names whose region boundary should be "
                "a hard step in bone_color (so a line appears there, e.g. "
                "'head' for a chin line). Empty = all soft blending"
            ),
            default=""
        ),
        "fp_half_color": FloatVectorProperty(
            name="Half mask color",
            description="Color used by Half Fill",
            subtype='COLOR',
            size=4,
            min=0.0,
            max=1.0,
            default=(1.0, 0.0, 0.0, 1.0)
        )
    }

    for prop_name, prop_value in props_to_register.items():
        if not hasattr(bpy.types.Scene, prop_name):
            setattr(scene, prop_name, prop_value)
            logger.info(f"Registered property: {prop_name}")
        else:
            logger.info(f"Property already exists: {prop_name}")

    # 手描き系の仕上がりでの塗り方(オブジェクト単位)。自動はリグの付き方で
    # 見分ける(vertex_color.paint_as)。リグ付きロボットをメカに、リグ無しの
    # 人をキャラにしたいときに上書きする
    if not hasattr(bpy.types.Object, "fp_paint_as"):
        bpy.types.Object.fp_paint_as = EnumProperty(
            name="Paint as",
            description=(
                "How STEP1 paints this object in the hand-drawn finishes "
                "(Character / Background). Precise always splits by angle"
            ),
            items=[
                ('AUTO', "Auto",
                 "Rigged objects are painted as characters, unless most "
                 "vertices follow a single bone (a robot)"),
                ('MECHA', "Mecha",
                 "Split by edge angle and keep every panel line, even when "
                 "rigged"),
                ('CHARA', "Character",
                 "Coarse paint: one color per part, joints blended by bone "
                 "weights. Also works without a rig"),
            ],
            default='AUTO'
        )

    # 物ごとの線の太さ(v2.9)。1 以外の物があるときだけ合成にノードを挿す(line_scale)
    if not hasattr(bpy.types.Object, "fp_line_scale"):
        bpy.types.Object.fp_line_scale = FloatProperty(
            name="Line width",
            description=(
                "Line width for this object. 1 = as is, 2 = thicker, "
                "0.5 = lighter, 0 = no lines"
            ),
            default=1.0, min=0.0, max=3.0, soft_max=3.0, step=10, precision=2,
            update=_update_line_scale
        )

    # カメラ一括レンダリング対象のチェック(オブジェクト単位)
    if not hasattr(bpy.types.Object, "fp_cam_render"):
        bpy.types.Object.fp_cam_render = BoolProperty(
            name="Render this camera",
            description=(
                "Include this camera in FreePencil's "
                "'Render checked cameras' batch"
            ),
            default=True
        )

def unregister_props():
    """プロパティを解除する関数"""
    scene = bpy.types.Scene
    props_to_clear = [
        "fp_sharp_edges", "fp_sharp_auto", "fp_auto_split_floor",
        "fp_seam_boundaries",
        "fp_min_island_area_pct", "fp_sharp_clear",
        "fp_ridge_amount", "fp_ridge_radius",
        "fp_color_type", "fp_mat_count",
        "fp_gen_color", "fp_mask_color", "fp_line_color",
        "fp_mat_color", "fp_bone_color", "fp_enable_compositor_view",
        "fp_include_antialiasing", "fp_line_sensitivity",
        "fp_line_weight", "fp_lw_strength", "fp_lw_density",
        "fp_lw_far", "fp_lw_far_sens", "fp_lw_far_fade", "fp_lw_far_start", "fp_lw_far_end",
        "fp_lw_dense", "fp_lw_stripe_fade", "fp_lw_far_amount", "fp_lw_relief",
        "fp_foliage_clumps", "fp_far_lod_px", "fp_gap_fill", "fp_lw_ink", "fp_lw_soften",
        "fp_fine_lines", "fp_lw_e1", "fp_lw_e2", "fp_lw_e3", "fp_lw_e4",
        "fp_far_relief", "fp_far_relief_radius", "fp_far_relief_threshold",
        "fp_ch_mecha", "fp_ch_depth", "fp_ch_bone", "fp_ch_gen", "fp_ch_mat",
        "fp_file_output", "fp_file_output_path",
        "fp_fo_line", "fp_fo_color", "fp_fo_light", "fp_fo_shadow",
        "fp_fo_cel_color", "fp_fo_cel_shadow",
        "fp_white_preview", "fp_preview_mode", "fp_mono_floor",
        "fp_cel_threshold", "fp_cel_softness", "fp_cel_shadow_color", "fp_cel_pale",
        "fp_cel_sky", "fp_cel_sky_color", "fp_cel_shadow_line",
        "fp_cel_shadow_line_color", "fp_cel_shadow_line_width",
        "fp_white_keep_glass", "fp_supersample",
        "fp_auto_sharp", "fp_auto_seam", "fp_auto_merge", "fp_auto_part_tint",
        "fp_auto_bone", "fp_auto_aa", "fp_auto_hashed", "fp_auto_file_output",
        "fp_auto_detect_aov", "fp_auto_supersample", "fp_auto_white_preview",
        "fp_auto_style",
        "fp_color_noise_scale", "fp_min_neighbor_color_distance",
        "fp_max_color_retries",
        "fp_use_random_seed", "fp_color_seed",
        "fp_bone_grouping_mode", "fp_bone_hard_names", "fp_part_tint",
        "fp_node_type",
        "fp_half_color"
    ]
    
    for prop_name in props_to_clear:
        if hasattr(scene, prop_name):
            try:
                delattr(scene, prop_name)
                logger.info(f"Cleared property: {prop_name}")
            except AttributeError:
                logger.exception(f"Failed to clear property: {prop_name}")
        else:
            logger.info(f"Property does not exist: {prop_name}")

    for prop_name in ("fp_cam_render", "fp_paint_as", "fp_line_scale"):
        if hasattr(bpy.types.Object, prop_name):
            try:
                delattr(bpy.types.Object, prop_name)
            except AttributeError:
                logger.exception(f"Failed to clear property: {prop_name}")
