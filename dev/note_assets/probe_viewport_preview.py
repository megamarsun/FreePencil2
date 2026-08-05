"""ビューポートのリアルタイムプレビューに線が出るかを撮って確かめる (GUI)。

FreePencil のプレビューは View3DShading.use_compositor='ALWAYS' に依存する
(sample_node.py)。プロパティが存在することと、実際にそのグラフが
ビューポートで評価されることは別なので、画で確認する。

  blender --factory-startup -p 0 0 1600 1000 <prepared.blend> \
      --python probe_viewport_preview.py -- --out out/preview --tag 4.2.3

出力: <out>/viewport_<tag>.png と同 .log
"""
from __future__ import annotations

import sys
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))

import fp_batch  # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = Path(ARGV[ARGV.index("--out") + 1]) if "--out" in ARGV else Path.cwd()
TAG = ARGV[ARGV.index("--tag") + 1] if "--tag" in ARGV else "unknown"
OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / f"viewport_{TAG}.log"
LOG.write_text("", encoding="utf-8")


def log(msg: str) -> None:
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(str(msg) + "\n")


def main_window():
    return bpy.context.window_manager.windows[0]


def view3d():
    for area in main_window().screen.areas:
        if area.ui_type == "VIEW_3D":
            return area
    return None


_state = {"phase": 0}


def tick():
    try:
        area = view3d()
        space = area.spaces.active
        win = main_window()
        region = next((r for r in area.regions if r.type == "WINDOW"), None)

        if _state["phase"] == 0:
            # STEP0 を実行してコンポジタを組む
            meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
            for o in meshes:
                o.select_set(True)
            if meshes:
                bpy.context.view_layer.objects.active = meshes[0]
            bpy.context.scene.fp_enable_compositor_view = True
            res = bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
            log(f"auto_setup: {list(res)}")
            log(f"node groups: {[g.name for g in bpy.data.node_groups]}")
            _state["phase"] = 1
            return 1.0

        if _state["phase"] == 1:
            # ビューポートをレンダー表示 + コンポジタ常時ON にする
            space.shading.type = "RENDERED"
            space.shading.use_compositor = "ALWAYS"
            space.overlay.show_overlays = False
            with bpy.context.temp_override(window=win, screen=win.screen,
                                           area=area, region=region):
                bpy.ops.view3d.view_all()
            log(f"shading={space.shading.type} "
                f"use_compositor={space.shading.use_compositor} "
                f"engine={bpy.context.scene.render.engine} "
                f"device={getattr(bpy.context.scene.render, 'compositor_device', 'n/a')}")
            area.tag_redraw()
            _state["phase"] = 2
            return 6.0          # EEVEE とコンポジタが収束するまで待つ

        if _state["phase"] == 2:
            with bpy.context.temp_override(window=win, screen=win.screen,
                                           area=area, region=region):
                bpy.ops.screen.screenshot_area(
                    filepath=str(OUT / f"viewport_{TAG}.png"))
            log(f"shot viewport_{TAG}.png {area.width}x{area.height}")
            bpy.ops.wm.quit_blender()
            return None
    except Exception:
        import traceback
        log("ERROR\n" + traceback.format_exc())
        bpy.ops.wm.quit_blender()
        return None


try:
    log(f"start {bpy.app.version_string} file={bpy.data.filepath}")
    fp_batch.install_addon()
    bpy.app.timers.register(tick, first_interval=1.5)
except Exception:
    import traceback
    log("SETUP ERROR\n" + traceback.format_exc())
