"""手作業デモの 4K 版: 手直しの各段階を F12 で 4K に撮る(動画は assemble_girl_4k.py で組む)。

  blender -b --factory-startup --python girl_4k_states.py -- <girl_clean.blend> <out_dir>

手直しの順番(v2 — 「目のフチの線は消す、顔は正面から光」の指摘で組み直した):
  1. STEP0(キャラ)
  2. モデルのトゥーン用の殻(Solidify + Outline 材質)を切る。髪の線が全部二重になっていた
  3. 目のまわりの形の線をまとめる(ai.merge)。眼球の丸い線が出ていた。目は絵の色で描く
  4. ボタン: 服の絵の線をボタンのまわりだけ
  5. 日を正面(カメラの向きから 25° 上・見る人の左へ 15°)、影のしきい値 0.25。横からの日では顔に
     大きな影が出た。左へ少し振ると鼻の影が薄くなる(4 通りを画像で比べて決めた)
4K は 2倍レンダを使わない(出力が大きいほど線が画面に対して細くなるため。画像で比べて決めた)。
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "batch"))
import fp_batch                                   # noqa: E402
fp_batch.install_addon()
import bpy                                        # noqa: E402
from mathutils import Matrix                      # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = Path(ARGV[0]).resolve(), Path(ARGV[1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(SRC))
sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = 3840, 2160
sc.eevee.taa_render_samples = 32
cam = sc.camera
sun = bpy.data.objects["Sun"]


def sun_from_camera(up_deg, side_deg=0.0):
    m = (cam.matrix_world.to_3x3() @ Matrix.Rotation(math.radians(up_deg), 3, "X")
         @ Matrix.Rotation(math.radians(side_deg), 3, "Y"))
    sun.rotation_euler = m.to_euler()
    bpy.context.view_layer.update()


SIDE_SUN = tuple(sun.rotation_euler)   # 元のファイルの日(横から)。比べるために控える
sun_from_camera(25, -15)               # 元の 3D も同じ日で撮る(比べる場面で光が違わないように)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "girl_4k.blend"))
fp = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.ai"))

EYES = (0.39, 0.33, 0.51, 0.49)        # 部品より少し広く(狭いと範囲の縁に短い線が残った)
BUTTONS = (0.40, 0.62, 0.50, 0.84)


def shoot(name):
    fp.render(name, scale=1.0, grid=False)


fp.preview("NONE")
shoot("s0_model")
fp.auto("WEIGHTED")
sc.fp_supersample = False
bpy.ops.freepencil2.link_button()
bpy.ops.freepencil.measure_line_weight()
fp.preview("WHITE")
shoot("s1_step0")
for o in sc.objects:                   # 2. トゥーン用の殻を切る
    for m in getattr(o, "modifiers", []):
        if m.type == "SOLIDIFY":
            m.show_render = m.show_viewport = False
bpy.ops.freepencil.measure_line_weight()
shoot("s2_noshell")
fp.merge({"objects": ["Face"], "rect": EYES})       # 3. 目のまわり
shoot("s3_eyes")
fp.texture_lines({"objects": ["Clothes"], "rect": BUTTONS}, strength=0.3)   # 4. ボタン
shoot("s4_buttons")
keep_sun = tuple(sun.rotation_euler)
sun.rotation_euler = SIDE_SUN                        # 比べる: 横からの日のセル
bpy.context.view_layer.update()
fp.cel(threshold=0.25)
shoot("s5_cel_side")
sun.rotation_euler = keep_sun                        # 5. セル(日は正面)
bpy.context.view_layer.update()
fp.cel(threshold=0.25)
shoot("s5_cel")
fp.preview("WHITE")
bpy.ops.wm.save_mainfile()
print("@@@ done", flush=True)
