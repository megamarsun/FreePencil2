"""Operator to fill half loops with specified vertex color."""

import bpy
import bmesh
from mathutils import Vector

from . import utils

class LINK_MAKE_FP_OT_HALF_FILL(bpy.types.Operator):
    """Paint selected vertices on one side of a boundary."""
    bl_idname = "freepencil5.link_button"
    bl_label = "Half Fill"
    bl_description = "Fill half by selected verts"
    bl_options = {'REGISTER', 'UNDO'}

    direction: bpy.props.IntProperty(default=-1)

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.mode == 'EDIT' and obj.type == 'MESH'

    @classmethod
    def description(cls, context, properties):
        return bpy.app.translations.pgettext("Half Fill")

    def execute(self, context):
        obj = context.edit_object
        if "mecha_color" not in utils.get_vertex_colors(obj):
            utils.show_message_box("Execute from STEP1")
            return {'CANCELLED'}
        bm = bmesh.from_edit_mesh(obj.data)

        sel_verts = {v for v in bm.verts if v.select}
        if len(sel_verts) < 2:
            utils.show_message_box("境界になる頂点を2点以上選択してください")
            return {'CANCELLED'}

        v0, v1 = list(sel_verts)[:2]
        p0 = Vector((v0.co.x, v0.co.y))
        p1 = Vector((v1.co.x, v1.co.y))
        d2 = (p1 - p0).normalized()
        n2 = Vector((-d2.y, d2.x))
        eps = 1e-6

        def is_on_paint_side(center):
            side = n2.dot(Vector((center.x, center.y)) - p0)
            return self.direction * side < -eps

        col_layer = bm.loops.layers.color.get("mecha_color")

        col = context.scene.fp_half_color

        for face in bm.faces:
            fc = face.calc_center_median()
            if not is_on_paint_side(fc):
                continue
            for loop in face.loops:
                if loop.vert in sel_verts:
                    loop[col_layer] = col

        bmesh.update_edit_mesh(obj.data, loop_triangles=False)
        return {'FINISHED'}
