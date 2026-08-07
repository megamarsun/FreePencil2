"""UI panels for accessing FreePencil tools.

構成: 親パネル(FreePencil) + 折りたたみ可能なサブパネル
  STEP1 頂点カラー / STEP2 AOV / STEP3 ノード生成 /
  カメラ一括レンダリング / STEP4 手動塗り
"""

import bpy

from . import ADDON_VERSION
from . import compat

from .vertex_color import LINK_MAKE_OT_FP, FREEPENCIL_OT_randomize_seed
from .sample_node import LINK_MAKE_FP_OT_NODE
from .aov_node import LINK_MAKE_FP_OT_AOV_NODE
from .paint_vertex_color import LINK_MAKE_FP_OT_VCOLOR
from .half_fill import LINK_MAKE_FP_OT_HALF_FILL
from .render_cameras import FP_OT_RENDER_CAMERAS
from .auto_setup import FP_OT_AUTO_SETUP


class FP_PT_Line(bpy.types.Panel):
    """Main sidebar panel (parent of the collapsible sections)."""

    bl_label = f"FreePencil v{'.'.join(map(str, ADDON_VERSION))}"
    bl_idname = "FREEPENCIL_PT_LINE"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "FreePencil"

    def draw(self, context):
        # 4.2 は限定対応。レンダリングは動くがライブプレビューが出ないので、
        # 黙っていると「壊れている」と受け取られる。最初に伝える。
        if not compat.HAS_AOV_IN_VIEWPORT_COMPOSITOR:
            t = bpy.app.translations.pgettext
            box = self.layout.box()
            col = box.column(align=True)
            col.label(text=t("Limited support on this Blender"), icon="INFO")
            col.label(text=t("Render with F12. Live preview needs 4.3+."))


class _FPSub:
    """Mixin: common settings for FreePencil sub-panels.

    注意: 自動登録(toposort)は登録順を保証しないため、表示順は
    bl_order で明示的に固定する(登録順に依存すると毎回シャッフルされる)。
    """

    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "FreePencil"
    bl_parent_id = "FREEPENCIL_PT_LINE"
    # 初期状態は STEP0(全自動)だけ開く。STEP1〜5 は通常の手順では
    # 触らないので、全部開いていると縦に長くなり STEP0 が埋もれる。
    # DEFAULT_CLOSED が効くのは初回表示時だけで、以降はユーザーの
    # 開閉状態が .blend 側に保存される。
    bl_options = {"DEFAULT_CLOSED"}


class FP_PT_Step0(_FPSub, bpy.types.Panel):
    bl_label = "STEP0: Full Auto"
    bl_idname = "FREEPENCIL_PT_STEP0"
    bl_order = 0
    bl_options = set()  # ここだけ既定で開く

    def draw(self, context):
        t = bpy.app.translations.pgettext
        layout = self.layout
        scene = context.scene
        col = layout.column(align=True)
        col.label(text=t("Recommended settings for this scene"), icon="INFO")
        col = layout.column(align=True)
        col.prop(scene, "fp_auto_sharp", text=t("Auto edge angle"))
        col.prop(scene, "fp_auto_seam", text=t("Seam/material boundaries"))
        col.prop(scene, "fp_auto_merge", text=t("Merge small islands"))
        col.prop(scene, "fp_auto_part_tint", text=t("Part tint"))
        col.prop(scene, "fp_auto_bone", text=t("Bone AOV by rig detection"))
        col.prop(scene, "fp_auto_aa", text=t("Anti-aliasing"))
        col.prop(scene, "fp_auto_supersample",
                 text=t("2x supersampling (thin lines)"))
        col.prop(scene, "fp_auto_hashed", text=t("BLEND to HASHED (keep glass)"))
        col.prop(scene, "fp_auto_detect_aov", text=t("Auto AOVs from scene"))
        col.prop(scene, "fp_auto_white_preview",
                 text=t("White material preview"))
        col.prop(scene, "fp_auto_file_output", text=t("Enable File Output"))
        layout.operator(FP_OT_AUTO_SETUP.bl_idname,
                        text=t("Auto setup (STEP1-3)"), icon="AUTO")


class FP_PT_Step1(_FPSub, bpy.types.Panel):
    bl_label = "STEP1: Auto Vertex Color"
    bl_idname = "FREEPENCIL_PT_STEP1"
    bl_order = 1

    def draw(self, context):
        t = bpy.app.translations.pgettext
        layout = self.layout
        scene = context.scene

        col = layout.column(align=True)
        col.prop(scene, "fp_to_quads", text=t("This to Quads"))
        col.prop(scene, "fp_mat_count", text=t("Add the material ID"))

        # --- 島分割 ---
        box = layout.box()
        box.label(text=t("Island split:"), icon="MOD_EDGESPLIT")
        col = box.column(align=True)
        col.prop(scene, "fp_sharp_auto", text=t("Auto edge angle"))
        row = col.row(align=True)
        row.enabled = not scene.fp_sharp_auto
        row.prop(scene, "fp_sharp_edges", slider=True, text=t("Edge Angle"))
        col.prop(scene, "fp_seam_boundaries", text=t("Seam/material boundaries"))
        col.prop(scene, "fp_min_island_area_pct", text=t("Min island area %"))

        # --- ボーン(キャラ用) ---
        box = layout.box()
        box.label(text=t("Bone options:"), icon="BONE_DATA")
        col = box.column(align=True)
        col.prop(scene, "fp_bone_grouping_mode", text=t("Bone grouping"))
        col.prop(scene, "fp_bone_hard_names", text=t("Hard boundary bones"))
        col.prop(scene, "fp_part_tint", text=t("Part tint (mecha color)"))

        # --- 配色シード(再現性) ---
        box = layout.box()
        box.label(text=t("Color seed:"), icon="FILE_REFRESH")
        col = box.column(align=True)
        col.prop(scene, "fp_use_random_seed", text=t("Random seed each run"))
        row = col.row(align=True)
        row.enabled = not scene.fp_use_random_seed
        row.prop(scene, "fp_color_seed", text=t("Seed"))
        row.operator(FREEPENCIL_OT_randomize_seed.bl_idname,
                     text="", icon="FILE_REFRESH")

        layout.operator(LINK_MAKE_OT_FP.bl_idname,
                        text=t("Separate Paint Vertex Colors"),
                        icon="MESH_CUBE")


class FP_PT_Step2(_FPSub, bpy.types.Panel):
    bl_label = "STEP2: AOV"
    bl_idname = "FREEPENCIL_PT_STEP2"
    bl_order = 2

    def draw(self, context):
        t = bpy.app.translations.pgettext
        layout = self.layout
        scene = context.scene

        col = layout.column(align=True)
        col.prop(scene, "fp_bone_color", text=t("AOV Bone Color"))
        col.prop(scene, "fp_gen_color", text=t("AOV Generate Color"))
        col.prop(scene, "fp_mask_color",
                 text=t("AOV Mask Color(paint to erase lines)"))
        col.prop(scene, "fp_line_color",
                 text=t("AOV Line Color(line darkness)"))
        col.prop(scene, "fp_mat_color", text=t("AOV Material Boundary Color"))
        layout.operator(LINK_MAKE_FP_OT_AOV_NODE.bl_idname,
                        text=t("Generate AOV Node"), icon="NODETREE")


class FP_PT_Step3(_FPSub, bpy.types.Panel):
    bl_label = "STEP3: Node Generation"
    bl_idname = "FREEPENCIL_PT_STEP3"
    bl_order = 3

    def draw(self, context):
        t = bpy.app.translations.pgettext
        layout = self.layout
        scene = context.scene

        col = layout.column(align=True)
        col.prop(scene, "fp_node_type", text=t("Select Node Type"))
        # 4.2 のビューポートコンポジタは AOV を評価しないので、ONにしても
        # プレビューは出ない。触れるままにすると誤解を招くため無効化する
        row = col.row(align=True)
        row.enabled = compat.HAS_AOV_IN_VIEWPORT_COMPOSITOR
        row.prop(scene, "fp_enable_compositor_view",
                 text=t("Enable Compositor Preview"))
        if not compat.HAS_AOV_IN_VIEWPORT_COMPOSITOR:
            col.label(text=t("Live preview needs Blender 4.3+"), icon="INFO")
        col.prop(scene, "fp_white_preview",
                 text=t("White material preview"), icon="MATERIAL",
                 toggle=True)
        col.prop(scene, "fp_include_antialiasing",
                 text=t("Include Anti-Aliasing Node"))
        col.prop(scene, "fp_supersample",
                 text=t("2x supersampling (thin lines)"))
        col.prop(scene, "fp_line_sensitivity", text=t("Line sensitivity"))

        # 遠景で線が黒ベタにつぶれるのを軽減する(0 で無効=画は変わらない)
        box = layout.box()
        box.label(text=t("Far crush relief:"), icon="MOD_SMOOTH")
        col = box.column(align=True)
        col.prop(scene, "fp_far_relief", text=t("Amount"), slider=True)
        sub = col.column(align=True)
        sub.enabled = scene.fp_far_relief > 0.0
        sub.prop(scene, "fp_far_relief_radius", text=t("Radius (px)"))
        sub.prop(scene, "fp_far_relief_threshold", text=t("Threshold"),
                 slider=True)

        # チャンネル別の線の強さ(生成済みノードへ即時反映)
        box = layout.box()
        box.label(text=t("Line strength per channel:"), icon="MOD_LINEART")
        col = box.column(align=True)
        col.prop(scene, "fp_ch_depth", text=t("Depth"), slider=True)
        col.prop(scene, "fp_ch_mecha", text=t("Mecha"), slider=True)
        col.prop(scene, "fp_ch_bone", text=t("Bone"), slider=True)
        col.prop(scene, "fp_ch_mat", text=t("Material"), slider=True)
        col.prop(scene, "fp_ch_gen", text=t("Generate"), slider=True)

        box = layout.box()
        box.label(text=t("File Output"), icon="FILE_FOLDER")
        col = box.column(align=True)
        col.prop(scene, "fp_file_output", text=t("Enable File Output"))

        sub = col.column(align=True)
        sub.enabled = scene.fp_file_output
        sub.prop(scene, "fp_file_output_path", text=t("Output path"))
        # 書き出すパスを個別に選ぶ。チェック名がそのままファイル名になる
        sub.label(text=t("Passes to write:"))
        grid = sub.grid_flow(columns=2, align=True)
        grid.prop(scene, "fp_fo_line", text="line")
        grid.prop(scene, "fp_fo_color", text="color")
        grid.prop(scene, "fp_fo_light", text=t("light (diffuse)"))
        grid.prop(scene, "fp_fo_shadow", text=t("shadow"))
        if scene.fp_file_output and not any(
            getattr(scene, name)
            for name in ("fp_fo_line", "fp_fo_color",
                         "fp_fo_light", "fp_fo_shadow")
        ):
            col.label(text=t("No pass selected"), icon="ERROR")

        layout.operator(LINK_MAKE_FP_OT_NODE.bl_idname,
                        text=t("Generate Sample Node"), icon="NODETREE")


class FP_PT_Cameras(_FPSub, bpy.types.Panel):
    bl_label = "STEP5: Camera Batch Render"
    bl_idname = "FREEPENCIL_PT_CAMERAS"
    bl_order = 5

    def draw(self, context):
        t = bpy.app.translations.pgettext
        layout = self.layout
        scene = context.scene

        cams = sorted((o for o in scene.objects if o.type == "CAMERA"),
                      key=lambda o: o.name.lower())
        if not cams:
            layout.label(text=t("No cameras in scene"), icon="INFO")
            return
        col = layout.column(align=True)
        for cam in cams:
            row = col.row(align=True)
            row.prop(cam, "fp_cam_render", text="")
            icon = ("OUTLINER_OB_CAMERA" if cam == scene.camera
                    else "CAMERA_DATA")
            row.label(text=cam.name, icon=icon)
        layout.operator(FP_OT_RENDER_CAMERAS.bl_idname,
                        text=t("Render checked cameras"), icon="RENDER_STILL")


class FP_PT_Step4(_FPSub, bpy.types.Panel):
    bl_label = "STEP4: Manual Vertex Color"
    bl_idname = "FREEPENCIL_PT_STEP4"
    bl_order = 4

    def draw(self, context):
        t = bpy.app.translations.pgettext
        layout = self.layout
        scene = context.scene

        layout.prop(scene, "fp_color_type", text=t("Vertex Color Type"))
        layout.operator(LINK_MAKE_FP_OT_VCOLOR.bl_idname,
                        text=t("Paint Vertex Color"), icon="VPAINT_HLT")

        box = layout.box()
        box.label(text=t("Vertex-color options:"), icon="COLOR")
        col = box.column(align=True)
        col.prop(scene, "fp_color_noise_scale",
                 text=t("Color noise scale"), slider=True)
        col.prop(scene, "fp_min_neighbor_color_distance",
                 text=t("Min color distance"))
        col.prop(scene, "fp_max_color_retries", text=t("Max color retries"))

        row = layout.row(align=True)
        row.prop(scene, "fp_half_color", text="")
        row.operator(LINK_MAKE_FP_OT_HALF_FILL.bl_idname,
                     text=t("Half Fill"), icon="BRUSH_DATA")


class FP_PT_CompositorOptions(bpy.types.Panel):
    """Panel for FreePencil options in the Compositor node editor."""

    bl_label = "FreePencil"
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "FreePencil"

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return bool(space and space.tree_type == "CompositorNodeTree")

    def draw(self, context):
        layout = self.layout
        layout.prop(
            context.scene,
            "fp_include_antialiasing",
            text=bpy.app.translations.pgettext("Include Anti-Aliasing Node"),
        )
