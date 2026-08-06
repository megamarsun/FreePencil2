"""配布ページ用の作例レンダーを出す。

dev/batch/fp_batch.py の検証済みパイプラインをそのまま使い、同じシーン・
同じカメラから 2 枚を書き出す:

  <name>_line.png   最終線画 (白マテリアル + PROコンポジタ)
  <name>_paint.png  塗り分けの状態 (mecha_color 頂点カラーをそのまま表示)

使い方:
  blender -b --factory-startup --python render_samples.py -- \
      --blend <asset.blend> --name mecha --out out --res 1600
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
BATCH_DIR = HERE.parent / "batch"
sys.path.insert(0, str(BATCH_DIR))

import fp_batch  # noqa: E402


def parse_args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--blend", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--out", default=str(HERE / "out"))
    p.add_argument("--res", type=int, default=1600)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--preset", default="default")
    return p.parse_args(argv)


def vcol_preview_material(meshes) -> None:
    """全メッシュを mecha_color 頂点カラーのフラット表示に差し替える。

    Emission なのでライティングの影響を受けず、塗り分けの色そのものが出る。
    """
    mat = bpy.data.materials.new("FP_VColPreview")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_type = "GEOMETRY"
    attr.attribute_name = "mecha_color"
    attr.location = (-300, 0)
    emit = nt.nodes.new("ShaderNodeEmission")
    emit.inputs["Strength"].default_value = 1.0
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (200, 0)
    nt.links.new(attr.outputs["Color"], emit.inputs["Color"])
    nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    for o in meshes:
        o.data.materials.clear()
        o.data.materials.append(mat)


def stage_model(blend: Path):
    """アセットを読み込み、外れジオメトリを落として正規化する。"""
    objs, others = fp_batch.append_objects(blend)
    if not objs:
        raise RuntimeError("no mesh objects in asset")

    shape_names = set()
    for a in others:
        if a.type == "ARMATURE" and a.pose:
            for pb in a.pose.bones:
                if pb.custom_shape is not None:
                    shape_names.add(pb.custom_shape.name)
    for o in objs:
        if o.name in shape_names or o.name.lower().startswith(
                ("cs_", "wgt", "shape_")):
            o.hide_render = True

    content = [o for o in objs if not o.hide_render] or objs
    cluster = fp_batch.dominant_cluster(content)
    for o in content:
        if o not in cluster:
            o.hide_render = True
    framed = [o for o in content if o in cluster] or content
    fp_batch.normalize(objs + others, framed)
    return objs, others


def apply_preset(scene, preset: dict, seed: int, has_armature: bool) -> None:
    scene.fp_use_random_seed = False
    scene.fp_color_seed = seed
    scene.fp_sharp_auto = preset.get("sharp_auto", False)
    scene.fp_sharp_edges = preset["sharp_edges"]
    scene.fp_color_noise_scale = preset["color_noise_scale"]
    scene.fp_min_neighbor_color_distance = preset["min_neighbor_color_distance"]
    scene.fp_max_color_retries = preset["max_color_retries"]
    scene.fp_to_quads = preset.get("to_quads", False)
    scene.fp_sharp_clear = preset.get("sharp_clear", False)
    scene.fp_min_island_area_pct = preset.get("min_island_area_pct", 0.02)
    scene.fp_bone_color = preset.get("bone_color", has_armature)
    scene.fp_bone_grouping_mode = preset.get("bone_grouping", "basename")
    scene.fp_bone_hard_names = preset.get("bone_hard_names", "")
    scene.fp_part_tint = preset.get("part_tint", True)
    scene.fp_seam_boundaries = preset.get("seam_boundaries", False)
    scene.fp_line_sensitivity = preset.get("line_sensitivity", 1.0)
    scene.fp_include_antialiasing = preset.get("antialiasing", True)
    scene.fp_node_type = "pro"
    scene.fp_enable_compositor_view = False


def main() -> None:
    args = parse_args()
    # Blender の Image.save / render.filepath は相対パスを CWD 以外の基準で
    # 解決することがあり、書き出し先が消える。必ず絶対パスにする。
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    rec: dict = {"name": args.name, "blend": args.blend,
                 "blender": bpy.app.version_string}
    t0 = time.time()

    preset = json.loads((BATCH_DIR / "presets.json").read_text(
        encoding="utf-8"))[args.preset]

    bpy.ops.wm.read_homefile(use_empty=True)
    fp_batch.install_addon()
    scene = bpy.context.scene

    objs, others = stage_model(Path(args.blend))
    rec["mesh_objects"] = len(objs)
    rec["faces_total"] = int(sum(len(o.data.polygons) for o in objs))
    has_armature = (any(o.type == "ARMATURE" for o in others)
                    or any(m.type == "ARMATURE" and m.object
                           for o in objs for m in o.modifiers))
    fp_batch.apply_white_material(objs)
    apply_preset(scene, preset, args.seed, has_armature)

    fp_batch.select_meshes()
    t1 = time.time()
    bpy.ops.freepencil.auto_vertex_color()
    rec["step1_seconds"] = round(time.time() - t1, 2)
    objs = fp_batch.select_meshes()
    bpy.ops.freepencil4.link_button()
    bpy.ops.freepencil2.link_button()

    fp_batch.setup_camera_and_light()
    scene.render.engine = fp_batch.eevee_engine()
    scene.eevee.taa_render_samples = 8
    ss = 2
    scene.render.resolution_x = args.res * ss
    scene.render.resolution_y = args.res * ss
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"

    line_png = out_dir / f"{args.name}_line.png"
    t2 = time.time()
    fp_batch.render_still(scene, line_png, ss)
    rec["line_seconds"] = round(time.time() - t2, 2)
    rec["line_metrics"] = fp_batch.lineart_metrics(line_png)

    # 塗り分けの見た目: コンポジタを外し、頂点カラーをそのまま出す
    if hasattr(scene, "compositing_node_group"):   # 5.x
        scene.compositing_node_group = None
    if hasattr(scene, "use_nodes"):                # 4.5
        scene.use_nodes = False
    vcol_preview_material(objs)
    paint_png = out_dir / f"{args.name}_paint.png"
    t3 = time.time()
    fp_batch.render_still(scene, paint_png, ss)
    rec["paint_seconds"] = round(time.time() - t3, 2)

    rec["total_seconds"] = round(time.time() - t0, 2)
    (out_dir / f"{args.name}_render.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[render_samples] " + json.dumps(rec, ensure_ascii=False))


if __name__ == "__main__":
    main()
