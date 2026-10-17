"""窓のある Blender で、パネルのボタンと同じ呼び方(INVOKE)で順に押して、毎回撮る(v2.9.1 の点検)。

バッチの点検(audit_buttons.py)は EXEC で押すので、ボタンの本当の通り道
(STEP0/STEP1 の進捗バー付きのモーダル、外すの確認、頂点ペイントの表示切り替え、
ノードエディタの書き出し/読み込み、Ctrl+Z)を通らない。それをここで通す。

  blender --enable-event-simulate <out_dir>/base_clean.blend --python gui_buttons.py -- <out_dir>

撮るもの: 毎回ウィンドウ全体(ビューポートはコンポジタ表示)、要所で F12 の絵も。
"""
import json
import math
import sys
import time
import traceback
from pathlib import Path

import bpy

OUT = Path(sys.argv[sys.argv.index("--") + 1:][0]).resolve() / "gui"
OUT.mkdir(parents=True, exist_ok=True)
LOG = []
S = {"i": 0, "t0": time.time(), "wait_until": None}


def win():
    return bpy.context.window_manager.windows[0]


def area(kind="VIEW_3D"):
    return next(a for a in win().screen.areas if a.type == kind)


def ov(kind="VIEW_3D"):
    a = area(kind)
    r = next(r for r in a.regions if r.type == "WINDOW")
    return dict(window=win(), area=a, region=r, screen=win().screen)


def shot(name):
    with bpy.context.temp_override(window=win()):
        bpy.ops.screen.screenshot(filepath=str(OUT / f"{S['i']:02d}_{name}.png"))


def f12(name):
    sc = bpy.context.scene
    keep = sc.render.filepath
    sc.render.filepath = str(OUT / f"{S['i']:02d}_{name}_F12.png")
    with bpy.context.temp_override(**ov()):
        bpy.ops.render.render(write_still=True)
    sc.render.filepath = keep


def comp_nodes():
    sc = bpy.context.scene
    t = getattr(sc, "compositing_node_group", None) or getattr(sc, "node_tree", None)
    return 0 if t is None else len(t.nodes)


def state(tag, **kw):
    sc = bpy.context.scene
    ob = bpy.context.object
    d = {"step": S["i"], "tag": tag, "t": round(time.time() - S["t0"], 1),
         "comp_nodes": comp_nodes(),
         "aovs": [a.name for a in bpy.context.view_layer.aovs],
         "preview": sc.fp_preview_mode,
         "mode": ob.mode if ob else None,
         "active": ob.name if ob else None,
         "shading": area().spaces[0].shading.type,
         "use_compositor": getattr(area().spaces[0].shading, "use_compositor", None),
         "color_attrs": ([a.name for a in ob.data.color_attributes] if ob and ob.type == "MESH" else None)}
    d.update(kw)
    LOG.append(d)
    (OUT / "log.json").write_text(json.dumps(LOG, ensure_ascii=False, indent=1), encoding="utf-8")
    print("@@@", json.dumps(d, ensure_ascii=False), flush=True)


def press(idname, mode="INVOKE_DEFAULT", kind="VIEW_3D", **kw):
    cat, _, name = idname.partition(".")
    fn = getattr(getattr(bpy.ops, cat), name)
    with bpy.context.temp_override(**ov(kind)):
        if not fn.poll():
            return "poll False"
        try:
            return sorted(fn(mode, **kw))
        except RuntimeError as e:
            return f"RuntimeError: {e}"


def select(names):
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        with bpy.context.temp_override(**ov()):
            bpy.ops.object.mode_set(mode="OBJECT")
    for o in bpy.context.scene.objects:
        o.select_set(o.name in names)
    bpy.context.view_layer.objects.active = bpy.data.objects[sorted(names)[0] if "Monkey" not in names else "Monkey"]


def all_meshes():
    return {o.name for o in bpy.context.scene.objects if o.type == "MESH"}


def rendered_view():
    sp = area().spaces[0]
    sp.shading.type = "RENDERED"


# ---------------------------------------------------------------- 手順
def s_setup():
    a = area()
    sp = a.spaces[0]
    sp.show_region_ui = True
    with bpy.context.temp_override(**ov()):
        bpy.ops.view3d.view_camera()
        bpy.ops.view3d.view_center_camera()
    rendered_view()
    bpy.context.scene.fp_enable_compositor_view = True     # 下に敷いた場面では切ってあった
    select(all_meshes())
    shot("clean")
    state("clean")
    return 3


def s_step0():
    S["r"] = press("freepencil.auto_setup")        # モーダル(進捗バー)で回る
    S["wait_until"] = lambda: comp_nodes() > 0 and "mecha_color" in [x.name for x in bpy.context.view_layer.aovs]
    shot("step0_running")
    state("STEP0 pressed (modal)", result=S["r"])
    return 1


def s_step0_done():
    shot("step0_done")
    f12("step0")
    state("STEP0 done")
    return 2


def s_step3():
    r = press("freepencil2.link_button")
    shot("step3_again")
    state("STEP3 again", result=r)
    return 2


def mk_preview(mode):
    def s():
        bpy.context.scene.fp_preview_mode = mode
        return 3
    def t():
        shot(f"preview_{mode}")
        state(f"preview {mode}")
        return 1
    return [s, t]


def s_preview_back():
    bpy.context.scene.fp_preview_mode = "WHITE"
    return 2


def s_measure():
    r = press("freepencil.measure_line_weight")
    shot("measure")
    state("measure", result=r)
    return 2


def s_paint_mask():
    select({"Monkey"})
    bpy.context.scene.fp_color_type = "mask_color"
    r = press("freepencil3.link_button")
    S["paint_r"] = r
    return 2


def s_paint_mask_shot():
    shot("paint_mask_mode")         # 頂点カラー表示に切り替わるはず
    state("paint button (mask)", result=S["paint_r"])
    ob = bpy.data.objects["Monkey"]
    me = ob.data
    a = me.color_attributes["mask_color"]
    for lp in me.loops:
        if me.vertices[lp.vertex_index].co.x > 0:
            a.data[lp.index].color = (1, 1, 1, 1)
    me.update()
    return 2


def s_paint_mask_back():
    shot("paint_mask_painted")
    with bpy.context.temp_override(**ov()):
        bpy.ops.object.mode_set(mode="OBJECT")
    rendered_view()
    return 3


def s_paint_mask_result():
    shot("paint_mask_result")
    f12("mask")
    state("after mask paint, back to rendered view")
    return 1


def s_halffill_prep():
    ob = bpy.data.objects["Panel"]
    me = ob.data
    a = me.color_attributes["mecha_color"]
    for lp in me.loops:
        x = me.vertices[lp.vertex_index].co.x
        a.data[lp.index].color = (0.9, 0.25, 0.2, 1) if x < 0.01 else (0.15, 0.3, 0.9, 1)
    me.update()
    select({"Panel"})
    shot("halffill_before")
    f12("halffill_before")
    bpy.context.scene.fp_color_type = "mecha_color"
    S["paint_r"] = press("freepencil3.link_button")
    return 2


def s_halffill_select():
    ob = bpy.data.objects["Panel"]
    me = ob.data
    # 使う人の手順: 頂点の選択マスクに切り替え、Alt+A で全部外して、境目の頂点を選ぶ
    me.use_paint_mask_vertex = True
    with bpy.context.temp_override(**ov()):
        bpy.ops.paint.vert_select_all(action="DESELECT")
    for v in me.vertices:
        v.select = abs(v.co.x) < 1e-3
    me.update()
    S["sel"] = sum(v.select for v in me.vertices)
    with bpy.context.temp_override(**ov()):
        bpy.ops.wm.call_panel(name="FREEPENCIL_PT_STEP4", keep_open=True)
    return 2


def s_halffill_press():
    shot("halffill_panel_vpaint")
    r = press("freepencil5.link_button")
    state("Half Fill in vertex paint", result=r, paint=S["paint_r"], selected_verts=S.get("sel"))
    return 2


def s_halffill_done():
    with bpy.context.temp_override(**ov()):
        bpy.ops.object.mode_set(mode="OBJECT")
    rendered_view()
    return 3


def s_halffill_result():
    shot("halffill_after")
    f12("halffill_after")
    state("after Half Fill")
    select(all_meshes())
    return 1


def s_step5():
    sc = bpy.context.scene
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "gui_scene.blend"))
    sc.fp_file_output = True
    press("freepencil2.link_button")
    r = press("freepencil.render_cameras")
    files = sorted(str(p.relative_to(OUT)) for p in (OUT / "camera_renders").rglob("*.png")) \
        if (OUT / "camera_renders").exists() else []
    shot("step5")
    state("STEP5", result=r, files=files)
    return 2


def s_node_editor():
    # 下のタイムラインをコンポジタのノードエディタにして、FreePencil のグループを書き出す/読み込む
    a = next(a for a in win().screen.areas if a.type in ("DOPESHEET_EDITOR", "TIMELINE"))
    a.type = "NODE_EDITOR"
    sp = a.spaces[0]
    sp.tree_type = "CompositorNodeTree"
    sc = bpy.context.scene
    tree = getattr(sc, "compositing_node_group", None) or sc.node_tree
    if hasattr(sp, "node_tree"):
        try:
            sp.node_tree = tree
        except Exception:                 # noqa: BLE001
            pass
    grp = next(n for n in tree.nodes if n.type == "GROUP" and n.node_tree
               and n.node_tree.name.startswith("FreePencil_v1"))
    for n in tree.nodes:
        n.select = n is grp
    tree.nodes.active = grp
    S["grp"] = grp.node_tree.name
    S["grp_nodes"] = len(grp.node_tree.nodes)
    return 2


def s_node_export():
    p = OUT / "exported_group.py"
    with bpy.context.temp_override(**ov("NODE_EDITOR")):
        et = bpy.context.space_data.edit_tree
        if et is not None:              # ノードエディタが見ている木で選び直す(使う人がクリックするのと同じ)
            for n in et.nodes:
                n.select = (n.type == "GROUP" and n.node_tree is not None
                            and n.node_tree.name == S["grp"])
            S["sel_types"] = sorted({n.bl_idname for n in et.nodes if n.select})
        S["edit_tree"] = (et.name if et else None,
                          [n.name for n in et.nodes if n.select and n.type == "GROUP"] if et else None)
    r1 = press("node.export_group_to_python", "EXEC_DEFAULT", kind="NODE_EDITOR", filepath=str(p))
    before = {g.name for g in bpy.data.node_groups}
    r2 = press("node.import_group_from_python", "EXEC_DEFAULT", kind="NODE_EDITOR", filepath=str(p))
    new = sorted({g.name for g in bpy.data.node_groups} - before)
    n_new = len(bpy.data.node_groups[new[0]].nodes) if new else None
    links_src = len(bpy.data.node_groups[S["grp"]].links)
    links_new = len(bpy.data.node_groups[new[0]].links) if new else None
    shot("node_editor_io")
    state("node export/import", edit_tree=S["edit_tree"], sel_types=S.get("sel_types"), export=r1, imported=r2, group=S["grp"], nodes_src=S["grp_nodes"],
          new_groups=new, nodes_new=n_new, links_src=links_src, links_new=links_new,
          file_bytes=p.stat().st_size if p.exists() else None)
    # 読み込んだグループに差し替えて F12、元に戻す
    sc = bpy.context.scene
    tree = getattr(sc, "compositing_node_group", None) or sc.node_tree
    grp = tree.nodes.active
    if new:
        keep = grp.node_tree
        linked0 = sum(i.is_linked for i in grp.inputs)
        grp.node_tree = bpy.data.node_groups[new[0]]
        linked1 = sum(i.is_linked for i in grp.inputs)
        f12("imported_group")
        grp.node_tree = keep
        linked2 = sum(i.is_linked for i in grp.inputs)
        f12("original_group")
        state("group swap", inputs_linked_original=linked0, inputs_linked_imported=linked1,
              inputs_linked_back=linked2,
              sockets_src=[s.identifier + ":" + s.name for s in keep.interface.items_tree if getattr(s, "in_out", "") == "INPUT"],
              sockets_new=[s.identifier + ":" + s.name for s in bpy.data.node_groups[new[0]].interface.items_tree if getattr(s, "in_out", "") == "INPUT"])
    return 2


def s_remove():
    with bpy.context.temp_override(**ov()):
        bpy.ops.ed.undo_push(message="before remove")   # 使う人がボタンを押すたびに入る区切り
    S["pre_remove_nodes"] = comp_nodes()
    S["r"] = press("freepencil.remove")             # 確認が出る
    return 2


def s_remove_dialog():
    shot("remove_confirm")
    state("remove pressed (confirm shown?)", result=S["r"])
    w = win()
    try:
        w.event_simulate(type="RET", value="PRESS")
        w.event_simulate(type="RET", value="RELEASE")
    except Exception as e:                          # noqa: BLE001
        state("event_simulate failed", error=str(e))
    return 3


def s_remove_done():
    shot("removed")
    f12("removed")
    state("removed")
    return 1


def s_undo():
    with bpy.context.temp_override(**ov()):
        try:
            bpy.ops.ed.undo()
            r = "ok"
        except Exception as e:                      # noqa: BLE001
            r = str(e)
    S["r"] = r
    return 3


def s_undo_done():
    rendered_view()
    shot("undo")
    state("Ctrl+Z after remove", result=S["r"], pre_remove_nodes=S.get("pre_remove_nodes"))
    return 2


def s_undo_f12():
    f12("undo")
    return 1


def s_redo():
    with bpy.context.temp_override(**ov()):
        bpy.ops.ed.redo()
    return 3


def s_redo_done():
    shot("redo")
    state("Ctrl+Shift+Z (redo = removed again)")
    with bpy.context.temp_override(**ov()):
        bpy.ops.ed.undo()
    return 3


def s_undo2_done():
    shot("undo2")
    state("Ctrl+Z again")
    return 1


def s_step1_modal():
    select(all_meshes())
    S["r"] = press("freepencil.auto_vertex_color")   # 単独の STEP1 もモーダル
    S["wait_until"] = lambda: True
    return 4


def s_step1_done():
    shot("step1_modal")
    state("STEP1 modal", result=S["r"])
    return 1


STEPS = [s_setup, s_step0, s_step0_done, s_step3]
for m in ("NONE", "MONO_LIGHT", "CEL", "WHITE"):
    STEPS += mk_preview(m)
STEPS += [s_measure, s_paint_mask, s_paint_mask_shot, s_paint_mask_back, s_paint_mask_result,
          s_halffill_prep, s_halffill_select, s_halffill_press, s_halffill_done, s_halffill_result,
          s_step5, s_node_editor, s_node_export, s_remove, s_remove_dialog, s_remove_done,
          s_undo, s_undo_done, s_undo_f12, s_redo, s_redo_done, s_undo2_done, s_step1_modal, s_step1_done]


def tick():
    try:
        if S["wait_until"] is not None:
            if not S["wait_until"]() and time.time() - S["t0"] < 600:
                return 0.5
            S["wait_until"] = None
            return 2.0          # 終わってから少し待つ(モーダルの後始末)
        if S["i"] >= len(STEPS):
            state("done")
            bpy.ops.wm.quit_blender()
            return None
        f = STEPS[S["i"]]
        w = f()
        S["i"] += 1
        return float(w)
    except Exception:                               # noqa: BLE001
        state("EXCEPTION", error=traceback.format_exc()[-1500:])
        S["i"] += 1
        return 1.0


bpy.app.timers.register(tick, first_interval=4.0)
