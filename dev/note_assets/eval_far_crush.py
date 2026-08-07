"""遠景で線がつぶれる度合いを、奥行き方向の帯ごとに測る。

デパートのように「密な什器が奥まで並ぶ」状況を合成シーンで再現し、
カメラからの距離帯ごとに「線の量(ink)」と「つぶれ度(黒が連続して
埋まっている割合)」を出す。対策の前後をこの数字で比べる。

  blender -b --factory-startup --python eval_far_crush.py -- --out <dir>
                                                   [--far-fade 0.6]
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
import fp_batch  # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


OUT = Path(arg("--out", str(HERE / "out" / "farcrush"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES = int(arg("--res", "1200"))
ROWS = int(arg("--rows", "26"))


def build_corridor():
    """奥へ向かって棚が並ぶ通路。奥ほど画面上で密になる。"""
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene

    for r in range(ROWS):
        z = -1.2 - r * 1.55          # 奥へ
        for side in (-1, 1):
            x = side * 2.3
            # 棚(縦の板)
            bpy.ops.mesh.primitive_cube_add(size=1, location=(x, z, 1.0))
            o = bpy.context.object
            o.scale = (0.35, 0.6, 1.0)
            o.name = f"SHELF_{r}_{side}"
            # 棚板と商品(小さい箱を積む) = 遠景でつぶれる原因
            for k in range(4):
                for c in range(3):
                    bpy.ops.mesh.primitive_cube_add(
                        size=1,
                        location=(x + (c - 1) * 0.22, z, 0.25 + k * 0.45))
                    p = bpy.context.object
                    p.scale = (0.085, 0.5, 0.17)
                    p.name = f"PRD_{r}_{side}_{k}_{c}"
    # 床
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, -20, 0))
    bpy.context.object.name = "FLOOR"

    # カメラは通路の入口から奥を見る
    cam_data = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cam_data)
    scene.collection.objects.link(cam)
    # 通路は -Y 方向に伸びるので、カメラも -Y を向ける
    cam.location = (0.0, 3.2, 1.6)
    cam.rotation_euler = (math.radians(88.0), 0.0, math.radians(180.0))
    cam_data.lens = 35.0
    cam_data.clip_end = 200.0
    scene.camera = cam

    light_data = bpy.data.lights.new("Sun", type="SUN")
    light_data.energy = 3.0
    light = bpy.data.objects.new("Sun", light_data)
    scene.collection.objects.link(light)
    light.rotation_euler = (math.radians(50), 0, math.radians(30))
    return scene


def depth_map(scene, path: Path) -> np.ndarray:
    """カメラからの距離(Z)を EXR で焼いて配列で返す。"""
    vl = bpy.context.view_layer
    vl.use_pass_z = True
    ng = bpy.data.node_groups.new("zdump", "CompositorNodeTree")
    prev = getattr(scene, "compositing_node_group", None)
    is5 = bpy.app.version >= (5, 0, 0)
    if is5:
        scene.compositing_node_group = ng
        tree = ng
    else:
        scene.use_nodes = True
        tree = scene.node_tree
        saved = [(n.name) for n in tree.nodes]
        tree.nodes.clear()
    rl = tree.nodes.new("CompositorNodeRLayers")
    if is5:
        out = tree.nodes.new("NodeGroupOutput")
        tree.interface.new_socket("Image", in_out="OUTPUT",
                                  socket_type="NodeSocketColor")
    else:
        out = tree.nodes.new("CompositorNodeComposite")
    zsock = next(s for s in rl.outputs if s.name in ("Depth", "Z"))
    tree.links.new(zsock, out.inputs[0])
    scene.render.image_settings.file_format = "OPEN_EXR"
    scene.render.image_settings.color_depth = "32"
    scene.render.filepath = str(path.with_suffix(""))
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(str(path.with_suffix(".exr")))
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)[:, :, 0]
    bpy.data.images.remove(img)
    if is5:
        scene.compositing_node_group = prev
    return px


def crush_metrics(png: Path, z: np.ndarray, bands=6, z_max=60.0) -> dict:
    """距離帯ごとに、線の量と「べた塗りになっている割合」を出す。

    Blender 内では PIL が使えないので画像は bpy で読む。
    背景(クリップ端まで抜けている画素)は帯に入れない。
    """
    img = bpy.data.images.load(str(png.resolve()))
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    bpy.data.images.remove(img)
    a = px[:, :, 3]
    # 透過背景は白として合成
    g = px[:, :, :3].mean(axis=2) * a + (1.0 - a)
    if g.shape != z.shape:
        return {"error": f"サイズ不一致 line={g.shape} z={z.shape}"}
    ink = g < 0.5

    # つぶれ = 3x3 の窓が全部インクで埋まっている画素の割合
    solid = ink.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            solid &= np.roll(np.roll(ink, dy, 0), dx, 1)

    finite = np.isfinite(z) & (z < z_max)
    zs = z[finite]
    if not len(zs):
        return {}
    lo, hi = float(zs.min()), float(zs.max())
    edges = np.linspace(lo, hi, bands + 1)
    rows = []
    for b in range(bands):
        m = finite & (z >= edges[b]) & (z < edges[b + 1])
        n = int(m.sum())
        if n < 200:
            continue
        rows.append({
            "band": b,
            "z_from": round(float(edges[b]), 2),
            "z_to": round(float(edges[b + 1]), 2),
            "pixels": n,
            "ink_ratio": round(float(ink[m].sum()) / n, 4),
            "crush_ratio": round(float(solid[m].sum()) / n, 4),
        })
    return {"bands": rows,
            "ink_total": round(float(ink.mean()), 5),
            "crush_total": round(float(solid.mean()), 5)}


def main() -> None:
    fp_batch.install_addon()
    scene = build_corridor()
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 42
    scene.fp_enable_compositor_view = False
    scene.fp_supersample = True
    scene.render.resolution_x = scene.render.resolution_y = RES
    scene.render.engine = fp_batch.eevee_engine()
    scene.eevee.taa_render_samples = 16

    meshes = [o for o in scene.objects if o.type == "MESH"]
    print(f"[far] メッシュ {len(meshes)} 個 "
          f"面 {sum(len(o.data.polygons) for o in meshes):,}", flush=True)

    z = depth_map(scene, OUT / "z")
    print(f"[far] 深度 {np.nanmin(z):.2f} 〜 "
          f"{np.percentile(z[np.isfinite(z) & (z < 1e6)], 99):.2f}", flush=True)

    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    relief = float(arg("--relief", "0"))
    if relief > 0:
        scene.fp_far_relief = relief
        scene.fp_far_relief_radius = float(arg("--radius", "6"))
        scene.fp_far_relief_threshold = float(arg("--threshold", "0.35"))
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    if relief > 0:
        from freepencil2 import fp_core
        n = 0
        for ng in bpy.data.node_groups:
            if ng.name.startswith(fp_core.NODE_GROUP_PREFIX):
                n += fp_core.far_relief_from_scene(ng, scene)
        print(f"[far] つぶれ軽減 strength={relief} radius="
              f"{scene.fp_far_relief_radius} thr="
              f"{scene.fp_far_relief_threshold} ノード{n}個", flush=True)

    tag = arg("--tag", "base")
    png = OUT / f"corridor_{tag}.png"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    fp_batch.render_still(scene, png, 2 if scene.fp_supersample else 1)
    m = crush_metrics(png, z)
    print("[far] " + json.dumps(m, ensure_ascii=False), flush=True)
    (OUT / f"metrics_{tag}.json").write_text(json.dumps(m, indent=1,
                                                 ensure_ascii=False),
                                      encoding="utf-8")


if __name__ == "__main__":
    main()
