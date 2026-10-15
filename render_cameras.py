"""Batch-render checked cameras through the compositor File Output nodes.

各カメラの fp_cam_render チェックを見て、チェック済みカメラを順に
レンダリングする。File Output ノードの保存先をカメラごとの
//camera_renders/NN_カメラ名/ に振り替えて書き出す。仕上がりの絵(合成の出力)も
同じフォルダに final.png で残す(v2.9)。実行後は元の設定に戻す。
"""

import os
import re

import bpy

from . import compat


def _safe_name(name: str) -> str:
    """Windowsでファイル名に使えない文字を置換"""
    return re.sub(r'[\\/:*?"<>|]', "_", name)


class FP_OT_RENDER_CAMERAS(bpy.types.Operator):
    """Render every checked camera via the compositor File Output nodes."""
    bl_idname = "freepencil.render_cameras"
    bl_label = "Render checked cameras"
    bl_description = (
        "Render each checked camera; File Output nodes write into "
        "//camera_renders/NN_<camera>/ per camera"
    )
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene

        if not bpy.data.filepath:
            self.report({'ERROR'}, "Save the .blend file first")
            return {'CANCELLED'}

        node_tree = compat.get_compositor_tree(scene)
        if node_tree is None:
            self.report({'ERROR'}, "No compositor node tree (run STEP3 first)")
            return {'CANCELLED'}

        file_output_nodes = [
            n for n in node_tree.nodes
            if n.bl_idname == "CompositorNodeOutputFile"
        ]
        if not file_output_nodes:
            self.report({'ERROR'},
                        "No File Output node (enable it in STEP3 and rerun)")
            return {'CANCELLED'}

        cameras = sorted(
            (o for o in scene.objects
             if o.type == "CAMERA" and getattr(o, "fp_cam_render", True)),
            key=lambda o: o.name.lower())
        if not cameras:
            self.report({'ERROR'}, "No cameras checked")
            return {'CANCELLED'}

        root_dir = bpy.path.abspath("//camera_renders")
        os.makedirs(root_dir, exist_ok=True)

        original_camera = scene.camera
        original_use_compositing = scene.render.use_compositing
        original_paths = []
        for node in file_output_nodes:
            if bpy.app.version >= (5, 0, 0):
                original_paths.append((node, node.directory, node.file_name))
            else:
                original_paths.append((node, compat.file_output_get_dir(node)))

        try:
            scene.render.use_compositing = True
            for index, camera in enumerate(cameras, start=1):
                scene.camera = camera
                camera_dir = os.path.join(
                    root_dir, f"{index:02d}_{_safe_name(camera.name)}")
                os.makedirs(camera_dir, exist_ok=True)
                for node in file_output_nodes:
                    if bpy.app.version >= (5, 0, 0):
                        node.directory = camera_dir
                    else:
                        compat.file_output_set_dir(node, camera_dir)
                print(f"[freepencil] ({index}/{len(cameras)}) "
                      f"rendering: {camera.name}")
                bpy.ops.render.render(write_still=False)
                # 仕上がりの絵(合成の出力)もカメラのフォルダに final.png で残す(v2.9)。
                # パスだけでは、セルなど合成した絵が手元に残らなかった
                res = bpy.data.images.get("Render Result")
                if res is not None:
                    fmt = scene.render.image_settings
                    keep = (fmt.file_format, fmt.color_mode)
                    try:
                        fmt.file_format = 'PNG'
                        fmt.color_mode = 'RGBA'
                        final = os.path.join(camera_dir, "final.png")
                        res.save_render(filepath=final, scene=scene)
                    finally:
                        fmt.file_format, fmt.color_mode = keep
                    # ほかの書き出しと同じく最終サイズにそろえる(細線化中は 2 倍で出る)
                    w, h = scene.render.resolution_x, scene.render.resolution_y
                    img = bpy.data.images.load(final, check_existing=False)
                    try:
                        if tuple(img.size) != (w, h):
                            img.scale(w, h)
                            img.save()
                    finally:
                        bpy.data.images.remove(img)
        finally:
            scene.camera = original_camera
            scene.render.use_compositing = original_use_compositing
            for data in original_paths:
                node = data[0]
                if bpy.app.version >= (5, 0, 0):
                    node.directory = data[1]
                    node.file_name = data[2]
                else:
                    compat.file_output_set_dir(node, data[1])

        self.report({'INFO'},
                    f"Rendered {len(cameras)} cameras -> {root_dir}")
        return {'FINISHED'}
