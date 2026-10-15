"""パネルの項目とボタンを総当りする(リリース前の点検)。

v2.8.0 で「プレビューの種類を切り替えても、STEP3 の作り直しで別の種類に戻る」
(設定を2か所に持っていて片方が古いまま)を見逃した。同じ型の漏れと、
触っても何も変わらない項目、押すとエラーになるボタンを探す。

項目ごとに、仕上がり(精密/キャラ/手描き背景)の STEP0 後のシーンを開き直して
  A  そのまま(仕上がりごとに1枚)
  B  項目を既定から変えた直後(その場で効くはずの項目)
  C  そのあと STEP3 を押し直した後(効果が消えていないか)
を撮る。STEP1 / STEP2 / STEP0 の項目は、その工程をやり直してから C を撮る。
判定は別スクリプト(audit_panel_sheet.py)で画像の差を出し、疑わしいものを並べて目で見る。

  blender -b --factory-startup --python audit_panel.py -- [--out out/audit/<tag>] [--styles PRECISE,WEIGHTED,BACKGROUND]
"""
from __future__ import annotations

import json
import math
import re
import sys
import traceback
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = Path(arg("--out", str(HERE / "out" / "audit" / "now"))).resolve()
STYLES = arg("--styles", "PRECISE,WEIGHTED,BACKGROUND").split(",")
sys.path.insert(0, str(HERE))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402

OUT.mkdir(parents=True, exist_ok=True)

# パネルが描く項目(panel.py から拾う)
PANEL = re.findall(r'\.prop\((scene|obj|cam),\s*"(\w+)"',
                   (REPO / "panel.py").read_text(encoding="utf-8"))
_seen = []
for k in PANEL:
    if k not in _seen:
        _seen.append(k)
PANEL = _seen

STEP0 = {n for _, n in PANEL if n.startswith("fp_auto_") and n != "fp_auto_style"}
STEP1 = {"fp_mat_count", "fp_sharp_auto", "fp_sharp_edges", "fp_seam_boundaries",
         "fp_min_island_area_pct", "fp_foliage_clumps", "fp_ridge_amount",
         "fp_ridge_radius", "fp_bone_grouping_mode", "fp_bone_hard_names",
         "fp_part_tint", "fp_use_random_seed", "fp_color_seed", "fp_paint_as",
         "fp_far_lod_px"}
STEP2 = {"fp_bone_color", "fp_gen_color", "fp_mask_color", "fp_line_color", "fp_mat_color"}
# 絵には出ない項目(別の方法で確かめる)
NOT_IMAGE = {"fp_file_output", "fp_file_output_path", "fp_fo_line", "fp_fo_color",
             "fp_fo_light", "fp_fo_shadow", "fp_cam_render", "fp_enable_compositor_view",
             "fp_color_type", "fp_color_noise_scale", "fp_min_neighbor_color_distance",
             "fp_max_color_retries", "fp_half_color", "fp_auto_style",
             "fp_auto_file_output", "fp_auto_detect_aov",
             "fp_fo_cel_color", "fp_fo_cel_shadow"}


def build_scene():
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    objs = []
    bpy.ops.mesh.primitive_monkey_add(size=1.6, location=(-1.4, 0, 0.9))
    mk = bpy.context.object
    mk.modifiers.new("S", "SUBSURF")
    bpy.ops.object.shade_smooth()
    objs.append(mk)
    bpy.ops.mesh.primitive_cube_add(size=1.2, location=(0.6, 0.3, 0.6))
    cb = bpy.context.object
    bv = cb.modifiers.new("B", "BEVEL")
    bv.width, bv.segments = 0.08, 2
    for i in range(4):                      # パネルの溝(メカの線)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0.6, -0.31, 0.2 + i * 0.28))
        g = bpy.context.object
        g.scale = (1.0, 0.02, 0.03)
        objs.append(g)
    objs.append(cb)
    # リグ付きの筒(ボーン2本、関節でなめらかに)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.25, depth=1.6, location=(2.2, 0, 0.8), vertices=24)
    cy = bpy.context.object
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.subdivide(number_cuts=6)
    bpy.ops.object.mode_set(mode="OBJECT")
    ad = bpy.data.armatures.new("A")
    arm = bpy.data.objects.new("A", ad)
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
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 8, 0))
    objs.append(bpy.context.object)
    bpy.ops.mesh.primitive_monkey_add(size=1.6, location=(1.5, 16, 1.0))
    objs.append(bpy.context.object)
    cam = bpy.data.objects.new("C", bpy.data.cameras.new("C"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = (0.3, -6.5, 2.0)
    cam.rotation_euler = (math.radians(80), 0, 0)
    lt = bpy.data.objects.new("L", bpy.data.lights.new("L", "SUN"))
    sc.collection.objects.link(lt)
    lt.rotation_euler = (math.radians(45), 0, math.radians(30))
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = 4
    sc.render.resolution_x, sc.render.resolution_y = 320, 240
    sc.render.image_settings.file_format = "PNG"
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
        setattr(sc, p_, False)
    sc.fp_color_seed = 11
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    return sc


def render(sc, path):
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return path.name


def select_all_meshes(sc):
    bpy.ops.object.select_all(action="DESELECT")
    ms = [o for o in sc.objects if o.type == "MESH"]
    for o in ms:
        o.select_set(True)
    bpy.context.view_layer.objects.active = ms[0]
    return ms


def test_value(owner, name):
    """既定(いまの値)から目に見えて離れた値。"""
    p = owner.bl_rna.properties[name]
    cur = getattr(owner, name)
    if getattr(p, "array_length", 0) and p.type == "FLOAT":     # 色(v2.9 のセル): 反対の色
        return tuple(1.0 - float(c) for c in cur)
    if p.type == "BOOLEAN":
        return not cur
    if p.type == "ENUM":
        items = [i.identifier for i in p.enum_items]
        return next((i for i in items if i != cur), cur)
    if p.type in ("INT", "FLOAT"):
        lo, hi = p.soft_min, p.soft_max
        if p.type == "FLOAT" and hi > 1e5:
            hi = max(cur * 3, 1.0)
        if p.type == "INT" and hi > 1e5:
            hi = max(cur * 3, 8)
        v = lo + 0.85 * (hi - lo) if cur <= lo + 0.5 * (hi - lo) else lo + 0.1 * (hi - lo)
        return int(round(v)) if p.type == "INT" else float(v)
    if p.type == "STRING" and name == "fp_bone_hard_names":
        return "hi"
    return None


def run_props():
    records = []
    sc = build_scene()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "base.blend"))
    for style in STYLES:
        bpy.ops.wm.open_mainfile(filepath=str(OUT / "base.blend"))
        sc = bpy.context.scene
        select_all_meshes(sc)
        sc.fp_auto_style = style
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        sb = OUT / f"style_{style}.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(sb))
        a = render(sc, OUT / f"{style}__A.png")
        print(f"@@@ style {style}", flush=True)
        for kind, name in PANEL:
            if name in NOT_IMAGE:
                continue
            bpy.ops.wm.open_mainfile(filepath=str(sb))
            sc = bpy.context.scene
            ms = select_all_meshes(sc)
            owner = sc if kind == "scene" else ms[0]
            rec = {"style": style, "prop": name, "A": a}
            try:
                if not hasattr(owner, name):
                    rec["error"] = "not registered"
                    records.append(rec)
                    continue
                cur = getattr(owner, name)
                v = test_value(owner, name)
                rec["from"], rec["to"] = repr(cur), repr(v)
                if v is None or v == cur:
                    rec["skip"] = "no test value"
                    records.append(rec)
                    continue
                if name.startswith("fp_cel_"):       # セルのつまみはセルのプレビューで比べる(v2.9)
                    sc.fp_preview_mode = "CEL"
                    if name == "fp_cel_shadow_line_color" or name == "fp_cel_shadow_line_width":
                        sc.fp_cel_shadow_line = True
                    if name == "fp_cel_sky_color":
                        sc.fp_cel_sky = True
                    rec["A"] = render(sc, OUT / f"{style}__{name}__A.png")
                    cur = getattr(owner, name)
                    v = test_value(owner, name)
                    rec["from"], rec["to"] = repr(cur), repr(v)
                if name in ("fp_ridge_radius",):
                    sc.fp_ridge_amount = 0.45
                if name == "fp_color_seed":
                    sc.fp_use_random_seed = False
                if kind == "obj" and name == "fp_paint_as":
                    for o in ms:
                        setattr(o, name, v)
                else:
                    setattr(owner, name, v)
                rec["B"] = render(sc, OUT / f"{style}__{name}__B.png")
                if name in STEP0:
                    select_all_meshes(sc)
                    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
                    rec["redo"] = "STEP0"
                elif name in STEP1 or kind == "obj":
                    select_all_meshes(sc)
                    bpy.ops.freepencil.auto_vertex_color()
                    bpy.ops.freepencil2.link_button()
                    rec["redo"] = "STEP1+3"
                elif name in STEP2:
                    bpy.ops.freepencil4.link_button()
                    bpy.ops.freepencil2.link_button()
                    rec["redo"] = "STEP2+3"
                else:
                    bpy.ops.freepencil2.link_button()
                    rec["redo"] = "STEP3"
                rec["after"] = repr(getattr(owner, name))
                rec["C"] = render(sc, OUT / f"{style}__{name}__C.png")
            except Exception:           # noqa: BLE001
                rec["error"] = traceback.format_exc()[-800:]
            records.append(rec)
            print(f"@@@ {style} {name} {rec.get('error', '')[:80]}", flush=True)
    (OUT / "props.json").write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")


def run_ops():
    """アドオンのボタン(オペレーター)を全部押す。"""
    root = next(n for n in sys.modules if n.endswith("freepencil2")
                and hasattr(sys.modules[n], "bl_info"))
    ops = []
    for mname, m in list(sys.modules.items()):
        if not mname.startswith(root):
            continue
        for v in vars(m).values():
            if isinstance(v, type) and issubclass(v, bpy.types.Operator) and getattr(v, "bl_idname", ""):
                if v.bl_idname not in [o[0] for o in ops]:
                    ops.append((v.bl_idname, v.__name__, mname))
    results = []
    for style in STYLES[:1] + ["WEIGHTED"]:
        sb = OUT / f"style_{style}.blend"
        if not sb.exists():
            continue
        for idn, cname, mname in ops:
            bpy.ops.wm.open_mainfile(filepath=str(sb))
            sc = bpy.context.scene
            select_all_meshes(sc)
            cat, _, name = idn.partition(".")
            fn = getattr(getattr(bpy.ops, cat), name)
            rec = {"style": style, "op": idn, "class": cname, "module": mname}
            try:
                rec["poll"] = bool(fn.poll())
                if not rec["poll"]:
                    rec["result"] = "poll False"
                else:
                    rec["result"] = sorted(fn("EXEC_DEFAULT"))
            except Exception as e:      # noqa: BLE001
                rec["error"] = f"{type(e).__name__}: {str(e)[:300]}"
            results.append(rec)
            print(f"@@@ op {style} {idn} {rec.get('result')} {rec.get('error', '')[:100]}", flush=True)
    (OUT / "ops.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    fp_batch.install_addon()
    if "--ops-only" not in ARGV:
        run_props()
    run_ops()
    print("@@@ done", flush=True)
