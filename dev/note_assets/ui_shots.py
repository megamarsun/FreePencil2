"""マニュアル用のUIスクリーンショットを撮る (フェーズ2・GUI)。

ui_prepare.py が作った .blend を GUI の Blender で開き、実際に
インストールされている拡張機能を有効化して、そのまま撮影する。

  10_ui_sidebar_step0.png   初回起動時のサイドバー (STEP0 だけ開いている)
  11_ui_step3.png           STEP3 の線調整パネル
  12_ui_preferences.png     プリファレンス→アドオンの画面
  13_ui_outliner.png        アウトライナ「Blenderファイル」→ノードグループ

使い方:
  blender --factory-startup -p 0 0 2400 1400 <prepared.blend> \
      --python ui_shots.py -- --out out

注意:
- 撮る前に scripts\\sync_extension.bat で実機の拡張機能を最新にしておくこと。
  ここでは junction ではなく「実際に配布される拡張機能」を有効化する。
- ProseMirror ならぬ Blender の UI も、描画されるまで
  region.active_panel_category に値を入れられない。だからタブ切替は
  サイドバーを開いた次のティックで行う。
"""
from __future__ import annotations

import sys
from pathlib import Path

import bpy

ADDON_MODULE = "bl_ext.user_default.freepencil2"

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = Path(ARGV[ARGV.index("--out") + 1]) if "--out" in ARGV else Path.cwd()
OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "ui_shots.log"
LOG.write_text("", encoding="utf-8")


def log(msg: str) -> None:
    """GUI の Blender は stdout がバッファされるのでファイルへ書く。"""
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def main_window():
    return bpy.context.window_manager.windows[0]


def find_area(ui_type: str):
    for area in main_window().screen.areas:
        if area.ui_type == ui_type:
            return area
    return None


def shoot(area, name: str) -> None:
    win = main_window()
    region = next((r for r in area.regions if r.type == "WINDOW"), None)
    with bpy.context.temp_override(window=win, screen=win.screen,
                                   area=area, region=region):
        bpy.ops.screen.screenshot_area(filepath=str(OUT / name))
    log(f"shot {name} area={area.ui_type} {area.width}x{area.height}")


# ------------------------------------------------------------- panel state
# パネルの開閉は Python から触れず、bl_options を書き換えて再登録しても
# 既に描画済みのパネルには効かない (Blender が idname ごとに状態を持つ)。
# そこで別 idname のサブクラスを登録し直す。未描画の idname は bl_options の
# 既定値で描かれるので、狙った開閉状態になる。
PANEL_ORDER = ["FREEPENCIL_PT_STEP0", "FREEPENCIL_PT_STEP1",
               "FREEPENCIL_PT_STEP2", "FREEPENCIL_PT_STEP3",
               "FREEPENCIL_PT_STEP4", "FREEPENCIL_PT_CAMERAS"]
_current: dict[str, type] = {}
_variant = {"n": 0}
_big_outliner: dict = {}


def panels_variant(open_ids: set[str]) -> None:
    for cls in _current.values():
        bpy.utils.unregister_class(cls)
    _variant["n"] += 1
    suffix = f"_V{_variant['n']}"
    for idname in PANEL_ORDER:
        base = _ORIGINALS[idname]
        new = type(base.__name__ + suffix, (base,),
                   {"bl_idname": idname + suffix,
                    "bl_options": set() if idname in open_ids
                    else {"DEFAULT_CLOSED"}})
        bpy.utils.register_class(new)
        _current[idname] = new
    log(f"panels variant {suffix} open={sorted(open_ids)}")


def open_sidebar():
    area = find_area("VIEW_3D")
    space = area.spaces.active
    space.show_region_ui = True
    space.shading.type = "SOLID"
    space.overlay.show_overlays = False
    region = next((r for r in area.regions if r.type == "WINDOW"), None)
    with bpy.context.temp_override(window=main_window(),
                                   screen=main_window().screen,
                                   area=area, region=region):
        bpy.ops.view3d.view_all()
    return area


def select_fp_tab():
    area = find_area("VIEW_3D")
    for r in area.regions:
        if r.type == "UI":
            try:
                r.active_panel_category = "FreePencil"
            except Exception as exc:                   # noqa: BLE001
                log(f"tab switch failed: {exc}")
    return area


def prep_step3():
    panels_variant({"FREEPENCIL_PT_STEP3"})
    return find_area("VIEW_3D")


def prep_preferences():
    """3Dビューのエリアを一時的にプリファレンスへ切り替える (広く撮るため)。"""
    area = find_area("VIEW_3D")
    area.ui_type = "PREFERENCES"
    bpy.context.preferences.active_section = "ADDONS"
    bpy.context.window_manager.addon_search = "FreePencil"
    return area


def prep_outliner():
    """STEP0 を実行してノードグループを作り、広いエリアをアウトライナにする。"""
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    for o in meshes:
        o.select_set(True)
    if meshes:
        bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    log(f"node groups: {[g.name for g in bpy.data.node_groups]}")
    area = find_area("PREFERENCES")
    area.ui_type = "OUTLINER"
    space = area.spaces.active
    space.display_mode = "LIBRARIES"     # =「Blenderファイル」
    # 復旧手順で消すのは FreePencil で始まるノードグループだけ。
    # 検索で絞らないと全オブジェクトのツリーが出て何も読めない
    space.filter_text = "FreePencil"
    _big_outliner["area"] = area
    return area


def show_outliner():
    """OUTLINER は2つある。prep で掴んだ広い方を使う。"""
    return _big_outliner["area"]


STEPS = [
    (open_sidebar, "_warmup.png"),
    (select_fp_tab, "10_ui_sidebar_step0.png"),
    (prep_step3, "11_ui_step3.png"),
    (prep_preferences, "12_ui_preferences.png"),
    (prep_outliner, "_outliner_unfiltered.png"),
    (show_outliner, "13_ui_outliner.png"),
]

_state = {"i": 0, "area": None, "phase": "prep"}


def tick():
    try:
        if _state["i"] >= len(STEPS):
            log("done")
            bpy.ops.wm.quit_blender()
            return None
        prep, name = STEPS[_state["i"]]
        if _state["phase"] == "prep":
            log(f"prep {name}")
            _state["area"] = prep()
            for a in main_window().screen.areas:
                a.tag_redraw()
            _state["phase"] = "shoot"
            return 0.8              # 描画が落ち着くまで待つ
        shoot(_state["area"], name)
        _state["i"] += 1
        _state["phase"] = "prep"
        return 0.3
    except Exception:
        import traceback
        log("ERROR\n" + traceback.format_exc())
        bpy.ops.wm.quit_blender()
        return None


try:
    log("start " + bpy.data.filepath)
    log("addon_enable: " + str(
        bpy.ops.preferences.addon_enable(module=ADDON_MODULE)))
    view = bpy.context.preferences.view
    view.language = "ja_JP"
    view.use_translate_interface = True
    view.use_translate_tooltips = True
    view.ui_scale = 1.25            # マニュアルで読める字の大きさにする
    _ORIGINALS = {n: getattr(bpy.types, n) for n in PANEL_ORDER}
    _current.update(_ORIGINALS)
    bpy.app.timers.register(tick, first_interval=1.5)
    log("timer registered")
except Exception:
    import traceback
    log("SETUP ERROR\n" + traceback.format_exc())
