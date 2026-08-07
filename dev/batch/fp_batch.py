"""Headless FreePencil pipeline for one BlenderKit model.

Called by run_batch.py (or manually):
    blender -b --factory-startup -P fp_batch.py -- --blend <path> --name <id>
            --seed 42 --preset default --out <out_dir>

Steps:
  1. Empty scene, append mesh objects from the asset .blend, normalize size.
  2. STEP1 auto vertex color via the real operator (fixed seed).
  3. STEP2 AOV setup   via the real operator (freepencil4.link_button).
  4. STEP3 PRO node    via the real operator (freepencil2.link_button).
  5. Render line art PNG + compute metrics -> out/metrics/<name>.json

STEP2/3 operators are headless-safe since the fp_core refactor: all core
logic lives in freepencil2/fp_core.py and the operators skip UI-only work
in background mode. This file therefore exercises the exact same code
path a UI user gets.

The repo folder name (22_FreePencil) starts with a digit and cannot be
imported directly, so install_addon() exposes it through a directory
junction %TEMP%/fp_addon_pkg/freepencil2 -> repo (created once, no admin
required). The add-on always loads live from the repo - nothing to keep
in sync. Falls back to a full copy if the junction cannot be created.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

import bpy

REPO = Path(__file__).resolve().parents[2]  # .../22_FreePencil
ADDON_NAME = "freepencil2"
NODE_GROUP_PRO = "FreePencil_v1_1_0_pro"
EXCLUDE_DIRS = {".git", ".github", "__pycache__", "old_ver", "dev"}


# ---------------------------------------------------------------- utilities
def parse_args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--blend", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--preset", default="default")
    p.add_argument("--out", required=True)
    p.add_argument("--res", type=int, default=1024)
    p.add_argument("--material", choices=["white", "keep"], default="white",
                   help="white: strip all materials and use flat white emission "
                        "(clean ink metrics); keep: leave asset materials as-is")
    p.add_argument("--supersample", type=int, default=2,
                   help="render at N x resolution and box-downscale to --res "
                        "(antialiased thin lines). 1 = off")
    p.add_argument("--turntable", type=int, default=0,
                   help="render N frames orbiting 360deg and encode an mp4 "
                        "with per-frame metrics. 0 = off")
    p.add_argument("--fps", type=int, default=12)
    return p.parse_args(argv)


def _points_to_repo(path: Path) -> bool:
    try:
        return os.path.normcase(os.path.realpath(path)) == os.path.normcase(str(REPO))
    except OSError:
        return False


def install_addon() -> None:
    """Register the repo as the `freepencil2` add-on package (live, via junction)."""
    pkg_root = Path(tempfile.gettempdir()) / "fp_addon_pkg"
    staging = pkg_root / ADDON_NAME
    pkg_root.mkdir(parents=True, exist_ok=True)

    if staging.exists() and not _points_to_repo(staging):
        # stale junction or old copy: remove (rmdir deletes only the junction)
        try:
            os.rmdir(staging)
        except OSError:
            shutil.rmtree(staging, ignore_errors=True)

    if not staging.exists():
        r = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(staging), str(REPO)],
            capture_output=True,
        )
        if r.returncode != 0 or not (staging / "__init__.py").exists():
            # fallback: one-shot copy (kept for exotic setups)
            staging.mkdir(parents=True, exist_ok=True)
            for item in REPO.iterdir():
                if item.name in EXCLUDE_DIRS:
                    continue
                if item.is_dir():
                    shutil.copytree(item, staging / item.name,
                                    ignore=shutil.ignore_patterns("__pycache__"),
                                    dirs_exist_ok=True)
                elif item.suffix in {".py", ".toml"} or item.name == "LICENSE":
                    shutil.copy2(item, staging / item.name)

    sys.path.insert(0, str(pkg_root))
    mod = importlib.import_module(ADDON_NAME)
    mod.register()


def comp_tree(scene=None):
    """シーンのコンポジタツリー。Blender 5.x で scene.node_tree が
    scene.compositing_node_group に変わったため、テスト側もここを通す。"""
    scene = scene or bpy.context.scene
    if bpy.app.version >= (5, 0, 0):
        return scene.compositing_node_group
    return scene.node_tree


def is_output_node(node) -> bool:
    """最終出力ノードか。4.x は Composite、5.x は Group Output。"""
    return node.type in ("COMPOSITE", "GROUP_OUTPUT")


def fo_dir(fo) -> str:
    """File Output の出力先(4.x base_path / 5.x directory)。"""
    return fo.directory if bpy.app.version >= (5, 0, 0) else fo.base_path


def fo_slot_names(fo) -> set:
    """File Output のスロット名集合。5.x は file_output_items。"""
    if bpy.app.version >= (5, 0, 0):
        return {it.name for it in fo.file_output_items}
    return {s.path for s in fo.file_slots}


def eevee_engine() -> str:
    """EEVEE のエンジン識別子。4.x は BLENDER_EEVEE_NEXT、5.x で
    BLENDER_EEVEE に戻った。"""
    ids = bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items.keys()
    for cand in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        if cand in ids:
            return cand
    return "BLENDER_EEVEE"


def append_objects(blend: Path) -> tuple[list[bpy.types.Object], list[bpy.types.Object]]:
    """Link all asset objects except cameras/lights; keep hierarchies intact.

    Returns (meshes, others). Empties/armatures must be linked too or
    parented meshes lose their transforms and normalize() cannot scale them.
    """
    with bpy.data.libraries.load(str(blend), link=False) as (src, dst):
        dst.objects = list(src.objects)
    meshes: list[bpy.types.Object] = []
    others: list[bpy.types.Object] = []
    for obj in dst.objects:
        if obj is None or obj.type in {"CAMERA", "LIGHT"}:
            continue  # the asset's own camera/lights would fight ours
        bpy.context.scene.collection.objects.link(obj)
        (meshes if obj.type == "MESH" else others).append(obj)
    return meshes, others


def dominant_cluster(meshes: list[bpy.types.Object]) -> set:
    """空間的な主要クラスタに属するメッシュ集合を返す(外れジオメトリ除外)。

    一部アセットは本体から遠く離れた小物(地面板・参照用オブジェクト等)を
    含み、bbox全体へのカメラフィットだと本体が豆粒になる(terna で実測)。

    - シード: リグ付きメッシュ(あればそれが被写体)/なければ面積最大メッシュ
    - 取り込み: オブジェクト中心から現クラスタbboxまでの距離が
      シード対角×0.35 以下なら追加(許容ギャップをシード基準に固定する
      ことで、飛び石連鎖で遠方の外れ物まで繋がるのを防ぐ)
    """
    from mathutils import Vector

    infos = []
    for o in meshes:
        pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
        mn = Vector((min(p[i] for p in pts) for i in range(3)))
        mx = Vector((max(p[i] for p in pts) for i in range(3)))
        area = sum(p.area for p in o.data.polygons)
        rigged = any(m.type == "ARMATURE" and m.object for m in o.modifiers)
        infos.append([o, mn, mx, area, rigged])
    if not infos:
        return set()

    # シード=リグ付きの中で面積最大の1個(なければ全体で面積最大)。
    # 「全リグ付き」をシードにすると、離れて配置されたリグ付き付属品
    # (terna の絨毯など)まで一括で枠に入ってしまう
    rigged_infos = [t for t in infos if t[4]]
    pool = rigged_infos if rigged_infos else infos
    seed = max(pool, key=lambda t: t[3])
    cluster = {seed[0]}
    mn, mx = seed[1].copy(), seed[2].copy()
    gap = max((mx - mn).length, 1e-3) * 0.35

    def dist_to_bounds(p):
        d2 = 0.0
        for i in range(3):
            if p[i] < mn[i]:
                d2 += (mn[i] - p[i]) ** 2
            elif p[i] > mx[i]:
                d2 += (p[i] - mx[i]) ** 2
        return d2 ** 0.5

    changed = True
    while changed:
        changed = False
        for o, omn, omx, _a, _r in infos:
            if o in cluster:
                continue
            oc = (omn + omx) / 2
            if dist_to_bounds(oc) <= gap:
                cluster.add(o)
                mn = Vector(map(min, mn, omn))
                mx = Vector(map(max, mx, omx))
                changed = True
    return cluster


def normalize(all_objs: list[bpy.types.Object],
              meshes: list[bpy.types.Object], target: float = 2.0) -> dict:
    """Center the group at origin and scale so the mesh bbox fits `target` meters.

    Re-parents only top-level objects (parent None) to a scaled root, so
    parented hierarchies (mesh under empty, etc.) scale as one unit.
    """
    from mathutils import Vector

    bpy.context.view_layer.update()
    mins = Vector((1e18,) * 3)
    maxs = Vector((-1e18,) * 3)
    for o in meshes:
        for corner in o.bound_box:
            w = o.matrix_world @ Vector(corner)
            mins = Vector(map(min, mins, w))
            maxs = Vector(map(max, maxs, w))
    center = (mins + maxs) / 2
    dim = max((maxs - mins).length, 1e-6)
    scale = target / dim
    root = bpy.data.objects.new("FP_BatchRoot", None)
    bpy.context.scene.collection.objects.link(root)
    linked = set(all_objs)
    for o in all_objs:
        if o.parent is None or o.parent not in linked:
            keep = o.matrix_world.copy()
            o.parent = root
            o.matrix_parent_inverse.identity()
            o.matrix_world = keep  # matrix_world assignment compensates via local
    root.location = -center * scale
    root.scale = (scale,) * 3
    bpy.context.view_layer.update()
    return {"bbox_dim": round(dim, 4), "scale": round(scale, 6)}


def setup_camera_and_light() -> None:
    from mathutils import Vector

    cam_data = bpy.data.cameras.new("FP_Cam")
    cam = bpy.data.objects.new("FP_Cam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    direction = Vector((1.0, -1.0, 0.65)).normalized()
    cam.location = direction * 3.4  # model normalized to ~2m box at origin
    look = (Vector((0, 0, 0)) - cam.location).normalized()
    cam.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
    cam_data.lens = 50
    bpy.context.scene.camera = cam

    # 全メッシュのbboxにカメラをフィットさせてフレームを最大活用する
    # (細長いモデルが画面の1/4しか使わず線が潰れるのを防ぐ)
    coords: list[float] = []
    for o in bpy.context.scene.objects:
        if o.type == "MESH" and not o.hide_render:
            for corner in o.bound_box:
                coords.extend(o.matrix_world @ Vector(corner))
    if coords:
        bpy.context.view_layer.update()
        depsgraph = bpy.context.evaluated_depsgraph_get()
        loc, _ = cam.camera_fit_coords(depsgraph, coords)
        cam.location = loc * 1.06  # 6% margin

    sun_data = bpy.data.lights.new("FP_Sun", type="SUN")
    sun_data.energy = 3.0
    sun = bpy.data.objects.new("FP_Sun", sun_data)
    bpy.context.scene.collection.objects.link(sun)
    sun.rotation_euler = (0.8, 0.2, 0.6)


def apply_white_material(meshes: list[bpy.types.Object]) -> None:
    """Strip all asset materials and assign one flat white emission material.

    Emission is shading-free, so the combined pass is pure white + line art:
    ink metrics are not polluted by dark textures or unlit faces.
    """
    mat = bpy.data.materials.new("FP_White")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    emit = nt.nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    emit.inputs["Strength"].default_value = 1.0
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (200, 0)
    nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    for o in meshes:
        o.data.materials.clear()
        o.data.materials.append(mat)


def select_meshes() -> list[bpy.types.Object]:
    """Select all mesh objects in the scene and return them."""
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in meshes:
        o.select_set(True)
    if meshes:
        bpy.context.view_layer.objects.active = meshes[0]
    return meshes


def downscale_box(src: Path, dst: Path, factor: int) -> None:
    """Box-downscale a PNG by `factor` with premultiplied-alpha averaging.

    2pxほどある線を 1px のアンチエイリアス線に落とすためのスーパー
    サンプリング後処理。ストレートアルファのまま平均すると透明画素の
    RGBが縁ににじむので、プリマルチプライして平均し、戻す。
    """
    import numpy as np

    img = bpy.data.images.load(str(src))
    try:
        w, h = img.size
        px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    finally:
        bpy.data.images.remove(img)

    nh, nw = h // factor, w // factor
    px = px[:nh * factor, :nw * factor]
    a = px[..., 3:4]
    pm = px[..., :3] * a
    pm = pm.reshape(nh, factor, nw, factor, 3).mean(axis=(1, 3))
    a = a.reshape(nh, factor, nw, factor, 1).mean(axis=(1, 3))
    rgb = pm / np.maximum(a, 1e-6)
    out_px = np.concatenate([np.clip(rgb, 0, 1), np.clip(a, 0, 1)], axis=-1)

    out = bpy.data.images.new("FP_Downscale", nw, nh, alpha=True)
    try:
        out.pixels[:] = out_px.ravel().tolist()
        # 相対パスだと保存先が迷子になる(render_still の注記を参照)
        out.filepath_raw = str(Path(dst).resolve())
        out.file_format = "PNG"
        out.save()
    finally:
        bpy.data.images.remove(out)


# ---------------------------------------------------------------- metrics
def mesh_color_metrics(objs: list[bpy.types.Object], min_dist: float) -> dict:
    """Distinct island colors + adjacent-color-distance violations.

    Uses mesh.color_attributes directly (works for BYTE/FLOAT corner or
    point colors in Blender 4.x) instead of bmesh layer APIs.
    """
    distinct = set()
    violations = 0
    adjacent_pairs = 0
    for obj in objs:
        me = obj.data
        attr = me.color_attributes.get("mecha_color") if hasattr(me, "color_attributes") else None
        if attr is None or len(me.polygons) == 0:
            continue

        def poly_color(poly):
            if attr.domain == "CORNER":
                c = attr.data[poly.loop_start].color
            else:  # POINT
                c = attr.data[me.loops[poly.loop_start].vertex_index].color
            return (round(c[0], 3), round(c[1], 3), round(c[2], 3))

        face_color = {}
        for poly in me.polygons:
            key = poly_color(poly)
            face_color[poly.index] = key
            distinct.add(key)

        edge_faces: dict[tuple, list] = {}
        for poly in me.polygons:
            for ek in poly.edge_keys:
                edge_faces.setdefault(ek, []).append(poly.index)

        seen = set()
        for faces in edge_faces.values():
            if len(faces) == 2:
                c1, c2 = face_color[faces[0]], face_color[faces[1]]
                if c1 != c2:
                    pair = tuple(sorted((c1, c2)))
                    if pair in seen:
                        continue
                    seen.add(pair)
                    adjacent_pairs += 1
                    d = sum((a - b) ** 2 for a, b in zip(c1, c2)) ** 0.5
                    if d < min_dist:
                        violations += 1
    return {
        "distinct_colors": len(distinct),
        "adjacent_color_pairs": adjacent_pairs,
        "min_distance_violations": violations,
    }


def lineart_metrics(png_path: Path) -> dict:
    """Pixel metrics of the rendered line art."""
    import numpy as np

    # Blender は相対パスを CWD ではなく別の基準で解決するので、
    # 相対パスのまま渡すと読めずに落ちる(render_still と同じ理由)
    img = bpy.data.images.load(str(Path(png_path).resolve()))
    try:
        w, h = img.size
        px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    finally:
        bpy.data.images.remove(img)

    alpha = px[..., 3]
    lum = px[..., :3].mean(axis=-1)
    transparent_bg = float(alpha.mean()) < 0.95
    # alpha>0.9: シルエット縁の半透明フリンジ(暗く見える)をインク誤検出しない
    ink = (alpha > 0.9) & (lum < 0.5) if transparent_bg else (lum < 0.5)

    ink_ratio = float(ink.mean())
    # シルエット(不透明画素)に対するインク率: フレーム占有率に依存しない線密度
    coverage = float((alpha > 0.5).mean()) if transparent_bg else 1.0
    ink_silhouette = ink_ratio / coverage if coverage > 1e-6 else 0.0

    # connected components on a downsampled mask (rough fragmentation measure)
    step = max(1, w // 512)
    small = ink[::step, ::step]
    sh, sw = small.shape
    labels = -np.ones(small.shape, dtype=np.int32)
    n_components = 0
    stack = []
    for y in range(sh):
        for x in range(sw):
            if small[y, x] and labels[y, x] < 0:
                n_components += 1
                stack.append((y, x))
                labels[y, x] = n_components
                while stack:
                    cy, cx = stack.pop()
                    for ny, nx in ((cy-1, cx), (cy+1, cx), (cy, cx-1), (cy, cx+1)):
                        if 0 <= ny < sh and 0 <= nx < sw and small[ny, nx] and labels[ny, nx] < 0:
                            labels[ny, nx] = n_components
                            stack.append((ny, nx))
    return {
        "ink_ratio": round(ink_ratio, 5),
        "coverage": round(coverage, 5),
        "ink_silhouette": round(ink_silhouette, 5),
        "components": int(n_components),
        "transparent_bg": bool(transparent_bg),
        "resolution": [int(w), int(h)],
    }


def render_still(scene, png: Path, ss: int) -> None:
    """1枚レンダ(スーパーサンプリング+縮小込み)。

    Blender の render.filepath / Image.save は相対パスを CWD 以外の基準で
    解決することがあり、指定した場所に何も出ないまま処理が進む(実測。
    メトリクスだけ取れて PNG が消える)。必ず絶対パスにしてから渡す。
    """
    png = Path(png).resolve()
    png.parent.mkdir(parents=True, exist_ok=True)
    render_target = png if ss == 1 else png.with_suffix(".ss.png")
    scene.render.filepath = str(render_target)
    bpy.ops.render.render(write_still=True)
    if ss > 1:
        downscale_box(render_target, png, ss)
        render_target.unlink(missing_ok=True)


def _frame_band_score(ink_sil: float) -> float:
    lo, hi = INK_BAND
    if lo <= ink_sil <= hi:
        return 1.0
    if ink_sil < lo:
        return max(0.0, (ink_sil - 0.003) / (lo - 0.003))
    return max(0.0, (0.55 - ink_sil) / (0.55 - hi))


def render_turntable(args, scene, renders: Path, out_dir: Path,
                     name_base: str) -> dict:
    """カメラを360°周回させてNフレーム描画し、mp4化+フレーム毎採点。"""
    import math
    from mathutils import Matrix, Vector

    n = args.turntable
    ss = max(1, args.supersample)
    cam = scene.camera

    coords: list[float] = []
    for o in scene.objects:
        if o.type == "MESH" and not o.hide_render:
            for corner in o.bound_box:
                coords.extend(o.matrix_world @ Vector(corner))

    # 全方位で収まる半径を求める(8方位でフィットして最大)
    d0 = Vector((1.0, -1.0, 0.65)).normalized()
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    radius = 0.0
    for k in range(8):
        dir_k = Matrix.Rotation(2 * math.pi * k / 8, 4, 'Z') @ d0
        cam.location = dir_k * 3.4
        cam.rotation_euler = (-dir_k).to_track_quat('-Z', 'Y').to_euler()
        loc, _ = cam.camera_fit_coords(depsgraph, coords)
        radius = max(radius, loc.length)
    radius *= 1.06

    frame_dir = renders / f"{name_base}_turn"
    frame_dir.mkdir(parents=True, exist_ok=True)
    frame_paths: list[Path] = []
    frame_metrics: list[dict] = []
    for f in range(n):
        dir_f = Matrix.Rotation(2 * math.pi * f / n, 4, 'Z') @ d0
        cam.location = dir_f * radius
        cam.rotation_euler = (-dir_f).to_track_quat('-Z', 'Y').to_euler()
        png = frame_dir / f"f{f:03d}.png"
        render_still(scene, png, ss)
        frame_paths.append(png)
        frame_metrics.append(lineart_metrics(png))

    video = renders / f"{name_base}_turn.mp4"
    encode_video(frame_paths, video, args.fps, args.res, args.res)

    inks = [m["ink_silhouette"] for m in frame_metrics]
    comps = [m["components"] for m in frame_metrics]
    scores = [_frame_band_score(v) for v in inks]
    worst_i = min(range(n), key=lambda i: scores[i])
    return {
        "video": str(video.relative_to(out_dir)).replace("\\", "/"),
        "frames": n,
        "fps": args.fps,
        "ink_per_frame": [round(v, 5) for v in inks],
        "comp_per_frame": comps,
        "score_mean": round(sum(scores) / n, 4),
        "score_worst": round(min(scores), 4),
        "worst_frame": worst_i,
        "worst_angle_deg": round(360.0 * worst_i / n, 1),
        "ink_min": round(min(inks), 5),
        "ink_mean": round(sum(inks) / n, 5),
        "ink_max": round(max(inks), 5),
    }


def encode_video(frame_paths: list[Path], out_mp4: Path,
                 fps: int, width: int, height: int) -> None:
    """PNG連番をVSEで白背景に合成してH264 mp4に書き出す。

    透過PNGをそのまま動画化すると背景が黒になり黒線が見えなくなるため、
    白のカラーストリップの上にALPHA_OVERで重ねる。
    """
    sc = bpy.data.scenes.new("FP_Encode")
    try:
        sc.render.resolution_x = width
        sc.render.resolution_y = height
        sc.render.resolution_percentage = 100
        sc.render.fps = fps
        sc.frame_start = 1
        sc.frame_end = len(frame_paths)
        sc.render.image_settings.file_format = 'FFMPEG'
        sc.render.ffmpeg.format = 'MPEG4'
        sc.render.ffmpeg.codec = 'H264'
        sc.render.ffmpeg.constant_rate_factor = 'HIGH'
        sc.render.filepath = str(out_mp4)
        se = sc.sequence_editor_create()
        bg = se.sequences.new_effect(
            "bg", 'COLOR', 1, 1, frame_end=len(frame_paths) + 1)
        bg.color = (1.0, 1.0, 1.0)
        strip = se.sequences.new_image(
            "frames", str(frame_paths[0]), 2, 1)
        for p in frame_paths[1:]:
            strip.elements.append(p.name)
        strip.blend_type = 'ALPHA_OVER'
        bpy.ops.render.render(animation=True, scene=sc.name)
    finally:
        bpy.data.scenes.remove(sc)


# ---------------------------------------------------------------- pipeline
def run_pipeline(args: argparse.Namespace, preset: dict, out_dir: Path,
                 overrides: dict | None = None) -> dict:
    """Run the full STEP1-3 + render pipeline once and return the record.

    `overrides` maps scene prop names (fp_*) to values applied on top of the
    preset (used by the adaptive retry). The retry render gets an `_adj`
    filename suffix so both attempts stay on disk.
    """
    renders = out_dir / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    tag = overrides.pop("tag", "_adj") if overrides else ""

    record: dict = {
        "name": args.name,
        "blend": args.blend,
        "seed": args.seed,
        "preset": args.preset,
        "preset_values": preset,
        "material": args.material,
        "blender": bpy.app.version_string,
        "ok": False,
    }
    if overrides:
        record["overrides"] = overrides
    t0 = time.time()
    try:
        bpy.ops.wm.read_homefile(use_empty=True)
        install_addon()
        scene = bpy.context.scene

        objs, others = append_objects(Path(args.blend))
        if not objs:
            raise RuntimeError("no mesh objects in asset")
        record["mesh_objects"] = len(objs)
        record["faces_total"] = int(sum(len(o.data.polygons) for o in objs))
        # 面数が極端に少ない=霧用平面などの評価対象外アセット
        record["degenerate"] = record["faces_total"] <= 8
        has_armature = (any(o.type == "ARMATURE" for o in others)
                        or any(m.type == "ARMATURE" and m.object
                               for o in objs for m in o.modifiers))
        record["has_armature"] = has_armature

        # リグのカスタムシェイプ(ボーン表示用メッシュ: cs_*/WGT-* や
        # pose.bones.custom_shape 参照)はレンダ対象外。terna では50個以上の
        # 操作シェイプが本体の周囲に散在し、フレーミングを破壊していた
        shape_names = set()
        for a in others:
            if a.type == "ARMATURE" and a.pose:
                for pb in a.pose.bones:
                    if pb.custom_shape is not None:
                        shape_names.add(pb.custom_shape.name)
        n_shapes = 0
        for o in objs:
            base = o.name.lower()
            if (o.name in shape_names
                    or base.startswith(("cs_", "wgt", "shape_"))):
                o.hide_render = True
                n_shapes += 1
        if n_shapes:
            record["rig_shapes_hidden"] = n_shapes
        content = [o for o in objs if not o.hide_render] or objs

        # 外れジオメトリ(本体から離れた小物)はレンダとフレーミングから除外
        cluster = dominant_cluster(content)
        outliers = [o for o in content if o not in cluster]
        for o in outliers:
            o.hide_render = True
        if outliers:
            record["outliers_hidden"] = len(outliers)
            print(f"[fp_batch] outliers hidden: "
                  f"{[o.name[:20] for o in outliers][:8]}")
        framed = [o for o in content if o in cluster] or content
        record["normalize"] = normalize(objs + others, framed)

        if args.material == "white":
            apply_white_material(objs)

        # preset -> scene props
        scene.fp_use_random_seed = False
        scene.fp_color_seed = args.seed
        scene.fp_sharp_auto = preset.get("sharp_auto", False)
        scene.fp_sharp_edges = preset["sharp_edges"]
        scene.fp_color_noise_scale = preset["color_noise_scale"]
        scene.fp_min_neighbor_color_distance = preset["min_neighbor_color_distance"]
        scene.fp_max_color_retries = preset["max_color_retries"]
        scene.fp_to_quads = preset.get("to_quads", False)
        scene.fp_sharp_clear = preset.get("sharp_clear", False)
        scene.fp_min_island_area_pct = preset.get("min_island_area_pct", 0.02)
        # リグ付きアセットはボーン境界が線の主役なので bone AOV を自動有効化
        # (プリセットで明示指定があればそちらが勝つ)
        scene.fp_bone_color = preset.get("bone_color", has_armature)
        scene.fp_bone_grouping_mode = preset.get("bone_grouping", "basename")
        scene.fp_bone_hard_names = preset.get("bone_hard_names", "")
        scene.fp_part_tint = preset.get("part_tint", True)
        scene.fp_seam_boundaries = preset.get("seam_boundaries", False)
        scene.fp_line_sensitivity = preset.get("line_sensitivity", 1.0)
        scene.fp_include_antialiasing = preset.get("antialiasing", True)
        scene.fp_node_type = "pro"
        scene.fp_enable_compositor_view = False
        for key, value in (overrides or {}).items():
            if key.startswith("fp_"):
                setattr(scene, key, value)

        select_meshes()

        # STEP1: auto vertex color (may split objects into islands)
        t1 = time.time()
        result = bpy.ops.freepencil.auto_vertex_color()
        record["step1_result"] = list(result)
        record["step1_seconds"] = round(time.time() - t1, 2)
        objs = select_meshes()  # re-collect + re-select after split

        # STEP2: AOV setup via the real operator
        bpy.ops.freepencil4.link_button()
        if "mecha_color" not in [a.name for a in bpy.context.view_layer.aovs]:
            raise RuntimeError("STEP2 failed: mecha_color AOV missing")

        # STEP3: PRO compositor node via the real operator
        bpy.ops.freepencil2.link_button()
        _tree = comp_tree(scene)
        if _tree is None or not any(
            n.label == NODE_GROUP_PRO for n in _tree.nodes
        ):
            raise RuntimeError("STEP3 failed: compositor tree not built")

        setup_camera_and_light()
        scene.render.engine = eevee_engine()
        if args.material == "white":
            # フラット白Emissionは陰影が無いのでサンプル数を絞って高速化
            scene.eevee.taa_render_samples = 8
        ss = max(1, args.supersample)
        scene.render.resolution_x = args.res * ss
        scene.render.resolution_y = args.res * ss
        png = renders / (f"{args.name}_seed{args.seed}_{args.preset}"
                         f"_{args.material}{tag}.png")
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGBA"
        t2 = time.time()
        render_still(scene, png, ss)
        if ss > 1:
            record["supersample"] = ss
        record["render_seconds"] = round(time.time() - t2, 2)
        record["render"] = str(png.relative_to(out_dir)).replace("\\", "/")

        record["mesh_metrics"] = mesh_color_metrics(
            objs, preset["min_neighbor_color_distance"])
        record["lineart_metrics"] = lineart_metrics(png)

        if args.turntable > 0:
            t3 = time.time()
            record["turntable"] = render_turntable(
                args, scene, renders, out_dir,
                f"{args.name}_seed{args.seed}_{args.preset}_{args.material}{tag}")
            record["turntable"]["seconds"] = round(time.time() - t3, 1)
        record["ok"] = True
    except Exception:
        record["error"] = traceback.format_exc()
    record["total_seconds"] = round(time.time() - t0, 2)
    return record


# 線密度の目標帯(スコアの許容帯と同じ)。帯から外れた度合いで比較する
# 2倍スーパーサンプリング(1px線)基準で再キャリブレーション済み
INK_BAND = (0.02, 0.30)


def _band_distance(v: float) -> float:
    lo, hi = INK_BAND
    if lo <= v <= hi:
        return 0.0
    return lo - v if v < lo else v - hi


def choose_adaptive_overrides(ink_sil: float) -> list[dict]:
    """1回目の線密度から適応リトライの候補列を決める(不要なら空)。

    注意: fp_sharp_auto が ON のままだと角度上書きが無効化されるため、
    リトライでは必ず auto を切って明示角度で振る。
    「線が少ない」は段階制: 20°で拾えないモデル(強ベベルの家具など、
    二面角が全て20°未満)は 8° まで下げて拾う(kallax で実証)。
    """
    if ink_sil < 0.016:
        return [
            {"fp_sharp_auto": False, "fp_sharp_edges": 20.0,
             "tag": "_adj1", "reason": "too few lines (20deg)"},
            {"fp_sharp_auto": False, "fp_sharp_edges": 8.0,
             "tag": "_adj2", "reason": "too few lines (8deg)"},
        ]
    if ink_sil > 0.45:
        return [{"fp_sharp_auto": False, "fp_sharp_edges": 85.0,
                 "fp_min_island_area_pct": 0.2,
                 "tag": "_adj1", "reason": "ink saturated"}]
    return []


# ---------------------------------------------------------------- main
def main() -> None:
    args = parse_args()
    out_dir = Path(args.out)
    metrics_dir = out_dir / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    presets = json.loads((Path(__file__).parent / "presets.json").read_text(encoding="utf-8"))
    preset = presets[args.preset]

    record = run_pipeline(args, preset, out_dir)

    # 適応リトライ: 線が少なすぎ/飽和のときに設定を振って最良を採用
    if record["ok"]:
        first_ink = record["lineart_metrics"]["ink_silhouette"]
        best_d = _band_distance(first_ink)
        rejected = []
        for override in choose_adaptive_overrides(first_ink):
            if best_d == 0.0:
                break
            retry = run_pipeline(args, preset, out_dir,
                                 {k: v for k, v in override.items()
                                  if k.startswith("fp_") or k == "tag"})
            if not retry["ok"]:
                continue
            ink2 = retry["lineart_metrics"]["ink_silhouette"]
            if _band_distance(ink2) < best_d:
                retry["adaptive"] = {k: v for k, v in override.items()
                                     if k != "tag"}
                retry["first_attempt"] = {
                    "ink_silhouette": first_ink,
                    "render": record.get("render"),
                }
                record = retry
                best_d = _band_distance(ink2)
            else:
                rejected.append({**override, "retry_ink_silhouette": ink2})
        if rejected:
            record["adaptive_rejected"] = rejected

    out = metrics_dir / f"{args.name}_seed{args.seed}_{args.preset}_{args.material}.json"
    out.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[fp_batch] {'OK' if record['ok'] else 'FAIL'} {args.name} "
          f"({record['total_seconds']}s"
          f"{', adaptive: ' + record['adaptive']['reason'] if record.get('adaptive') else ''})")
    if not record["ok"]:
        print(record.get("error", ""))
        sys.exit(1)


if __name__ == "__main__":
    main()
