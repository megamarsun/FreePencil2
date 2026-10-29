"""2 影・アニメの影色・光るリムの試し撮り。影の形を作った後の .blend(try_shade_shape.py の after.blend)から撮る。

  blender -b --factory-startup --python try_shadow2.py -- <after.blend> <出力フォルダ>

光の向きは触らずに開く(既定のカメラから: 左・影の量 0.3・高さ 35°)。
出力:
  default.png   既定(影色はアニメ: 暖色は赤紫、灰色・寒色は青紫の影・鮮やかさ 0.5)
  flat.png      影色 1 色(いままでの影)
  anime_cool.png アニメで影の色を青紫 1 色に
  anime_pink.png アニメで影の色を赤紫 1 色に
  s2_ao.png / s2_ao_lo.png / s2_ao_hi.png  アニメ + 2 影(すき間、量 0.5 / 0.2 / 0.8)
  glow_key.png  アニメ + 光るリム(影の側、白)
  glow_back.png 逆光(影の量 0.8)+ 光るリム(ぐるり、薄い水色)
  shadow2.blend s2_ao の設定で保存 / glow.blend glow_back の設定で保存
"""
import math
import sys
from pathlib import Path

import bpy

ARGV = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = Path(ARGV[0]), Path(ARGV[1])
ONLY = set(ARGV[2].split(",")) if len(ARGV) > 2 else None
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fp_batch  # noqa: E402

fp_batch.install_addon()
bpy.ops.wm.open_mainfile(filepath=str(SRC))
sc = bpy.context.scene
OUT.mkdir(parents=True, exist_ok=True)
# 保存したときの木を使わず、今のコードで組み直す
sc.fp_preview_mode = "NONE"
sc.fp_preview_mode = "CEL"


def shot(name):
    if ONLY and name not in ONLY:
        return
    bpy.context.view_layer.update()
    sc.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    print("@@ shot", name, sc.fp_light_mode, sc.fp_cel_shadow_style, sc.fp_cel_shadow2,
          "rim" if sc.fp_cel_rim else "", flush=True)


def setv(**kw):
    for k, v in kw.items():
        setattr(sc, k, v)


shot("default")
setv(fp_cel_shadow_style="FLAT")
shot("flat")
setv(fp_cel_shadow_style="ANIME", fp_cel_shadow_warm=(0.62, 0.62, 0.80))
shot("anime_cool")
setv(fp_cel_shadow_warm=(0.72, 0.56, 0.82), fp_cel_shadow_color=(0.72, 0.56, 0.82))
shot("anime_pink")
setv(fp_cel_shadow_color=(0.62, 0.62, 0.80))
setv(fp_cel_shadow2="AO")
for name, amount in (("s2_ao_lo", 0.2), ("s2_ao_hi", 0.8), ("s2_ao", 0.5)):
    setv(fp_cel_shadow2_threshold=amount)
    shot(name)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "shadow2.blend"), copy=True)
setv(fp_cel_shadow2="NONE", fp_cel_rim=True, fp_cel_rim_side="AUTO", fp_cel_rim_style="GLOW",
     fp_cel_rim_color=(1.0, 1.0, 1.0), fp_cel_rim_width=6.0)
shot("glow_key")
setv(fp_light_amount=0.8, fp_cel_rim_side="ALL", fp_cel_rim_color=(0.75, 1.0, 0.95))
shot("glow_back")
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "glow.blend"), copy=True)
print("@@ done", flush=True)
