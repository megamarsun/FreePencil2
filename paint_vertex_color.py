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

        # マスク/ライン/生成の色は、その AOV が無いと塗っても線に出ない。STEP0 は塗っていない
        # 色の AOV を作らないので、STEP0 の後にマスクを塗っても線が消えなかった(v2.9 の点検で
        # 発見)。塗る前に AOV を入れてコンポジタを作り直す。塗っていない(黒の)所は線を変えない
        # ので、塗るまで絵は変わらず、塗るとその場で線に出る
        scene = context.scene
        prop = f"fp_{color_type}"
        if color_type != "mecha_color" and hasattr(scene, prop) and not getattr(scene, prop):
            from . import fp_core, compat
            setattr(scene, prop, True)
            fp_core.setup_aov(scene, context.view_layer)
            tree = compat.get_compositor_tree(scene)
            if tree is not None and any(n.type == "GROUP" and n.node_tree is not None
                                        and n.node_tree.name.startswith(fp_core.NODE_GROUP_PREFIX)
                                        for n in tree.nodes):
                fp_core.setup_compositor(scene, context.view_layer)

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
                    # 3D ビューから押されたときだけ表示を切り替える。3D ビューが
                    # 無い所(検索メニューやスクリプト)から呼ぶと落ちていた
                    area = context.area
                    space = (area.spaces.active if area is not None
                             and area.type == 'VIEW_3D' else None)
                    if space is not None:
                        space.shading.type       = 'SOLID'
                        space.shading.light      = 'FLAT'
                        space.shading.color_type = 'VERTEX'
                    break

        return {'FINISHED'}



