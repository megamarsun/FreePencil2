"""コンポジタのノードエディタを撮って、配置を目で確かめる。

指標(重なり/逆流/交差)だけでは読みやすさが分からないので画で見る。
2フェーズ。GUI 起動時にファイルを渡さないとスプラッシュが画に入る。

  # フェーズ1: STEP0 まで通した .blend を作る
  blender -b --factory-startup --python shot_node_editor.py -- \
      --prepare <abs>/nodes.blend
  # フェーズ2: それを開いて各ツリーを撮る
  blender --factory-startup -p 0 0 2400 1400 <abs>/nodes.blend \
      --python shot_node_editor.py -- --out <abs dir> --tag after
"""
from __future__ import annotations

import sys
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))

import fp_batch  # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

# ---------------------------------------------------------------- phase 1
if "--prepare" in ARGV:
    save = Path(ARGV[ARGV.index("--prepare") + 1]).resolve()
    save.parent.mkdir(parents=True, exist_ok=True)
    fp_batch.install_addon()
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.mesh.primitive_cube_add()
    bpy.context.active_object.select_set(True)
    bpy.context.scene.fp_node_type = "pro"
    bpy.context.scene.fp_enable_compositor_view = False
    print("prepare auto_setup: "
          + str(list(bpy.ops.freepencil.auto_setup("EXEC_DEFAULT"))))
    bpy.ops.wm.save_as_mainfile(filepath=str(save))
    print(f"[prepare] saved {save}")
    sys.exit(0)

# ---------------------------------------------------------------- phase 2
OUT = Path(ARGV[ARGV.index("--out") + 1]).resolve()
TAG = ARGV[ARGV.index("--tag") + 1]
OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / f"nodes_{TAG}.log"
LOG.write_text("", encoding="utf-8")


def log(m) -> None:
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(str(m) + "\n")


def win():
    return bpy.context.window_manager.windows[0]


def area_of(ui_type):
    for a in win().screen.areas:
        if a.ui_type == ui_type:
            return a
    return None


_state = {"phase": 0, "targets": [], "i": 0}


def tick():
    try:
        if _state["phase"] == 0:
            area = area_of("VIEW_3D")
            area.ui_type = "CompositorNodeTree"
            # ルート + FreePencil のグループを順に撮る
            _state["targets"] = [None] + [
                g.name for g in bpy.data.node_groups
                if g.name.startswith("FreePencil")]
            log("targets: " + str(_state["targets"]))
            _state["phase"] = 1
            return 1.0

        area = area_of("CompositorNodeTree")
        space = area.spaces.active
        region = next((r for r in area.regions if r.type == "WINDOW"), None)

        if _state["phase"] == 1:
            if _state["i"] >= len(_state["targets"]):
                log("done")
                bpy.ops.wm.quit_blender()
                return None
            name = _state["targets"][_state["i"]]
            # グループへは path を積んで入る。node_tree への代入では
            # ルートが差し替わるだけでグループの中身は見えない
            while len(space.path) > 1:
                space.path.pop()
            if name is not None:
                space.path.append(bpy.data.node_groups[name])
            area.tag_redraw()
            log(f"showing {name or 'root'} (path depth {len(space.path)})")
            _state["phase"] = 3
            return 1.2

        if _state["phase"] == 3:
            # 視点合わせはパス切替が効いた後で。同じティックでやると
            # 前のツリーの選択状態を見てしまう
            with bpy.context.temp_override(window=win(), screen=win().screen,
                                           area=area, region=region):
                bpy.ops.node.select_all(action="SELECT")
                bpy.ops.node.view_selected()
                bpy.ops.node.select_all(action="DESELECT")
            area.tag_redraw()
            _state["phase"] = 2
            return 1.2

        name = _state["targets"][_state["i"]] or "root"
        with bpy.context.temp_override(window=win(), screen=win().screen,
                                       area=area, region=region):
            bpy.ops.screen.screenshot_area(
                filepath=str(OUT / f"nodes_{TAG}_{name}.png"))
        log(f"shot nodes_{TAG}_{name}.png")
        _state["i"] += 1
        _state["phase"] = 1
        return 0.4
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
