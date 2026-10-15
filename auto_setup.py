"""STEP0: One-button full-auto setup.

シーンを解析しておすすめ設定を適用し、STEP1(頂点カラー)→STEP2(AOV)→
STEP3(PROノード)まで一括実行する。判定内容:
  - 対象: 選択メッシュ、無ければレンダリング対象の全メッシュ
  - リグ(Armature)があれば bone AOV を自動ON
  - 島分割は自動しきい値+シーム境界+小島マージ、パーツ・トーン分けON
  - blend_method='BLEND' は EEVEE が AOV を書かないため、本物のガラス
    (Transmission/低Alpha)以外を HASHED へ変更
  - film_transparent はシーンの見た目を尊重して元の値を維持
"""

import bpy

from . import utils
from . import vertex_color
from .fp_core import is_real_glass as _is_real_glass


def _channel_painted(objs, name: str) -> bool:
    """頂点カラー name が実際に塗られているか(黒=既定値のみは未塗り扱い)。

    STEP1 が mask/line/bone を既定の黒で常に作成するため、属性の存在では
    判定できない。RGB のどこかが黒以外なら「塗ってある」。
    """
    import numpy as np
    # リンク複製は同じメッシュ実体を指すので、実体ごとに1回だけ読む。
    # 1,186オブジェクト/159メッシュのシーンでは読み取り量が8分の1になる。
    # 小さいものから見るのは、塗ってあるチャンネルなら早い段階で
    # 打ち切れて巨大メッシュの読み込み(1枚 678MB)を回避できるため
    meshes = {o.data.name: o.data for o in objs}
    for me in sorted(meshes.values(), key=lambda m: len(m.loops)):
        attr = me.color_attributes.get(name)
        if attr is None or len(attr.data) == 0:
            continue
        buf = np.empty(len(attr.data) * 4, dtype=np.float32)
        attr.data.foreach_get("color", buf)
        if buf.reshape(-1, 4)[:, :3].max() > 1e-4:
            return True
    return False


def _looks_like_ground(obj, targets) -> bool:
    """視界より大きい平面か。面が少なく、薄く、他のどの物よりも 2 倍以上広い。

    中央値の 5 倍で判定すると、小物の多い町では家の土台や階段(平たい
    板)まで地面になった(実測)。一番大きい物と比べる。
    """
    from mathutils import Vector
    if len(obj.data.polygons) > 8:
        return False

    def dims(o):
        pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
        return Vector((max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3)))
    d = dims(obj)
    xy = max(d.x, d.y)
    if xy <= 0.0 or d.z > xy * 0.02:
        return False
    others = [max(dims(o)) for o in targets if o is not obj]
    if not others:
        return False
    return xy >= max(others) * 2.0


class FP_OT_AUTO_SETUP(vertex_color.FPProgressModalMixin, bpy.types.Operator):
    """Analyze the scene, apply recommended settings and run STEP1-3."""
    bl_idname = "freepencil.auto_setup"
    bl_label = "Auto Setup"
    bl_description = (
        "Analyze the scene, apply recommended settings and run "
        "STEP1 (vertex colors), STEP2 (AOV) and STEP3 (PRO node) at once"
    )
    bl_options = {'REGISTER', 'UNDO'}

    # STEP0 の所要時間はほぼ STEP1(塗り分け)なので、そこだけ進捗を出す
    _progress_label = "FreePencil STEP1/3"

    def _prepare(self, context):
        """STEP1 の前段(対象メッシュの決定・おすすめ設定・AOV判定)。

        続行できない場合は None を返す。戻り値は _finish() に渡す。
        """
        # 「FreePencil を外す」ための元の値を、何かを変える前に控える
        from . import undo_setup
        undo_setup.snapshot(context)
        scene = context.scene
        view_layer = context.view_layer

        # --- 対象メッシュ: 選択があれば選択、無ければ表示中の全メッシュ ---
        targets = [o for o in context.selected_objects if o.type == "MESH"]
        if not targets:
            for o in context.selected_objects:
                o.select_set(False)
            for o in scene.objects:
                if o.type != "MESH" or o.hide_render:
                    continue
                try:
                    o.select_set(True)
                except RuntimeError:
                    continue  # ビューレイヤー外
                targets.append(o)
        if not targets:
            self.report({'ERROR'}, "No mesh objects")
            return None
        # 手描き背景: 地面(視界より大きい平面)は塗らない。塗ると地平線が
        # 太い輪郭になり、黒い帯が出る(実測: 町のデモは手で外していた)
        if getattr(scene, "fp_auto_style", 'PRECISE') == 'BACKGROUND':
            ground = [o for o in targets if _looks_like_ground(o, targets)]
            if ground and len(ground) < len(targets):
                for o in ground:
                    o.select_set(False)
                    print(f"[freepencil.auto_setup] 地面とみなして塗らない: {o.name}")
                targets = [o for o in targets if o not in ground]
        view_layer.objects.active = targets[0]

        # --- 仕上がり。精密 = v2.7 の出力そのまま、キャラ = AO の強弱、
        # 背景 = キャラ + 特殊処理(奥の扱い・葉の房) ---
        style = getattr(scene, "fp_auto_style", 'PRECISE')
        weighted = style in ('WEIGHTED', 'BACKGROUND')
        background = style == 'BACKGROUND'
        # 人工分割の下限。14 の根拠は utils.ARTIFICIAL_SPLIT_FLOOR
        scene.fp_auto_split_floor = 14.0 if weighted else 5.0
        scene.fp_line_weight = weighted
        # 奥の扱い(値の根拠は dev/note_assets/eval_far_ideas.py の 24案比較)
        scene.fp_lw_far = 1.0 if background else 0.0
        # 奥の線減らしは 2.0(3.0 だと町の奥のビルの窓が消えすぎた。
        # dev/note_assets/eval_density_options.py の案 ABC)
        scene.fp_lw_far_sens = 2.0 if background else 1.0
        # 奥を薄くするのは 0.15(2026-10 に変更)。0.35 では詰まった線を薄くする段と重なって
        # 「色を薄くしただけ」に見えた(並木道で 精密と比べて確認)
        scene.fp_lw_far_fade = 0.15 if background else 0.0
        # 詰まった線を薄く(つぶれ軽減)。密度の高い町で、手すり・網戸・外階段が
        # 黒い塊になった。0.6 で塊が灰色の調子になり、輪郭は黒のまま(1.0 は薄すぎ)。
        # 2026-10 に 0.3: 0.6 は並木を灰色の面にし、白プレビューで「色を薄くしただけ」
        # に見えた。0.3 で葉の陰に黒が残り、町の手すりも黒い塊にはならない(画像で確認)
        scene.fp_lw_dense = 0.3 if background else 0.0
        # 細かすぎる縞を奥ほど薄く。低い視点から水平の線の多い面を見ると、奥が
        # つぶれて動かすとちらついた(試験場 test_grazing で総当り)
        # v2.8.3 で既定を切った(0)。カメラが動くと、遠くの窓の格子が画素とのずれで
        # コマごとに見え方を変え、薄める範囲と灰色の濃さが揺れて灰色のまだらが
        # ちらついた。縁石のような近い 2 本の線も細い二重線になった(大通りの飛行で
        # 確認、dev/note_assets/flicker_compare.py)。低い視点の横縞のモアレには効くので、
        # STEP3 の詳細のつまみで入れられる
        scene.fp_lw_stripe_fade = 0.0
        # パネルのつまみ(上の5つをまとめた2本)。1.0 が上の値と同じ。更新フック
        # を動かすと STEP0 の途中で STEP3 を作り直すので、フックを止めて書く
        from .props import _write_quiet
        _write_quiet(scene, {"fp_lw_far_amount": 1.0 if background else 0.0,
                             "fp_lw_relief": 1.0 if background else 0.0})
        # 葉を房に(カエデは 4〜8、ヤシは 1 が良い。既定は 4)
        scene.fp_foliage_clumps = 4 if background else 0
        # 遠い区画をまとめる 500px(v2.8.3)。150 ではほとんど効かず、500 で奥の高層が
        # 輪郭と帯になった(dev/note_assets/far_lod_proto.py)。手前は変わらない
        scene.fp_far_lod_px = 500.0 if background else 0.0
        # 細い線(精密の分割)を重ねる。線を太くせず本数で戻す(0.35 ではアパートの
        # 窓枠が精密より明らかに少なかった)。2026-10 に 0.6 -> 1.0: 0.6 は細い線が
        # 灰色になり、精密と並べると「色を薄くしただけ」に見えた。1.0 で並木の陰と
        # 枝が黒く入り、町の手すりも塊にならない(並木道と町で確認)
        scene.fp_fine_lines = 1.0 if background else 0.0
        # 細い線を使うときは、STEP1 を 2 回塗る。1 回目はここで精密の値に
        # しておき(この後のモーダルが塗る)、_finish で fine_color へ写して
        # から手描きの値で塗り直す
        if background and scene.fp_fine_lines > 0.0:
            scene.fp_auto_split_floor = 5.0
            # 1 回目はメカの塗り。切れすぎの抑え(島/面の上限)を外して
            # 線を全部出す。_finish で外す
            scene["fp_fine_pass"] = True
        elif "fp_fine_pass" in scene:
            del scene["fp_fine_pass"]
        # キャラ(リグ付き)は手描き系ではざっくり塗り + ボーンの塗り。
        # 精密は v2.7 のまま(リグ付きでも角度で分ける)
        if weighted:
            scene["fp_rig_coarse"] = True
        elif "fp_rig_coarse" in scene:
            del scene["fp_rig_coarse"]
        # 葉の隙間埋め 6px(200% 基準 = 1080p で 3px)。線の濃さは 1.0(黒)。
        # v2.8.2 までは 0.75(濃い灰色)で、精密と並べると薄く見えた
        # 背景は線を細く(強さ 0.5 = 最大 6px、1080p で 3px)。太いのは
        # 近くに寄ったときだけでよい
        scene.fp_gap_fill = 6 if background else 0
        scene.fp_lw_ink = 1.0
        # キャラは 0.6(ほんのり強弱)。1.0 は輪郭が太すぎ、細かいメカを小さく
        # 写すと黒く詰まった(リグ付きロボット)。太くしたいときはスライダーで
        # 上げればその場で効く
        scene.fp_lw_strength = 0.5 if background else (0.6 if weighted else 1.0)
        # 深度チャンネルは地面と空の境(深度の段差)を太い帯にする(実測)。
        # 背景では切る。奥の距離の計測もその帯を線に数えて狂っていた
        # (奥の終わり 238 -> 切ると 71)
        if background:
            scene.fp_ch_depth = 0.0

        # --- おすすめ設定(STEP0 のチェックが入っている項目のみ適用) ---
        if scene.fp_auto_sharp:
            scene.fp_sharp_auto = True
        if scene.fp_auto_seam:
            scene.fp_seam_boundaries = True
        if scene.fp_auto_merge:
            # 0.02% は「小島の掃除」の値で、塗りの粒度には効かなかった。
            # 実測(スザンヌ適用済み 7,872面): 0% -> 429色 / 0.5% -> 9色 /
            # 1% -> 6色 / 2% -> 4色。1% で頭が1色にまとまり、目と口だけが
            # 残る。メカも 1% ならパネルの区別を保ったまま粒が落ちる
            scene.fp_min_island_area_pct = 1.0
            # 広くまとめると島の中の線が消えるので、稜線の起伏で補う。
            # 平らな面では残差がほぼゼロなのでメカには足されない。
            #
            # 0.45 にする根拠(BlenderKit・2026-09): 0.25/0.35/0.45/0.50 を
            # 10体で振ったところ、どの値でもどのモデルも内側の線が減らず
            # (最小 99.9%)、中央は 100/111/123/132% と増える一方だった。
            # 0.50 は上限で調整の余地が無く、ハンガーの屋根が詰まりはじめる。
            # メカと壺は全域で1画素も変わらない(平らな面では残差ゼロ)。
            # スザンヌの口の輪郭は 0.45 でないと戻らない(下限14度と役割が別)。
            # 精密(v2.7)は 0.25 のまま
            scene.fp_ridge_amount = 0.45 if weighted else 0.25
            # 細い線の 1 回目は本当の精密(稜線 0.25)で塗る。_finish で
            # fine_color へ写したあと 0.45 に戻して塗り直す
            if background and scene.fp_fine_lines > 0.0:
                scene.fp_ridge_amount = 0.25
            scene.fp_ridge_radius = 0.08
        if scene.fp_auto_part_tint:
            scene.fp_part_tint = True
        scene.fp_bone_grouping_mode = 'basename'
        has_rig = any(
            m.type == 'ARMATURE' and m.show_viewport and m.object
            for o in targets for m in o.modifiers)
        if scene.fp_auto_bone:
            scene.fp_bone_color = has_rig
        # 線の強さも自動化に含める。ここを触らないと、古いファイルに
        # 残った 1.0 がそのまま使われて線が弱いままになる
        scene.fp_line_sensitivity = 0.5
        scene.fp_node_type = 'pro'
        if scene.fp_auto_aa:
            scene.fp_include_antialiasing = True
        if scene.fp_auto_supersample:
            # 細線化はFreePencilの品質の要(縮小しないと線が太い)
            scene.fp_supersample = True
        if scene.fp_auto_file_output:
            scene.fp_file_output = True

        # AOVの完全自動設定: STEP2 の手動チェックには依存せず、
        # シーンから判定して ON/OFF 両方を決める(自動がAOV構成を所有)。
        #   gen/mask/line = その頂点カラーが塗られているか
        #   mat          = マテリアルID加算が有効か
        #   (mecha=常時、bone=リグ検出は上で設定済み)
        detected = []
        if scene.fp_auto_detect_aov:
            from .fp_core import texture_plugged
            for ch in ("gen_color", "mask_color", "line_color"):
                on = _channel_painted(targets, ch)
                if ch == "mask_color" and not on:
                    # マスクを絵(AOV グループの mask_texture)でつないでいる(v2.9)
                    on = texture_plugged("mask_texture")
                setattr(scene, f"fp_{ch}", on)
                if on:
                    detected.append(ch)
            scene.fp_mat_color = bool(scene.fp_mat_count)
            if scene.fp_mat_color:
                detected.append("mat_color")

        # STEP2 が film_transparent を True にするが、マテリアル/背景を
        # 残すシーンでは見た目が変わるため元の値を維持する
        film_transparent = scene.render.film_transparent

        return {"targets": targets, "has_rig": has_rig,
                "detected": detected, "film_transparent": film_transparent}

    def _finish(self, context, info):
        """STEP1 完了後: STEP2(AOV)/STEP3(PROノード)と後始末。"""
        scene = context.scene

        # 細い線: 1 回目(精密の分割)の結果を fine_color へ写し、手描きの
        # 値で塗り直す。線の検出はどちらも同じ仕組みなので、塗り分けだけ
        # 2 枚持てば、合成の割合をスライダーで変えられる
        if getattr(scene, "fp_fine_lines", 0.0) > 0.0 and scene.fp_line_weight:
            from . import utils as _utils
            n = 0
            for obj in info["targets"]:
                if _utils.copy_vertex_color(obj, "mecha_color", "fine_color"):
                    n += 1
            scene.fp_auto_split_floor = 14.0
            if scene.fp_auto_merge:
                scene.fp_ridge_amount = 0.45
            if "fp_fine_pass" in scene:
                del scene["fp_fine_pass"]       # 2 回目(手描き)は抑える
            bpy.ops.freepencil.auto_vertex_color("EXEC_DEFAULT")
            print(f"[freepencil.auto_setup] 細い線: fine_color を {n} 個に写して塗り直した")

        bpy.ops.freepencil4.link_button()
        # STEP0 の中は背景を透過にして進める(線の強弱の計測が透過の前提で合わせてある)。
        # 終わりに元の値へ戻す。v2.9 で STEP2 が透過にしなくなったので、ここで明示する
        scene.render.film_transparent = True
        bpy.ops.freepencil2.link_button()

        # 強弱: しきい値はカットごとに違う(実モデル11体で15倍ひらく)ので、
        # STEP3 が建った後に1回測って固定し、STEP3 を組み直す。
        # ここで測らないと、使う人が「しきい値を測る」を押すまで既定値の
        # まま動く
        measured = None
        if scene.fp_line_weight:
            from . import line_weight
            edges = line_weight.measure_edges(scene, context.view_layer)
            if edges is not None:
                for i, v in enumerate(edges, start=1):
                    setattr(scene, f"fp_lw_e{i}", v)
                bpy.ops.freepencil2.link_button()
                measured = edges
        info["measured"] = measured

        scene.render.film_transparent = info["film_transparent"]

        # 白マテリアルでプレビュー。線画がすぐ見える状態にして終わる。
        # コンポジタ切替方式なのでマテリアル自体は触らない。必ず STEP3 で
        # コンポジタが建った後に立てること(先に立てても差し込む先が無い)
        # 種類で見る(旧トグルは v2.7 のファイルで立ったまま残っていることがあり、
        # それを見て「もう白だ」と飛ばしていた)
        if scene.fp_auto_white_preview and scene.fp_preview_mode not in ("WHITE", "CEL"):
            scene.fp_preview_mode = "WHITE"

        # BLEND は AOV が書かれない → 本物のガラス以外は HASHED へ
        hashed = 0
        if scene.fp_auto_hashed:
            for m in bpy.data.materials:
                if getattr(m, "blend_method", "OPAQUE") != "BLEND":
                    continue
                if _is_real_glass(m):
                    continue
                m.blend_method = "HASHED"
                hashed += 1

        style = getattr(scene, "fp_auto_style", 'PRECISE').lower()
        msg = (f"style={style}, meshes={len(info['targets'])}, "
               f"bone_aov={'ON' if info['has_rig'] else 'OFF'}, hashed={hashed}"
               + (f", lw_edges={'/'.join(f'{v:.3f}' for v in info['measured'])}"
                  if info.get("measured") else "")
               + (f", detected_aov={'+'.join(info['detected'])}"
                  if info["detected"] else ""))
        print(f"[freepencil.auto_setup] {msg}")
        self.report({'INFO'}, f"Auto setup done ({msg})")
        # ステータスバーだけだと見落とされる。STEP1〜3 を一気に走らせる
        # ボタンなので、終わったことをはっきり出す
        utils.show_message_box(f"STEP1-3 done. {msg}",
                               title="FreePencil STEP0", icon='CHECKMARK')
        return {'FINISHED'}

    @staticmethod
    def _clear_fine_pass(context):
        """メカの塗りの目印を外す(途中で止まっても次の STEP1 に残さない)。"""
        if "fp_fine_pass" in context.scene:
            del context.scene["fp_fine_pass"]

    def execute(self, context):
        """同期実行(スクリプト/バッチ/ヘッドレス用)。"""
        info = self._prepare(context)
        if info is None:
            self._clear_fine_pass(context)
            return {'CANCELLED'}
        bpy.ops.freepencil.auto_vertex_color()
        if not (getattr(context.scene, "fp_fine_lines", 0.0) > 0.0
                and context.scene.fp_line_weight):
            self._clear_fine_pass(context)
        return self._finish(context, info)

    def invoke(self, context, event):
        """GUI実行: STEP1 をモーダルで回して進捗バーを出し(応答なし対策)、
        終わってから STEP2/STEP3 を続ける。"""
        if bpy.app.background or context.window is None:
            return self.execute(context)
        info = self._prepare(context)
        if info is None:
            self._clear_fine_pass(context)
            return {'CANCELLED'}
        self._info = info
        gen, state = vertex_color.make_vertex_color_gen(context, quiet=True)
        if not self._progress_start(context, gen, state):
            self._clear_fine_pass(context)
            return state._result  # STEP1 が即失敗 → STEP2/3 は走らせない
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC':
            self._clear_fine_pass(context)
            self._progress_cancel(context)
            self.report({'INFO'}, "FreePencil: cancelled")
            return {'CANCELLED'}
        if event.type != 'TIMER':
            return {'RUNNING_MODAL'}  # 処理中は他の操作をブロック
        status = self._progress_step(context)
        if status == 'RUNNING':
            return {'RUNNING_MODAL'}
        if status == 'ERROR':
            self._clear_fine_pass(context)
            return {'CANCELLED'}
        self._progress_end(context)
        if self._state._result != {'FINISHED'}:
            self._clear_fine_pass(context)
            return self._state._result
        return self._finish(context, self._info)
