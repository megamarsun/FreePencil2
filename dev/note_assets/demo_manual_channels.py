"""STEP4 の手動チャンネルの実挙動を、スザンヌで見せるサンプルを作る。

右半分だけを塗り、左半分(未塗装)と並べて効果を見る。
ラベルの "White erases lines" は 2023年の初版から実装と逆で、実際は
  mask_color : 暗く塗ると線が消える(0.2付近が最大。白は無効)
  line_color : 線の濃さが変わる(明るいほど薄く、白で見えなくなる)
という挙動。これを画で示す。

  blender -b --factory-startup --python demo_manual_channels.py -- --out <abs dir>
"""
from __future__ import annotations

import sys
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))

import fp_batch  # noqa: E402

fp_batch.install_addon()

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = Path(ARGV[ARGV.index("--out") + 1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)


def paint_half(obj, attr_name: str, value: float) -> None:
    """右半分(ローカルX>0)のループだけを塗る。左半分は未塗装のまま残す。"""
    attr = obj.data.color_attributes.get(attr_name)
    assert attr is not None, attr_name
    mesh = obj.data
    for poly in mesh.polygons:
        cx = sum(mesh.vertices[v].co.x for v in poly.vertices) / len(poly.vertices)
        if cx <= 0.0:
            continue
        for li in poly.loop_indices:
            attr.data[li].color = (value, value, value, 1.0)
    mesh.update()


def build(channel: str | None, value: float, tag: str) -> Path:
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_monkey_add()
    obj = bpy.context.active_object
    # サブディビジョンは掛けない。滑らかにすると島が減って線が出なくなる
    fp_batch.normalize([obj], [obj])   # 画面いっぱいに収める
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    scene = bpy.context.scene
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 1234
    scene.fp_enable_compositor_view = False
    scene.fp_supersample = False
    scene.fp_auto_white_preview = True
    scene.fp_line_sensitivity = 2.0   # 見本なので線をはっきり出す
    # 塗る前に AOV を用意する必要があるので自動検出は使わない
    scene.fp_auto_detect_aov = False
    scene.fp_mask_color = True
    scene.fp_line_color = True
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")

    if channel:
        paint_half(obj, channel, value)

    fp_batch.setup_camera_and_light()
    scene.render.engine = fp_batch.eevee_engine()
    scene.eevee.taa_render_samples = 16
    scene.render.resolution_x = scene.render.resolution_y = 1000
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    png = OUT / f"suzanne_{tag}.png"
    fp_batch.render_still(scene, png, 1)
    print(f"[demo] {png.name}  {fp_batch.lineart_metrics(png)['ink_ratio']}")
    return png


build(None, 0.0, "base")
for v in (0.2, 0.5, 1.0):
    build("mask_color", v, f"mask_{v}")
for v in (0.3, 0.6, 1.0):
    build("line_color", v, f"line_{v}")
print("[demo] done")
