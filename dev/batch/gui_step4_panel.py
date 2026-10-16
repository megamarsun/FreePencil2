"""STEP4 のパネルを、オブジェクトモードと頂点ペイントでポップアップに出して撮る(窓のある Blender)。
  blender <file.blend> --python gui_step4_panel.py -- <out_dir>
"""
import sys
from pathlib import Path
import bpy
OUT = Path(sys.argv[sys.argv.index("--") + 1:][0]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
STEPS = ["OBJECT", "VERTEX_PAINT"]
state = {"i": 0, "phase": 0}


def win_area():
    win = bpy.context.window_manager.windows[0]
    area = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    return win, area


def tick():
    win, area = win_area()
    region = next(r for r in area.regions if r.type == 'WINDOW')
    if state["i"] >= len(STEPS):
        bpy.ops.wm.quit_blender()
        return None
    mode = STEPS[state["i"]]
    if state["phase"] == 0:
        obj = bpy.data.objects.get("Monkey")
        with bpy.context.temp_override(window=win, area=area, region=region):
            if bpy.context.object and bpy.context.object.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            if mode == "VERTEX_PAINT":
                bpy.context.scene.fp_color_type = "mecha_color"
                bpy.ops.freepencil3.link_button()
            bpy.ops.wm.call_panel(name="FREEPENCIL_PT_STEP4", keep_open=True)
        state["phase"] = 1
        return 1.5
    with bpy.context.temp_override(window=win):
        bpy.ops.screen.screenshot(filepath=str(OUT / f"{state['i']}_{mode}.png"))
    print("@@@ shot", mode, flush=True)
    state["phase"] = 0
    state["i"] += 1
    return 1.0


bpy.app.timers.register(tick, first_interval=3.0)
