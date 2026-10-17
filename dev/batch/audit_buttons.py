"""パネルのボタンを全部、いろいろな状態で押して、押した効果を測る(リリース前の点検、v2.9.1)。

ボタンごとに
  ・押す前と後の F12 の絵(と、必要なら頂点カラーをそのまま見た絵)
  ・戻り値と、出たメッセージ(report / ポップアップ)
  ・変わった中身(頂点カラー・材質のノード・AOV・コンポジタ・レンダー設定・fp_ の設定・書き出したファイル)
  ・かかった時間
を残す。判定は audit_buttons_sheet.py で並べた画像を目で見て行う(数字は仕分けだけ)。

状態:
  clean      何もしていないシーン(全部選んでいる)
  nosel      何もしていないシーン(何も選んでいない)
  s_<仕上がり>  STEP0 の後(PRECISE / WEIGHTED / BACKGROUND)

  blender -b --factory-startup --python audit_buttons.py -- [--out out/audit_buttons/<版>] [--only 名前の一部]
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import sys
import time
import traceback
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d   # noqa: E731
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bpy                        # noqa: E402
import numpy as np                # noqa: E402
import fp_batch                   # noqa: E402

VER = bpy.app.version_string.split()[0]
OUT = Path(arg("--out", str(HERE / "out" / "audit_buttons" / VER))).resolve()
ONLY = arg("--only", "")
STYLES = arg("--styles", "PRECISE,WEIGHTED,BACKGROUND").split(",")
if OUT.exists() and not ONLY:
    shutil.rmtree(OUT)
OUT.mkdir(parents=True, exist_ok=True)
fp_batch.install_addon()

# ---------------------------------------------------------------- メッセージを拾う
MSGS: list[str] = []


def _hook_messages():
    root = next(n for n in sys.modules if n.endswith("freepencil2")
                and hasattr(sys.modules[n], "bl_info"))
    ut = sys.modules[root + ".utils"]
    orig = ut.show_message_box

    def box(message, title="Message", icon="INFO"):
        MSGS.append(f"[popup {icon}] {title}: {message}")
        return orig(message, title, icon)
    ut.show_message_box = box
    n = 0
    for mname, m in list(sys.modules.items()):
        if not mname.startswith(root):
            continue
        if getattr(m, "show_message_box", None) is orig:   # from .utils import show_message_box
            m.show_message_box = box
        for v in list(vars(m).values()):
            if (isinstance(v, type) and issubclass(v, bpy.types.Operator)
                    and getattr(v, "bl_idname", "") and "report" not in v.__dict__):
                def rep(self, kind, msg, _cls=v):
                    MSGS.append(f"[{'/'.join(sorted(kind))}] {msg}")
                    try:
                        return super(_cls, self).report(kind, msg)
                    except Exception:              # noqa: BLE001
                        print("report:", kind, msg)
                try:
                    v.report = rep
                    n += 1
                except Exception:                      # noqa: BLE001
                    pass
    print("@@@ hooked operators:", n, flush=True)


_hook_messages()


# ---------------------------------------------------------------- シーン
def mat(name, col):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*col, 1)
    return m


def build_scene():
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    objs = []
    bpy.ops.mesh.primitive_monkey_add(size=1.6, location=(-1.4, 0, 0.9))
    mk = bpy.context.object
    mk.name = "Monkey"
    mk.modifiers.new("S", "SUBSURF")
    bpy.ops.object.shade_smooth()
    mk.data.materials.append(mat("Red", (0.8, 0.15, 0.1)))
    objs.append(mk)
    bpy.ops.mesh.primitive_cube_add(size=1.2, location=(0.6, 0.3, 0.6))
    cb = bpy.context.object
    cb.name = "Box"
    bv = cb.modifiers.new("B", "BEVEL")
    bv.width, bv.segments = 0.08, 2
    cb.data.materials.append(mat("Yellow", (0.9, 0.75, 0.2)))
    objs.append(cb)
    # リグ付きの筒(ボーン2本、関節でなめらかに)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.25, depth=1.6, location=(2.2, 0, 0.8), vertices=24)
    cy = bpy.context.object
    cy.name = "Arm"
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.subdivide(number_cuts=6)
    bpy.ops.object.mode_set(mode="OBJECT")
    cy.data.materials.append(mat("Green", (0.2, 0.7, 0.3)))
    ad = bpy.data.armatures.new("Rig")
    arm = bpy.data.objects.new("Rig", ad)
    sc.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    for n, (h, t) in (("lo", ((2.2, 0, 0), (2.2, 0, 0.8))), ("hi", ((2.2, 0, 0.8), (2.2, 0, 1.6)))):
        b = ad.edit_bones.new(n)
        b.head, b.tail = h, t
    bpy.ops.object.mode_set(mode="OBJECT")
    lo, hi = cy.vertex_groups.new(name="lo"), cy.vertex_groups.new(name="hi")
    for v in cy.data.vertices:
        z = (cy.matrix_world @ v.co).z
        w = min(1.0, max(0.0, (z - 0.6) / 0.4))
        lo.add([v.index], 1 - w, "REPLACE")
        hi.add([v.index], w, "REPLACE")
    cy.modifiers.new("A", "ARMATURE").object = arm
    arm.pose.bones["hi"].rotation_mode = "XYZ"
    arm.pose.bones["hi"].rotation_euler.x = math.radians(35)
    objs.append(cy)
    # Half Fill 用の板(カメラに正対、8x8)
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=8, y_subdivisions=8, size=1.6,
                                    location=(-0.2, 1.6, 2.1), rotation=(math.radians(90), 0, 0))
    pn = bpy.context.object
    pn.name = "Panel"
    pn.data.materials.append(mat("White", (0.85, 0.85, 0.85)))
    objs.append(pn)
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 8, 0))
    gd = bpy.context.object
    gd.name = "Ground"
    gd.data.materials.append(mat("Blue", (0.25, 0.4, 0.75)))
    objs.append(gd)
    for nm, loc, rot in (("CamA", (0.3, -6.5, 2.0), (80, 0, 0)), ("CamB", (5.5, -4.5, 2.6), (76, 0, 50))):
        cam = bpy.data.objects.new(nm, bpy.data.cameras.new(nm))
        sc.collection.objects.link(cam)
        cam.location = loc
        cam.rotation_euler = tuple(math.radians(a) for a in rot)
    sc.camera = bpy.data.objects["CamA"]
    lt = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    lt.data.energy = 4
    sc.collection.objects.link(lt)
    lt.rotation_euler = (math.radians(45), 0, math.radians(30))
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 4
    sc.render.resolution_x, sc.render.resolution_y = 320, 240
    sc.render.image_settings.file_format = "PNG"
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
        setattr(sc, p_, False)
    sc.fp_color_seed = 11
    select_meshes(sc)
    return sc


def meshes(sc=None):
    sc = sc or bpy.context.scene
    return [o for o in sc.objects if o.type == "MESH"]


def select_meshes(sc=None, names=None):
    sc = sc or bpy.context.scene
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    ms = [o for o in meshes(sc) if names is None or o.name in names]
    for o in ms:
        o.select_set(True)
    bpy.context.view_layer.objects.active = ms[0] if ms else None
    return ms


def deselect(sc=None):
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = None


# ---------------------------------------------------------------- 中身の写し
def _val(v):
    if isinstance(v, float):
        return round(v, 5)
    if hasattr(v, "__len__") and not isinstance(v, str):
        try:
            return [_val(x) for x in v]
        except TypeError:
            return str(v)
    if hasattr(v, "name") and not isinstance(v, (str, int, bool)):
        return f"<{v.name}>"
    return v


def _color_hash(attr):
    n = len(attr.data)
    if not n:
        return "empty"
    buf = np.empty(n * 4, dtype=np.float32)
    attr.data.foreach_get("color", buf)
    q = np.round(buf.reshape(-1, 4), 3)
    uniq = len(np.unique(q, axis=0))
    return f"{hashlib.md5(q.tobytes()).hexdigest()[:8]} n{uniq}"


def comp_tree(sc):
    try:
        return fp_batch.comp_tree(sc)
    except Exception:                      # noqa: BLE001
        return None


def snap():
    obj = bpy.context.object
    mode = obj.mode if obj else "OBJECT"
    if mode == "EDIT":
        bpy.ops.object.mode_set(mode="OBJECT")
        s = _snap()
        s[f"obj/{obj.name}/mode"] = "EDIT"
        bpy.ops.object.mode_set(mode="EDIT")
        return s
    return _snap()


def _snap():
    sc = bpy.context.scene
    vl = bpy.context.view_layer
    s = {}
    s["active"] = bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None
    s["selected"] = sorted(o.name for o in sc.objects if o.select_get())
    for o in sorted(sc.objects, key=lambda o: o.name):
        for p in o.bl_rna.properties:
            if p.identifier.startswith("fp_"):
                s[f"obj/{o.name}/{p.identifier}"] = _val(getattr(o, p.identifier))
        for k in o.keys():
            s[f"obj/{o.name}/[{k}]"] = str(_val(o[k]))[:60]
        if o.type != "MESH":
            continue
        s[f"obj/{o.name}/mode"] = o.mode
        ca = o.data.color_attributes
        if o.mode == "EDIT":
            s[f"obj/{o.name}/color_attrs"] = "(edit mode)"
            continue
        s[f"obj/{o.name}/color_attrs"] = sorted(f"{a.name}:{a.domain}:{a.data_type}" for a in ca)
        s[f"obj/{o.name}/active_color"] = ca.active_color.name if ca.active_color else None
        for a in ca:
            s[f"obj/{o.name}/vc/{a.name}"] = _color_hash(a)
        s[f"obj/{o.name}/materials"] = [m.name if m else None for m in o.data.materials]
    for m in sorted(bpy.data.materials, key=lambda m: m.name):
        s[f"mat/{m.name}/blend"] = getattr(m, "blend_method", None)
        if m.node_tree:
            nodes = m.node_tree.nodes
            s[f"mat/{m.name}/nodes"] = len(nodes)
            s[f"mat/{m.name}/aov"] = sorted(n.aov_name if hasattr(n, "aov_name") else n.name
                                            for n in nodes if n.bl_idname == "ShaderNodeOutputAOV")
            s[f"mat/{m.name}/groups"] = sorted(n.node_tree.name for n in nodes
                                               if n.bl_idname == "ShaderNodeGroup" and n.node_tree)
    s["viewlayer/aovs"] = sorted(f"{a.name}:{a.type}" for a in vl.aovs)
    for owner, tag in ((vl, "vl"), (getattr(vl, "eevee", None), "vl.eevee")):
        if owner is None:
            continue
        for p in owner.bl_rna.properties:
            if p.identifier.startswith("use_pass"):
                s[f"pass/{tag}.{p.identifier}"] = getattr(owner, p.identifier)
    t = comp_tree(sc)
    if t is None:
        s["comp/tree"] = None
    else:
        s["comp/nodes"] = len(t.nodes)
        kinds = {}
        for n in t.nodes:
            kinds[n.bl_idname] = kinds.get(n.bl_idname, 0) + 1
        s["comp/kinds"] = kinds
        s["comp/labels"] = sorted({n.label for n in t.nodes if n.label})
        s["comp/file_outputs"] = sum(1 for n in t.nodes if n.bl_idname == "CompositorNodeOutputFile")
    s["use_nodes"] = getattr(sc, "use_nodes", None)
    s["node_groups"] = sorted(g.name for g in bpy.data.node_groups)
    r = sc.render
    for k in ("engine", "resolution_x", "resolution_y", "resolution_percentage",
              "film_transparent", "use_compositing", "filepath"):
        s[f"render/{k}"] = _val(getattr(r, k))
    s["render/view_transform"] = sc.view_settings.view_transform
    s["render/look"] = sc.view_settings.look
    for k in ("use_gtao", "taa_render_samples"):
        if hasattr(sc.eevee, k):
            s[f"render/eevee.{k}"] = getattr(sc.eevee, k)
    for p in sc.bl_rna.properties:
        if p.identifier.startswith("fp_"):
            s[f"fp/{p.identifier}"] = _val(getattr(sc, p.identifier))
    for k in sc.keys():
        s[f"scene/[{k}]"] = str(_val(sc[k]))[:60]
    s["camera"] = sc.camera.name if sc.camera else None
    return s


def diff_state(a, b):
    out = []
    for k in sorted(set(a) | set(b)):
        if k == "render/filepath":
            continue
        if a.get(k, "<none>") != b.get(k, "<none>"):
            out.append([k, a.get(k, "<none>"), b.get(k, "<none>")])
    return out


# ---------------------------------------------------------------- 撮る
def render(path):
    sc = bpy.context.scene
    obj = bpy.context.object
    mode = obj.mode if obj else "OBJECT"
    if mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")    # 編集中の変更を形に入れてから撮る
    keep = sc.render.filepath
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    sc.render.filepath = keep
    if mode != "OBJECT":
        bpy.ops.object.mode_set(mode=mode)
    return path.name


def render_vc(path, layer):
    """頂点カラーをそのまま(光なし、コンポジタなし)見る。"""
    sc = bpy.context.scene
    obj = bpy.context.object
    mode = obj.mode if obj else "OBJECT"
    if mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    keep = (sc.render.engine, sc.render.use_compositing, sc.render.filepath,
            sc.display.shading.light, sc.display.shading.color_type)
    act = {}
    for o in meshes(sc):
        ca = o.data.color_attributes
        act[o.name] = ca.active_color_index
        if layer in ca:
            ca.active_color = ca[layer]
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.render.use_compositing = False
    sc.display.shading.light = "FLAT"
    sc.display.shading.color_type = "VERTEX"
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    (sc.render.engine, sc.render.use_compositing, sc.render.filepath,
     sc.display.shading.light, sc.display.shading.color_type) = keep
    for o in meshes(sc):
        if act[o.name] >= 0:
            o.data.color_attributes.active_color_index = act[o.name]
    if mode != "OBJECT":
        bpy.ops.object.mode_set(mode=mode)
    return path.name


# ---------------------------------------------------------------- 状態を作る
BASES = {}


def make_bases():
    sc = build_scene()
    p = OUT / "base_clean.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(p))
    BASES["clean"] = p
    render(OUT / "ref_clean.png")
    (OUT / "ref_clean.json").write_text(json.dumps(snap(), ensure_ascii=False, indent=0), encoding="utf-8")
    for st in STYLES:
        bpy.ops.wm.open_mainfile(filepath=str(p))
        sc = bpy.context.scene
        select_meshes(sc)
        sc.fp_auto_style = st
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        q = OUT / f"base_s_{st}.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(q))
        BASES[f"s_{st}"] = q
        render(OUT / f"ref_s_{st}.png")
        (OUT / f"ref_s_{st}.json").write_text(json.dumps(snap(), ensure_ascii=False, indent=0),
                                              encoding="utf-8")
        print("@@@ base", st, flush=True)


def open_base(name):
    bpy.ops.wm.open_mainfile(filepath=str(BASES[name]))
    return bpy.context.scene


# ---------------------------------------------------------------- 手で塗る(STEP4 の筆の代わり)
def paint_half(obj, layer, col, side=1):
    """オブジェクトの右半分(ローカル x>0)を塗る。"""
    me = obj.data
    a = me.color_attributes[layer]
    if a.domain == "CORNER":
        for lp in me.loops:
            if me.vertices[lp.vertex_index].co.x * side > 0:
                a.data[lp.index].color = col
    else:
        for v in me.vertices:
            if v.co.x * side > 0:
                a.data[v.index].color = col
    me.update()


def panel_gradient(obj, layer="mecha_color"):
    """板の左右を 2 色に塗り、境目の列は左の色にする(右の 1 列の面がぼかしになる)。"""
    me = obj.data
    a = me.color_attributes[layer]
    A, B = (0.9, 0.25, 0.2, 1.0), (0.15, 0.3, 0.9, 1.0)
    for lp in me.loops:
        x = me.vertices[lp.vertex_index].co.x
        c = A if x < 0.01 else B
        if a.domain == "CORNER":
            a.data[lp.index].color = c
        else:
            a.data[lp.vertex_index].color = c
    me.update()


def select_mid_column(obj):
    for v in obj.data.vertices:
        v.select = abs(v.co.x) < 1e-3
    for e in obj.data.edges:
        e.select = all(obj.data.vertices[i].select for i in e.vertices)
    for f in obj.data.polygons:
        f.select = False


# ---------------------------------------------------------------- 押す
def press(idname, mode="INVOKE_DEFAULT", **kw):
    cat, _, name = idname.partition(".")
    fn = getattr(getattr(bpy.ops, cat), name)
    if not fn.poll():
        return "poll False"
    try:
        return sorted(fn(mode, **kw))
    except RuntimeError as e:          # report({'ERROR'}) は例外として返る
        MSGS.append(f"[ERROR] {str(e).replace('Error: ', '').strip()}")
        return ["CANCELLED (ERROR report)"]


CASES = []


def case(name, base, vc=None, ref=None, note=""):
    def deco(f):
        CASES.append(dict(name=name, base=base, fn=f, vc=vc, ref=ref, note=note))
        return f
    return deco


# ---- 何もしていないシーン
for st in STYLES:
    def _mk(st=st):
        @case(f"clean__STEP0_{st}", "clean", vc="mecha_color", ref=f"ref_s_{st}.png",
              note="STEP0 を押す(期待: 基準の STEP0 の絵と同じ)")
        def _(sc, ctx):
            sc.fp_auto_style = st
            return press("freepencil.auto_setup")
    _mk()


@case("clean__Remove", "clean", ref="ref_clean.png", note="何もしていないシーンで外す(期待: 何も変わらない)")
def _(sc, ctx):
    return press("freepencil.remove")


@case("clean__STEP1", "clean", vc="mecha_color", note="STEP1 だけ")
def _(sc, ctx):
    return press("freepencil.auto_vertex_color")


@case("clean__Seed", "clean", note="種を変える(期待: 種の数だけ変わる)")
def _(sc, ctx):
    return press("freepencil.randomize_seed")


@case("clean__STEP2", "clean", note="STEP1 の前に STEP2")
def _(sc, ctx):
    return press("freepencil4.link_button")


@case("clean__STEP3", "clean", note="STEP1/2 の前に STEP3")
def _(sc, ctx):
    return press("freepencil2.link_button")


@case("clean__STEP1_2_3", "clean", vc="mecha_color", ref="ref_s_PRECISE.png",
      note="STEP1→2→3 を手で(期待: STEP0 精密に近い)")
def _(sc, ctx):
    return [press("freepencil.auto_vertex_color"), press("freepencil4.link_button"),
            press("freepencil2.link_button")]


@case("clean__Measure", "clean", note="STEP0 の前に「しきい値を測る」")
def _(sc, ctx):
    return press("freepencil.measure_line_weight")


@case("clean__STEP5_unsaved", "clean", note="保存していないファイルで STEP5(期待: 保存してと出る)")
def _(sc, ctx):
    bpy.ops.wm.read_homefile(use_empty=True)
    build_scene()
    return press("freepencil.render_cameras")


@case("clean__STEP5", "clean", note="STEP0 の前に STEP5(期待: STEP3 を先にと出る)")
def _(sc, ctx):
    return press("freepencil.render_cameras")


@case("clean__STEP4_paint", "clean", note="STEP1 の前に「頂点カラーを塗る」(期待: STEP1 からと出る)")
def _(sc, ctx):
    return press("freepencil3.link_button")


@case("clean__HalfFill_object", "clean", note="オブジェクトモードで Half Fill(期待: 押せない)")
def _(sc, ctx):
    return press("freepencil5.link_button")


@case("nosel__STEP0", "clean", note="何も選ばずに STEP0")
def _(sc, ctx):
    deselect()
    return press("freepencil.auto_setup")


@case("nosel__STEP1", "clean", note="何も選ばずに STEP1")
def _(sc, ctx):
    deselect()
    return press("freepencil.auto_vertex_color")


@case("nosel__STEP4_paint", "clean", note="何も選ばずに「頂点カラーを塗る」")
def _(sc, ctx):
    deselect()
    return press("freepencil3.link_button")


@case("onlyMonkey__STEP0", "clean", vc="mecha_color", note="サルだけ選んで STEP0(ほかの物はどうなるか)")
def _(sc, ctx):
    select_meshes(sc, names={"Monkey"})
    return press("freepencil.auto_setup")


@case("edit__STEP0", "clean", vc="mecha_color", note="サルを編集モードにしたまま STEP0")
def _(sc, ctx):
    bpy.ops.object.mode_set(mode="EDIT")
    return press("freepencil.auto_setup")


# ---- STEP0 の後
for st in STYLES:
    def _mk(st=st):
        B = f"s_{st}"

        @case(f"{B}__STEP0_again", B, ref=f"ref_s_{st}.png", note="STEP0 をもう一度(期待: 同じ絵)")
        def _(sc, ctx):
            return press("freepencil.auto_setup")

        @case(f"{B}__Remove", B, ref="ref_clean.png", note="外す(期待: STEP0 の前と同じ絵・同じ中身)")
        def _(sc, ctx):
            return press("freepencil.remove")

        @case(f"{B}__Remove_twice", B, ref="ref_clean.png", note="外すを 2 回")
        def _(sc, ctx):
            return [press("freepencil.remove"), press("freepencil.remove")]

        @case(f"{B}__Remove_STEP0", B, ref=f"ref_s_{st}.png", note="外して、もう一度 STEP0(期待: 最初の STEP0 と同じ)")
        def _(sc, ctx):
            return [press("freepencil.remove"), press("freepencil.auto_setup")]

        @case(f"{B}__Remove_STEP3", B, note="外した後に STEP3 だけ")
        def _(sc, ctx):
            return [press("freepencil.remove"), press("freepencil2.link_button")]

        @case(f"{B}__Save_reopen_Remove", B, ref="ref_clean.png", note="保存して開き直してから外す")
        def _(sc, ctx):
            p = ctx["dir"] / "saved.blend"
            bpy.ops.wm.save_as_mainfile(filepath=str(p))
            bpy.ops.wm.open_mainfile(filepath=str(p))
            return press("freepencil.remove")

        @case(f"{B}__STEP1_again", B, vc="mecha_color", ref=f"ref_s_{st}.png", note="STEP1 をもう一度")
        def _(sc, ctx):
            return press("freepencil.auto_vertex_color")

        @case(f"{B}__Seed_STEP1", B, vc="mecha_color", note="種を変えて STEP1(期待: 色だけ変わり、線の位置は同じ)")
        def _(sc, ctx):
            return [press("freepencil.randomize_seed"), press("freepencil.auto_vertex_color")]

        @case(f"{B}__STEP2_again", B, ref=f"ref_s_{st}.png", note="STEP2 をもう一度(期待: 同じ絵)")
        def _(sc, ctx):
            return press("freepencil4.link_button")

        @case(f"{B}__STEP3_again", B, ref=f"ref_s_{st}.png", note="STEP3 をもう一度(期待: 同じ絵)")
        def _(sc, ctx):
            return press("freepencil2.link_button")

        @case(f"{B}__Measure", B, ref=f"ref_s_{st}.png", note="しきい値を測る(期待: 同じかほぼ同じ)")
        def _(sc, ctx):
            return press("freepencil.measure_line_weight")

        @case(f"{B}__STEP5_noFO", B, note="書き出しを入れずに STEP5(期待: 書き出しを入れてと出る)")
        def _(sc, ctx):
            p = ctx["dir"] / "saved.blend"
            bpy.ops.wm.save_as_mainfile(filepath=str(p))
            return press("freepencil.render_cameras")

        @case(f"{B}__STEP5", B, note="書き出しを全部入れて STEP3 → STEP5(2 台)")
        def _(sc, ctx):
            p = ctx["dir"] / "saved.blend"
            bpy.ops.wm.save_as_mainfile(filepath=str(p))
            sc.fp_file_output = True
            for k in ("fp_fo_line", "fp_fo_color", "fp_fo_light", "fp_fo_shadow",
                      "fp_fo_cel_color", "fp_fo_cel_shadow"):
                setattr(sc, k, True)
            press("freepencil2.link_button")
            for c in ("CamA", "CamB"):
                bpy.data.objects[c].fp_cam_render = True
            return press("freepencil.render_cameras")

        @case(f"{B}__STEP5_uncheck", B, note="カメラのチェックを全部外して STEP5")
        def _(sc, ctx):
            p = ctx["dir"] / "saved.blend"
            bpy.ops.wm.save_as_mainfile(filepath=str(p))
            sc.fp_file_output = True
            press("freepencil2.link_button")
            for c in ("CamA", "CamB"):
                bpy.data.objects[c].fp_cam_render = False
            return press("freepencil.render_cameras")

        for layer, col, what in (("mask_color", (1, 1, 1, 1), "白で塗る(期待: 線が消える)"),
                                 ("line_color", (1, 1, 1, 1), "白で塗る(期待: 線が薄くなる・消える)"),
                                 ("mecha_color", (0.1, 0.9, 0.2, 1), "緑で塗る(期待: 塗った境目に線)")):
            def _mk2(layer=layer, col=col, what=what):
                @case(f"{B}__STEP4_{layer}", B, vc=layer,
                      note=f"STEP4 {layer}: サルの右半分を{what}")
                def _(sc, ctx):
                    select_meshes(sc, names={"Monkey"})
                    sc.fp_color_type = layer
                    r = press("freepencil3.link_button")
                    ob = bpy.context.object
                    ctx["mode_after_paint"] = ob.mode
                    ctx["active_after_paint"] = (ob.data.color_attributes.active_color.name
                                                 if ob.data.color_attributes.active_color else None)
                    if layer in ob.data.color_attributes:
                        paint_half(ob, layer, col)
                    bpy.ops.object.mode_set(mode="OBJECT")
                    return r
            _mk2()

        @case(f"{B}__STEP4_paint_then_Remove", B, ref="ref_clean.png",
              note="頂点ペイントのまま外す(期待: 塗った分も消え、STEP0 の前に戻る)")
        def _(sc, ctx):
            select_meshes(sc, names={"Monkey"})
            sc.fp_color_type = "mask_color"
            press("freepencil3.link_button")
            paint_half(bpy.context.object, "mask_color", (1, 1, 1, 1))
            return press("freepencil.remove")

        @case(f"{B}__STEP4_paint_then_STEP0", B, vc="mask_color",
              note="マスクを塗った後に STEP0 を押し直す(塗った分は残るか)")
        def _(sc, ctx):
            select_meshes(sc, names={"Monkey"})
            sc.fp_color_type = "mask_color"
            press("freepencil3.link_button")
            paint_half(bpy.context.object, "mask_color", (1, 1, 1, 1))
            bpy.ops.object.mode_set(mode="OBJECT")
            select_meshes(sc)
            return press("freepencil.auto_setup")

        @case(f"{B}__HalfFill_edit", B, vc="mecha_color",
              note="板の境目をぼかしにして、編集モードで中の列を選んで Half Fill(期待: 境目がくっきり)")
        def _(sc, ctx):
            ob = select_meshes(sc, names={"Panel"})[0]
            panel_gradient(ob)
            ctx["before_override"] = True
            select_mid_column(ob)
            bpy.ops.object.mode_set(mode="EDIT")
            sc.fp_color_type = "mecha_color"
            return press("freepencil5.link_button")

        @case(f"{B}__HalfFill_vpaint", B, vc="mecha_color",
              note="同じ板を頂点ペイント(頂点の選択マスク)で Half Fill")
        def _(sc, ctx):
            ob = select_meshes(sc, names={"Panel"})[0]
            panel_gradient(ob)
            sc.fp_color_type = "mecha_color"
            press("freepencil3.link_button")
            # マニュアルの手順: 頂点の選択マスクに切り替え、全部外してから境目の頂点を選ぶ
            # (「頂点カラーを塗る」は面の選択マスクにして全部を選ぶ)
            ctx["sel_after_paint"] = sum(v.select for v in ob.data.vertices)
            ob.data.use_paint_mask_vertex = True
            select_mid_column(ob)
            return press("freepencil5.link_button")

        @case(f"{B}__HalfFill_allsel", B, vc="mecha_color",
              note="全部選んだまま Half Fill(期待: 境目だけ選んでと出て、何も変わらない)")
        def _(sc, ctx):
            ob = select_meshes(sc, names={"Panel"})[0]
            panel_gradient(ob)
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            return press("freepencil5.link_button")

        @case(f"{B}__vpaint_STEP0", B, vc="mecha_color",
              note="頂点ペイントのまま STEP0 を押す")
        def _(sc, ctx):
            select_meshes(sc, names={"Monkey"})
            sc.fp_color_type = "mecha_color"
            press("freepencil3.link_button")
            for o in meshes(sc):
                o.select_set(True)
            return press("freepencil.auto_setup")
    _mk()


# ---------------------------------------------------------------- 走らせる
def run_case(c):
    d = OUT / c["name"]
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    sc = open_base(c["base"])
    select_meshes(sc)
    ctx = {"dir": d}
    rec = {"name": c["name"], "base": c["base"], "note": c["note"], "ref": c["ref"], "vc": c["vc"]}
    try:
        # 板の Half Fill は、ぼかしを付けた後を「前」にする
        if "HalfFill" in c["name"] and "object" not in c["name"]:
            ob = bpy.data.objects["Panel"]
            if "mecha_color" in ob.data.color_attributes:
                panel_gradient(ob)
        before = snap()
        rec["before"] = render(d / "before.png")
        if c["vc"]:
            rec["before_vc"] = render_vc(d / "before_vc.png", c["vc"])
        MSGS.clear()
        t0 = time.perf_counter()
        res = c["fn"](bpy.context.scene, ctx)
        rec["sec"] = round(time.perf_counter() - t0, 2)
        rec["result"] = res
        rec["msgs"] = list(MSGS)
        after = snap()
        rec["after"] = render(d / "after.png")
        if c["vc"]:
            rec["after_vc"] = render_vc(d / "after_vc.png", c["vc"])
        rec["changed"] = diff_state(before, after)
        if c["ref"]:
            refst = json.loads((OUT / c["ref"].replace(".png", ".json")).read_text(encoding="utf-8"))
            rec["vs_ref_state"] = diff_state(refst, after)
        for k in ("mode_after_paint", "active_after_paint", "sel_after_paint"):
            if k in ctx:
                rec[k] = ctx[k]
        files = sorted(str(p.relative_to(d)) for p in d.rglob("*")
                       if p.is_file() and p.suffix in (".png", ".exr", ".jpg")
                       and p.name not in ("before.png", "after.png", "before_vc.png", "after_vc.png"))
        rec["files"] = files
    except Exception:                          # noqa: BLE001
        rec["error"] = traceback.format_exc()[-1500:]
        rec["msgs"] = list(MSGS)
    (d / "rec.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"@@@ case {c['name']} {rec.get('result')} {rec.get('sec')}s"
          f" {('ERROR ' + rec['error'].splitlines()[-1]) if 'error' in rec else ''}", flush=True)
    return rec


if __name__ == "__main__":
    make_bases()
    recs = []
    for c in CASES:
        if ONLY and ONLY not in c["name"]:
            continue
        recs.append(run_case(c))
    (OUT / "cases.json").write_text(json.dumps(recs, ensure_ascii=False, indent=1, default=str),
                                    encoding="utf-8")
    print("@@@ done", len(recs), flush=True)
