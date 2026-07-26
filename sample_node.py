"""Utilities for generating sample node groups.

These utilities rely on the Real-Time Compositor introduced in Blender 4.3.
"""

import bpy
from . import fp_core

class LINK_MAKE_FP_OT_NODE(bpy.types.Operator):
    """Create a sample compositor node group for FreePencil."""
    bl_idname = "freepencil2.link_button"
    bl_label = "freepencil2"
    bl_description = "Generate Sample Node"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def description(cls, context, properties):
        return bpy.app.translations.pgettext("Generate Sample Node")

    def execute(self, context):
        """Build a compositor setup with the selected node group."""
        def show_message(message="", title="Message Box", icon='INFO'):
            if bpy.app.background:
                print(f"[freepencil2] {message}")
                return
            def draw(self, _):
                self.layout.label(text=bpy.app.translations.pgettext(message))
            bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)

        # AOV mecha_color チェック
        if "mecha_color" not in [aov.name for aov in context.view_layer.aovs]:
            show_message("Execute from STEP2")
            return {'FINISHED'}

        # ── コア処理（ノードグループ生成・Compositorツリー構築）──
        fp_core.setup_compositor(context.scene, context.view_layer)

        # ── ここから UI 専用処理（ヘッドレスではスキップ）──
        if bpy.app.background:
            return {'FINISHED'}

        if context.scene.fp_enable_compositor_view:
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.spaces[0].shading.type = 'RENDERED'
                    area.spaces[0].shading.use_compositor = 'ALWAYS'
                    area.spaces[0].shading.render_pass = 'COMBINED'
                    break

        # かつてはノードを確認・手直しする前提だったので、ここで
        # wm.window_new() して Compositor ビューへ切り替えていた。
        # STEP0 の全自動セットアップが標準になった今は、実行のたびに
        # 別ウィンドウが開くだけで用がないため行わない。ノードを見たい
        # ときは通常どおりエディタを Compositor に切り替える。

        return {'FINISHED'}


