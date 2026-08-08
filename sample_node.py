"""Utilities for generating sample node groups.

ビューポートのライブプレビューは、リアルタイムコンポジタが AOV 出力を
評価できる Blender 4.3 以降でのみ成立する。4.2 では AOV が空のまま渡る
ため、レンダー表示に切り替えると真っ白な画面になる(実測)。そのため
4.2 では切り替え自体を行わない — compat.HAS_AOV_IN_VIEWPORT_COMPOSITOR。
F12 のレンダリングは 4.2 でも問題なく線画になる。
"""

import bpy
from . import compat
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
        info = fp_core.setup_compositor(context.scene, context.view_layer)

        # ── ここから UI 専用処理（ヘッドレスではスキップ）──
        if bpy.app.background:
            return {'FINISHED'}

        # 押しても無反応に見える、という声があったので結果を出す
        t = bpy.app.translations.pgettext
        verb = {"created": "Created", "updated": "Updated",
                "kept": "Already up to date"}.get(info["action"], "Ready")
        summary = (f"{t(verb)}: {info['group']}  ({info['nodes']} "
                   f"{t('nodes')})")
        if info["passes"]:
            summary += (f"  |  {t('File output')}: "
                        f"{', '.join(info['passes'])} -> "
                        f"{info['file_output_dir'] or '//'}")
        if info.get("relief"):
            summary += f"  |  {t('Far crush relief')} {info['relief']:.2f}"
        self.report({'INFO'}, summary)
        show_message(summary, title="STEP3")

        if context.scene.fp_enable_compositor_view:
            if compat.HAS_AOV_IN_VIEWPORT_COMPOSITOR:
                for area in context.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.spaces[0].shading.type = 'RENDERED'
                        area.spaces[0].shading.use_compositor = 'ALWAYS'
                        area.spaces[0].shading.render_pass = 'COMBINED'
                        break
            else:
                # 4.2: 切り替えると真っ白になるだけなので触らない。
                # 何も言わずに無視すると「効かない」と誤解されるため伝える。
                show_message(
                    "Live preview needs Blender 4.3+. Render with F12 instead.",
                    title="FreePencil", icon='INFO')

        # かつてはノードを確認・手直しする前提だったので、ここで
        # wm.window_new() して Compositor ビューへ切り替えていた。
        # STEP0 の全自動セットアップが標準になった今は、実行のたびに
        # 別ウィンドウが開くだけで用がないため行わない。ノードを見たい
        # ときは通常どおりエディタを Compositor に切り替える。

        return {'FINISHED'}


