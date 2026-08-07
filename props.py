"""Scene properties used by FreePencil operators."""

import bpy
import logging
from bpy.props import (
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    EnumProperty,
    BoolProperty,
)

logger = logging.getLogger(__name__)

def _update_line_tuning(self, context):
    """線の感度/チャンネル強さスライダーの即時反映。

    生成済みの FreePencil ノードグループのランプ位置を直接更新する
    (ノードエディタを開かずにサイドバーだけで調整できる)。
    """
    from . import fp_core
    scene = context.scene
    for ng in bpy.data.node_groups:
        if ng.name.startswith(fp_core.NODE_GROUP_PREFIX):
            fp_core.apply_line_tuning(
                ng,
                getattr(scene, "fp_line_sensitivity", 1.0),
                fp_core.channel_strengths_from_scene(scene))


def _update_far_relief(self, context):
    """遠景つぶれ軽減のスライダーを、生成済みノードへ即時反映する。"""
    from . import fp_core
    scene = context.scene
    for ng in bpy.data.node_groups:
        if ng.name.startswith(fp_core.NODE_GROUP_PREFIX):
            fp_core.far_relief_from_scene(ng, scene)


def _update_white_preview(self, context):
    """白マテリアル強制プレビューの ON/OFF(非破壊スワップ)。"""
    from . import fp_core
    scene = context.scene
    n = fp_core.set_white_preview(
        scene, scene.fp_white_preview,
        keep_glass=getattr(scene, "fp_white_keep_glass", True))
    logger.info(f"White preview {'ON' if scene.fp_white_preview else 'OFF'}: "
                f"{n} objects")


def _update_white_keep_glass(self, context):
    """プレビュー中にガラス維持を切り替えたら復元→再適用で反映する。"""
    from . import fp_core
    scene = context.scene
    if scene.fp_white_preview:
        fp_core.set_white_preview(scene, False)
        fp_core.set_white_preview(scene, True,
                                  keep_glass=scene.fp_white_keep_glass)


def register_props():
    """プロパティを登録する関数"""
    scene = bpy.types.Scene

    t = bpy.app.translations.pgettext
    color_type_items = [
        ('mecha_color', t("Mecha Color"), t("Mecha Color")),
        ('mask_color',  t("Mask Color(paint to erase lines)"),
         t("Lines vanish where painted. The brightness does not matter")),
        ('line_color',  t("Line Color(line darkness)"),
         t("Sets how dark the line is. White makes it invisible")),
    ]
    node_type_items = [
        ('test', t("Test Node"), t("Test Node")),
        ('pro',  t("Pro Node"),  t("Pro Node")),
    ]

    props_to_register = {
        "fp_sharp_clear": BoolProperty(
            name="clear sharp",
            description="Erase outline's sharp edges",
            default=False
        ),
        "fp_to_quads": BoolProperty(
            name="to quads",
            description="Join triangles into quads",
            default=False
        ),
        "fp_mat_count": BoolProperty(
            name="material ID",
            description="Add the material ID",
            default=False
        ),
        "fp_sharp_auto": BoolProperty(
            name="Auto edge angle",
            description=(
                "Choose the sharp-edge angle automatically from the mesh's "
                "dihedral-angle distribution (per object)"
            ),
            # 既定OFF: 既存ワークフロー(特にボーン系キャラ)の挙動を変えない。
            # 一括評価パイプラインはプリセットで明示的にONにする。
            default=False
        ),
        "fp_sharp_edges": FloatProperty(
            name="Line sharp edges",
            description="Outline's angle threshold.",
            default=30.0,
            min=0.0,
            max=180.0
        ),
        "fp_seam_boundaries": BoolProperty(
            name="Seam/material boundaries",
            description=(
                "Treat UV seams and material borders as island boundaries "
                "in addition to the edge angle"
            ),
            default=False
        ),
        "fp_min_island_area_pct": FloatProperty(
            name="Min island area %",
            description=(
                "Merge islands smaller than this % of total mesh area "
                "into their largest neighbor (0 = off)"
            ),
            # 既定OFF(0): 既存挙動を変えない。バッチはプリセットで0.02を指定
            default=0.0,
            min=0.0,
            max=5.0,
            step=0.01,
            precision=3
        ),
        "fp_color_type": EnumProperty(
            name="Vertex color type",
            description="Select vertex color type.",
            items=color_type_items,
            default='mecha_color'
        ),
        "fp_node_type": EnumProperty(
            name="Select node type",
            description="Select Node Type",
            items=node_type_items,
            default='test'
        ),
        # Requires Blender 4.3+ for Real-Time Compositor preview
        "fp_enable_compositor_view": BoolProperty(
            name="Enable Compositor Preview",
            description="Enable Compositor Preview",
            default=True
        ),
        "fp_far_relief": FloatProperty(
            name="Far crush relief",
            description=(
                "Thin out lines where they have merged into solid black "
                "(typically the far background of a large set). "
                "0 = off, no change to the image"
            ),
            default=0.0, min=0.0, max=1.0, step=0.05, precision=2,
            update=_update_far_relief
        ),
        "fp_far_relief_radius": FloatProperty(
            name="Relief radius",
            description=(
                "How far to look when measuring how crowded the lines are, "
                "in pixels. Larger = only wide black areas are thinned"
            ),
            default=6.0, min=1.0, max=32.0, step=100, precision=0,
            update=_update_far_relief
        ),
        "fp_far_relief_threshold": FloatProperty(
            name="Relief threshold",
            description=(
                "How crowded an area must be before it is thinned. "
                "Lower = starts working on sparser lines"
            ),
            default=0.35, min=0.05, max=0.95, step=0.05, precision=2,
            update=_update_far_relief
        ),
        "fp_line_sensitivity": FloatProperty(
            name="Line sensitivity",
            description=(
                "Scale the line-detection thresholds inside the node group. "
                "Lower = weaker edges also become solid lines (1.0 = original)"
            ),
            default=1.0,
            min=0.05,
            max=2.0,
            step=0.05,
            precision=2,
            update=_update_line_tuning
        ),
        **{
            f"fp_ch_{ch}": FloatProperty(
                name=f"{label} strength",
                description=(
                    f"Line strength of the {label} channel. "
                    "1.0 = current, higher = more/stronger lines, 0 = off"
                ),
                default=1.0,
                min=0.0,
                max=2.0,
                step=0.05,
                precision=2,
                subtype='FACTOR',
                update=_update_line_tuning
            )
            for ch, label in (
                ("mecha", "Mecha"), ("depth", "Depth"), ("bone", "Bone"),
                ("gen", "Generate"), ("mat", "Material"),
            )
        },
        # STEP0 全自動が適用する項目の個別ON/OFF
        **{
            name: BoolProperty(name=label, description=desc, default=default)
            for name, label, desc, default in (
                ("fp_auto_sharp", "Auto: edge angle",
                 "Full auto sets the sharp-edge angle automatically", True),
                ("fp_auto_seam", "Auto: seam/material boundaries",
                 "Full auto splits islands at UV seams and material borders", True),
                ("fp_auto_merge", "Auto: merge small islands",
                 "Full auto merges tiny islands (0.02%)", True),
                ("fp_auto_part_tint", "Auto: part tint",
                 "Full auto separates touching parts by brightness bands", True),
                ("fp_auto_bone", "Auto: bone AOV by rig detection",
                 "Full auto enables the bone AOV when an armature is found", True),
                ("fp_auto_aa", "Auto: anti-aliasing",
                 "Full auto includes the anti-aliasing node", True),
                ("fp_auto_hashed", "Auto: BLEND to HASHED",
                 "Full auto converts BLEND materials (except real glass) to "
                 "HASHED so AOVs render", True),
                ("fp_auto_supersample", "Auto: 2x supersampling",
                 "Full auto enables 2x render + 50% output scaling. "
                 "Near-essential: FreePencil lines are too thick without it",
                 True),
                ("fp_auto_detect_aov", "Auto: AOVs from scene",
                 "Full auto owns the AOV setup: gen/mask/line follow whether "
                 "those vertex colors are painted, mat follows material ID. "
                 "STEP2 manual toggles are overridden while this is on", True),
                ("fp_auto_file_output", "Auto: enable File Output",
                 "Full auto also enables the STEP3 File Output node", False),
                ("fp_auto_white_preview", "Auto: white material preview",
                 "Full auto turns on the white material preview so the line "
                 "art is visible right after setup. Materials are untouched "
                 "(the compositor is switched); turn it off to see the "
                 "original materials", True),
            )
        },
        "fp_supersample": BoolProperty(
            name="2x supersampling (thin lines)",
            description=(
                "Render at 200% resolution and scale the compositor output "
                "back to 50%, turning 2px lines into crisp 1px lines. "
                "Applies to the Composite output and File Output slots"
            ),
            default=False
        ),
        "fp_white_preview": BoolProperty(
            name="White material preview",
            description=(
                "Temporarily replace all materials with a flat white "
                "emission (AOV-enabled) to preview pure line art. "
                "Original materials are backed up per object and fully "
                "restored when turned off"
            ),
            default=False,
            update=_update_white_preview
        ),
        "fp_white_keep_glass": BoolProperty(
            name="Keep glass transparent",
            description=(
                "While white preview is on, leave real glass materials "
                "(Transmission / low Alpha) untouched so you can still "
                "see through windows"
            ),
            default=True,
            update=_update_white_keep_glass
        ),
        "fp_file_output": BoolProperty(
            name="File Output",
            description=(
                "Add a File Output node to the generated compositor tree "
                "that writes the selected passes as PNGs"
            ),
            default=False
        ),
        # どのパスを書き出すかは個別に選ぶ。影は EEVEE だとノイズが多く
        # 使えないことが多いので既定 OFF、ディフューズ直接光を既定 ON。
        "fp_fo_line": BoolProperty(
            name="Write line pass",
            description="Write the line art to line.png",
            default=True
        ),
        "fp_fo_color": BoolProperty(
            name="Write color pass",
            description="Write the flat color output to color.png",
            default=True
        ),
        "fp_fo_light": BoolProperty(
            name="Write light pass",
            description=(
                "Write the diffuse direct light pass to light.png. "
                "Easier to composite than the shadow pass"
            ),
            default=True
        ),
        "fp_fo_shadow": BoolProperty(
            name="Write shadow pass",
            description=(
                "Write the shadow pass to shadow.png. "
                "EEVEE's shadow pass is often noisy"
            ),
            default=False
        ),
        "fp_file_output_path": bpy.props.StringProperty(
            name="File Output path",
            description="Base path for the File Output node",
            default="//render/",
            subtype='DIR_PATH'
        ),
        "fp_include_antialiasing": BoolProperty(
            name="Include Anti-Aliasing Node",
            description="Insert Anti-Aliasing node before Composite",
            default=False,
        ),
        "fp_gen_color": BoolProperty(
            name="generator color",
            description="AOV Generator Color",
            default=False
        ),
        "fp_mask_color": BoolProperty(
            name="mask color",
            description="AOV Mask Color(White erases lines)",
            default=False
        ),
        "fp_line_color": BoolProperty(
            name="line color",
            description="AOV Line Color",
            default=False
        ),
        "fp_mat_color": BoolProperty(
            name="material color",
            description="AOV Material Boundary Color",
            default=False
        ),
        "fp_bone_color": BoolProperty(
            name="bone color",
            description="AOV Bone Color",
            default=False
        ),
        "fp_color_noise_scale": FloatProperty(
            name="Color noise scale",
            description="Increasing the scale scatters island colors more randomly.",
            default=1.0,
            min=0.01,
            max=10.0,
            step=0.1,
            precision=2,
            subtype='FACTOR'
        ),
        "fp_min_neighbor_color_distance": FloatProperty(
            name="Min color distance",
            description="Minimum RGB distance between neighboring islands (0–1.732). Lower values allow similar colors.",
            default=0.5,
            min=0.0,
            max=1.732,
            step=0.01,
            precision=2
        ),
        "fp_max_color_retries": IntProperty(
            name="Max color retries",
            description="How many times to retry when a color already exists",
            default=30,
            min=1,
            max=200
        ),
        "fp_use_random_seed": BoolProperty(
            name="Random seed each run",
            description=(
                "Generate a new random seed every run. "
                "Turn this off to reproduce exactly the same island colors."
            ),
            default=True
        ),
        "fp_color_seed": IntProperty(
            name="Color seed",
            description=(
                "Seed for island color generation. "
                "The same seed with the same mesh reproduces the same colors."
            ),
            default=0,
            min=0,
            max=2147483647
        ),
        "fp_bone_grouping_mode": EnumProperty(
            name=t("Bone color grouping"),
            description=t("How to group bone names when coloring bone_color"),
            items=[
                ('exact', t("Exact"), t("Use the bone/vertex-group name as-is")),
                ('basename', t("Basename (.###)"), t("Treat suffix like .001 as the same")),
                ('stripdigits', t("Strip trailing digits"), t("Ignore trailing digits even without dot")),
            ],
            default='basename',
        ),
        "fp_part_tint": BoolProperty(
            name="Part tint (mecha color)",
            description=(
                "Give touching parts (objects) different brightness bands "
                "in mecha_color so part boundaries (hairline, collar) become "
                "lines; bone_color stays a pure weight blend and the node "
                "composites both channels"
            ),
            default=True
        ),
        "fp_bone_hard_names": bpy.props.StringProperty(
            name="Hard boundary bones",
            description=(
                "Comma-separated bone names whose region boundary should be "
                "a hard step in bone_color (so a line appears there, e.g. "
                "'head' for a chin line). Empty = all soft blending"
            ),
            default=""
        ),
        "fp_half_color": FloatVectorProperty(
            name="Half mask color",
            description="Color used by Half Fill",
            subtype='COLOR',
            size=4,
            min=0.0,
            max=1.0,
            default=(1.0, 0.0, 0.0, 1.0)
        )
    }

    for prop_name, prop_value in props_to_register.items():
        if not hasattr(bpy.types.Scene, prop_name):
            setattr(scene, prop_name, prop_value)
            logger.info(f"Registered property: {prop_name}")
        else:
            logger.info(f"Property already exists: {prop_name}")

    # カメラ一括レンダリング対象のチェック(オブジェクト単位)
    if not hasattr(bpy.types.Object, "fp_cam_render"):
        bpy.types.Object.fp_cam_render = BoolProperty(
            name="Render this camera",
            description=(
                "Include this camera in FreePencil's "
                "'Render checked cameras' batch"
            ),
            default=True
        )

def unregister_props():
    """プロパティを解除する関数"""
    scene = bpy.types.Scene
    props_to_clear = [
        "fp_sharp_edges", "fp_sharp_auto", "fp_seam_boundaries",
        "fp_min_island_area_pct", "fp_to_quads", "fp_sharp_clear",
        "fp_color_type", "fp_mat_count",
        "fp_gen_color", "fp_mask_color", "fp_line_color",
        "fp_mat_color", "fp_bone_color", "fp_enable_compositor_view",
        "fp_include_antialiasing", "fp_line_sensitivity",
        "fp_far_relief", "fp_far_relief_radius", "fp_far_relief_threshold",
        "fp_ch_mecha", "fp_ch_depth", "fp_ch_bone", "fp_ch_gen", "fp_ch_mat",
        "fp_file_output", "fp_file_output_path",
        "fp_fo_line", "fp_fo_color", "fp_fo_light", "fp_fo_shadow",
        "fp_white_preview", "fp_white_keep_glass", "fp_supersample",
        "fp_auto_sharp", "fp_auto_seam", "fp_auto_merge", "fp_auto_part_tint",
        "fp_auto_bone", "fp_auto_aa", "fp_auto_hashed", "fp_auto_file_output",
        "fp_auto_detect_aov", "fp_auto_supersample", "fp_auto_white_preview",
        "fp_color_noise_scale", "fp_min_neighbor_color_distance",
        "fp_max_color_retries",
        "fp_use_random_seed", "fp_color_seed",
        "fp_bone_grouping_mode", "fp_bone_hard_names", "fp_part_tint",
        "fp_node_type",
        "fp_half_color"
    ]
    
    for prop_name in props_to_clear:
        if hasattr(scene, prop_name):
            try:
                delattr(scene, prop_name)
                logger.info(f"Cleared property: {prop_name}")
            except AttributeError:
                logger.exception(f"Failed to clear property: {prop_name}")
        else:
            logger.info(f"Property does not exist: {prop_name}")

    if hasattr(bpy.types.Object, "fp_cam_render"):
        try:
            delattr(bpy.types.Object, "fp_cam_render")
        except AttributeError:
            logger.exception("Failed to clear property: fp_cam_render")
