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

from . import vertex_color
from .fp_core import is_real_glass as _is_real_glass


def _channel_painted(objs, name: str) -> bool:
    """頂点カラー name が実際に塗られているか(黒=既定値のみは未塗り扱い)。

    STEP1 が mask/line/bone を既定の黒で常に作成するため、属性の存在では
    判定できない。RGB のどこかが黒以外なら「塗ってある」。
    """
    import numpy as np
    for o in objs:
        attr = o.data.color_attributes.get(name)
        if attr is None or len(attr.data) == 0:
            continue
        buf = np.empty(len(attr.data) * 4, dtype=np.float32)
        attr.data.foreach_get("color", buf)
        if buf.reshape(-1, 4)[:, :3].max() > 1e-4:
            return True
    return False


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
        view_layer.objects.active = targets[0]

        # --- おすすめ設定(STEP0 のチェックが入っている項目のみ適用) ---
        if scene.fp_auto_sharp:
            scene.fp_sharp_auto = True
        if scene.fp_auto_seam:
            scene.fp_seam_boundaries = True
        if scene.fp_auto_merge:
            scene.fp_min_island_area_pct = 0.02
        if scene.fp_auto_part_tint:
            scene.fp_part_tint = True
        scene.fp_bone_grouping_mode = 'basename'
        has_rig = any(
            m.type == 'ARMATURE' and m.show_viewport and m.object
            for o in targets for m in o.modifiers)
        if scene.fp_auto_bone:
            scene.fp_bone_color = has_rig
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
            for ch in ("gen_color", "mask_color", "line_color"):
                on = _channel_painted(targets, ch)
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

        bpy.ops.freepencil4.link_button()
        bpy.ops.freepencil2.link_button()

        scene.render.film_transparent = info["film_transparent"]

        # 白マテリアルでプレビュー。線画がすぐ見える状態にして終わる。
        # コンポジタ切替方式なのでマテリアル自体は触らない。必ず STEP3 で
        # コンポジタが建った後に立てること(先に立てても差し込む先が無い)
        if scene.fp_auto_white_preview and not scene.fp_white_preview:
            scene.fp_white_preview = True

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

        msg = (f"meshes={len(info['targets'])}, "
               f"bone_aov={'ON' if info['has_rig'] else 'OFF'}, hashed={hashed}"
               + (f", detected_aov={'+'.join(info['detected'])}"
                  if info["detected"] else ""))
        print(f"[freepencil.auto_setup] {msg}")
        self.report({'INFO'}, f"Auto setup done ({msg})")
        return {'FINISHED'}

    def execute(self, context):
        """同期実行(スクリプト/バッチ/ヘッドレス用)。"""
        info = self._prepare(context)
        if info is None:
            return {'CANCELLED'}
        bpy.ops.freepencil.auto_vertex_color()
        return self._finish(context, info)

    def invoke(self, context, event):
        """GUI実行: STEP1 をモーダルで回して進捗バーを出し(応答なし対策)、
        終わってから STEP2/STEP3 を続ける。"""
        if bpy.app.background or context.window is None:
            return self.execute(context)
        info = self._prepare(context)
        if info is None:
            return {'CANCELLED'}
        self._info = info
        gen, state = vertex_color.make_vertex_color_gen(context, quiet=True)
        if not self._progress_start(context, gen, state):
            return state._result  # STEP1 が即失敗 → STEP2/3 は走らせない
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
        if self._state._result != {'FINISHED'}:
            return self._state._result
        return self._finish(context, self._info)
