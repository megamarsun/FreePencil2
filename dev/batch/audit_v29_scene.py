"""audit_v29 の場面(赤いサル・黄色い箱・青い地面・日)。"""
import math

import bpy


def scene_setup(transparent, RES=480):
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
    monkey.name = "Monkey"
    monkey.data.materials.append(mat("Red", (0.8, 0.15, 0.1)))
    bpy.ops.mesh.primitive_cube_add(size=1.2, location=(1.0, 0.3, 0.6))
    cube = bpy.context.object
    cube.name = "Box"
    cube.data.materials.append(mat("Yellow", (0.9, 0.75, 0.2)))
    bpy.ops.mesh.primitive_plane_add(size=12, location=(0, 2, 0))
    ground = bpy.context.object
    ground.name = "Ground"
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
    sc.render.resolution_x, sc.render.resolution_y = RES, RES * 9 // 16
    sc.eevee.taa_render_samples = 8
    sc.render.film_transparent = transparent
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
        setattr(sc, p_, False)
    bpy.ops.object.select_all(action="DESELECT")
    for o in (monkey, cube, ground):
        o.select_set(True)
    bpy.context.view_layer.objects.active = monkey
    return sc, {"Monkey": monkey, "Box": cube, "Ground": ground}
