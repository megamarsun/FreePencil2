"""テクスチャで塗り分けを差し込む技法(AOV グループの line_texture / mask_texture)を撮る。

  blender -b --factory-startup --python audit_texture.py -- [--out out/audit_texture/<版>]

場面: 左の板 = line_texture に「塗り分けた絵」(円と帯を色で塗った画像)をつなぐ。
       右の箱 = mask_texture に「左半分を白」の絵をつなぐ(白い所の線が消えるはず)。
仕上がり 3 つ x 白 / セル。手順は利用者と同じ: 材質の FreePencil AOV グループの入力に
画像テクスチャをつなぐ(STEP2 の後)-> STEP3。STEP0 を押し直した場合も撮る。
"""
from __future__ import annotations

import math
import sys
import traceback
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d   # noqa: E731
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bpy                        # noqa: E402
import numpy as np                # noqa: E402
import fp_batch                   # noqa: E402

OUT = Path(arg("--out", str(HERE / "out" / "audit_texture" / bpy.app.version_string.split()[0]))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
fp_batch.install_addon()


def make_image(name, fn, size=256):
    img = bpy.data.images.new(name, size, size)
    yy, xx = np.mgrid[0:size, 0:size] / size
    px = np.ones((size, size, 4), dtype=np.float32)
    px[..., :3] = fn(xx, yy)
    img.pixels.foreach_set(px.ravel())
    img.pack()
    return img


def split_pattern(x, y):
    """塗り分けた絵: 円(赤)、斜めの帯(青)、残り(黄)。"""
    out = np.zeros(x.shape + (3,), dtype=np.float32)
    out[...] = (0.9, 0.8, 0.2)
    band = np.abs((x - y)) < 0.12
    out[band] = (0.1, 0.3, 0.9)
    circ = (x - 0.3) ** 2 + (y - 0.7) ** 2 < 0.04
    out[circ] = (0.9, 0.1, 0.1)
    return out


def half_white(x, y):
    out = np.zeros(x.shape + (3,), dtype=np.float32)
    out[x < 0.5] = 1.0
    return out


def scene_setup():
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    bpy.ops.mesh.primitive_plane_add(size=2.0, location=(-1.3, 0, 1.0), rotation=(math.radians(90), 0, 0))
    plate = bpy.context.object
    plate.name = "Plate"
    bpy.ops.mesh.primitive_cube_add(size=1.4, location=(1.3, 0.3, 0.8))
    box = bpy.context.object
    box.name = "Box"
    for o, col in ((plate, (0.8, 0.8, 0.8)), (box, (0.7, 0.8, 0.9))):
        m = bpy.data.materials.new(o.name + "_mat")
        m.use_nodes = True
        m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*col, 1)
        o.data.materials.append(m)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.location = (0, -6, 1.2)
    cam.rotation_euler = (math.radians(88), 0, 0)
    sc.collection.objects.link(cam)
    sc.camera = cam
    lt = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    lt.data.energy = 4
    lt.rotation_euler = (math.radians(40), 0, math.radians(-30))
    sc.collection.objects.link(lt)
    sc.render.resolution_x, sc.render.resolution_y = 640, 360
    sc.eevee.taa_render_samples = 8
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view"):
        setattr(sc, p_, False)
    bpy.ops.object.select_all(action="DESELECT")
    plate.select_set(True)
    box.select_set(True)
    bpy.context.view_layer.objects.active = plate
    return sc, plate, box


def plug(obj, socket_name, img):
    """材質の FreePencil AOV グループの入力 socket_name に、画像テクスチャ(UV)をつなぐ。"""
    nt = obj.data.materials[0].node_tree
    grp = next(n for n in nt.nodes if n.type == "GROUP" and n.node_tree
               and n.node_tree.name.startswith("FreePencil"))
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Closest"
    nt.links.new(tex.outputs["Color"], grp.inputs[socket_name])
    return grp


def shot(sc, name):
    sc.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    print("@@@", name, flush=True)


split_img = None
for style in ("PRECISE", "WEIGHTED", "BACKGROUND"):
    try:
        sc, plate, box = scene_setup()
        split_img = make_image("split", split_pattern)
        mask_img = make_image("halfwhite", half_white)
        sc.fp_auto_style = style
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        sc.fp_preview_mode = "WHITE"
        shot(sc, f"{style}_0_step0")
        plug(plate, "line_texture", split_img)
        plug(box, "mask_texture", mask_img)
        shot(sc, f"{style}_1_plugged")
        bpy.ops.freepencil2.link_button()
        shot(sc, f"{style}_2_step3")
        bpy.ops.freepencil4.link_button()
        bpy.ops.freepencil2.link_button()
        shot(sc, f"{style}_3_step23")
        sc.fp_preview_mode = "CEL"
        shot(sc, f"{style}_4_cel")
        sc.fp_preview_mode = "WHITE"
        bpy.ops.object.select_all(action="DESELECT")
        plate.select_set(True)
        box.select_set(True)
        bpy.context.view_layer.objects.active = plate
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        shot(sc, f"{style}_5_step0_again")
        bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{style}.blend"))
    except Exception:                                            # noqa: BLE001
        print("@@@ ERROR", style, traceback.format_exc(), flush=True)

# 塗り分けの絵そのもの(比べる用)
sc, plate, box = scene_setup()
mat = plate.data.materials[0]
nt = mat.node_tree
tex = nt.nodes.new("ShaderNodeTexImage")
tex.image = make_image("split_ref", split_pattern)
tex.interpolation = "Closest"
nt.links.new(tex.outputs["Color"], nt.nodes["Principled BSDF"].inputs["Base Color"])
sc.render.engine = fp_batch.eevee_engine()
shot(sc, "ref_texture")
print("@@@ done", flush=True)
