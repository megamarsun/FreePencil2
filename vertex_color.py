"""Utility operators for automatic vertex color generation."""

import bpy
import math
import time
import random
import colorsys
import logging
import hashlib
import re

import numpy as np
from mathutils import Vector

from . import mesh_islands
from . import utils

# パレットの上限。実際の色数は palette_for_diversity が距離・輝度差の契約を
# 見て決めるので、既定の輝度窓では5色前後で頭打ちになる。窓を広げた
# パーツ・トーン分けのときに、もう少し取れる余地を残すための上限
PALETTE_SIZE = 16


logger = logging.getLogger(__name__)

# シード上限（Blender IntProperty は符号付き32bit のため 2^31-1 に収める）
SEED_MAX = 2147483647


def stable_hash_u32(text: str) -> int:
    """Return a process-independent 32-bit hash for a string.

    The built-in ``hash()`` is salted per Python process, so it cannot be used
    when reproducible colors are required across Blender sessions.
    """
    digest = hashlib.sha1(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") & 0xFFFFFFFF

# 定数
VCOL_LAYER_MECHA = "mecha_color"
VCOL_LAYER_MASK = "mask_color"
VCOL_LAYER_LINE = "line_color"
VCOL_LAYER_BONE = "bone_color"
# キャラのざっくり塗りで「小さいパーツ」とみなす面積の割合(オブジェクト全体比)
COARSE_SMALL_PART = 0.02
# キャラ(ざっくり塗り)でボーンの色を隣の頂点と平均する回数
BONE_SMOOTH_ITERS = 8
# リグ付きでも、頂点の大半がボーン1本に固定(剛体)されていればメカとして塗る。
# ロボットは部品ごとに1本のボーンへ100%で付き、人は関節でなめらかに混ざる。
# 実測(頂点のうちボーン1本が 99% 以上を持つ割合): ザク 0.94 /
# anime-girl 0.80(髪・スカートが頭や腰に固定) / fredy 0.15 / man_01 0.27 /
# mozo 0.20 / space_scavenger(宇宙服の人) 0.41
RIGID_MECHA = 0.9
# ボーンが少ないリグは判定しない(キャラのまま)。ボーンが 1〜2 本なら頂点は
# どうしても1本に固定される。デッサン人形は頭だけ別のリグ(ボーン 2 本)で、
# その頭が 0.93 になりロボットと判定された。ザクは 64 本すべてを使う
RIGID_MIN_BONES = 8
DEFAULT_MATERIAL_NAME = "FreePencil_Material"
# 頭のボーンの名前(mixamorig:Head / J_Bip_C_Head / DEF-head / 頭)。forehead は入れない
HEAD_BONE_RE = re.compile(r"(?:^|[^a-z])head(?:[._]x)?$|頭$")
# 頭の下でも頭の色にしない毛(髪と顔の境の線はボーンの色の違いで出ている)
HEAD_KEEP_RE = re.compile(r"hair|bang|ponytail|髪")
# 顔の部品の名前。Rigify は顔のボーンが頭の子でなく ORG-face の下にあり、変形のボーンは
# DEF-lip.T.L のような名前(fredy)。forearm の ear は拾わない
FACE_PART_RE = re.compile(
    r"(?:^|[^a-z])(?:lips?|brows?|eyebrows?|lids?|eyelids?|cheeks?|jaw|chin|nose|nostrils?|ears?|"
    r"forehead|temples?|teeth|tooth|tongue|eyes?|mouth|lash(?:es)?|face)(?:[^a-z]|$)")


def head_family(bones, norm, deform=()):
    """顔のボーンを 1 色にまとめるための (顔のボーンの正規化した名前の集合, 頭の正規化した名前 or None)。

    顔のリグ(眉・まぶた・唇・頬に小さいボーンが何十本もある)では、ボーンごとに色が
    違うので、ウェイトの混ざりで顔じゅうに色のまだらができ、線が目や口のまわりの
    しみのような塊になった(fredy。ボーンのチャンネルを止めると消える)。顔のボーンは
    頭と同じ色にする。目や口の形は材質と物の切れ目の線で出る。髪の毛のボーンはそのまま。
    顔のボーン = 頭のボーンの子孫 + 顔の部品の名前のボーン。2 本未満なら空の集合。
    頭の名前のボーンが複数あれば、ウェイトを持つ物(deform に名前がある物)を選ぶ。操作用の
    c_head.x の子に変形用の head.x があるリグで、head.x まで顔に入れて首の色にした(terna)。
    """
    heads = [b for b in bones if HEAD_BONE_RE.search(b.name.lower())]
    heads = [b for b in heads if norm(b.name) in deform] or heads

    def descendants(b):
        out, stack = [], list(b.children)
        while stack:
            c = stack.pop()
            out.append(c)
            stack.extend(c.children)
        return out

    head, fam = None, []
    if heads:
        head, fam = max(((h, descendants(h)) for h in heads), key=lambda t: len(t[1]))
    fam += [b for b in bones if FACE_PART_RE.search(b.name.lower())]
    names = {norm(c.name) for c in fam if not HEAD_KEEP_RE.search(c.name.lower())}
    if head is not None:
        names.discard(norm(head.name))
    if len(names) < 2:
        return set(), None
    return names, (norm(head.name) if head is not None else None)


def face_target(obj, verts, family_idx, bone_idx, name_of):
    """頭のボーンの色が使えないとき、顔のボーンと一番ウェイトを分け合っている顔以外のボーン(頭)を返す。"""
    acc = {}
    for v in verts:
        gs = v.groups
        if not any(g.group in family_idx and g.weight > 0.0 for g in gs):
            continue
        for g in gs:
            if g.group in bone_idx and g.group not in family_idx:
                acc[g.group] = acc.get(g.group, 0.0) + g.weight
    if not acc:
        return "face"
    return name_of[max(acc, key=acc.get)]

# ハッシュ関数
def get_pseudo_random_float_from_vec(
    p_x: float,
    p_y: float,
    p_z: float,
    master_seed_int: int,
    instance_seed_int: int,
    scale_factor: float,
) -> float:
    """Return a deterministic pseudo random float based on a vector and seeds."""
    val_x = p_x * scale_factor
    val_y = p_y * scale_factor
    val_z = p_z * scale_factor
    h = master_seed_int 
    h = (h ^ instance_seed_int) * 16777619 
    h &= 0xFFFFFFFF 
    ix = int(val_x * 1000.0) 
    iy = int(val_y * 1000.0)
    iz = int(val_z * 1000.0)
    h = (h ^ ix) * 16777619
    h = ((h << 13) | (h >> (32 - 13))) & 0xFFFFFFFF
    h = (h ^ iy) * 16777619
    h = ((h << 13) | (h >> (32 - 13))) & 0xFFFFFFFF
    h = (h ^ iz) * 16777619
    h = ((h << 13) | (h >> (32 - 13))) & 0xFFFFFFFF
    h ^= (h >> 16)
    h = (h * 0x85ebca6b) & 0xFFFFFFFF
    h ^= (h >> 13)
    h = (h * 0xc2b2ae35) & 0xFFFFFFFF
    h ^= (h >> 16)
    return (h / 0xFFFFFFFF)

# RGB色間のユークリッド距離
_RIGID_CACHE = {}


def _rigid_counts(obj, bones, used):
    """1 メッシュの (ウェイトのある頂点数, ボーン1本が 99% 以上を持つ頂点数)。
    ボーン名と一致する頂点グループだけを数える(マスク用のグループは除く)。
    ウェイトの付いたボーンの名前を used に足す。"""
    name_of = {vg.index: vg.name for vg in obj.vertex_groups if vg.name in bones}
    if not name_of:
        return 0, 0
    tot = rigid = 0
    for v in obj.data.vertices:
        gs = [(g.group, g.weight) for g in v.groups
              if g.group in name_of and g.weight > 1e-4]
        if not gs:
            continue
        tot += 1
        ws = [w for _, w in gs]
        if max(ws) >= 0.99 * sum(ws):
            rigid += 1
        for gi, _ in gs:
            used.add(name_of[gi])
    return tot, rigid


def rigid_ratio(obj):
    """(割合, 使っているボーンの数)。このメッシュを動かすリグ(アーマチュア)で
    動く全メッシュのうち、ボーン1本がウェイトの 99% 以上を持つ頂点の割合。

    リグ単位でまとめて測る。部品が別オブジェクトのキャラでは、頭だけ・兜だけは
    1本のボーンに固定されていて、1つずつ測るとロボットに見えた(デッサン人形の
    頭 0.93、全体では 0.64)。
    """
    arm = next((m.object for m in obj.modifiers
                if m.type == 'ARMATURE' and m.object), None)
    if arm is None or obj.type != 'MESH':
        return 0.0, 0
    if arm.name in _RIGID_CACHE:
        return _RIGID_CACHE[arm.name]
    bones = set(arm.data.bones.keys())
    used = set()
    tot = rigid = 0
    for o in bpy.data.objects:
        if o.type != 'MESH' or not any(m.type == 'ARMATURE' and m.object == arm
                                       for m in o.modifiers):
            continue
        t, r = _rigid_counts(o, bones, used)
        tot += t
        rigid += r
    res = (rigid / tot if tot else 0.0, len(used))
    _RIGID_CACHE[arm.name] = res
    return res


def paint_as(obj):
    """手描き系の仕上がりでの塗り方: 'CHARA'(ざっくり塗り + ボーン塗り)か
    'MECHA'(角度で分ける)。

    オブジェクトの設定(fp_paint_as)が自動なら、リグの無い物はメカ、
    リグ付きはボーンを RIGID_MIN_BONES 本以上使い、rigid_ratio >= RIGID_MECHA
    ならメカ、それ以外はキャラ。
    判定の結果は obj["fp_paint_auto"] に残す(パネルに出す)。
    """
    mode = getattr(obj, "fp_paint_as", 'AUTO')
    if mode in ('MECHA', 'CHARA'):
        return mode
    rigged = any(m.type == 'ARMATURE' and m.object for m in obj.modifiers)
    if not rigged:
        kind = 'MECHA'
    else:
        r, n_bones = rigid_ratio(obj)
        kind = ('MECHA' if r >= RIGID_MECHA and n_bones >= RIGID_MIN_BONES
                else 'CHARA')
        obj["fp_rigid_ratio"] = round(r, 3)
    obj["fp_paint_auto"] = kind
    return kind


# 画面で小さすぎる区画は、どの仕上がりでもまとめる(px^2、横 1920 基準。v3.0)。
# AI が作ったメカ(walker_robot / walker_mech / mech_tank)は、1 つのメッシュが画面で数 px の
# 破片(walker_robot は 6835 区画)に割れていて、破片の縁が黒い点と塊になった。
# 40 では点が残り、150 で塊が消えて、角とパネルの線は残った(dev/batch/exp_tiny_px.py)。
# 代わりに、ドワーフの指の小さな印やローバーの灯りの格子は単純になる。
# 手描き背景は fp_far_lod_px(500)の方が大きいのでそちらが効く
PRECISE_TINY_PX = 150.0
# ただし画面でこの長さ(px、横 1920 基準)以上ある区画は、面積が小さくても残す。
# 面積だけで見ると、吊り橋の橋桁(細長い帯)まで 1 本の線にまとまった
PRECISE_TINY_LEN_PX = 40.0
FAR_LOD_FRAME_SAMPLES = 33   # カメラが動くとき、動きの範囲から取る位置の数
FAR_LOD_REF_WIDTH = 1920     # 遠い区画のしきい値(px^2)はこの横幅の絵で測る


def far_lod_cameras(scene):
    """遠い区画をまとめる(mesh_islands.merge_far_islands)ためのカメラ。

    戻り値 (位置のリスト, 焦点距離 px) か None(カメラが無い・平行投影)。
    焦点距離は「横 1920 px の絵」に揃えて測る(FAR_LOD_REF_WIDTH)。レンダの
    大きさで変えると、小さく試し撮りしたときと本番で塗りが変わり、240px の
    試験では 1m の箱の側面までまとまって角の線が消えた(t58)。
    カメラ(か親)にアニメーションか拘束があれば、シーンのフレーム範囲から
    位置を取る。近づく予定の物は、一番近づく位置で粗さを決める
    (STEP0 の位置だけで決めると、近づいたビルの窓が描かれないままになった)。
    """
    cam = scene.camera
    if cam is None or cam.type != 'CAMERA' or cam.data.type != 'PERSP':
        return None
    rx, ry = scene.render.resolution_x, scene.render.resolution_y
    fit = cam.data.sensor_fit
    if fit == 'VERTICAL':
        size, sensor = ry, cam.data.sensor_height
    elif fit == 'HORIZONTAL':
        size, sensor = rx, cam.data.sensor_width
    else:
        size, sensor = max(rx, ry), cam.data.sensor_width
    # 横 1920 に揃える(縦横比は保つ)
    size = size * FAR_LOD_REF_WIDTH / max(rx, 1)
    fpx = size * cam.data.lens / max(sensor, 1e-6)

    def moves(o):
        while o is not None:
            ad = o.animation_data
            if (ad is not None and (ad.action is not None or len(ad.drivers))) or len(o.constraints):
                return True
            o = o.parent
        return False

    if not moves(cam):
        return [tuple(cam.matrix_world.translation)], fpx
    f0, f1 = scene.frame_start, scene.frame_end
    keep = scene.frame_current
    n = max(1, min(FAR_LOD_FRAME_SAMPLES, f1 - f0 + 1))
    pos = []
    try:
        for k in range(n):
            f = int(round(f0 + (f1 - f0) * k / max(1, n - 1)))
            scene.frame_set(f)
            pos.append(tuple(cam.matrix_world.translation))
    finally:
        scene.frame_set(keep)
    return pos, fpx


def color_distance_rgb(rgb1, rgb2):
    """Return the Euclidean distance between two RGB tuples."""
    return math.sqrt(sum([(c1 - c2)**2 for c1, c2 in zip(rgb1, rgb2)]))

# かつてここに backup_and_replace_edge_smooth_with_freestyle_mark /
# restore_edge_smooth があった。use_edge_sharp を Freestyle マークで一時的に
# 上書きし、処理後に戻すという破壊的な作りで、復元漏れの温床でもあった。
# 実測で BlenderKit のメカ/機関車とも Freestyle マークは0本(誰も使って
# いない)。なお Blender 5.0 で edge.use_freestyle_mark という Python
# プロパティは削除されたが、これは属性API(mesh.attributes["freestyle_edge"])
# への移行であって、Freestyle 本体もエッジマークも現役である。
# アーティストの意図は「シャープ」で受け取る方式に統一し、島境界の判定も
# メッシュに書かずローカルな配列で持つようにしたため、置換も復元も不要。


class VCRunState:
    """_run() の結果受け皿。

    _run() は生成器で、本体は self._result にしか書かない。モーダルで
    駆動する側(STEP1 単体と STEP0)がそれを受け取るための最小の入れ物。
    オペレーター自身を渡す代わりにこれを使うことで、STEP0 からも同じ
    処理を回せる。
    """

    def __init__(self, quiet=False):
        self._result = {'FINISHED'}
        # モーダル駆動時は完了ポップアップを出さない。popup_menu を
        # タイマーイベント中に呼ぶのは不安定なうえ、STEP0 では直後に
        # STEP2/3 が続くため。代わりにステータスバーへ report する。
        self._quiet = quiet


def make_vertex_color_gen(context, quiet=False):
    """STEP1 の処理ジェネレーターと状態オブジェクトを作る。

    STEP0(auto_setup)が STEP1 と同じ進捗バーで駆動するための共有入口。
    """
    from . import undo_setup          # 「FreePencil を外す」ための元の値を控える
    undo_setup.snapshot(context)
    state = VCRunState(quiet=quiet)
    return LINK_MAKE_OT_FP._run(state, context), state


class FPProgressModalMixin:
    """STEP1 のジェネレーターをタイマーで1ステップずつ回し、ビューポート
    下部に進捗バーを描く共通処理(応答なし対策)。

    使う側は invoke() で _progress_start()、modal() で _progress_step()
    を呼ぶ。STEP1 単体(LINK_MAKE_OT_FP)と STEP0(auto_setup)で共有する。
    """

    _progress_label = "FreePencil"
    _timer = None
    _draw_handle = None
    _gen = None
    _state = None

    def _progress_start(self, context, gen, state):
        """最初の1ステップを消費し、タイマーと描画ハンドラを張る。

        戻り値 False は生成器が即終了した場合(検証エラー等。理由は
        state._result に入っている)。
        """
        self._gen, self._state = gen, state
        self._done, self._total, self._name = 0, 0, ""
        self._t0 = time.time()
        try:
            step = next(gen)
        except StopIteration:
            return False
        self._done, self._total, self._name = step
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.01, window=context.window)
        self._draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw_vc_progress, (self,), 'WINDOW', 'POST_PIXEL')
        self._update_status(context)
        return True

    def _progress_step(self, context):
        """1オブジェクト分進める。'RUNNING'/'DONE'/'ERROR' を返す。"""
        try:
            step = next(self._gen)
        except StopIteration:
            return 'DONE'
        except Exception as ex:
            # ここで捕まえないとタイマーと描画ハンドラが残り、進捗バーが
            # 画面に貼り付いたままモーダルも抜けられなくなる
            logger.exception("FreePencil: auto vertex color failed")
            self._progress_cancel(context)
            self.report({'ERROR'}, f"FreePencil: {ex}")
            return 'ERROR'
        self._done, self._total, self._name = step
        self._update_status(context)
        return 'RUNNING'

    def _progress_cancel(self, context):
        """中断時の後片付け。

        島境界の判定はローカルな配列で持ちメッシュを書き換えないため、
        途中で止めてもジオメトリ側に戻すものは無い。編集モードのまま
        止まりうる点だけ面倒を見る。
        """
        self._progress_end(context)
        # オブジェクト内フェーズで中断すると編集モードのまま止まりうるので
        # オブジェクトモードへ戻す(戻さないと以降の操作が噛み合わない)
        try:
            if context.object is not None and context.object.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

    def _progress_end(self, context):
        wm = context.window_manager
        if self._timer is not None:
            wm.event_timer_remove(self._timer)
            self._timer = None
        if self._draw_handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._draw_handle, 'WINDOW')
            self._draw_handle = None
        context.workspace.status_text_set(None)
        self._redraw(context)

    def _update_status(self, context):
        pct = 100.0 * self._done / max(1, self._total)
        context.workspace.status_text_set(
            f"{self._progress_label} {self._done}/{self._total} ({pct:.0f}%) - "
            f"{self._name}  [ESC: cancel]")
        self._redraw(context)

    def _redraw(self, context):
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


class LINK_MAKE_OT_FP(FPProgressModalMixin, bpy.types.Operator):
    """Operator that separates meshes into islands and applies vertex colors."""
    bl_idname = "freepencil.auto_vertex_color"
    bl_label = "Auto Vertex Color (FreePencil)"
    bl_description = "Automatically separate and paint vertex colors on selected mesh objects"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def description(cls, context, properties):
        return bpy.app.translations.pgettext("Separate Paint Vertex Colors")

    def _run(self, context):
        """本体処理のジェネレーター。

        1オブジェクト処理するごとに (完了数, 総数, 次のオブジェクト名) を
        yield する。execute() は全消費(同期)、invoke() はモーダルの
        タイマーで1ステップずつ消費し、UIを固まらせない(応答なし対策)。
        結果は self._result に入れる。
        """
        self._result = {'FINISHED'}
        time_start = time.time()
        scene = context.scene
        active_obj = context.active_object
        _RIGID_CACHE.clear()          # ウェイトを直したあとの塗り直しで古い判定を使わない

        # --- マスターシード決定（再現性のため）---
        # ランダム指定時は新しいシードを生成し、実際に使った値を
        # fp_color_seed に書き戻して UI から確認・固定できるようにする。
        if getattr(scene, "fp_use_random_seed", True):
            master_operation_seed_int = random.randint(0, SEED_MAX)
            try:
                scene.fp_color_seed = master_operation_seed_int
            except Exception:
                pass
        else:
            master_operation_seed_int = int(getattr(scene, "fp_color_seed", 0)) & 0xFFFFFFFF

        if not context.selected_objects:
            utils.show_message_box(bpy.app.translations.pgettext("Select a mesh."), icon='ERROR')
            self._result = {'CANCELLED'}
            return

        selected_mesh_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not selected_mesh_objects:
            utils.show_message_box(bpy.app.translations.pgettext("No mesh objects selected."), icon='ERROR')
            self._result = {'CANCELLED'}
            return

        # リンク複製(同じメッシュ実体を共有するオブジェクト)は代表1体だけ
        # 塗る。塗り分けはメッシュデータに書き込むので、代表を塗れば残りにも
        # そのまま反映される。
        #
        # これが無いと同じメッシュを人数分やり直すことになる。実測(デパート
        # シーン): 1,186オブジェクト/159メッシュ、オブジェクト合計 711M面 に
        # 対しメッシュ実体は 89M面 ——8倍の無駄。しかもシードは
        # オブジェクト名から作るため、共有メッシュは処理順で結果が変わる
        # (最後に塗ったオブジェクトが勝つ)という非決定性まで抱えていた。
        #
        # 代表は名前順の先頭に固定するので、選択順に依存しない。
        by_mesh = {}
        for obj in selected_mesh_objects:
            cur = by_mesh.get(obj.data.name)
            if cur is None or obj.name < cur.name:
                by_mesh[obj.data.name] = obj
        shared_skipped = len(selected_mesh_objects) - len(by_mesh)
        if shared_skipped:
            selected_mesh_objects = [by_mesh[k] for k in sorted(by_mesh)]
            print(f"[FreePencil] linked duplicates: {shared_skipped} objects "
                  f"share data with others; painting "
                  f"{len(selected_mesh_objects)} unique meshes")

        # 進捗はビューポートの進捗バー(_draw_vc_progress)が担当する。
        # 以前あった wm.progress_begin/update/end のマウスカーソル横の
        # 数字表示は、バーが無かった頃の簡易表示なので廃止した。
        n_objs = len(selected_mesh_objects)

        # 最初の1回はここで必ず制御を返す。以降の準備処理(Freestyleマーク
        # 置換・ルースパーツ数え上げ)だけで数秒かかるモデルがあり、ここで
        # 返さないとバーが出る前に「応答なし」になる(C62機関車で実測6.3秒)。
        yield 0.0, n_objs, bpy.app.translations.pgettext("Preparing")

        default_noise_scale = 1.0
        color_noise_scale = getattr(scene, "fp_color_noise_scale", default_noise_scale)
        min_neighbor_color_distance = getattr(scene, "fp_min_neighbor_color_distance", 0.5)
        max_color_generation_retries = getattr(scene, "fp_max_color_retries", 30)
        ridge_amount = getattr(scene, "fp_ridge_amount", 0.0)
        ridge_radius = getattr(scene, "fp_ridge_radius", 0.08)
        angle_threshold_rad = math.radians(scene.fp_sharp_edges)
        clear_sharps_option = scene.fp_sharp_clear # UIの「シャープを削除」オプション
        # UVシーム/マテリアル境界を島境界として使う(アーティストの意図情報)
        seam_boundaries_option = getattr(scene, "fp_seam_boundaries", False)

        # パーツ(オブジェクト)ごとの mecha トーン分け。
        # 髪と顔のような接する別オブジェクトは、メッシュ辺を共有しないため
        # 島の隣接グラフでは「隣」にならず、同じ明度帯の色が付くと境界線が
        # 出ない(リグ付きでは bone_color も head ボーン同士で同色)。
        # ボーン時の塗り分けはほぼパーツ単位=mecha がパーツ境界線を担い、
        # bone は元のソフトブレンドのままノードで合成する、が正しい分担。
        # 近接オブジェクト同士が異なる明度クラスになるよう近接グラフを
        # 彩色し、mecha パレット全体をパーツごとに持ち上げる。
        part_tint = {}
        if (getattr(scene, "fp_part_tint", True)
                and len(selected_mesh_objects) > 1):
            from mathutils import Vector as _V
            bounds = []
            for o in selected_mesh_objects:
                pts = [o.matrix_world @ _V(c) for c in o.bound_box]
                mn = _V((min(p[i] for p in pts) for i in range(3)))
                mx = _V((max(p[i] for p in pts) for i in range(3)))
                bounds.append((mn, mx))
            scene_diag = max(
                max(mx[i] for _, mx in bounds) - min(mn[i] for mn, _ in bounds)
                for i in range(3))
            tol = max(scene_diag, 1e-3) * 0.02
            prox = [set() for _ in selected_mesh_objects]
            for i in range(len(bounds)):
                for j in range(i + 1, len(bounds)):
                    gap = 0.0
                    for ax in range(3):
                        d = max(bounds[i][0][ax] - bounds[j][1][ax],
                                bounds[j][0][ax] - bounds[i][1][ax], 0.0)
                        gap = max(gap, d)
                    if gap <= tol:
                        prox[i].add(j)
                        prox[j].add(i)
            part_classes = utils.color_graph_greedy(prox)
            for o, cls in zip(selected_mesh_objects, part_classes):
                # 明度そのものではなくクラス番号を持つ。窓の作り方は
                # utils.part_luma_window に一本化してある
                part_tint[o.name] = cls % utils.PART_TINT_STEPS

        # 選択全体のルースパーツ数(自動しきい値の判定に使用)。
        # パーツの多い組立モデル(骨格標本など)はシルエット/深度線が
        # 十分あるので、滑面への人工分割線を出さない
        many_loose_parts = False
        if getattr(scene, "fp_sharp_auto", False):
            # 高密度メッシュだと単体で数秒かかる(C62で3.8秒)
            yield 0.0, n_objs, bpy.app.translations.pgettext("Analyzing parts")
            # 見たいのは「8個以上あるか」だけ。
            # オブジェクトが8個以上あれば、それぞれ最低1つはルースパーツを
            # 持つので、数えるまでもなく成立する。デパートのような
            # 大規模シーンではここで即決まる
            if len(selected_mesh_objects) >= 8:
                many_loose_parts = True
            else:
                # 小さい方から数えて、8に届いた時点でやめる。最後まで
                # 数えると 320万面のメッシュで 5.6 秒かかっていた(実測)
                total_parts = 0
                for o in sorted(selected_mesh_objects,
                                key=lambda x: len(x.data.polygons)):
                    total_parts += utils.count_loose_parts(
                        o.data, stop_at=8 - total_parts,
                        rep=mesh_islands.split_seam_rep(o.data))
                    if total_parts >= 8:
                        break
                many_loose_parts = total_parts >= 8

        # 遠い区画をまとめる(手描き背景、既定 0 = 通らない)。カメラは1回だけ見る
        # 精密・キャラでも、画面で小さすぎる区画だけはまとめる(PRECISE_TINY_PX)
        far_lod_px = max(float(getattr(scene, "fp_far_lod_px", 0.0)), PRECISE_TINY_PX)
        far_cams = far_lod_cameras(scene) if far_lod_px > 0.0 else None

        # オブジェクト内フェーズの刻みは編集モード中に制御を返すため、その
        # たびにビューポートが編集モード状態で再描画され、パーツ数が多いと
        # 画面が激しく点滅する。パーツが多ければオブジェクト単位の刻み
        # (ループ先頭・オブジェクトモード中)だけで十分バーが進むので、
        # 細かい刻みは単一〜少数メッシュのモデルに限る。
        fine_progress = n_objs < 8
        # 角度が一様で人工分割をやめた物(卵)。STEP0 が奥行きの線で境目を出す(auto_setup)
        uniform_objs = []

        for i, obj in enumerate(selected_mesh_objects):
            # モーダル側はここで一旦制御を返す(=イベントループが回り
            # UIが応答し続ける)。i 個完了済み、これから obj を処理する。
            # ここはまだオブジェクトモードなので再描画しても点滅しない
            yield i, n_objs, obj.name
            context.view_layer.objects.active = obj
            # 決定論的ハッシュ（同じオブジェクト名なら常に同じシード）
            obj_instance_seed_int = stable_hash_u32(obj.name)

            # --- マテリアル & 頂点カラーレイヤー準備 ---
            if not obj.active_material:
                if not obj.material_slots: obj.data.materials.append(None)
                mat = bpy.data.materials.get(DEFAULT_MATERIAL_NAME)
                if not mat:
                    mat = bpy.data.materials.new(name=DEFAULT_MATERIAL_NAME)
                    mat.use_nodes = True
                if obj.material_slots and obj.active_material_index < len(obj.material_slots):
                     obj.material_slots[obj.active_material_index].material = mat

            # 材質が名前の空の色ノードで元の頂点の色を読んでいたら、その名前で固定する
            # (下で mecha_color をレンダー用にすると、材質がまだらに化ける)
            from . import undo_setup
            if undo_setup.pin_color_nodes(obj):
                print(f"[FreePencil] '{obj.name}': 材質の頂点の色ノードを元の色に固定")
            utils.ensure_vertex_color(obj, VCOL_LAYER_MASK, (0.0, 0.0, 0.0, 1.0))
            utils.ensure_vertex_color(obj, VCOL_LAYER_LINE, (0.0, 0.0, 0.0, 1.0))
            bone_color_index = utils.ensure_vertex_color(obj, VCOL_LAYER_BONE, (0.0, 0.0, 0.0, 1.0))
            mecha_color_index = utils.ensure_vertex_color(obj, VCOL_LAYER_MECHA, (1.0, 1.0, 1.0, 1.0))

            original_mode = obj.mode
            # かつてここに「四角面化(This to Quads)」があったが v2.6.1 で
            # 廃止した。線画がほぼ変わらないのに、編集モードへ入るため
            # 高い代償を払っていた。実測(8モデル):
            #   8モデル中6モデルで線の量が1ビットも変わらず、時間だけ増加
            #   (A320 0.6->7.1秒、アウディ 6.5->22.9秒)
            #   1000万面のメッシュでは 31秒 / +13.8GB、しかも面数が
            #   10,594,485 -> 9,040,042 に恒久的に書き換わる
            # 古いファイルに設定が残っていても読まないので無視される。

            # 島の抽出は numpy 配列でやる(mesh_islands)。以前は bmesh を
            # 作って辺と面を Python で1つずつ触っていたが、それが速度と
            # メモリの壁だった。実測(1000万面のメッシュ1個):
            #   bmesh.from_mesh だけで +5.65 GB、BMFace ラッパで +0.85 GB、
            #   境界判定と島検出に 31.6 秒。
            # 配列版は同じ島を出しつつ 12.2 秒・数百MBで済む。
            # 出力が変わらないことは mesh_islands の docstring 参照。
            topo = mesh_islands.MeshTopology(obj.data)
            face_count = topo.n_faces
            if topo.n_stitched:
                # AI が作った 3D の UV の切れ目(mesh_islands.SPLIT_STITCH_DEG)
                print(f"[FreePencil] '{obj.name}': 面の切れ目 {topo.n_stitched} 本を縫った")
            if face_count == 0:
                if obj.mode != original_mode:
                    bpy.ops.object.mode_set(mode=original_mode)
                continue

            # キャラ(リグ付き)は手描き系の仕上がりでは「ざっくり塗り」にする。
            # 角度・UV シームでは分けず、つながったメッシュ x マテリアルごとに
            # 1色。キャラの線は、このパーツの境目とボーンの塗り(ウェイトで
            # ぼかした bone_color)で出す。角度で細かく分けると、腕や髪が線で
            # 黒く潰れた(ジョギングの動画で実測)
            #
            # 塗り方はオブジェクトごとに上書きできる(fp_paint_as)。自動のときは
            # リグの付き方で見分ける: ボーン1本に固定された頂点が多い物は
            # ロボットとしてメカの塗り(精密と同じ角度の分け方)にする。
            # リグ付きのザクがざっくり塗りになり、胴体が1色でパネルの線が
            # 消えた(棲み分けの試験、dev/note_assets/out/separation)
            rig_coarse = (bool(scene.get("fp_rig_coarse"))
                          and paint_as(obj) == 'CHARA')
            try:
                # --- 0. 自動しきい値: 二面角の分布からモデル系統を判定 ---
                effective_threshold_rad = angle_threshold_rad
                auto_merge_pct = None
                # サブディビジョンが生きていると、STEP1 が見ているのは
                # なめらかな形を作るための粗いケージ。塗った色はサブディブ
                # で補間されてから描かれる
                has_subsurf = any(m.type == 'SUBSURF' and m.show_viewport
                                  for m in obj.modifiers)
                if getattr(scene, "fp_sharp_auto", False) and not rig_coarse:
                    angle_samples = topo.angle_samples_deg()
                    # リグ付きモデルは bone_color が線の主役なので保守的に
                    has_arm = any(m.type == 'ARMATURE' and m.object
                                  for m in obj.modifiers)
                    auto_info = {}
                    auto_deg, auto_merge_pct = utils.choose_auto_threshold(
                        angle_samples, has_armature=has_arm,
                        many_parts=many_loose_parts, has_subsurf=has_subsurf,
                        split_floor=getattr(scene, "fp_auto_split_floor", None),
                        info=auto_info)
                    if auto_info.get("uniform"):
                        uniform_objs.append(obj.name)
                    effective_threshold_rad = math.radians(auto_deg)
                    print(f"[FreePencil] auto sharp threshold for '{obj.name}': "
                          f"{auto_deg:.1f} deg"
                          + (f", merge {auto_merge_pct}%" if auto_merge_pct else ""))

                # --- 1. 島境界エッジの判定 ---
                # メッシュには書き込まない。以前は edge.smooth を書き換えて
                # BFS に渡し、最後に元へ戻していたが、その一時改変が破壊的で
                # 復元漏れの温床だった。アーティストの意図は Freestyle
                # マークではなく「シャープ」で受け取る(実測でマークは
                # 使われておらず、5.x では属性ごと消えているため)。
                if getattr(scene, "fp_sharp_auto", False) and not rig_coarse:
                    # 自動のときは切った結果を見て閾値を詰める。
                    # 分布から系統を当てる方式だけでは、実測で 39モデル中
                    # 9モデルが網目状に砕けていた
                    max_ratio = mesh_islands.MAX_ISLANDS_PER_FACE
                    # 手描き背景の1回目(メカの塗り = 細い線用)は抑えない。
                    # 抑えるのは手描きの塗りの役目で、メカの塗りは線を全部
                    # 出す。上限 0.08 島/面 は箱を結合した低ポリの建物で
                    # 「切れすぎ」と誤判定し、179度まで上げて角の線を消した
                    # (町の家: 137面に箱23個、上限10島)
                    if scene.get("fp_fine_pass"):
                        max_ratio = 1.0
                    used_deg, tries, ratio = mesh_islands.resolve_threshold(
                        topo, math.degrees(effective_threshold_rad),
                        seam_boundaries_option, clear_sharps_option,
                        max_ratio=max_ratio,
                        max_deg=float(scene.get("fp_raise_cap", 179.0)))
                    if tries > 1:
                        print(f"[FreePencil] '{obj.name}': island ratio too "
                              f"high, raised to {used_deg:.1f} deg "
                              f"({tries} tries, {ratio:.4f} islands/face)")
                    effective_threshold_rad = math.radians(used_deg)

                    # 上げるだけでは、多数派の角度に隠れた少数派を拾えない。
                    # 実測(sample2の面取りした箱、10面): 二面角は
                    # 90度x8 / 79度x4 / 64度x4 / 25.6度x4 で、p95 が 90度に
                    # なるため 60度が選ばれ、緩い斜面の 25.6度 が消えていた。
                    # 下げても島が増えすぎないなら下げる
                    #
                    # リグ付きと多パーツ組立は対象外。どちらも「人工分割を
                    # しない」ことが既存の設計で、線の主役はボーン境界と
                    # パーツ間のシルエットにある。ここを下げると、そのために
                    # 置いたガードを素通しして細片が出る(t20/t24/t25 が落ちた)
                    if not has_arm and not many_loose_parts:
                        n_parts = utils.count_loose_parts(obj.data, rep=topo.split_rep)
                        low_deg, low_n = mesh_islands.lower_threshold_for_detail(
                            topo, n_parts, seam_boundaries_option,
                            clear_sharps_option)
                        if low_deg is not None and low_deg < used_deg - 0.5:
                            print(f"[FreePencil] '{obj.name}': lowered "
                                  f"{used_deg:.1f} -> {low_deg:.1f} deg "
                                  f"({low_n} islands / {n_parts} parts)")
                            used_deg = low_deg
                            effective_threshold_rad = math.radians(used_deg)
                        topo.mark_boundaries(effective_threshold_rad,
                                             seam_boundaries_option,
                                             clear_sharps_option)
                        topo.build_islands()
                elif rig_coarse:
                    # ざっくり塗り: つながったパーツ x マテリアルごとに1色。
                    # ただし小さいパーツ(面積が全体の COARSE_SMALL_PART 未満)は
                    # マテリアルごとに1つへまとめる。髪はカードが数百枚の別
                    # パーツで、1枚ずつ色が変わると線だらけになった(anime-girl
                    # の髪 568島)。マテリアル単位にまとめ切ると、服が1マテリアル
                    # のモデルでスカートとブラウスの境目まで消えた
                    topo.mark_boundaries(math.pi, False, True)
                    sel = topo.two_face
                    topo.is_boundary[sel] |= (topo.material[topo.face_a[sel]]
                                              != topo.material[topo.face_b[sel]])
                    topo.build_islands()
                    area = np.asarray(topo.area, dtype=np.float64)
                    total = max(float(area.sum()), 1e-12)
                    mats = np.asarray(topo.material)
                    keep, small = [], {}
                    for isl in topo.islands:
                        if area[isl].sum() / total >= COARSE_SMALL_PART:
                            keep.append(isl)
                        else:
                            small.setdefault(int(mats[isl[0]]), []).append(isl)
                    keep += [np.concatenate(v).astype(np.int32)
                             for v in small.values()]
                    topo.set_islands(keep)
                    print(f"[FreePencil] '{obj.name}': キャラ(リグ付き)は"
                          f"ざっくり塗り {len(topo.islands)}島")
                else:
                    topo.mark_boundaries(effective_threshold_rad,
                                         seam_boundaries_option,
                                         clear_sharps_option)
                    topo.build_islands()

                # --- 2. 島の検出 ---
                # 以降のフェーズは単一の高密度メッシュだと各数秒〜十数秒
                # かかる。オブジェクト単位の刻みだけだと1メッシュのモデルで
                # バーが 0/1 のまま固まるため、フェーズ境界でも制御を返す。
                if fine_progress:
                    yield i + 0.15, n_objs, f"{obj.name} - " + \
                        bpy.app.translations.pgettext("Detecting islands")
                islands = topo.islands   # 上で切り終えている

                # --- 2.5 微小島のマージ ---
                # 面積がメッシュ全体の一定割合未満の島は線として視認できず、
                # 色制約違反・線の断片化・処理時間を悪化させるだけなので併合する
                min_island_area_pct = getattr(scene, "fp_min_island_area_pct", 0.0)
                if auto_merge_pct is not None:
                    # 散乱ジオメトリ判定時は強めのマージを適用
                    min_island_area_pct = max(min_island_area_pct, auto_merge_pct)
                if min_island_area_pct > 0.0 and len(islands) > 1:
                    if fine_progress:
                        yield i + 0.35, n_objs, f"{obj.name} - " + \
                            bpy.app.translations.pgettext("Merging small islands")
                    mesh_islands.merge_small_islands(topo, min_island_area_pct)
                    islands = topo.islands

                # --- 2.6 形のある葉(ヤシの小葉)を 1 色に(v3.0) ---
                # 小葉 1 枚ごとに太い輪郭が付き、茂みが黒く潰れた(mesh_islands.merge_leaflets)。
                # 房分け(2.7、手描き背景)を使うときは房分けに任せる
                k_clumps = int(getattr(scene, "fp_foliage_clumps", 0))
                if k_clumps <= 0 and len(islands) > 1 and not rig_coarse:
                    from .leaf_clump import LEAF_RE
                    leaf_mats = {i for i, s in enumerate(obj.material_slots)
                                 if s.material and LEAF_RE.search(s.material.name)}
                    n_leaf = mesh_islands.merge_leaflets(topo, leaf_mats)
                    if n_leaf:
                        islands = topo.islands
                        print(f"[FreePencil] '{obj.name}': 葉の小さい部品 "
                              f"{n_leaf}島を 1 色に")

                # --- 2.7 葉を房にまとめる(手描き背景モードだけ) ---
                # 既定 0 = この分岐を通らない。精密・キャラの経路は不変
                if k_clumps > 0 and len(islands) > 1 and not rig_coarse:
                    n_before = len(islands)
                    n_clumps = mesh_islands.clump_small_islands(
                        topo, k_clumps, master_operation_seed_int)
                    if n_clumps:
                        islands = topo.islands
                        print(f"[FreePencil] '{obj.name}': 葉を房に "
                              f"{n_before}島 -> {len(islands)}島(房{n_clumps})")

                # --- 2.8 遠い区画をまとめる(手描き背景、v2.8.3) ---
                # 房の後に置く: 手前の木の房は崩さず、遠い木の房だけをまとめる。
                # 同じメッシュを使う物(並木など)は、カメラに近い数本で測り、
                # 一番大きく写る値を使う(手前の物を粗くしない)
                # 精密の下限(PRECISE_TINY_PX)だけのときは、配列で並べる物を外す。元の 1 枚が
                # 画面で小さくても、並べた全体は大きい(吊り橋の路面は 2m の板を 85 枚並べていて、
                # 板の中の帯がまとまって路面の線が消えた)
                tiny_only = far_lod_px <= PRECISE_TINY_PX
                arrayed = tiny_only and any(m.type == 'ARRAY' for m in obj.modifiers)
                if far_cams is not None and len(islands) > 1 and not rig_coarse and not arrayed:
                    users = [o for o in context.scene.objects
                             if o.type == 'MESH' and o.data == obj.data
                             and not o.hide_render] or [obj]
                    cams_np = np.asarray(far_cams[0], dtype=np.float64)

                    def _near(o):
                        c = np.asarray(o.matrix_world.translation, dtype=np.float64)
                        return float(np.min(np.linalg.norm(cams_np - c, axis=1)))
                    users.sort(key=_near)
                    mats = [np.asarray(o.matrix_world, dtype=np.float64)
                            for o in users[:mesh_islands.FAR_LOD_INSTANCES]]
                    face_px, face_scale = mesh_islands.face_screen_area(
                        topo, obj.data, mats, far_cams[0], far_cams[1], with_scale=True)
                    # 精密の下限(PRECISE_TINY_PX)だけのときは、細長い区画を残す
                    length_px = None
                    if tiny_only:
                        length_px = mesh_islands.island_screen_length(
                            topo, obj.data, face_scale, matrix=mats[0])
                    n_before = len(islands)
                    n_far = mesh_islands.merge_far_islands(
                        topo, face_px, far_lod_px, matrix=mats[0],
                        length_px=length_px, keep_len_px=PRECISE_TINY_LEN_PX)
                    if n_far:
                        islands = topo.islands
                        print(f"[FreePencil] '{obj.name}': 画面で小さい区画をまとめる "
                              f"({far_lod_px:.0f}px) {n_before}島 -> {len(islands)}島")

                # --- 3. 島の隣接グラフ彩色 + パレット配色 ---
                # 乱数リトライで隣接色距離を満たそうとする方式をやめ、
                # 隣接グラフをグリーディ彩色して「相互距離を最大化した
                # 固定パレット」をクラスに割り当てる。隣接島は必ず別クラス
                # になるため、パレット最小距離 >= しきい値 なら違反は
                # 構造的にゼロ。シードはパレット開始点とジッターに効く。
                if fine_progress:
                    yield i + 0.5, n_objs, f"{obj.name} - " + \
                        bpy.app.translations.pgettext("Coloring adjacency graph")
                # 島の切り方と隣接の見方が同じ基準でないと、隣り合う島が
                # 「隣接なし」と判定されて同じ色クラスになり境界線が消える。
                # だから隣接も島境界エッジ越しだけを見る
                island_neighbors = topo.island_adjacency(boundary_only=True)
                # 辺で繋がっていない島(別のルースパーツ)は上の判定では
                # 「隣接なし」になり、貪欲彩色が全部を同じクラスに置く。
                # 画面では重なっているのに境界の色差がゼロになるので、
                # 近接しているルースパーツ同士を隣として足す
                n_prox = mesh_islands.add_loose_part_proximity(
                    topo, obj.data, island_neighbors)
                island_classes = utils.color_graph_greedy(island_neighbors)
                n_classes = (max(island_classes) + 1) if island_classes else 1
                # パーツ・トーン分け: 明度「窓」をパーツごとにずらして
                # パレットを生成する。生成後にオフセットを足す方式は
                # クランプが距離保証を壊す(min距離違反、実測)ため、
                # 制約はパレット生成器の中で扱う。
                # 窓は全パーツで同じ幅にし、位置だけずらす
                # (utils.part_luma_window に理由と実測値)。
                obj_part_class = part_tint.get(obj.name, 0)
                luma_lo, luma_hi = utils.part_luma_window(obj_part_class)
                # 彩色数ぶんしか色を作らないと、島同士がメッシュで繋がって
                # いない形(文字など)で色が足りない。実測: "Text" は124島でも
                # 彩色数2、自動しきい値だと1で、全部が同じ黄色になっていた。
                # 契約(距離・輝度差)を守れる範囲で色数を増やす
                palette, palette_min_dist, palette_min_luma = \
                    utils.palette_for_diversity(
                        min_neighbor_color_distance,
                        min(len(islands), PALETTE_SIZE),
                        master_operation_seed_int, min_k=n_classes,
                        luma_lo=luma_lo, luma_hi=luma_hi)
                # 従来の割り当てを出発点に、制約を壊さない範囲でだけ散らす
                island_classes, n_used = utils.diversify_island_colors(
                    island_neighbors, island_classes, palette,
                    min_neighbor_color_distance)
                if len(palette) > n_classes or n_prox:
                    print(f"[FreePencil] '{obj.name}': 島{len(islands)} "
                          f"近接隣接{n_prox} "
                          f"彩色数{n_classes} -> パレット{len(palette)} "
                          f"使った色{n_used}")

                # 隣接距離と輝度差(=線の検出性)の保証を壊さない範囲で
                # 島ごとに色を揺らす
                if palette_min_dist == float("inf"):
                    jitter_r = 0.15 * color_noise_scale
                else:
                    jitter_r = max(0.0, (palette_min_dist - min_neighbor_color_distance) / 2.0)
                    jitter_r = min(jitter_r, 0.15 * color_noise_scale,
                                   0.25 * palette_min_luma)

                if fine_progress:
                    yield i + 0.6, n_objs, f"{obj.name} - " + \
                        bpy.app.translations.pgettext("Assigning colors")
                # 面ごとの最終色。既定は白(どの島にも入らない面は無いが、
                # 旧実装と同じ初期値にしておく)
                final_face_colors_r = np.ones(face_count, dtype=np.float32)
                final_face_colors_g = np.ones(face_count, dtype=np.float32)
                final_face_colors_b = np.ones(face_count, dtype=np.float32)

                for current_island_id, current_island_faces_list in enumerate(islands):
                        # 代表面は島の最小面番号。polygon.center は
                        # BMFace.calc_center_median() とビット一致する(実測)
                        rep = int(current_island_faces_list[0])
                        island_rep_coord = obj.matrix_world @ Vector(
                            topo.center[rep])
                        base_r, base_g, base_b = palette[island_classes[current_island_id]]

                        j_seed = (obj_instance_seed_int + current_island_id * 131 + 10131) & 0xFFFFFFFF
                        jx = get_pseudo_random_float_from_vec(island_rep_coord.x, island_rep_coord.y, island_rep_coord.z, master_operation_seed_int, j_seed, color_noise_scale) - 0.5
                        jy = get_pseudo_random_float_from_vec(island_rep_coord.x, island_rep_coord.y, island_rep_coord.z, master_operation_seed_int, (j_seed + 1) & 0xFFFFFFFF, color_noise_scale) - 0.5
                        jz = get_pseudo_random_float_from_vec(island_rep_coord.x, island_rep_coord.y, island_rep_coord.z, master_operation_seed_int, (j_seed + 2) & 0xFFFFFFFF, color_noise_scale) - 0.5

                        # RGB立方体の壁までの距離内に収める(クランプで距離保証を壊さない)
                        wall = min(base_r, base_g, base_b, 1.0 - base_r, 1.0 - base_g, 1.0 - base_b)
                        # 黒(背景)との距離0.5を割るとシルエット線が薄くなるため制限
                        to_black = (base_r * base_r + base_g * base_g + base_b * base_b) ** 0.5
                        r_i = max(0.0, min(jitter_r, wall - 0.005, to_black - 0.5))
                        f_scale = r_i / 0.87  # |(jx,jy,jz)| <= sqrt(3)/2 = 0.87

                        best_r_island = base_r + jx * f_scale
                        best_g_island = base_g + jy * f_scale
                        best_b_island = base_b + jz * f_scale

                        final_face_colors_r[current_island_faces_list] = best_r_island
                        final_face_colors_g[current_island_faces_list] = best_g_island
                        final_face_colors_b[current_island_faces_list] = best_b_island
            finally:
                # bmesh を作らなくなったので解放するものは無い。
                # topo は普通の numpy 配列なので GC に任せる
                pass

            # 稜線の起伏。島は面の縁でしか色を変えられないので、なめらかな
            # 出っ張り(まぶたの上など)に線が出せない。法線から「大きな向き」
            # を引いた残りを島の中に薄く足して、そこだけ色を動かす。
            # 平らな面では残差がほぼゼロなので、メカには何も足されない。
            # STEP0 のカメラで小さく写る細かいくぼみの点は消す(RIDGE_SPOT_PX)
            ridge_offset = None
            if ridge_amount > 0.0 and not rig_coarse:
                spot = {}
                if far_cams is not None:
                    spot = dict(matrix=np.asarray(obj.matrix_world, dtype=np.float64),
                                cam_positions=far_cams[0], fpx=far_cams[1])
                got = mesh_islands.ridge_residual(obj.data, ridge_radius,
                                                  rep=topo.split_rep, **spot)
                if got is not None:
                    d, n_iter = got
                    ridge_offset = d * ridge_amount
                    print(f"[FreePencil] '{obj.name}': 稜線の起伏 "
                          f"{ridge_amount:.2f} 距離{ridge_radius:.3f} "
                          f"(均し{n_iter}回) 最大ズレ"
                          f"{float(np.abs(ridge_offset).max()):.3f}")

            if obj.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
            yield i + 0.85, n_objs, f"{obj.name} - " + \
                bpy.app.translations.pgettext("Writing vertex colors")
            utils.apply_face_colors(obj, mecha_color_index, final_face_colors_r, final_face_colors_g, final_face_colors_b, ridge_offset)

            # --- Bone color generation ---
            armature_mod = next((m for m in obj.modifiers
                                 if m.type == 'ARMATURE' and m.show_viewport and m.object), None)
            verts = obj.data.vertices
            if armature_mod:
                arm_obj = armature_mod.object
                mode = getattr(context.scene, "fp_bone_grouping_mode", "basename")
                group_colors = {}

                def normalize_name(name: str) -> str:
                    if mode == 'exact':
                        return name
                    elif mode == 'basename':
                        # 末尾の .001 だけ落とす（.L/.R は維持）
                        return re.sub(r'\.\d+$', '', name)
                    else:  # 'stripdigits'
                        # 末尾の数字を落としつつ、.L/.R は残す
                        # 例: pointer1.L -> pointer.L,  pointer2 -> pointer,  pointer.003.R -> pointer.R
                        side = ''
                        if name.endswith('.L') or name.endswith('.R'):
                            side = name[-2:]
                            base = name[:-2]
                        else:
                            base = name
                        base = re.sub(r'\.\d+$', '', base)  # ".001" を除去
                        base = re.sub(r'\d+$', '', base)    # 末尾の数字を除去
                        return base + side

                # 比較も同じ規則で正規化してから行う（.001 などを正しく拾う）
                def norm(n: str) -> str:
                    return normalize_name(n) if mode != 'exact' else n
                normalized_bone_names = {norm(b.name) for b in arm_obj.data.bones}

                # 元実装(ウェイト加重平均)。ボーン塗りは柔らかいブレンドが正:
                # 支配ボーンによる離散塗り分け+境界線化の実験は 2026-07-17 に
                # ユーザー判断で差し戻した(切れ目状の線は不要、元が良い)。
                group_base_name = {}
                hard_lower = {s.strip().lower() for s in
                              getattr(scene, "fp_bone_hard_names", "").split(",") if s.strip()}
                # 顔のボーンは頭の色(硬境界に挙げたボーンは自分の色のまま)
                bone_vg = {vg.index: norm(vg.name) for vg in obj.vertex_groups
                           if norm(vg.name) in normalized_bone_names}
                fam_names, head_name = head_family(arm_obj.data.bones, norm, set(bone_vg.values()))
                fam_names = {k for k in fam_names if k.lower() not in hard_lower}
                fam_idx = {i for i, nm in bone_vg.items() if nm in fam_names}
                face = {}
                if fam_idx:
                    target = (head_name if head_name in bone_vg.values()
                              else face_target(obj, verts, fam_idx, set(bone_vg), bone_vg))
                    face = {bone_vg[i]: target for i in fam_idx}
                    print(f"[FreePencil] '{obj.name}': 顔のボーン {len(face)} 本を {target} の色に")
                for vg in obj.vertex_groups:
                    if norm(vg.name) in normalized_bone_names:
                        base = norm(vg.name)
                        group_base_name[vg.index] = base
                        h = int(hashlib.sha1(face.get(base, base).encode('utf8')).hexdigest(), 16)
                        r = ((h >> 0) & 0xFF) % 45 + 16
                        g = ((h >> 8) & 0xFF) % 45 + 16
                        b = ((h >> 16) & 0xFF) % 45 + 16
                        group_colors[vg.index] = (r / 100.0, g / 100.0, b / 100.0)

                # 硬境界ボーン(顎下ラインなど): ウェイトがなだらかだと色も
                # 階調になりエッジ検出に掛からない(=線が出ない)ため、
                # ここに列挙したボーンが関与する頂点はブレンドせず支配ボーンの
                # 純色で塗る。支配の切り替わり(例: head/neck)がステップになり
                # 線として検出される。既定は空(挙動不変)。
                hard_names = {s.strip().lower() for s in
                              getattr(scene, "fp_bone_hard_names", "").split(",")
                              if s.strip()}

                vertex_colors = [(1.0, 1.0, 1.0)] * len(verts)
                hard_mask = np.zeros(len(verts), dtype=bool)
                for v in verts:
                    accum = [0.0, 0.0, 0.0]
                    total = 0.0
                    best_g, best_w = None, 0.0
                    hard_touch = False
                    for g in v.groups:
                        if g.group in group_colors:
                            col = group_colors[g.group]
                            w = g.weight
                            accum[0] += col[0] * w
                            accum[1] += col[1] * w
                            accum[2] += col[2] * w
                            total += w
                            if w > best_w:
                                best_w, best_g = w, g.group
                            if (hard_names and w > 0.001
                                    and group_base_name[g.group].lower() in hard_names):
                                hard_touch = True
                    if hard_touch and best_g is not None:
                        hard_mask[v.index] = True
                        c = group_colors[best_g]
                        c = [min(1.0, c[0] + 0.1), min(1.0, c[1] + 0.1),
                             min(1.0, c[2] + 0.1)]
                    elif total > 0.0:
                        c = [min(1.0, (accum[0] / total) + 0.1),
                             min(1.0, (accum[1] / total) + 0.1),
                             min(1.0, (accum[2] / total) + 0.1)]
                    else:
                        c = [1.0, 1.0, 1.0]
                    vertex_colors[v.index] = tuple(c)
                # キャラ(ざっくり塗り)ではボーンの境目をさらにぼかす。粗いケージで
                # ウェイトが1辺で切り替わると(デッサン人形の胸: spine_02 -> 03)、
                # サブディビジョンがその段差を数px の帯に広げ、線にも無地にも
                # ならない灰色の塊になった。隣の頂点と平均を数回とる。密な
                # メッシュでは広がりがごく小さいので、ほぼ変わらない
                n_smooth = int(scene.get("fp_bone_smooth", BONE_SMOOTH_ITERS))
                if rig_coarse and n_smooth > 0 and len(verts) > 1:
                    ev = np.empty(len(obj.data.edges) * 2, dtype=np.int32)
                    obj.data.edges.foreach_get("vertices", ev)
                    ev = ev.reshape(-1, 2)
                    cols = np.asarray(vertex_colors, dtype=np.float64)
                    hard_cols = cols[hard_mask].copy()
                    deg = np.bincount(ev.ravel(), minlength=len(verts)).astype(np.float64)
                    for _ in range(n_smooth):
                        acc = cols.copy()
                        np.add.at(acc, ev[:, 0], cols[ev[:, 1]])
                        np.add.at(acc, ev[:, 1], cols[ev[:, 0]])
                        cols = acc / (deg + 1.0)[:, None]
                        # 硬境界ボーンの頂点はぼかさない(わざと段差を残した所)。
                        # ぼかしていたので、キャラ/手描き背景では硬境界が効かなかった
                        cols[hard_mask] = hard_cols
                    vertex_colors = [tuple(c) for c in cols.tolist()]
            else:
                vertex_colors = [(1.0, 1.0, 1.0)] * len(verts)

            vcols = obj.data.vertex_colors if bpy.app.version < (3, 4, 0) else obj.data.color_attributes
            if 0 <= bone_color_index < len(vcols):
                vc_data = vcols[bone_color_index].data
                for poly in obj.data.polygons:
                    for li in poly.loop_indices:
                        vidx = obj.data.loops[li].vertex_index
                        col = vertex_colors[vidx]
                        vc_data[li].color = (col[0], col[1], col[2], 1.0)

            try:
                if armature_mod and 0 <= bone_color_index < len(vcols):
                    target_index = bone_color_index
                elif 0 <= mecha_color_index < len(vcols):
                    target_index = mecha_color_index
                else:
                    target_index = None
                if target_index is not None:
                    if bpy.app.version < (3, 4, 0):
                        obj.data.vertex_colors.active_index = target_index
                    else:
                        # active_color_index: 頂点ペイントモードの表示用。
                        # render_color_index: シェーディング/レンダー/
                        # glTFエクスポータの export_vertex_color='ACTIVE'
                        # が実際に参照する方(別物!)。両方合わせないと
                        # エクスポート時に未着色レイヤー(既定黒)が
                        # 書き出される(実測で踏んだ)
                        obj.data.color_attributes.active_color_index = target_index
                        obj.data.color_attributes.render_color_index = target_index
            except Exception:
                pass

            if obj.mode != original_mode: bpy.ops.object.mode_set(mode=original_mode)

            area = context.area
            if area and area.type == 'VIEW_3D':
                space = area.spaces.active
                if space and space.type == 'VIEW_3D':
                    space.shading.type = 'SOLID'; space.shading.light = 'FLAT'; space.shading.color_type = 'VERTEX'

        if uniform_objs:
            scene["fp_uniform_smooth"] = len(uniform_objs)
        elif "fp_uniform_smooth" in scene:
            del scene["fp_uniform_smooth"]

        if active_obj and original_mode is not None :
            if context.view_layer.objects.active != active_obj:
                try: context.view_layer.objects.active = active_obj
                except ReferenceError: pass
            if active_obj.mode != original_mode and active_obj.name in bpy.data.objects:
                try: bpy.ops.object.mode_set(mode=original_mode)
                except RuntimeError: pass

        time_end = time.time()
        logger.info(
            f"FreePencil: Auto Vertex Color process finished in {time_end - time_start:.3f} seconds."
        )
        if not getattr(self, "_quiet", False):
            if selected_mesh_objects:
                utils.show_message_box(bpy.app.translations.pgettext("Vertex colors applied successfully."), title=bpy.app.translations.pgettext("Success"))
            else:
                utils.show_message_box(bpy.app.translations.pgettext("No mesh objects were processed."), title=bpy.app.translations.pgettext("Info"), icon='INFO')
        self._result = {'FINISHED'}

    def execute(self, context):
        """同期実行(スクリプト/バッチ/ヘッドレス用): 全ステップを消費する。"""
        gen, state = make_vertex_color_gen(context)
        for _ in gen:
            pass
        return state._result

    def invoke(self, context, event):
        """GUI実行: モーダル+タイマーで1オブジェクトずつ処理し、
        ビューポートに進捗バーを描く(応答なし対策)。"""
        if bpy.app.background or context.window is None:
            return self.execute(context)
        gen, state = make_vertex_color_gen(context, quiet=True)
        if not self._progress_start(context, gen, state):
            return state._result  # 検証エラー等(セットアップ内で通知済み)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC':
            self._progress_cancel(context)
            self.report({'INFO'}, "FreePencil: cancelled")
            return {'CANCELLED'}
        if event.type != 'TIMER':
            return {'RUNNING_MODAL'}  # 処理中は他の操作をブロック
        status = self._progress_step(context)
        if status == 'RUNNING':
            return {'RUNNING_MODAL'}
        if status == 'ERROR':
            return {'CANCELLED'}
        self._progress_end(context)
        if self._state._result == {'FINISHED'}:
            self.report({'INFO'}, bpy.app.translations.pgettext(
                "Vertex colors applied successfully."))
        return self._state._result


def _draw_vc_progress(op):
    """ビューポート下部に描く進捗バー(BlenderKit風のリッチ表示)。"""
    import gpu
    import blf
    from gpu_extras.batch import batch_for_shader

    region = bpy.context.region
    if region is None:
        return
    done, total = op._done, max(1, op._total)
    frac = min(1.0, done / total)
    elapsed = time.time() - op._t0
    if done > 0:
        eta = elapsed / done * (total - done)
        eta_txt = f"ETA {int(eta // 60)}:{int(eta % 60):02d}"
    else:
        eta_txt = "ETA --:--"

    bar_w = min(520, region.width - 80)
    if bar_w < 120:
        return
    bar_h = 16
    x = (region.width - bar_w) * 0.5
    y = 34.0

    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')

    def rect(x0, y0, w0, h0, col):
        batch = batch_for_shader(shader, 'TRI_FAN', {
            "pos": [(x0, y0), (x0 + w0, y0), (x0 + w0, y0 + h0), (x0, y0 + h0)]})
        shader.uniform_float("color", col)
        batch.draw(shader)

    # パネル背景 / トラック / フィル
    rect(x - 14, y - 12, bar_w + 28, bar_h + 46, (0.07, 0.07, 0.09, 0.88))
    rect(x, y, bar_w, bar_h, (0.20, 0.20, 0.23, 1.0))
    rect(x, y, bar_w * frac, bar_h, (0.25, 0.60, 1.00, 1.0))
    gpu.state.blend_set('NONE')

    font = 0
    blf.size(font, 12)
    blf.color(font, 1.0, 1.0, 1.0, 1.0)
    name = op._name if len(op._name) <= 42 else op._name[:39] + "..."
    blf.position(font, x, y + bar_h + 10, 0)
    # done はオブジェクト内フェーズを表す小数(例 2.35)なので、
    # 件数表示は切り捨て、細かい進みはパーセントで見せる
    count = f"{int(done)}/{total} " if total > 1 else ""
    blf.draw(font, f"{op._progress_label}: {count}({frac * 100:.0f}%)  {name}")
    blf.color(font, 0.75, 0.78, 0.85, 1.0)
    right = f"{eta_txt}   ESC: cancel"
    rw = blf.dimensions(font, right)[0]
    blf.position(font, x + bar_w - rw, y + bar_h + 10, 0)
    blf.draw(font, right)


class FREEPENCIL_OT_randomize_seed(bpy.types.Operator):
    """Assign a new random color seed."""
    bl_idname = "freepencil.randomize_seed"
    bl_label = "Randomize Seed"
    bl_description = "Assign a new random color seed"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def description(cls, context, properties):
        return bpy.app.translations.pgettext("Assign a new random color seed")

    def execute(self, context):
        context.scene.fp_color_seed = random.randint(0, SEED_MAX)
        return {'FINISHED'}


