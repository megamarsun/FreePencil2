"""Operator to paint vertex colors on the active mesh."""

import bpy
from . import utils

# ------------------------------------------------------------
# オペレーター本体
# ------------------------------------------------------------
class LINK_MAKE_FP_OT_VCOLOR(bpy.types.Operator):
    bl_idname      = "freepencil3.link_button"
    bl_label       = "Paint Vertex Color"
    bl_description = "Paint Vertex Color"
    bl_options     = {'REGISTER', 'UNDO'}

    @classmethod
    def description(cls, context, properties):
        return bpy.app.translations.pgettext("Paint Vertex Color")

    def execute(self, context):
        # 1) メッシュ選択チェック
        sel = [o for o in context.selected_objects if o.type == 'MESH']
        if not sel:
            utils.show_message_box("Select a mesh.")
            return {'CANCELLED'}
        obj = context.active_object
        if obj not in sel:
            utils.show_message_box("Active object must be a selected mesh.")
            return {'CANCELLED'}

        # 2) STEP1: mecha_color が存在するか
        for o in sel:
            if "mecha_color" not in utils.get_vertex_colors(o):
                utils.show_message_box("Execute from STEP1")
                return {'CANCELLED'}

        # 3) プルダウン値（identifier = レイヤー名）
        color_type = context.scene.fp_color_type

        # 4) ペイントモード準備
        for o in sel:
            bpy.context.view_layer.objects.active = o
            bpy.ops.object.mode_set(mode='VERTEX_PAINT')
            o.data.use_paint_mask = True
            bpy.ops.paint.face_select_all(action='SELECT')

            # 5) 対象レイヤーをアクティブに
            for idx, name in enumerate(utils.get_vertex_colors(o)):
                if "." in name:
                    continue
                if name == color_type:
                    utils.set_active_vertex_color(o, name, idx)

                    # ビューポートを頂点カラー表示に
                    area = context.area.spaces[0]
                    area.shading.type       = 'SOLID'
                    area.shading.light      = 'FLAT'
                    area.shading.color_type = 'VERTEX'
                    break

        return {'FINISHED'}



