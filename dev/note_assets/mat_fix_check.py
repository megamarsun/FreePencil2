"""マテリアル/モノクロのプレビューを、3 つの仕上がりで撮る(強弱のある線で色が消えていた不具合の確認)。

  blender -b --factory-startup --python mat_fix_check.py -- <out_dir>
"""
import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:]
OUT = Path(ARGV[0]).resolve()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "batch"))
import bpy, fp_batch          # noqa: E402

fp_batch.install_addon()
OUT.mkdir(parents=True, exist_ok=True)


def scene_setup():
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene

    def mat(name, col):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*col, 1)
        return m
    bpy.ops.mesh.primitive_monkey_add(size=1.6, location=(-1.0, 0, 0.9))
    bpy.ops.object.shade_smooth()
    monkey = bpy.context.object
    monkey.data.materials.append(mat("Red", (0.8, 0.15, 0.1)))
    bpy.ops.mesh.primitive_cube_add(size=1.2, location=(1.0, 0.3, 0.6))
    cube = bpy.context.object
    cube.data.materials.append(mat("Yellow", (0.9, 0.75, 0.2)))
    bpy.ops.mesh.primitive_plane_add(size=12, location=(0, 2, 0))
    ground = bpy.context.object
    ground.data.materials.append(mat("Blue", (0.2, 0.4, 0.8)))
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.location = (0, -6, 1.8)
    cam.rotation_euler = (math.radians(80), 0, 0)
    sc.collection.objects.link(cam)
    sc.camera = cam
    lt = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    lt.data.energy = 4
    lt.rotation_euler = (math.radians(50), 0, math.radians(-40))
    sc.collection.objects.link(lt)
    sc.render.resolution_x, sc.render.resolution_y = 480, 270
    sc.eevee.taa_render_samples = 16
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
        setattr(sc, p_, False)
    bpy.ops.object.select_all(action="DESELECT")
    for o in (monkey, cube, ground):
        o.select_set(True)
    bpy.context.view_layer.objects.active = monkey
    return sc


for style in ("PRECISE", "WEIGHTED", "BACKGROUND"):
    sc = scene_setup()
    sc.fp_auto_style = style
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    for mode in ("NONE", "MONO_LIGHT", "WHITE", "CEL", "NONE"):
        sc.fp_preview_mode = mode
        name = f"{style}_{mode}"
        if (OUT / f"{name}.png").exists():
            name += "_again"
        sc.render.filepath = str(OUT / f"{name}.png")
        bpy.ops.render.render(write_still=True)
        print("@@@", name, flush=True)
    # STEP3 を押し直してもマテリアルのまま(作り直しの最後で掛け直す)
    bpy.ops.freepencil2.link_button()
    sc.render.filepath = str(OUT / f"{style}_NONE_after_step3.png")
    bpy.ops.render.render(write_still=True)
    print("@@@", style, "after STEP3", sc.fp_preview_mode, flush=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{style}.blend"))
