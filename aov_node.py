"""Operators for generating FreePencil AOV node groups."""

import bpy
from . import compat
from . import utils
from . import fp_core

class LINK_MAKE_FP_OT_AOV_NODE(bpy.types.Operator):
    """Create AOV node groups in the current material."""
    bl_idname = "freepencil4.link_button"
    bl_label = "freepencil4"
    bl_description = "Generate Sample Node"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def description(cls, context, properties):
        return bpy.app.translations.pgettext("Generate Sample Node")

    def execute(self, context):
        """Generate and insert the FreePencil AOV node group."""
        from . import undo_setup          # 「FreePencil を外す」ための元の値を控える
        undo_setup.snapshot(context)
        def show_msg(msg, title="Message", icon='INFO'):
            if bpy.app.background:
                print(f"[freepencil4] {msg}")
                return
            def draw(self, _):
                self.layout.label(text=bpy.app.translations.pgettext(msg))
            context.window_manager.popup_menu(draw, title=title, icon=icon)

        # ── 事前チェック ───────────────────────────
        if not context.selected_objects:
            show_msg("Select a mesh.")
            return {'FINISHED'}

        obj = context.selected_objects[0]
        vcols = utils.get_vertex_colors(obj)
        if "mecha_color" not in vcols:
            show_msg("Execute from STEP1")
            return {'FINISHED'}

        # 塗ってある頂点カラー(マスク・ライン・生成)の AOV を入れる(v2.9)。STEP0 の中でしか
        # 見ていなかったので、STEP0 の後に STEP4 でマスクを塗り、STEP2 を押しても線が消えなかった。
        # 塗ってあれば入れるだけで、利用者が入れたものは外さない
        if getattr(context.scene, "fp_auto_detect_aov", True):
            from .auto_setup import _channel_painted
            meshes = [o for o in context.scene.objects if o.type == 'MESH' and o.data is not None]
            for ch in ("gen_color", "mask_color", "line_color"):
                if not getattr(context.scene, f"fp_{ch}") and _channel_painted(meshes, ch):
                    setattr(context.scene, f"fp_{ch}", True)
            # マスクを絵(mask_texture)でつないでいる場合も入れる
            if not context.scene.fp_mask_color and fp_core.texture_plugged("mask_texture"):
                context.scene.fp_mask_color = True

        # ── コア処理（マテリアル挿入・AOVスロット・レンダー設定）──
        info = fp_core.setup_aov(context.scene, context.view_layer)

        # 押しても無反応に見える、という声があったので結果を出す
        verb = {"created": "Created", "updated": "Updated",
                "kept": "Already up to date"}.get(info["action"], "Ready")
        summary = (f"{bpy.app.translations.pgettext(verb)}: "
                   f"{info['group']}  |  AOV {len(info['aovs'])}: "
                   f"{', '.join(info['aovs'])}")
        if info["materials"]:
            summary += (f"  |  +{info['materials']} "
                        + bpy.app.translations.pgettext("materials"))
        self.report({'INFO'}, summary)
        show_msg(summary, title="STEP2")

        # ── ビューポート設定 ---------------------------
        # 塗り分けの確認用に mecha_color パスを直接表示する。ただし 4.2 の
        # ビューポートコンポジタは AOV を評価しないため、切り替えても
        # 真っ白になるだけ。その場合は SOLID のままにしておく。
        if context.screen is not None and compat.HAS_AOV_IN_VIEWPORT_COMPOSITOR:
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.spaces[0].shading.type = 'RENDERED'
                    area.spaces[0].shading.render_pass = 'mecha_color'
                    break

        return {'FINISHED'}


