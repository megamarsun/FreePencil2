"""UI panels for accessing FreePencil tools.

構成: 親パネル(FreePencil) + 折りたたみ可能なサブパネル
  STEP1 頂点カラー / STEP2 AOV / STEP3 ノード生成 /
  カメラ一括レンダリング / STEP4 手動塗り
"""

import bpy

from . import ADDON_VERSION, version_label
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

    bl_label = f"FreePencil v{version_label()}"
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
        layout.prop(scene, "fp_auto_style", text=t("Finish"))
        # 選んでいるオブジェクトの塗り方(手描き系の仕上がりで効く)
        obj = context.active_object
        if obj is not None and obj.type == 'MESH':
            box = layout.box()
            box.enabled = scene.fp_auto_style != 'PRECISE'
            box.prop(obj, "fp_paint_as", text=t("Paint as"))
            kind = obj.get("fp_paint_auto")
            if obj.fp_paint_as == 'AUTO' and kind:
                label = t("Mecha") if kind == 'MECHA' else t("Character")
                box.label(text=t("Auto result: ") + label, icon="INFO")
        layout.operator(FP_OT_AUTO_SETUP.bl_idname,
                        text=t("Auto setup (STEP1-3)"), icon="AUTO")
        # STEP0〜3 で足したものを消し、元の設定へ戻す(v2.8.3)。確認を出してから。
        # 全自動セットアップのすぐ下に並べると押し間違えるので、間を空ける
        layout.separator(factor=1.5)
        layout.operator("freepencil.remove", text=t("Remove FreePencil"), icon="TRASH")


class FP_PT_Step0Options(bpy.types.Panel):
    """STEP0 の詳細。どれも既定のままでよいので閉じておく。"""

    bl_label = "Details"
    bl_idname = "FREEPENCIL_PT_STEP0_OPTIONS"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "FreePencil"
    bl_parent_id = "FREEPENCIL_PT_STEP0"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        t = bpy.app.translations.pgettext
        scene = context.scene
        col = self.layout.column(align=True)
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


class FP_PT_Step1(_FPSub, bpy.types.Panel):
    bl_label = "STEP1: Auto Vertex Color"
    bl_idname = "FREEPENCIL_PT_STEP1"
    bl_order = 1

    def draw(self, context):
        t = bpy.app.translations.pgettext
        layout = self.layout
        scene = context.scene

        col = layout.column(align=True)
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
        # 遠い区画をまとめる(手描き背景の STEP0 で 500)。STEP1 で効く
        col.prop(scene, "fp_far_lod_px", text=t("Merge far islands (px)"))
        # 稜線の起伏・葉の房は STEP0 が仕上がりごとに決める(v2.8.1 でパネルから外した)

        # --- ボーン(キャラ用) ---
        box = layout.box()
        box.label(text=t("Bone options:"), icon="BONE_DATA")
        col = box.column(align=True)
        col.label(text=t("Bone grouping"))
        col.prop(scene, "fp_bone_grouping_mode", text="")
        col.label(text=t("Hard boundary bones"))
        col.prop(scene, "fp_bone_hard_names", text="")
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

        # v2.8.1 で整理: 普段触るものだけ出し、残りは「詳細」に畳む。
        # STEP0 がほぼ全部を決めるので、ここは見ながら加減するつまみだけ
        col = layout.column(align=True)
        # 4.2 のビューポートコンポジタは AOV を評価しないので、ONにしても
        # プレビューは出ない。触れるままにすると誤解を招くため無効化する
        row = col.row(align=True)
        row.enabled = compat.HAS_AOV_IN_VIEWPORT_COMPOSITOR
        row.prop(scene, "fp_enable_compositor_view",
                 text=t("Enable Compositor Preview"))
        if not compat.HAS_AOV_IN_VIEWPORT_COMPOSITOR:
            col.label(text=t("Live preview needs Blender 4.3+"), icon="INFO")
        # プレビューの種類。どれも「線の下に何を敷くか」の違いで、
        # マテリアルには触らない
        box = layout.box()
        box.label(text=t("Preview:"), icon="MATERIAL")
        box.prop(scene, "fp_preview_mode", expand=True)
        if scene.fp_preview_mode == 'CEL':
            col = box.column(align=True)
            col.prop(scene, "fp_cel_threshold", text=t("Shadow threshold"), slider=True)
            col.prop(scene, "fp_cel_softness", text=t("Smooth shadow edges"))
            col.prop(scene, "fp_cel_pale", text=t("Paleness"), slider=True)
            row = box.row(align=True)
            row.prop(scene, "fp_cel_shadow_color", text=t("Shadow color"))
            row = box.row(align=True)
            row.prop(scene, "fp_cel_sky", text=t("Sky color"))
            sub = row.row(align=True)
            sub.enabled = scene.fp_cel_sky
            sub.prop(scene, "fp_cel_sky_color", text="")
            row = box.row(align=True)
            row.prop(scene, "fp_cel_shadow_line", text=t("Shadow line"))
            sub = row.row(align=True)
            sub.enabled = scene.fp_cel_shadow_line
            sub.prop(scene, "fp_cel_shadow_line_color", text="")
            sub.prop(scene, "fp_cel_shadow_line_width", text=t("Width"))
        if scene.fp_preview_mode == 'MONO_LIGHT':
            box.prop(scene, "fp_mono_floor", text=t("Shadow floor"),
                     slider=True)

        # 線の強弱(入り抜き)。くぼみが深いほど太くする
        box = layout.box()
        box.label(text=t("Line weight (cavities):"), icon="MOD_THICKNESS")
        col = box.column(align=True)
        col.prop(scene, "fp_line_weight", text=t("Line weight from cavities"))
        sub = col.column(align=True)
        sub.enabled = scene.fp_line_weight
        sub.prop(scene, "fp_lw_strength", text=t("Weight strength"),
                 slider=True)
        # 細い線はメカの塗り(fine_color)が無いと何も起きない。手描き背景の
        # STEP0 だけが作るので、無いときは灰色にして作り方を出す(総当りで、
        # キャラでは動かしても絵が変わらないことが分かった)
        obj = context.active_object
        has_fine = (obj is not None and obj.type == 'MESH'
                    and "fine_color" in obj.data.color_attributes)
        row = sub.row(align=True)
        row.enabled = has_fine
        row.prop(scene, "fp_fine_lines", text=t("Fine lines"), slider=True)
        if not has_fine:
            sub.label(text=t("Fine lines: run STEP0 with Background"), icon="INFO")
        # 奥の扱いとつぶれ軽減は、中の5つをまとめた2本(props.far_values /
        # relief_values)。1.0 が手描き背景の既定
        sub.prop(scene, "fp_lw_far_amount", text=t("Far lines"), slider=True)
        sub.prop(scene, "fp_lw_relief", text=t("Crush relief"), slider=True)
        # しきい値は絵ごとに15倍ひらくので固定値では配れない。STEP0 が
        # 1回測る。カメラを変えたときだけ押し直す
        sub.operator("freepencil.measure_line_weight",
                     text=t("Measure thresholds (once per cut)"),
                     icon="DRIVER_DISTANCE")

        layout.operator(LINK_MAKE_FP_OT_NODE.bl_idname,
                        text=t("Generate Sample Node"), icon="NODETREE")


class FP_PT_Step3Options(bpy.types.Panel):
    """STEP3 の詳細。STEP0 が決めるので普段は触らない(閉じておく)。"""

    bl_label = "Details"
    bl_idname = "FREEPENCIL_PT_STEP3_OPTIONS"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "FreePencil"
    bl_parent_id = "FREEPENCIL_PT_STEP3"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        t = bpy.app.translations.pgettext
        layout = self.layout
        scene = context.scene
        col = layout.column(align=True)
        col.label(text=t("Select Node Type"))
        col.prop(scene, "fp_node_type", text="")
        col = layout.column(align=True)
        col.prop(scene, "fp_include_antialiasing",
                 text=t("Include Anti-Aliasing Node"))
        col.prop(scene, "fp_supersample",
                 text=t("2x supersampling (thin lines)"))
        if scene.fp_supersample:
            # 2倍で出ることを先に言っておく。黙っていると「指定と違う
            # 大きさで出る」と受け取られる
            info = col.column(align=True)
            info.label(text=t("F12 renders at 2x."), icon="INFO")
            info.label(text=t("STEP5 writes the final size."), icon="BLANK1")
        col.prop(scene, "fp_line_sensitivity", text=t("Line sensitivity"))

        box = layout.box()
        box.label(text=t("Line weight (cavities):"), icon="MOD_THICKNESS")
        col = box.column(align=True)
        col.enabled = scene.fp_line_weight
        col.prop(scene, "fp_lw_ink", text=t("Ink darkness"), slider=True)
        col.prop(scene, "fp_lw_soften", text=t("Soften edges"), slider=True)
        col.prop(scene, "fp_gap_fill", text=t("Fill leaf gaps"))
        # 既定 0(v2.8.3)。低い視点の横縞のモアレが気になるときだけ入れる
        col.prop(scene, "fp_lw_stripe_fade", text=t("Fade fine stripes"), slider=True)

        # チャンネル別の線の強さ(生成済みノードへ即時反映)
        box = layout.box()
        box.label(text=t("Line strength per channel:"), icon="MOD_LINEART")
        col = box.column(align=True)
        col.prop(scene, "fp_ch_depth", text=t("Depth"), slider=True)
        col.prop(scene, "fp_ch_mecha", text=t("Mecha"), slider=True)
        col.prop(scene, "fp_ch_bone", text=t("Bone"), slider=True)
        col.prop(scene, "fp_ch_mat", text=t("Material"), slider=True)
        col.prop(scene, "fp_ch_gen", text=t("Generate"), slider=True)


def draw_file_output(layout, scene, t):
    """書き出しの設定。STEP5(カメラ一括)が使うので STEP5 に置く。"""
    box = layout.box()
    box.label(text=t("File Output"), icon="FILE_FOLDER")
    col = box.column(align=True)
    col.prop(scene, "fp_file_output", text=t("Enable File Output"))
    sub = col.column(align=True)
    sub.enabled = scene.fp_file_output
    sub.label(text=t("Output path"))
    sub.prop(scene, "fp_file_output_path", text="")
    # 書き出すパスを個別に選ぶ。チェック名がそのままファイル名になる
    sub.label(text=t("Passes to write:"))
    grid = sub.grid_flow(columns=2, align=True)
    grid.prop(scene, "fp_fo_line", text="line")
    grid.prop(scene, "fp_fo_color", text="color")
    grid.prop(scene, "fp_fo_light", text=t("light (diffuse)"))
    grid.prop(scene, "fp_fo_shadow", text=t("shadow"))
    grid.prop(scene, "fp_fo_cel_color", text=t("cel color"))
    grid.prop(scene, "fp_fo_cel_shadow", text=t("cel shadow"))
    if scene.fp_file_output and not any(
        getattr(scene, name)
        for name in ("fp_fo_line", "fp_fo_color", "fp_fo_light", "fp_fo_shadow",
                     "fp_fo_cel_color", "fp_fo_cel_shadow")
    ):
        col.label(text=t("No pass selected"), icon="ERROR")
    if scene.fp_file_output:
        col.label(text=t("Press STEP3 after changing these"), icon="INFO")


class FP_PT_Cameras(_FPSub, bpy.types.Panel):
    bl_label = "STEP5: Camera Batch Render"
    bl_idname = "FREEPENCIL_PT_CAMERAS"
    bl_order = 5

    def draw(self, context):
        t = bpy.app.translations.pgettext
        layout = self.layout
        scene = context.scene

        # 書き出しの設定(v2.8.1 で STEP3 から移した。使うのはこのボタン)
        draw_file_output(layout, scene, t)
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

        layout.label(text=t("Vertex Color Type"))
        layout.prop(scene, "fp_color_type", text="")
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
