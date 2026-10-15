"""ビューポートのライブプレビュー(ビューポートのコンポジタ)を、窓のある Blender で撮る。

  blender <file.blend> --python gui_viewport_check.py -- <out_dir>

3D ビューをカメラ視点・レンダー表示・コンポジタ「常に」にして、プレビューの種類と線の太さを
切り替えるたびに 3D ビューの領域を撮る。終わったら自分で閉じる(利用者の Blender には触らない)。
"""
import sys
from pathlib import Path

import bpy

ARGV = sys.argv[sys.argv.index("--") + 1:]
OUT = Path(ARGV[0]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
STEPS = [("WHITE", 1.0), ("NONE", 1.0), ("MONO_LIGHT", 1.0), ("CEL", 1.0), ("CEL", 2.0), ("NONE", 2.0),
         ("CEL", "sun")]                     # 最後: 日を 120 度回す(影がついて行くか)
state = {"i": -1, "wait": 0}


def view3d():
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                return win, area
    return None, None


def setup():
    win, area = view3d()
    sp = area.spaces[0]
    # 利用者と同じ手順: STEP3 の「コンポジタープレビューを有効化」で入れる
    with bpy.context.temp_override(window=win, area=area, screen=win.screen):
        bpy.context.scene.fp_enable_compositor_view = False
        bpy.context.scene.fp_enable_compositor_view = True
    sp.region_3d.view_perspective = 'CAMERA'
    sp.overlay.show_overlays = False
    region = next(r for r in area.regions if r.type == 'WINDOW')
    try:
        with bpy.context.temp_override(window=win, area=area, region=region):
            bpy.ops.view3d.view_center_camera()
    except RuntimeError as e:                # 中央寄せはできなくても撮る
        print("@@@ center failed", e, flush=True)


def tick():
    sc = bpy.context.scene
    if state["wait"] > 0:
        state["wait"] -= 1
        return 0.5
    win, area = view3d()
    if state["i"] >= 0:
        mode, scale = STEPS[state["i"]]
        with bpy.context.temp_override(window=win, area=area):
            bpy.ops.screen.screenshot_area(filepath=str(OUT / f"{state['i']:02d}_{mode}_{scale}.png"))
        print("@@@ shot", state["i"], mode, scale, flush=True)
    state["i"] += 1
    if state["i"] >= len(STEPS):
        bpy.ops.wm.quit_blender()
        return None
    mode, scale = STEPS[state["i"]]
    sc.fp_preview_mode = mode
    if scale == "sun":
        import math
        sun = next(o for o in sc.objects if o.type == 'LIGHT')
        sun.rotation_euler.z += math.radians(120)
        state["wait"] = 12
        return 0.5
    for o in sc.objects:
        if o.type == 'MESH':
            o.fp_line_scale = 1.0
    target = sc.objects.get("Monkey") or max((o for o in sc.objects if o.type == 'MESH'),
                                              key=lambda o: o.dimensions.length)
    target.fp_line_scale = scale
    state["wait"] = 12                      # 6 秒待つ(シェーダーとコンポジタの更新)
    return 0.5


def start():
    bpy.context.scene.fp_cel_sky = True          # 保存したファイルは「空なし」の手順の後
    bpy.context.scene.fp_cel_shadow_line = False
    setup()
    bpy.app.timers.register(tick, first_interval=3.0)
    return None


bpy.app.timers.register(start, first_interval=2.0)
