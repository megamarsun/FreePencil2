"""STEP0 がビューポート表示をどう変えるかだけを見る (GUI)。

4.2 ではライブプレビューが成立しない(AOV が評価されない)ため、
レンダー表示へ切り替えてはいけない。切り替えると真っ白になる。
ここでは STEP0 の前後で shading.type がどうなるかだけを記録する。

  blender --factory-startup -p 0 0 1200 800 <prepared.blend> \
      --python probe_step0_viewport.py -- --out <abs dir> --tag 4.2.3
"""
from __future__ import annotations

import sys
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))

import fp_batch  # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = Path(ARGV[ARGV.index("--out") + 1])
TAG = ARGV[ARGV.index("--tag") + 1]
OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / f"step0_viewport_{TAG}.log"
LOG.write_text("", encoding="utf-8")


def log(msg) -> None:
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(str(msg) + "\n")


def view3d():
    for area in bpy.context.window_manager.windows[0].screen.areas:
        if area.ui_type == "VIEW_3D":
            return area
    return None


_state = {"phase": 0}


def tick():
    try:
        area = view3d()
        shading = area.spaces.active.shading
        if _state["phase"] == 0:
            log(f"blender={bpy.app.version_string}")
            log(f"before: type={shading.type} "
                f"use_compositor={shading.use_compositor}")
            meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
            for o in meshes:
                o.select_set(True)
            if meshes:
                bpy.context.view_layer.objects.active = meshes[0]
            bpy.context.scene.fp_enable_compositor_view = True
            log("auto_setup: " + str(list(
                bpy.ops.freepencil.auto_setup("EXEC_DEFAULT"))))
            _state["phase"] = 1
            return 1.5
        log(f"after:  type={shading.type} "
            f"use_compositor={shading.use_compositor}")
        from freepencil2 import compat
        log(f"flag HAS_AOV_IN_VIEWPORT_COMPOSITOR="
            f"{compat.HAS_AOV_IN_VIEWPORT_COMPOSITOR}")
        expected = "RENDERED" if compat.HAS_AOV_IN_VIEWPORT_COMPOSITOR else "SOLID"
        log(("OK" if shading.type == expected else "NG")
            + f" expected={expected} actual={shading.type}")
        bpy.ops.wm.quit_blender()
        return None
    except Exception:
        import traceback
        log("ERROR\n" + traceback.format_exc())
        bpy.ops.wm.quit_blender()
        return None


try:
    fp_batch.install_addon()
    bpy.app.timers.register(tick, first_interval=1.5)
except Exception:
    import traceback
    log("SETUP ERROR\n" + traceback.format_exc())
