"""N パネルの FreePencil タブを開いて、STEP0/4/5 のパネルを撮る(窓のある Blender)。
  blender <file.blend> --python gui_panel_shot.py -- <out_dir>
"""
import sys
from pathlib import Path
import bpy
OUT = Path(sys.argv[sys.argv.index("--") + 1:][0]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
state = {"i": 0}


def tick():
    win = bpy.context.window_manager.windows[0]
    area = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    sp = area.spaces[0]
    if state["i"] == 0:
        sp.show_region_ui = True
        for r in area.regions:
            if r.type == 'UI':
                try:
                    r.active_panel_category = "FreePencil"
                except Exception:
                    pass
        for pid in ("FREEPENCIL_PT_STEP4", "FREEPENCIL_PT_CAMERAS"):
            try:
                bpy.ops.wm.context_toggle  # noqa: B018
            except Exception:
                pass
        state["i"] = 1
        return 3.0
    with bpy.context.temp_override(window=win, area=area):
        bpy.ops.screen.screenshot_area(filepath=str(OUT / "panel.png"))
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(tick, first_interval=3.0)
