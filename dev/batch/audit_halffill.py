"""Half Fill を絵で確かめる。カメラに向いた板(X/Z の面 = 以前は効かなかった向き)を 8x8 に分け、
頂点ペイントのように「x <= 0 の頂点を赤」で塗る(境目の列の頂点が両側の面で赤 = 右側の面にぼかし)。

  blender -b --factory-startup --python audit_halffill.py -- [--out out/audit_halffill/<版>]

撮るもの: A 塗った後(ぼかしの境目) / B 境目の列(x=0)を選んで Half Fill / C 頂点カラーそのもの(前後)
"""
import math
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d   # noqa: E731
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bpy                        # noqa: E402
import numpy as np                # noqa: E402
import fp_batch                   # noqa: E402

OUT = Path(arg("--out", str(HERE / "out" / "audit_halffill" / bpy.app.version_string.split()[0]))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
fp_batch.install_addon()

bpy.ops.wm.read_homefile(use_empty=True)
sc = bpy.context.scene
bpy.ops.mesh.primitive_grid_add(x_subdivisions=8, y_subdivisions=8, size=2.0,
                                location=(0, 0, 1.0), rotation=(math.radians(90), 0, 0))
plate = bpy.context.object
m = bpy.data.materials.new("P")
m.use_nodes = True
plate.data.materials.append(m)
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
cam.location = (0, -4.2, 1.0)
cam.rotation_euler = (math.radians(90), 0, 0)
sc.collection.objects.link(cam)
sc.camera = cam
sc.render.resolution_x, sc.render.resolution_y = 480, 480
sc.eevee.taa_render_samples = 8
for p_ in ("fp_use_random_seed", "fp_enable_compositor_view"):
    setattr(sc, p_, False)
sc.fp_auto_style = "PRECISE"
bpy.ops.object.select_all(action="DESELECT")
plate.select_set(True)
bpy.context.view_layer.objects.active = plate
bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
sc.fp_preview_mode = "WHITE"

# 頂点ペイントのように: x <= 0 の頂点の角を全部赤、他を青(境目の列 x=0 は両側の面で赤)
me = plate.data
attr = me.color_attributes["mecha_color"]
cols = np.empty(len(attr.data) * 4, dtype=np.float32)
loop_v = np.empty(len(me.loops), dtype=np.int64)
me.loops.foreach_get("vertex_index", loop_v)
xs = np.array([me.vertices[i].co.x for i in loop_v])
cols = cols.reshape(-1, 4)
cols[:] = (0.1, 0.3, 0.9, 1.0)
cols[xs <= 1e-4] = (0.9, 0.15, 0.1, 1.0)
attr.data.foreach_set("color", cols.ravel())
me.update()


def shot(name):
    sc.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    print("@@@", name, flush=True)


def colors(name):
    keep = sc.render.engine
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light = "FLAT"
    sh.color_type = "VERTEX"
    me.color_attributes.active_color = me.color_attributes["mecha_color"]
    keep_mode = sc.fp_preview_mode
    sc.render.use_compositing = False
    shot(name)
    sc.render.use_compositing = True
    sc.render.engine = keep


shot("A_lines_before")
colors("C_colors_before")
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="DESELECT")
bpy.ops.object.mode_set(mode="OBJECT")
for v in me.vertices:
    v.select = abs(v.co.x) < 1e-4
bpy.ops.object.mode_set(mode="EDIT")
sc.fp_color_type = "mecha_color"
import bmesh
_bm = bmesh.from_edit_mesh(me)
print("@@@ dbg layers color", list(_bm.loops.layers.color.keys()), "float", list(_bm.loops.layers.float_color.keys()),
      "sel", sum(1 for v in _bm.verts if v.select), flush=True)
res = bpy.ops.freepencil5.link_button()
bpy.ops.object.mode_set(mode="OBJECT")
print("@@@ half fill", res, flush=True)
shot("B_lines_after")
colors("D_colors_after")
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "halffill.blend"))
print("@@@ done", flush=True)
