"""手作業デモの 4K 版: 手直しの各段階を F12 で 4K に撮る(動画は assemble_girl_4k.py で組む)。

  blender -b --factory-startup --python girl_4k_states.py -- <girl_clean.blend> <out_dir>

4K は 2倍レンダを使わない。2倍レンダは「2倍で描いて半分に縮める」ので、出力が大きいほど線が
画面に対して細くなる。4K で切ると、1080p + 2倍レンダと同じ割合の太さと強弱になる(画像で比べて決めた)。
セルは日を正面やや上(40°、横 10°)、影のしきい値 0.35。頬が日から外へ向いて、大きな影が出ていた。
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "batch"))
import fp_batch                                   # noqa: E402
fp_batch.install_addon()
import bpy                                        # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = Path(ARGV[0]).resolve(), Path(ARGV[1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(SRC))
sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = 3840, 2160
sc.eevee.taa_render_samples = 32
bpy.data.objects["Sun"].rotation_euler = (math.radians(40), 0, math.radians(10))
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "girl_4k.blend"))
fp = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.ai"))

MOUTH = (0.39, 0.47, 0.49, 0.58)
BUTTONS = (0.40, 0.62, 0.50, 0.84)

fp.preview("NONE")
fp.render("s0_model", scale=1.0, grid=False)
fp.auto("WEIGHTED")
sc.fp_supersample = False
bpy.ops.freepencil2.link_button()
bpy.ops.freepencil.measure_line_weight()
fp.render("s1_step0", scale=1.0, grid=False)
fp.texture_lines({"objects": ["Face"], "rect": MOUTH}, strength=0.7)
fp.render("s2_mouth", scale=1.0, grid=False)
fp.texture_lines({"objects": ["Clothes"], "rect": BUTTONS}, strength=0.3)
fp.render("s3_buttons", scale=1.0, grid=False)
fp.texture_lines({"objects": ["Hair"]}, strength=0.25)
fp.render("s4_hair", scale=1.0, grid=False)
fp.cel(threshold=0.35)
fp.render("s5_cel", scale=1.0, grid=False)
fp.preview("NONE")
fp.render("s6_material_lines", scale=1.0, grid=False)
fp.preview("WHITE")
bpy.ops.wm.save_mainfile()
print("@@@ done", flush=True)
