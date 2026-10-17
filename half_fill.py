"""Half Fill: 選んだ頂点の列で、塗り分けの境目をくっきりさせる。

頂点ペイントで塗ると、境目の頂点は両側の面で同じ色になり、境目の隣の面がぼかし
(色の段差が面の中に広がる)になる。線はその中に太く・ぼやけて出る。

選んだ頂点(境目の列)に触れる面ごとに、その頂点の角を「その面の他の角の色」にする
(隣の色を拾う)。片側の面は片側の色、反対側の面は反対側の色になり、境目が選んだ頂点の
列にそろう。どちら側を塗るか・平面の向きは要らない。

v2.9 で作り直した。以前は選んだ頂点のうち任意の 2 点と、オブジェクトの X/Y 平面だけで
側を決めていたので、X/Y に乗らない境目(箱の正面など)では片側の面の角だけが指定の色に
なり、面の中に段差ができて黒い塊が出た(手作業の道具の点検で発見)。
"""

import bpy
import bmesh

from . import utils


class LINK_MAKE_FP_OT_HALF_FILL(bpy.types.Operator):
    """Make the color boundary follow the selected vertices."""
    bl_idname = "freepencil5.link_button"
    bl_label = "Half Fill"
    bl_description = (
        "Select a row of vertices along a color boundary. Each face touching "
        "them takes its own color at those corners, so the boundary becomes "
        "crisp along the selected row"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        # 編集モードか、頂点ペイント(STEP4 の「頂点カラーを塗る」の後)で使える(v2.9)。
        # 以前は編集モードだけで、頂点ペイントのままではグレーのまま押せなかった
        obj = context.active_object
        ok = obj is not None and obj.type == 'MESH' and obj.mode in ('EDIT', 'VERTEX_PAINT')
        if not ok:
            cls.poll_message_set(bpy.app.translations.pgettext(
                "Use in Edit Mode or Vertex Paint: select the vertices along the boundary"))
        return ok

    @classmethod
    def description(cls, context, properties):
        return bpy.app.translations.pgettext(
            "Select a row of vertices along a color boundary. Each face touching "
            "them takes its own color at those corners, so the boundary becomes "
            "crisp along the selected row")

    def execute(self, context):
        obj = context.active_object
        layer_name = getattr(context.scene, "fp_color_type", "mecha_color")
        if layer_name not in utils.get_vertex_colors(obj):
            utils.show_message_box("Execute from STEP1")
            return {'CANCELLED'}
        edit = obj.mode == 'EDIT'
        if edit:
            bm = bmesh.from_edit_mesh(obj.data)
        else:
            # 頂点ペイント: 頂点の選択マスク(または面の選択マスク)で選んだ頂点を使う
            bm = bmesh.new()
            bm.from_mesh(obj.data)
        layer = (bm.loops.layers.color.get(layer_name)
                 or bm.loops.layers.float_color.get(layer_name))
        if layer is None:
            # 頂点(角でない)に持つ色は、面ごとに分けられない
            utils.show_message_box("Half Fill needs a face-corner color attribute")
            return {'CANCELLED'}

        sel = {v for v in bm.verts if v.select}
        if not sel or len(sel) == len(bm.verts):
            # 全部選んだままだと、どの面も角が全部選んだ頂点になり何も変わらない
            if not edit:
                bm.free()
            utils.show_message_box("Select only the vertices along the boundary")
            return {'CANCELLED'}

        changed = 0
        for face in {f for v in sel for f in v.link_faces}:
            others = [lp for lp in face.loops if lp.vert not in sel]
            if not others:
                continue                    # 面の角が全部選んだ頂点: 決めようがないので触らない
            n = len(others)
            col = [sum(lp[layer][i] for lp in others) / n for i in range(4)]
            for lp in face.loops:
                if lp.vert in sel:
                    lp[layer] = col
                    changed += 1
        if edit:
            bmesh.update_edit_mesh(obj.data, loop_triangles=False)
        else:
            bm.to_mesh(obj.data)
            bm.free()
            obj.data.update()
        self.report({'INFO'}, f"Half Fill: {changed} corners")
        return {'FINISHED'}
