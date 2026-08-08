"""遠景つぶれ軽減を、実際の制作シーンで検証する。

合成した通路シーンでしか測っていなかったので、STEP0 済みのデパートを
開いて「軽減なし」と「効き具合0.6」を撮り比べる。STEP1 は済んでいるので
STEP3 の押し直しとレンダだけ。

  blender -b --factory-startup --python eval_far_relief_real.py -- \
      --blend <STEP0済みの.blend> --out <dir> [--res 1400] [--relief 0.6]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
import fp_batch  # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


BLEND = Path(arg("--blend")).resolve()
OUT = Path(arg("--out")).resolve()
OUT.mkdir(parents=True, exist_ok=True)
RES = int(arg("--res", "1400"))
RELIEF = float(arg("--relief", "0.6"))
T0 = time.time()


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


def metrics(png: Path) -> dict:
    """線の量と「べた塗りになっている割合」。3x3 が全部インクなら潰れ。"""
    img = bpy.data.images.load(str(png.resolve()))
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    bpy.data.images.remove(img)
    a = px[:, :, 3]
    g = px[:, :, :3].mean(axis=2) * a + (1.0 - a)
    ink = g < 0.5
    solid = ink.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            solid &= np.roll(np.roll(ink, dy, 0), dx, 1)
    return {"ink": round(float(ink.mean()), 5),
            "crush": round(float(solid.mean()), 5)}


fp_batch.install_addon()
bpy.ops.wm.open_mainfile(filepath=str(BLEND))
scene = bpy.context.scene
say(f"開いた objects={len(bpy.data.objects)} camera={scene.camera}")

if scene.camera is None:
    cams = [o for o in scene.objects if o.type == "CAMERA"]
    if cams:
        scene.camera = cams[0]
        say(f"カメラを {cams[0].name} に設定")
    else:
        # 制作の中間ファイル(MODEL_ONLY 等)にはカメラが無いことがある。
        # 全体のバウンディングボックスから、奥行きが出る向きに1台置く
        meshes = [o for o in scene.objects if o.type == "MESH"]
        pts = [o.matrix_world @ Vector(c)
               for o in meshes for c in o.bound_box]
        mn = Vector((min(p[i] for p in pts) for i in range(3)))
        mx = Vector((max(p[i] for p in pts) for i in range(3)))
        size = mx - mn
        cam_data = bpy.data.cameras.new("FP_Check")
        cam_data.lens = 35.0
        cam_data.clip_end = max(size) * 4.0
        cam = bpy.data.objects.new("FP_Check", cam_data)
        scene.collection.objects.link(cam)
        # 長辺方向の端から中心を見る = 奥行きが最も出る
        axis = max(range(3), key=lambda i: size[i])
        eye = (mn + mx) * 0.5
        eye[axis] = mn[axis] - size[axis] * 0.15
        eye[2] = mn[2] + size[2] * 0.55
        cam.location = eye
        target = (mn + mx) * 0.5
        target[2] = mn[2] + size[2] * 0.45
        d = target - eye
        cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        scene.camera = cam
        say(f"カメラが無いので自動配置 (長辺 {max(size):.1f}m, "
            f"位置 {tuple(round(v, 1) for v in eye)})")

scene.fp_enable_compositor_view = False
scene.render.engine = fp_batch.eevee_engine()
scene.eevee.taa_render_samples = 8
scene.render.resolution_x = scene.render.resolution_y = RES
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"

rows = {}
for tag, amount in (("off", 0.0), (f"relief{RELIEF}", RELIEF)):
    scene.fp_far_relief = amount
    t = time.time()
    bpy.ops.freepencil2.link_button()          # STEP3 を組み直す
    say(f"STEP3 (効き具合 {amount}) {time.time() - t:.1f}s")
    png = OUT / f"dept_{tag}.png"
    t = time.time()
    fp_batch.render_still(scene, png, 1)
    m = metrics(png)
    rows[tag] = m
    say(f"レンダ {time.time() - t:.1f}s  ink={m['ink']:.5f} "
        f"つぶれ={m['crush']:.5f}  -> {png.name}")

(OUT / "result.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
if rows["off"]["crush"] > 0:
    cut = (1 - rows[f"relief{RELIEF}"]["crush"] / rows["off"]["crush"]) * 100
    keep = rows[f"relief{RELIEF}"]["ink"] / max(rows["off"]["ink"], 1e-9) * 100
    say(f"つぶれ {cut:.1f}% 減、線は {keep:.1f}% 残った")
