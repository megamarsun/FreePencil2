"""FreePencil を外す(STEP0〜3 で足したものを消し、元の設定へ戻す)。v2.8.3。

利用者から「一度アドオンを適用したあと戻す方法は？ アングルを変えて光源込みで
レンダリングし直したい」と聞かれた。STEP0 は次のものをシーンに足す・書き換える:
  - メッシュの色属性(mecha_color / mask_color / line_color / bone_color / fine_color)
  - 材質の中の AOV グループと細い線の AOV ノード、透過材質の BLEND -> HASHED、pass_index
  - 材質の無いメッシュへの FreePencil_Material
  - ビューレイヤーの AOV とパス(深度・AO・ディフューズ直接光・影)
  - コンポジタ(RenderLayers / 出力 / ビューアを作り直し、線画のノードを足す)
  - レンダー設定(背景の透過、色の変換 Standard、2倍レンダ 200%、EEVEE の AO)
形状(頂点・面・辺・シャープ・シーム・モディファイア)は変えていない。

元の値は、FreePencil が最初にシーンに触る前に scene["fp_undo"] へ控える(snapshot)。
控えが無い .blend(v2.8 以前に作ったもの)は、足したものを消すだけにして、
元の値が分からない設定は今のまま残し、何を戻せなかったかを知らせる。
"""
from __future__ import annotations

import json

import bpy

from . import compat

UNDO_KEY = "fp_undo"
FP_COLOR_LAYERS = ("mecha_color", "mask_color", "line_color", "bone_color", "fine_color")
FP_AOVS = ("mecha_color", "gen_color", "mask_color", "line_color", "mat_color", "bone_color", "fine_color",
           "fp_shade")
PASSES = ("use_pass_z", "use_pass_ambient_occlusion", "use_pass_diffuse_direct", "use_pass_shadow",
          "use_pass_diffuse_color", "use_pass_emit")
EEVEE_KEYS = ("use_gtao", "gtao_distance", "fast_gi_distance")
COMP_KEEP_TYPES = {"R_LAYERS", "VIEWER", "REROUTE"} | set(compat.OUTPUT_NODE_TYPES)
DEFAULT_MATERIAL_NAME = "FreePencil_Material"


def _load(scene) -> dict | None:
    raw = scene.get(UNDO_KEY)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def _comp_snapshot(scene) -> dict:
    tree = None
    if compat.IS_5_PLUS:
        tree = scene.compositing_node_group
    elif scene.use_nodes:
        tree = scene.node_tree
    out = {"has_tree": tree is not None,
           "tree_name": tree.name if (tree is not None and compat.IS_5_PLUS) else None,
           "nodes": [], "links": [], "all": []}
    if tree is None:
        return out
    out["all"] = [n.name for n in tree.nodes]
    for n in tree.nodes:
        if n.type in COMP_KEEP_TYPES:
            rec = {"name": n.name, "idname": n.bl_idname, "label": n.label,
                   "loc": [n.location.x, n.location.y]}
            if n.type == "R_LAYERS":
                rec["layer"] = getattr(n, "layer", "")
            out["nodes"].append(rec)
    for lk in tree.links:
        out["links"].append([lk.from_node.name, lk.from_socket.identifier,
                             lk.to_node.name, lk.to_socket.identifier])
    return out


def snapshot(context) -> None:
    """FreePencil がシーンに触る前の値を控える。2 回目以降は足りない分だけ足す。

    STEP0 / STEP1 / STEP2 / STEP3 の入口から呼ぶ。シーン単位の値は最初の 1 回だけ、
    物と材質は、まだ控えていないものだけを足す(後から増えた物にも効くように)。
    """
    scene = context.scene
    vl = context.view_layer
    data = _load(scene)
    if data is None:
        data = {"version": 1, "objects": {}, "materials": {}}
        r = scene.render
        data["render"] = {"film_transparent": r.film_transparent,
                          "resolution_percentage": r.resolution_percentage,
                          "use_compositing": r.use_compositing,
                          "view_transform": scene.view_settings.view_transform}
        data["eevee"] = {k: getattr(scene.eevee, k) for k in EEVEE_KEYS if hasattr(scene.eevee, k)}
        data["view_layer"] = {"name": vl.name,
                              "passes": {k: getattr(vl, k) for k in PASSES if hasattr(vl, k)},
                              "aovs": [a.name for a in vl.aovs]}
        data["compositor"] = _comp_snapshot(scene)
    objs = data["objects"]
    for o in scene.objects:
        if o.type != "MESH" or o.name in objs or o.data is None:
            continue
        ca = o.data.color_attributes
        objs[o.name] = {"attrs": [a.name for a in ca],
                        "active": ca.active_color.name if ca.active_color else None,
                        "render": (ca[ca.render_color_index].name
                                   if 0 <= ca.render_color_index < len(ca) else None),
                        "slots": [s.material.name if s.material else None for s in o.material_slots]}
    mats = data["materials"]
    for m in bpy.data.materials:
        if m.name in mats or m.name == DEFAULT_MATERIAL_NAME:
            continue
        mats[m.name] = {"blend_method": getattr(m, "blend_method", None), "pass_index": m.pass_index}
    scene[UNDO_KEY] = json.dumps(data, ensure_ascii=False)


# ---------------------------------------------------------------- 戻す

def _remove_compositor(scene, snap, notes):
    tree = compat.get_compositor_tree(scene)
    if tree is None:
        return
    if snap is None or not snap.get("has_tree"):
        # FreePencil が作ったツリー(控えが無いときも、中身は STEP3 が組んだもの)。
        # 中身を空にしてから外す。4.x の埋め込みツリーは外しても中身が残るため
        for n in list(tree.nodes):
            tree.nodes.remove(n)
        compat.clear_compositor_tree(scene)
        if compat.IS_5_PLUS and tree.users == 0 and tree.name.startswith("FreePencil"):
            bpy.data.node_groups.remove(tree)
        return
    # 元からあったツリー: 控えに無いノード(FreePencil が足したもの)と、STEP3 が
    # 作り直した入出力(下で控えから作り直す)を消す
    before = set(snap.get("all", []))
    for n in list(tree.nodes):
        if n.name not in before or n.type in COMP_KEEP_TYPES:
            tree.nodes.remove(n)
    for rec in snap.get("nodes", []):
        try:
            n = tree.nodes.new(rec["idname"])
        except RuntimeError:
            continue
        n.name = rec["name"]
        n.label = rec.get("label", "")
        n.location = rec.get("loc", (0, 0))
        if n.type == "R_LAYERS":
            n.scene = scene
            if rec.get("layer"):
                try:
                    n.layer = rec["layer"]
                except TypeError:
                    pass
    for fn, fs, tn, ts in snap.get("links", []):
        a, b = tree.nodes.get(fn), tree.nodes.get(tn)
        if a is None or b is None:
            continue
        so = next((s for s in a.outputs if s.identifier == fs), None)
        si = next((s for s in b.inputs if s.identifier == ts), None)
        if so is not None and si is not None and not si.is_linked:
            tree.links.new(so, si)


def _restore_materials(data, notes):
    from . import fp_core
    mats = (data or {}).get("materials", {})
    for m in bpy.data.materials:
        if m.use_nodes and m.node_tree is not None:
            nodes = m.node_tree.nodes
            for n in list(nodes):
                if (n.type == "GROUP" and n.node_tree is not None
                        and n.node_tree.name.startswith("FreePencil")) or n.label in (
                            fp_core.FINE_AOV_LABEL, "FreePencil_shade_aov"):
                    nodes.remove(n)
        rec = mats.get(m.name)
        if rec is None:
            continue
        if rec.get("blend_method") and getattr(m, "blend_method", None) != rec["blend_method"]:
            try:
                m.blend_method = rec["blend_method"]
            except (TypeError, AttributeError):
                pass
        m.pass_index = int(rec.get("pass_index", m.pass_index))


def _restore_objects(scene, data, notes):
    objs = (data or {}).get("objects", {})
    fp_mat = bpy.data.materials.get(DEFAULT_MATERIAL_NAME)
    for o in scene.objects:
        if o.type != "MESH" or o.data is None:
            continue
        rec = objs.get(o.name)
        before = set(rec["attrs"]) if rec else set()
        ca = o.data.color_attributes
        for name in FP_COLOR_LAYERS:
            a = ca.get(name)
            if a is not None and name not in before:
                ca.remove(a)
        if rec and rec.get("active") and ca.get(rec["active"]) is not None:
            ca.active_color = ca[rec["active"]]
        if rec and rec.get("render") and ca.get(rec["render"]) is not None:
            ca.render_color_index = [a.name for a in ca].index(rec["render"])
        for k in ("fp_paint_auto", "fp_rigid_ratio"):
            if k in o:
                del o[k]
        if fp_mat is None:
            continue
        slots = rec["slots"] if rec else None
        if slots is None:
            continue
        # FreePencil が足したスロット(材質の無い物)を元の数・中身へ戻す
        # FreePencil が足すのは「材質が1つも無い物」へのスロット1つだけ。pop だと
        # 物側のスロット数が減らず(4.5 で実測)、clear なら両方そろって消える
        if not slots and len(o.material_slots):
            o.data.materials.clear()
        for i, s in enumerate(o.material_slots):
            if i < len(slots) and s.material == fp_mat and slots[i] != DEFAULT_MATERIAL_NAME:
                s.material = bpy.data.materials.get(slots[i]) if slots[i] else None
    if fp_mat is not None and fp_mat.users == 0:
        bpy.data.materials.remove(fp_mat)


def _restore_scene(scene, vl, data, notes):
    if data is None:
        if scene.render.resolution_percentage == 200:
            scene.render.resolution_percentage = 100
        for a in list(vl.aovs):
            if a.name in FP_AOVS:
                vl.aovs.remove(a)
        return
    r = data.get("render", {})
    for k in ("film_transparent", "resolution_percentage", "use_compositing"):
        if k in r:
            setattr(scene.render, k, r[k])
    if r.get("view_transform"):
        try:
            scene.view_settings.view_transform = r["view_transform"]
        except TypeError:
            pass
    for k, v in data.get("eevee", {}).items():
        if hasattr(scene.eevee, k):
            setattr(scene.eevee, k, v)
    vrec = data.get("view_layer", {})
    target = scene.view_layers.get(vrec.get("name", "")) or vl
    for k, v in vrec.get("passes", {}).items():
        if hasattr(target, k):
            setattr(target, k, v)
    keep = set(vrec.get("aovs", []))
    for a in list(target.aovs):
        if a.name in FP_AOVS and a.name not in keep:
            target.aovs.remove(a)


def _remove_node_groups():
    for _ in range(3):           # 入れ子のグループは外側から順に参照が外れる
        for g in list(bpy.data.node_groups):
            if g.name.startswith("FreePencil") and g.users <= (1 if g.use_fake_user else 0):
                bpy.data.node_groups.remove(g)


def remove_freepencil(context) -> list[str]:
    """FreePencil を外す。戻り値は、元の値が分からず戻せなかった項目(控えの無い .blend)。"""
    from . import fp_core
    from .props import _write_quiet
    scene = context.scene
    vl = context.view_layer
    data = _load(scene)
    notes: list[str] = []
    # プレビューを先に下ろす(古い版の材質の差し替えもここで戻る)
    try:
        fp_core.set_white_preview(scene, False)
        fp_core.set_mono_light_preview(scene, False)
        from . import cel_shade
        cel_shade.set_cel(scene, False)
    except Exception:            # noqa: BLE001  コンポジタが無いなど。次で消す
        pass
    _write_quiet(scene, {"fp_preview_mode": "NONE", "fp_white_preview": False})
    _remove_compositor(scene, (data or {}).get("compositor"), notes)
    _restore_materials(data, notes)
    _restore_objects(scene, data, notes)
    _restore_scene(scene, vl, data, notes)
    _remove_node_groups()
    if data is None:
        # 控えの無い .blend(v2.8 以前に STEP を押したもの)。足したものは消せたが、
        # 元の値が分からないものは今のまま
        notes.append("view transform, transparent film, EEVEE AO, transparent material blend mode")
    for k in (UNDO_KEY, "fp_fine_pass", "fp_rig_coarse"):
        if k in scene:
            del scene[k]
    # ビューポートのコンポジタ表示(STEP3 が「常に」にする)を切る
    if context.screen is not None:
        for area in context.screen.areas:
            if area.type == "VIEW_3D":
                sh = area.spaces[0].shading
                if getattr(sh, "use_compositor", "DISABLED") != "DISABLED":
                    sh.use_compositor = "DISABLED"
    return notes


class FP_OT_REMOVE_FREEPENCIL(bpy.types.Operator):
    """Remove everything FreePencil added to this scene and restore the settings it changed"""
    bl_idname = "freepencil.remove"
    bl_label = "Remove FreePencil"
    bl_description = ("Remove the vertex colors, AOVs and compositor nodes FreePencil added, and "
                      "restore the render settings and materials it changed (to before the first "
                      "STEP). The shape of the meshes was never changed. Ctrl+Z undoes this")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        notes = remove_freepencil(context)
        t = bpy.app.translations.pgettext
        if notes:
            self.report({"WARNING"}, t("Removed. Settings from before FreePencil were not recorded "
                                       "in this file, so these were left as they are: ") + ", ".join(t(n) for n in notes))
        else:
            self.report({"INFO"}, t("FreePencil removed. The scene is back to before the first STEP"))
        return {"FINISHED"}

    def invoke(self, context, event):
        if bpy.app.background or context.window is None:
            return self.execute(context)
        # 確認の題と本文を自分で渡す。既定では操作名がそのまま(英語のまま)出て、
        # 何が消えるのか書かれていなかった(GUI で確認)
        t = bpy.app.translations.pgettext
        try:
            return context.window_manager.invoke_confirm(
                self, event, title=t("Remove FreePencil"),
                message=t("Vertex colors (including STEP4 paint), AOVs and the line-art "
                          "compositor will be removed, and the render settings restored. "
                          "Ctrl+Z undoes this"),
                confirm_text=t("Remove"), icon="WARNING", translate=False)
        except TypeError:        # 古い版は題と本文を受け取らない
            return context.window_manager.invoke_confirm(self, event)
