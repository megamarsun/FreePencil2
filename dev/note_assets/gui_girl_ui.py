"""4K デモの小窓用: STEP0 のパネル(仕上がり=キャラ)と、STEP0 の進捗バーを、字幕なしで撮る(窓のある Blender)。

  blender --enable-event-simulate --window-maximized <girl_clean.blend> --python gui_girl_ui.py -- <out_dir>
"""
import sys
import time
from pathlib import Path

import bpy

OUT = Path(sys.argv[sys.argv.index("--") + 1:][0]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
S = {"i": 0, "n": 0, "t0": None}


def win():
    return bpy.context.window_manager.windows[0]


def v3d():
    areas = list(win().screen.areas)
    a = next((a for a in areas if a.type == "VIEW_3D"), None)
    if a is None:
        a = max(areas, key=lambda a: a.width * a.height)
        a.type = "VIEW_3D"
    return a


def ov():
    a = v3d()
    return dict(window=win(), area=a, region=next(r for r in a.regions if r.type == "WINDOW"),
                screen=win().screen)


def shot(name):
    with bpy.context.temp_override(window=win()):
        bpy.ops.screen.screenshot(filepath=str(OUT / f"{name}.png"))


def applied():
    sc = bpy.context.scene
    t = getattr(sc, "compositing_node_group", None) or getattr(sc, "node_tree", None)
    return t is not None and any(n.type == "GROUP" and n.node_tree and n.node_tree.name.startswith("FreePencil_v1")
                                 for n in t.nodes)


def step():
    w = win()
    i = S["i"]
    if i == 0:
        bpy.context.preferences.use_preferences_save = False
        with bpy.context.temp_override(**ov()):
            bpy.ops.screen.screen_full_area(use_hide_panels=False)
    elif i == 1:
        a = v3d()
        sp = a.spaces[0]
        sp.show_region_ui = False
        sp.show_region_toolbar = False
        sp.overlay.show_overlays = False
        sp.show_gizmo = False
        sp.shading.type = "RENDERED"
        sc = bpy.context.scene
        sc.view_settings.view_transform = "Standard"
        sc.eevee.taa_samples = 8
        sc.fp_auto_style = "WEIGHTED"            # キャラ
        sc.fp_enable_compositor_view = True
        with bpy.context.temp_override(**ov()):
            bpy.ops.view3d.view_camera()
            bpy.ops.view3d.view_center_camera()
        ms = [o for o in sc.objects if o.type == "MESH" and len(o.data.polygons) and not o.hide_render]
        for o in ms:
            o.select_set(True)
        bpy.context.view_layer.objects.active = ms[0]
    elif i == 2:
        # パネルはマウスの所に出る。ツールチップが出ないよう、出したらマウスをパネルの外へ
        w.event_simulate(type="MOUSEMOVE", value="NOTHING", x=int(w.width * 0.5), y=int(w.height * 0.6))
        with bpy.context.temp_override(**ov()):
            bpy.ops.wm.call_panel(name="FREEPENCIL_PT_STEP0", keep_open=True)
    elif i == 3:
        # ツールチップが出ないよう、ボタンの無い所(「詳細」の見出し)へマウスを置く
        w.event_simulate(type="MOUSEMOVE", value="NOTHING", x=1140, y=w.height - 524)
        S["i"] += 1
        return 1.2
    elif i == 4:
        shot("panel")
        w.event_simulate(type="ESC", value="PRESS")
        w.event_simulate(type="ESC", value="RELEASE")
    elif i == 5:
        with bpy.context.temp_override(**ov()):
            bpy.ops.freepencil.auto_setup("INVOKE_DEFAULT")
        S["t0"] = time.time()
    elif i == 6:
        if not applied() and time.time() - S["t0"] < 120:
            shot(f"progress_{S['n']:03d}")
            S["n"] += 1
            return 0.12
        shot("done")
        bpy.ops.wm.quit_blender()
        return None
    S["i"] += 1
    return 1.2 if i in (2,) else 0.8


bpy.app.timers.register(step, first_interval=4.0)
