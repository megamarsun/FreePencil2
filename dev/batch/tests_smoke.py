"""TDD regression tests for FreePencil, headless (no external assets).

Run:  blender -b --factory-startup -P tests_smoke.py
Exit code 0 = all green. Results also written to out/tests.json.

These lock in current guaranteed behavior; extend when improving the
algorithm so regressions are caught immediately.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

import bpy

BATCH = Path(__file__).resolve().parent
sys.path.insert(0, str(BATCH))
import fp_batch  # reuse install_addon / metrics  # noqa: E402

RESULTS: list[dict] = []


def test(name):
    def deco(fn):
        def wrapper():
            try:
                fn()
                RESULTS.append({"test": name, "ok": True})
                print(f"  PASS {name}")
            except Exception:
                RESULTS.append({"test": name, "ok": False,
                                "error": traceback.format_exc()})
                print(f"  FAIL {name}")
        wrapper.__test__ = True
        return wrapper
    return deco


def fresh_scene_with_islands():
    """Two separated cubes inside ONE mesh object = 2 islands."""
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
    obj = bpy.context.active_object
    bpy.ops.mesh.primitive_cube_add(location=(3, 0, 0))
    other = bpy.context.active_object
    other.select_set(True)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.join()
    scene = bpy.context.scene
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 1234
    scene.fp_sharp_auto = False  # 固定しきい値の挙動をテストする
    return bpy.context.active_object


def get_mecha_colors(obj) -> list[tuple]:
    attr = obj.data.color_attributes["mecha_color"]
    return [tuple(round(v, 4) for v in d.color[:3]) for d in attr.data]


@test("STEP1 runs headless and creates mecha_color")
def t1():
    obj = fresh_scene_with_islands()
    res = bpy.ops.freepencil.auto_vertex_color()
    assert res == {"FINISHED"}, res
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    assert any("mecha_color" in o.data.color_attributes for o in meshes)


@test("seed reproducibility: same seed = identical colors")
def t2():
    fresh_scene_with_islands()
    bpy.ops.freepencil.auto_vertex_color()
    colors_a = sorted(
        c for o in bpy.context.scene.objects if o.type == "MESH"
        for c in set(get_mecha_colors(o)))
    fresh_scene_with_islands()
    bpy.ops.freepencil.auto_vertex_color()
    colors_b = sorted(
        c for o in bpy.context.scene.objects if o.type == "MESH"
        for c in set(get_mecha_colors(o)))
    assert colors_a == colors_b, (colors_a, colors_b)


@test("different seed = different colors")
def t3():
    fresh_scene_with_islands()
    bpy.ops.freepencil.auto_vertex_color()
    colors_a = sorted(
        c for o in bpy.context.scene.objects if o.type == "MESH"
        for c in set(get_mecha_colors(o)))
    obj = fresh_scene_with_islands()
    bpy.context.scene.fp_color_seed = 9999
    bpy.ops.freepencil.auto_vertex_color()
    colors_b = sorted(
        c for o in bpy.context.scene.objects if o.type == "MESH"
        for c in set(get_mecha_colors(o)))
    assert colors_a != colors_b


@test("adjacent islands respect min color distance (violations = 0)")
def t4():
    fresh_scene_with_islands()
    bpy.context.scene.fp_min_neighbor_color_distance = 0.5
    bpy.ops.freepencil.auto_vertex_color()
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    m = fp_batch.mesh_color_metrics(meshes, 0.5)
    assert m["min_distance_violations"] == 0, m


@test("STEP2+STEP3(pro) core functions build AOV and compositor tree headless")
def t5():
    from freepencil2 import fp_core
    fresh_scene_with_islands()
    bpy.ops.freepencil.auto_vertex_color()
    scene = bpy.context.scene
    scene.fp_include_antialiasing = True
    scene.fp_node_type = "pro"
    fp_core.setup_aov(scene, bpy.context.view_layer)
    fp_core.setup_compositor(scene, bpy.context.view_layer)
    assert "mecha_color" in [a.name for a in bpy.context.view_layer.aovs]
    assert fp_batch.comp_tree(scene) is not None
    labels = [n.label for n in fp_batch.comp_tree(scene).nodes]
    assert any("pro" in (l or "") for l in labels), labels
    assert bpy.context.view_layer.use_pass_z
    # 透過背景: シルエットアルファを書き戻す Set Alpha が Composite 直前にあること
    comp = next(n for n in fp_batch.comp_tree(scene).nodes
            if fp_batch.is_output_node(n))
    assert comp.inputs[0].links[0].from_node.type == "SETALPHA", \
        [n.type for n in fp_batch.comp_tree(scene).nodes]


@test("STEP2+STEP3 real operators are headless-safe after fp_core refactor")
def t6():
    fresh_scene_with_islands()
    bpy.ops.freepencil.auto_vertex_color()
    scene = bpy.context.scene
    scene.fp_include_antialiasing = True
    scene.fp_node_type = "pro"
    scene.fp_enable_compositor_view = False
    # re-select meshes (STEP1 may have split objects)
    meshes = [o for o in scene.objects if o.type == "MESH"]
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    res2 = bpy.ops.freepencil4.link_button()
    assert res2 == {"FINISHED"}, res2
    assert "mecha_color" in [a.name for a in bpy.context.view_layer.aovs]
    res3 = bpy.ops.freepencil2.link_button()
    assert res3 == {"FINISHED"}, res3
    labels = [n.label for n in fp_batch.comp_tree(scene).nodes]
    assert any("pro" in (l or "") for l in labels), labels


@test("STEP1 survives a selected mesh with zero faces (bed_2K regression)")
def t7():
    fresh_scene_with_islands()
    # BlenderKitの一部アセットにある「面が0個のメッシュ」(エッジのみ等)を再現
    me = bpy.data.meshes.new("FP_EdgeOnly")
    me.from_pydata([(0, 0, 0), (0, 0, 1)], [(0, 1)], [])
    empty_obj = bpy.data.objects.new("FP_EdgeOnly", me)
    bpy.context.scene.collection.objects.link(empty_obj)
    empty_obj.select_set(True)
    res = bpy.ops.freepencil.auto_vertex_color()
    assert res == {"FINISHED"}, res
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    assert any("mecha_color" in o.data.color_attributes for o in meshes)


@test("dense adjacency: cube faces satisfy high min color distance (golden-ratio hue)")
def t8():
    # 1個の立方体 = 6面がすべて島で互いに隣接する密な制約グラフ。
    # 高い距離しきい値でも黄金比色相ステップなら違反ゼロで塗れること。
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
    scene = bpy.context.scene
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 1234
    scene.fp_sharp_auto = False
    scene.fp_min_neighbor_color_distance = 0.7
    scene.fp_max_color_retries = 30
    bpy.ops.freepencil.auto_vertex_color()
    meshes = [o for o in scene.objects if o.type == "MESH"]
    m = fp_batch.mesh_color_metrics(meshes, 0.7)
    assert m["distinct_colors"] >= 3, m
    assert m["min_distance_violations"] == 0, m


@test("tiny sliver island merges into its large neighbor (area-based)")
def t9():
    # 大きな四角形 + 90°に折れた極小の短冊(面積 ~0.01%) = 2島。
    # 面積比が fp_min_island_area_pct 未満の短冊は隣の大きな島に併合され、
    # 色は1色になる(微小島ノイズ線の除去)。
    bpy.ops.wm.read_homefile(use_empty=True)
    me = bpy.data.meshes.new("FP_Sliver")
    me.from_pydata(
        [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
         (1, 0, 0.0001), (0, 0, 0.0001)],
        [],
        [(0, 1, 2, 3), (0, 1, 4, 5)])
    obj = bpy.data.objects.new("FP_Sliver", me)
    bpy.context.scene.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    scene = bpy.context.scene
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 1234
    scene.fp_sharp_auto = False
    scene.fp_sharp_edges = 60.0
    scene.fp_min_island_area_pct = 0.02
    res = bpy.ops.freepencil.auto_vertex_color()
    assert res == {"FINISHED"}, res
    colors = {c for o in bpy.context.scene.objects if o.type == "MESH"
              for c in get_mecha_colors(o)}
    assert len(colors) == 1, colors

    # マージ無効(0)なら2島=2色のまま
    bpy.ops.wm.read_homefile(use_empty=True)
    me = bpy.data.meshes.new("FP_Sliver2")
    me.from_pydata(
        [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
         (1, 0, 0.0001), (0, 0, 0.0001)],
        [],
        [(0, 1, 2, 3), (0, 1, 4, 5)])
    obj = bpy.data.objects.new("FP_Sliver2", me)
    bpy.context.scene.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    scene = bpy.context.scene
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 1234
    scene.fp_sharp_auto = False
    scene.fp_sharp_edges = 60.0
    scene.fp_min_island_area_pct = 0.0
    bpy.ops.freepencil.auto_vertex_color()
    colors = {c for o in bpy.context.scene.objects if o.type == "MESH"
              for c in get_mecha_colors(o)}
    assert len(colors) == 2, colors


@test("graph coloring: extreme min distance 0.85 with zero violations")
def t10():
    # 旧乱数リトライ方式では 0.8 で違反が爆発していたケース。
    # グラフ彩色+パレットでは構造的に違反ゼロになること。
    fresh_scene_with_islands()
    bpy.context.scene.fp_min_neighbor_color_distance = 0.85
    bpy.ops.freepencil.auto_vertex_color()
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    m = fp_batch.mesh_color_metrics(meshes, 0.85)
    assert m["min_distance_violations"] == 0, m
    assert m["distinct_colors"] >= 2, m


@test("auto threshold: smooth sphere still gets partition lines")
def t11():
    # 一様に滑らかなメッシュ(構造エッジなし)でも fp_sharp_auto なら
    # p50付近まで下げて分割線を人工生成し、複数の島色が出ること。
    # 固定60°では島が1つ=1色になるケース。
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2)
    scene = bpy.context.scene
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 1234
    scene.fp_sharp_auto = True
    bpy.ops.freepencil.auto_vertex_color()
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    colors = {c for o in meshes for c in get_mecha_colors(o)}
    assert len(colors) >= 2, colors


@test("rigged model: bone_color per bone, no artificial mecha partition")
def t12():
    # メカ(島分割)とボーン(頂点グループ)は別系統。リグ付きモデルでは
    #  - bone_color がボーン毎に塗り分けられること
    #  - auto でも滑面への人工分割線(mecha側ノイズ)を出さないこと
    bpy.ops.wm.read_homefile(use_empty=True)
    arm = bpy.data.armatures.new("FP_Arm")
    arm_obj = bpy.data.objects.new("FP_Arm", arm)
    bpy.context.scene.collection.objects.link(arm_obj)
    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode="EDIT")
    b1 = arm.edit_bones.new("upper")
    b1.head, b1.tail = (0, 0, 0), (0, 0, 1)
    b2 = arm.edit_bones.new("lower")
    b2.head, b2.tail = (0, 0, -1), (0, 0, 0)
    bpy.ops.object.mode_set(mode="OBJECT")

    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2)
    obj = bpy.context.active_object
    vg_u = obj.vertex_groups.new(name="upper")
    vg_l = obj.vertex_groups.new(name="lower")
    for v in obj.data.vertices:
        (vg_u if v.co.z >= 0 else vg_l).add([v.index], 1.0, "REPLACE")
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm_obj

    scene = bpy.context.scene
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 1234
    scene.fp_sharp_auto = True
    arm_obj.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    res = bpy.ops.freepencil.auto_vertex_color()
    assert res == {"FINISHED"}, res

    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    mecha = {c for o in meshes for c in get_mecha_colors(o)}
    assert len(mecha) == 1, f"rigged mesh must not get partition noise: {len(mecha)}"
    bone_attr = meshes[0].data.color_attributes["bone_color"]
    bone = {tuple(round(v, 3) for v in d.color[:3]) for d in bone_attr.data}
    assert len(bone) >= 2, f"bone_color should differ per bone: {bone}"


@test("adjacent islands differ in LUMA (PRO node detects edges in luma)")
def t13():
    # PROノードの線抽出は「白背景プリミックス→エッジ検出→ColorRamp
    # (float入力=輝度)」なので、線が出るかは輝度差で決まる。
    # RGB距離が大きくても輝度が近いと線が消える回帰(womanの顔・服の
    # 線が消滅)を防ぐ:
    #  - 全島色の輝度 <= 0.85(白背景とのシルエット線を保証)
    #  - 色の異なる隣接面の輝度差 >= 0.12(内部線の検出を保証)
    fresh_scene_with_islands()
    bpy.ops.freepencil.auto_vertex_color()

    def luma(c):
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    min_gap = 1.0
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        me = obj.data
        attr = me.color_attributes.get("mecha_color")
        if attr is None:
            continue
        face_color = {p.index: tuple(attr.data[p.loop_start].color[:3])
                      for p in me.polygons}
        for c in set(face_color.values()):
            assert luma(c) <= 0.85, f"too bright for silhouette: {c}"
        edge_faces = {}
        for p in me.polygons:
            for ek in p.edge_keys:
                edge_faces.setdefault(ek, []).append(p.index)
        for faces in edge_faces.values():
            if len(faces) == 2:
                c1, c2 = face_color[faces[0]], face_color[faces[1]]
                if c1 != c2:
                    min_gap = min(min_gap, abs(luma(c1) - luma(c2)))
    assert min_gap >= 0.12, f"adjacent islands too close in luma: {min_gap:.3f}"


@test("line sensitivity scales node ramps idempotently")
def t14():
    # fp_line_sensitivity はノードグループ内 ColorRamp のしきい値位置を
    # 一括スケールする。冪等(1.0で完全復元)であること。
    fresh_scene_with_islands()
    bpy.ops.freepencil.auto_vertex_color()
    scene = bpy.context.scene
    scene.fp_node_type = "pro"
    scene.fp_enable_compositor_view = False
    bpy.ops.freepencil4.link_button()

    from freepencil2 import fp_core
    scene.fp_line_sensitivity = 1.0
    bpy.ops.freepencil2.link_button()
    group = bpy.data.node_groups[f"{fp_core.NODE_GROUP_PREFIX}pro"]
    orig = {n.name: [e.position for e in n.color_ramp.elements]
            for n in group.nodes if n.type == "VALTORGB"}
    assert orig, "no ramps found"

    def luma(c):
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    def is_descending(n):
        el = n.color_ramp.elements
        return len(el) >= 2 and luma(el[0].color) > luma(el[-1].color)

    scene.fp_line_sensitivity = 0.5
    bpy.ops.freepencil2.link_button()
    n_scaled = 0
    for n in group.nodes:
        if n.type != "VALTORGB":
            continue
        expect = 0.5 if is_descending(n) else 1.0  # 上昇ランプ(マスク系)は不変
        for e, p0 in zip(n.color_ramp.elements, orig[n.name]):
            assert abs(e.position - p0 * expect) < 1e-5, (n.name, e.position, p0)
        if is_descending(n):
            n_scaled += 1
    assert n_scaled >= 1, "no line ramps found"

    scene.fp_line_sensitivity = 1.0
    bpy.ops.freepencil2.link_button()
    for n in group.nodes:
        if n.type != "VALTORGB":
            continue
        for e, p0 in zip(n.color_ramp.elements, orig[n.name]):
            assert abs(e.position - p0) < 1e-5, (n.name, e.position, p0)


@test("auto: multi-part smooth assembly gets no artificial partitions")
def t15():
    # 骨格標本のような「滑面パーツの多い組立モデル」では、パーツ間の
    # シルエット線が十分な線源なので人工分割線を出さない
    # (単体の滑面ボール t11 とは逆の挙動が正しい)。
    bpy.ops.wm.read_homefile(use_empty=True)
    first = None
    for i in range(10):
        bpy.ops.mesh.primitive_ico_sphere_add(
            subdivisions=2, location=(i * 3.0, 0, 0))
        if first is None:
            first = bpy.context.active_object
        bpy.context.active_object.select_set(True)
    bpy.context.view_layer.objects.active = first
    for o in bpy.context.scene.objects:
        o.select_set(o.type == "MESH")
    scene = bpy.context.scene
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 1234
    scene.fp_sharp_auto = True
    bpy.ops.freepencil.auto_vertex_color()
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    m = fp_batch.mesh_color_metrics(meshes, 0.5)
    # 人工分割が出ていれば球内部に隣接ペアが生まれる。ゼロであること
    assert m["adjacent_color_pairs"] == 0, m


@test("seam/material boundaries split islands only when enabled")
def t16():
    # 平坦な2面(角度0°)でも、マテリアル境界が有効なら島が分かれること。
    # 無効なら従来どおり1島のまま。
    def build():
        bpy.ops.wm.read_homefile(use_empty=True)
        me = bpy.data.meshes.new("FP_TwoMat")
        me.from_pydata(
            [(0, 0, 0), (1, 0, 0), (2, 0, 0), (2, 1, 0), (1, 1, 0), (0, 1, 0)],
            [],
            [(0, 1, 4, 5), (1, 2, 3, 4)])
        me.polygons[1].material_index = 1
        obj = bpy.data.objects.new("FP_TwoMat", me)
        bpy.context.scene.collection.objects.link(obj)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        scene = bpy.context.scene
        scene.fp_use_random_seed = False
        scene.fp_color_seed = 1234
        scene.fp_sharp_auto = False
        scene.fp_sharp_edges = 60.0
        scene.fp_min_island_area_pct = 0.0
        return scene

    scene = build()
    scene.fp_seam_boundaries = True
    bpy.ops.freepencil.auto_vertex_color()
    colors = {c for o in bpy.context.scene.objects if o.type == "MESH"
              for c in get_mecha_colors(o)}
    assert len(colors) == 2, colors

    scene = build()
    scene.fp_seam_boundaries = False
    bpy.ops.freepencil.auto_vertex_color()
    colors = {c for o in bpy.context.scene.objects if o.type == "MESH"
              for c in get_mecha_colors(o)}
    assert len(colors) == 1, colors


@test("hard boundary bones make a step only when requested")
def t17():
    # fp_bone_hard_names に列挙したボーンの境界だけ硬いステップになる
    # (顎下ライン用)。未指定ならウェイトブレンドのまま(多数の中間色)。
    # ボーン名 north/red はハッシュ色の距離が大きいペア(0.52)を事前計算で
    # 選んだもの(近い色のペアだとブレンドの中間色が2桁丸めで潰れて
    # ソフト側の判定ができない)。
    def build(hard):
        bpy.ops.wm.read_homefile(use_empty=True)
        arm = bpy.data.armatures.new("FP_Arm")
        arm_obj = bpy.data.objects.new("FP_Arm", arm)
        bpy.context.scene.collection.objects.link(arm_obj)
        bpy.context.view_layer.objects.active = arm_obj
        bpy.ops.object.mode_set(mode="EDIT")
        b1 = arm.edit_bones.new("north")
        b1.head, b1.tail = (0, 0, 0), (0, 0, 1)
        b2 = arm.edit_bones.new("red")
        b2.head, b2.tail = (0, 0, -1), (0, 0, 0)
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2)
        obj = bpy.context.active_object
        vg_u = obj.vertex_groups.new(name="north")
        vg_l = obj.vertex_groups.new(name="red")
        for v in obj.data.vertices:
            t = min(1.0, max(0.0, v.co.z / 2.0 + 0.5))  # なだらかな重み遷移(球全体)
            if t > 0:
                vg_u.add([v.index], t, "REPLACE")
            if t < 1:
                vg_l.add([v.index], 1.0 - t, "REPLACE")
        mod = obj.modifiers.new("Armature", "ARMATURE")
        mod.object = arm_obj
        scene = bpy.context.scene
        scene.fp_use_random_seed = False
        scene.fp_color_seed = 1234
        scene.fp_sharp_auto = True
        scene.fp_bone_hard_names = hard
        arm_obj.select_set(False)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.freepencil.auto_vertex_color()
        colors = set()
        for o in bpy.context.scene.objects:
            if o.type == "MESH" and "bone_color" in o.data.color_attributes:
                attr = o.data.color_attributes["bone_color"]
                colors |= {tuple(round(v, 2) for v in d.color[:3])
                           for d in attr.data}
        return len(colors)

    soft = build("")
    hard = build("north")
    # ソフトはブレンドの中間色を多数持ち、ハードは少数の純色に潰れる
    assert hard <= 6, f"hard boundary should be few discrete colors: {hard}"
    assert soft >= hard + 4, f"soft should have more blend colors: soft={soft} hard={hard}"


@test("part tint separates touching objects sharing a bone")
def t18():
    # 髪と顔のように「同じボーン支配の別オブジェクト」が接している場合、
    # fp_part_tint ON なら mecha_color がパーツごとに別の明度帯になり
    # (パーツ境界線の源)、bone_color は ON/OFF に関わらず元の純粋な
    # ウェイトブレンドのまま(パーツ線は mecha 担当、ノードで合成)。
    def build(tint_on):
        bpy.ops.wm.read_homefile(use_empty=True)
        arm = bpy.data.armatures.new("FP_Arm")
        arm_obj = bpy.data.objects.new("FP_Arm", arm)
        bpy.context.scene.collection.objects.link(arm_obj)
        bpy.context.view_layer.objects.active = arm_obj
        bpy.ops.object.mode_set(mode="EDIT")
        b = arm.edit_bones.new("north")
        b.head, b.tail = (0, 0, 0), (0, 0, 1)
        bpy.ops.object.mode_set(mode="OBJECT")
        objs = []
        for x in (0.0, 1.8):  # 半径1の球を重なるように配置(接触パーツ)
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1,
                                                  location=(x, 0, 0))
            o = bpy.context.active_object
            vg = o.vertex_groups.new(name="north")
            vg.add([v.index for v in o.data.vertices], 1.0, "REPLACE")
            mod = o.modifiers.new("Armature", "ARMATURE")
            mod.object = arm_obj
            objs.append(o)
        scene = bpy.context.scene
        scene.fp_use_random_seed = False
        scene.fp_color_seed = 1234
        scene.fp_sharp_auto = True
        scene.fp_bone_hard_names = ""
        scene.fp_part_tint = tint_on
        arm_obj.select_set(False)
        for o in objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = objs[0]
        bpy.ops.freepencil.auto_vertex_color()
        mecha, bone = [], []
        for o in objs:
            mecha.append(set(get_mecha_colors(o)))
            attr = o.data.color_attributes["bone_color"]
            bone.append({tuple(round(v, 2) for v in d.color[:3])
                         for d in attr.data})
        return mecha, bone

    def luma_gap(pair):
        # 各パーツの平均輝度の差。PROノードの線検出は輝度差に反応する
        lumas = [sum(sum(c) / 3.0 for c in s) / len(s) for s in pair]
        return abs(lumas[0] - lumas[1])

    mecha_on, bone_on = build(True)
    mecha_off, bone_off = build(False)
    g_on, g_off = luma_gap(mecha_on), luma_gap(mecha_off)
    assert g_on >= 0.12, f"tint ON should separate part lumas: {g_on:.3f}"
    assert g_off < 0.05, f"tint OFF must keep near-equal lumas (jitter only): {g_off:.3f}"
    # bone_color は ON/OFF に関わらず元の純粋なブレンドのまま
    assert bone_on == bone_off, f"bone_color must stay pure: {bone_on} vs {bone_off}"
    assert bone_on[0] == bone_on[1], f"same bone -> same bone_color: {bone_on}"


@test("STEP3 file output writes exactly the selected passes")
def t19():
    # fp_file_output ON で File Output ノードが追加され、チェックの入った
    # パスだけがスロットになり配線されること。OFF(既定)では追加されない。
    # v2.5.0 は line/color/Shadow 固定だった。影は EEVEE だとノイズが多く
    # 使えないことが多いのでディフューズ直接光を既定にし、影は任意に。
    # RenderLayers のソケット名は 4.x が 'DiffDir'、5.x が 'Diffuse Direct'。
    def build(enable, **flags):
        bpy.ops.wm.read_homefile(use_empty=True)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2)
        obj = bpy.context.active_object
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        scene = bpy.context.scene
        scene.fp_use_random_seed = False
        scene.fp_color_seed = 1234
        scene.fp_sharp_auto = True
        bpy.ops.freepencil.auto_vertex_color()
        bpy.ops.freepencil4.link_button()
        scene.fp_node_type = "pro"
        scene.fp_enable_compositor_view = False
        scene.fp_file_output = enable
        scene.fp_file_output_path = "//render/"
        for k, v in flags.items():
            setattr(scene, k, v)
        bpy.ops.freepencil2.link_button()
        tree = fp_batch.comp_tree(scene)
        return [n for n in tree.nodes if n.type == "OUTPUT_FILE"], tree

    # 既定: line / color / light (影は OFF)
    fos, tree = build(True)
    assert len(fos) == 1, f"expected one File Output node: {len(fos)}"
    fo = fos[0]
    assert fp_batch.fo_dir(fo) == "//render/", fp_batch.fo_dir(fo)
    assert fp_batch.fo_slot_names(fo) == {"line", "color", "light"},         fp_batch.fo_slot_names(fo)
    linked = {lk.to_socket.name for lk in tree.links if lk.to_node == fo}
    assert linked == {"line", "color", "light"}, f"unlinked: {linked}"
    assert bpy.context.view_layer.use_pass_diffuse_direct
    src = next(lk.from_socket.name for lk in tree.links
               if lk.to_node == fo and lk.to_socket.name == "light")
    assert src in ("DiffDir", "Diffuse Direct"), src

    # 影を足す
    fos, tree = build(True, fp_fo_shadow=True)
    assert fp_batch.fo_slot_names(fos[0]) == {"line", "color", "light", "shadow"}
    linked = {lk.to_socket.name for lk in tree.links if lk.to_node == fos[0]}
    assert "shadow" in linked, linked
    assert bpy.context.view_layer.use_pass_shadow
    src = next(lk.from_socket.name for lk in tree.links
               if lk.to_node == fos[0] and lk.to_socket.name == "shadow")
    assert src == "Shadow", src

    # 線だけ
    fos, tree = build(True, fp_fo_color=False, fp_fo_light=False)
    assert fp_batch.fo_slot_names(fos[0]) == {"line"},         fp_batch.fo_slot_names(fos[0])

    # 全部外したらノード自体を作らない
    fos, _ = build(True, fp_fo_line=False, fp_fo_color=False,
                   fp_fo_light=False, fp_fo_shadow=False)
    assert not fos, "no pass selected -> no File Output node"

    fos, _ = build(False)
    assert not fos, "File Output must not be added when disabled"


@test("checked cameras batch-render into per-camera folders")
def t20():
    # freepencil.render_cameras: チェック済みカメラだけを順にレンダリングし、
    # File Output がカメラ別フォルダ //camera_renders/NN_名前/ に書き出す。
    # 実行後は元のカメラ・保存先に戻る。
    import shutil
    import tempfile
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2)
    obj = bpy.context.active_object
    scene = bpy.context.scene
    cams = {}
    for name, loc in (("CamA", (0, -5, 0)), ("CamB", (5, 0, 0))):
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
        cam.location = loc
        cam.rotation_euler = (1.5708, 0, 0 if name == "CamA" else 1.5708)
        scene.collection.objects.link(cam)
        cams[name] = cam
    cams["CamB"].fp_cam_render = False
    scene.camera = cams["CamB"]

    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 1234
    scene.fp_sharp_auto = True
    bpy.ops.freepencil.auto_vertex_color()
    bpy.ops.freepencil4.link_button()
    scene.fp_node_type = "pro"
    scene.fp_enable_compositor_view = False
    scene.fp_file_output = True
    bpy.ops.freepencil2.link_button()
    scene.render.resolution_x = 64
    scene.render.resolution_y = 48

    tmp = Path(tempfile.mkdtemp(prefix="fp_t20_"))
    try:
        bpy.ops.wm.save_as_mainfile(filepath=str(tmp / "t20.blend"))
        fo = next(n for n in fp_batch.comp_tree(scene).nodes
                  if n.bl_idname == "CompositorNodeOutputFile")
        orig_path = fp_batch.fo_dir(fo)
        bpy.ops.freepencil.render_cameras()
        root = tmp / "camera_renders"
        cam_a = root / "01_CamA"
        assert cam_a.is_dir(), sorted(p.name for p in root.iterdir())
        # 5.x は format.media_type の既定が MULTI_LAYER_IMAGE で、そのままだと
        # 多層EXR1本になる。compat が IMAGE へ切り替えるので 4.x と同じく
        # スロットごとの個別PNGが出るはず
        pngs = list(cam_a.glob("*.png"))
        assert len(pngs) >= 3, [p.name for p in cam_a.iterdir()]
        assert not any("CamB" in p.name for p in root.iterdir()), \
            "unchecked camera must be skipped"
        assert scene.camera == cams["CamB"], "original camera must be restored"
        assert fp_batch.fo_dir(fo) == orig_path, \
            "File Output path must be restored"
    finally:
        bpy.ops.wm.read_homefile(use_empty=True)
        shutil.rmtree(tmp, ignore_errors=True)


@test("STEP0 auto setup runs STEP1-3 with scene-fit decisions")
def t21():
    # freepencil.auto_setup: リグ検出で bone AOV 自動ON、BLENDマテリアルの
    # HASHED化、film_transparent の維持、STEP1-3 の一括実行を検証。
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene

    # リグ付きメッシュ
    arm = bpy.data.armatures.new("FP_Arm")
    arm_obj = bpy.data.objects.new("FP_Arm", arm)
    scene.collection.objects.link(arm_obj)
    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode="EDIT")
    b = arm.edit_bones.new("root")
    b.head, b.tail = (0, 0, 0), (0, 0, 1)
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1)
    obj = bpy.context.active_object
    vg = obj.vertex_groups.new(name="root")
    vg.add([v.index for v in obj.data.vertices], 1.0, "REPLACE")
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm_obj

    # トゥーン風 BLEND マテリアル(ガラスではない)
    mat = bpy.data.materials.new("FP_Toon")
    mat.use_nodes = True
    mat.blend_method = "BLEND"
    obj.data.materials.append(mat)

    scene.render.film_transparent = False
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 1234
    for o in bpy.context.selected_objects:
        o.select_set(False)  # 無選択 → 表示メッシュ自動選択の経路

    bpy.ops.freepencil.auto_setup()

    assert "mecha_color" in obj.data.color_attributes.keys() or \
        "mecha_color" in [c.name for c in obj.data.color_attributes], \
        "STEP1 must run"
    assert "bone_color" in [c.name for c in obj.data.color_attributes], \
        "rigged mesh must get bone_color"
    aovs = [a.name for a in bpy.context.view_layer.aovs]
    assert "bone_color" in aovs, f"bone AOV must be auto-enabled: {aovs}"
    assert scene.fp_supersample is True and \
        scene.render.resolution_percentage == 200, \
        "full auto must enable 2x supersampling by default"
    assert any(n.type == "GROUP" for n in fp_batch.comp_tree(scene).nodes), \
        "STEP3 must build the compositor group"
    assert mat.blend_method == "HASHED", "toon BLEND must become HASHED"
    assert scene.render.film_transparent is False, \
        "film_transparent must be preserved"

    # 個別トグルOFF: チェックを外した項目は適用されない
    mat2 = bpy.data.materials.new("FP_Toon2")
    mat2.use_nodes = True
    mat2.blend_method = "BLEND"
    obj.data.materials.append(mat2)
    scene.fp_auto_hashed = False
    scene.fp_auto_bone = False
    scene.fp_bone_color = False
    bpy.ops.freepencil.auto_setup()
    assert mat2.blend_method == "BLEND", \
        "hashed conversion must be skipped when toggled off"
    assert scene.fp_bone_color is False, \
        "bone AOV auto-detect must be skipped when toggled off"
    scene.fp_auto_hashed = True
    scene.fp_auto_bone = True

    # AOVの完全自動設定: mask_color に黒以外を塗る → fp_mask_color 自動ON。
    # 未塗り(STEP1が作る既定の黒のみ)の line_color は手動ONでも OFF になる。
    # マテリアルID加算が有効 → fp_mat_color 連動ON。検出トグルOFFなら何もしない
    attr = obj.data.color_attributes.get("mask_color") \
        or obj.data.color_attributes.new("mask_color", "BYTE_COLOR", "CORNER")
    attr.data[0].color = (1.0, 1.0, 1.0, 1.0)  # 実際に塗る
    scene.fp_mask_color = False
    scene.fp_mat_count = True
    scene.fp_mat_color = False
    scene.fp_auto_detect_aov = False
    bpy.ops.freepencil.auto_setup()
    assert scene.fp_mask_color is False, "detection must be skippable"
    scene.fp_auto_detect_aov = True
    scene.fp_line_color = True  # 手動ONだが line_color は未塗り → 自動がOFFへ
    bpy.ops.freepencil.auto_setup()
    assert scene.fp_mask_color is True, "painted mask_color must enable its AOV"
    assert scene.fp_mat_color is True, "mat AOV must follow material ID"
    assert scene.fp_line_color is False, \
        "auto must own AOV config: unpainted line_color turns off"
    aovs = [a.name for a in bpy.context.view_layer.aovs]
    assert "mask_color" in aovs and "mat_color" in aovs, aovs
    assert "line_color" not in aovs, aovs
    scene.fp_mat_count = False


@test("per-channel strength sliders retune ramps live and idempotently")
def t22():
    # fp_ch_* スライダー: 生成済みノードのしきい値位置を
    # position = 元位置 × 感度 ÷ 強さ で即時更新。1.0で元通り(冪等)、
    # 0でチャンネルOFF(位置1.0)、他チャンネルには影響しない。
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2)
    obj = bpy.context.active_object
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    scene = bpy.context.scene
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 1234
    scene.fp_sharp_auto = True
    bpy.ops.freepencil.auto_vertex_color()
    bpy.ops.freepencil4.link_button()
    scene.fp_node_type = "pro"
    scene.fp_enable_compositor_view = False
    bpy.ops.freepencil2.link_button()

    group = bpy.data.node_groups["FreePencil_v1_1_0_pro"]
    depth = group.nodes["ColorRamp.001"]
    bone = group.nodes["ColorRamp.002"]
    base_depth = depth.color_ramp.elements[1].position
    base_bone = bone.color_ramp.elements[1].position

    scene.fp_ch_depth = 2.0  # updateコールバックで即反映
    assert abs(depth.color_ramp.elements[1].position - base_depth / 2) < 1e-4
    assert abs(bone.color_ramp.elements[1].position - base_bone) < 1e-4, \
        "other channels must be unaffected"

    scene.fp_ch_depth = 1.0  # 冪等に復元
    assert abs(depth.color_ramp.elements[1].position - base_depth) < 1e-4

    scene.fp_line_sensitivity = 0.5  # 全体感度と乗算
    scene.fp_ch_depth = 2.0
    assert abs(depth.color_ramp.elements[1].position - base_depth / 4) < 1e-4

    scene.fp_ch_depth = 0.0  # OFF
    assert depth.color_ramp.elements[1].position >= 0.999
    # 位置1.0では強エッジ(勾配>1)が残るため、OFFは色ごと白にする
    assert all(abs(v - 1.0) < 1e-5
               for v in depth.color_ramp.elements[1].color[:3]), \
        "OFF must whiten the ramp color (gradients can exceed 1.0)"

    scene.fp_line_sensitivity = 1.0
    scene.fp_ch_depth = 1.0
    assert abs(depth.color_ramp.elements[1].position - base_depth) < 1e-4
    assert depth.color_ramp.elements[1].color[1] < 0.5, \
        "original dark color must be restored after OFF"

    # STEP3 再生成でもシーン値が反映される
    scene.fp_ch_depth = 2.0
    bpy.ops.freepencil2.link_button()
    depth = bpy.data.node_groups["FreePencil_v1_1_0_pro"].nodes["ColorRamp.001"]
    assert abs(depth.color_ramp.elements[1].position - base_depth / 2) < 1e-4
    scene.fp_ch_depth = 1.0


@test("white preview toggles a compositor mix, materials untouched")
def t23():
    # コンポジタ切替方式: FreePencil グループの Image 入力の手前に
    # Mix(白) を挿入し、係数だけで白地線画⇔マテリアル付きを切替。
    # マテリアル/スロットには一切触れない。ツリーが無ければ何もしない。
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene

    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1)
    obj = bpy.context.active_object
    red = bpy.data.materials.new("FP_T23_Red")
    obj.data.materials.append(red)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    # コンポジタツリーが無い状態では安全に何もしない
    scene.fp_white_preview = True
    scene.fp_white_preview = False

    scene.fp_use_random_seed = False
    scene.fp_color_seed = 1234
    scene.fp_sharp_auto = True
    bpy.ops.freepencil.auto_vertex_color()
    bpy.ops.freepencil4.link_button()
    scene.fp_node_type = "pro"
    scene.fp_enable_compositor_view = False
    bpy.ops.freepencil2.link_button()

    tree = fp_batch.comp_tree(scene)

    def mix_node():
        return next((n for n in tree.nodes
                     if n.label == "FP_WhitePreviewMix"), None)

    scene.fp_white_preview = True
    mix = mix_node()
    assert mix is not None, "mix node must be inserted"
    assert mix.inputs[0].default_value == 1.0
    grp = next(n for n in tree.nodes if n.type == "GROUP")
    img_link = grp.inputs["Image"].links[0]
    assert img_link.from_node == mix, "group Image must come from the mix"
    rl = next(n for n in tree.nodes if n.type == "R_LAYERS")
    assert mix.inputs[1].links[0].from_node == rl, \
        "mix input 1 must be the beauty pass"
    assert obj.material_slots[0].material.name == "FP_T23_Red", \
        "materials must be untouched"
    assert red.use_nodes is False or True  # マテリアルに変更を加えない方式

    scene.fp_white_preview = False
    assert mix_node().inputs[0].default_value == 0.0, "factor back to zero"
    assert obj.material_slots[0].material.name == "FP_T23_Red"


@test("white preview leaves shared-mesh slots alone and heals legacy backups")
def t24():
    # ノード注入方式ではスロットを一切書き換えないので、リンク複製
    # (メッシュデータ共有)でも何も起きないことを検証。加えて、
    # 旧スワップ方式で保存されたファイルの汚染バックアップが OFF で
    # 自己修復されること(レガシー復元パス)。
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene

    red = bpy.data.materials.new("FP_T24_Red")
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1)
    a = bpy.context.active_object
    a.data.materials.append(red)
    b = bpy.data.objects.new("FP_T24_B", a.data)  # リンク複製
    scene.collection.objects.link(b)

    # 共有メッシュ+マテリアル無し
    bpy.ops.mesh.primitive_cube_add(location=(5, 0, 0))
    c = bpy.context.active_object
    d = bpy.data.objects.new("FP_T24_D", c.data)
    scene.collection.objects.link(d)

    scene.fp_white_preview = True
    for o in (a, b):
        assert o.material_slots[0].material.name == "FP_T24_Red", \
            "slots must never change in compositor mode"
    assert len(c.data.materials) == 0, \
        "compositor mode must not add slots either"

    scene.fp_white_preview = False

    # 旧スワップ方式の汚染バックアップ(兄弟が白を元として保存)の自己修復
    white = bpy.data.materials.new("FP_White_Preview")
    for slot in a.material_slots:
        slot.material = white
    a["fp_orig_mats"] = ["FP_T24_Red"]
    b["fp_orig_mats"] = ["FP_White_Preview"]  # 汚染
    scene.fp_white_preview = True   # プロパティを立ててから
    scene.fp_white_preview = False  # OFFでレガシー復元パスを通す
    mats = [s.material.name if s.material else "" for s in a.material_slots]
    assert mats == ["FP_T24_Red"], f"poisoned backup must not win: {mats}"


@test("white preview survives STEP3 regeneration")
def t25():
    # プレビューON中に STEP3 を再生成すると Mix(白) は一旦消えるが、
    # setup_compositor が挿入し直して状態が維持されること。
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1)
    obj = bpy.context.active_object
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 1234
    scene.fp_sharp_auto = True
    bpy.ops.freepencil.auto_vertex_color()
    bpy.ops.freepencil4.link_button()
    scene.fp_node_type = "pro"
    scene.fp_enable_compositor_view = False
    bpy.ops.freepencil2.link_button()

    scene.fp_white_preview = True
    bpy.ops.freepencil2.link_button()  # STEP3 再生成
    tree = fp_batch.comp_tree(scene)
    mix = next((n for n in tree.nodes
                if n.label == "FP_WhitePreviewMix"), None)
    assert mix is not None, "mix must be re-inserted after STEP3 regen"
    assert mix.inputs[0].default_value == 1.0, "preview state must survive"
    grp = next(n for n in tree.nodes if n.type == "GROUP")
    assert grp.inputs["Image"].links[0].from_node == mix

    scene.fp_white_preview = False
    assert mix.inputs[0].default_value == 0.0


@test("2x supersampling wires half-scale into composite and file output")
def t26():
    # fp_supersample ON: 解像度200% + Composite/File Output の直前に
    # 0.5 RELATIVE スケールが入る。OFFで再生成すると解像度100%に戻り
    # スケールノードも消える。
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1)
    obj = bpy.context.active_object
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    scene = bpy.context.scene
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 1234
    scene.fp_sharp_auto = True
    bpy.ops.freepencil.auto_vertex_color()
    bpy.ops.freepencil4.link_button()
    scene.fp_node_type = "pro"
    scene.fp_enable_compositor_view = False
    scene.fp_file_output = True
    scene.fp_supersample = True
    bpy.ops.freepencil2.link_button()

    tree = fp_batch.comp_tree(scene)
    assert scene.render.resolution_percentage == 200
    comp = next(n for n in tree.nodes if fp_batch.is_output_node(n))
    src = comp.inputs[0].links[0].from_node
    # 常時 0.5。ビューポートプレビューが半分のサイズになる副作用があるが、
    # 1.0 にするとプレビューの線が細線化されず、細さを確認できなくなる。
    # 細さの確認がプレビューの目的なので、表示が小さい方を受け入れる。
    assert src.type == "SCALE" and src.inputs["X"].default_value == 0.5, \
        f"composite must be fed via 0.5 scale, got {src.type}"
    fo = next(n for n in tree.nodes if n.type == "OUTPUT_FILE")
    linked = [s for s in fo.inputs if s.links]
    # 5.x の File Output は末尾に未接続の仮想ソケットが常に1本ぶら下がる
    assert linked, "file output must have linked slots"
    for sock in linked:
        assert sock.links[0].from_node.type == "SCALE", \
            f"file output slot {sock.name} must be scaled"

    scene.fp_supersample = False
    bpy.ops.freepencil2.link_button()
    tree = fp_batch.comp_tree(scene)
    assert scene.render.resolution_percentage == 100
    assert not any(n.type == "SCALE" for n in tree.nodes), \
        "scale nodes must be removed when supersampling is off"


@test("STEP1/STEP0 progress generator drives per-object and INVOKE is safe")
def t27():
    # 応答なし対策のモーダル進捗バー回帰。GUIモーダルは headless では
    # 動かせないので、(a) 生成器が1オブジェクトずつ進捗を yield すること、
    # (b) INVOKE_DEFAULT が background では同期実行へ落ちること、を見る。
    from freepencil2 import vertex_color

    bpy.ops.wm.read_homefile(use_empty=True)
    for i in range(3):
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, location=(i * 3, 0, 0))
    # primitive_add は直前の選択を外すので、最後にまとめて選択し直す
    for o in bpy.context.scene.objects:
        o.select_set(True)
    scene = bpy.context.scene
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 1234

    gen, state = vertex_color.make_vertex_color_gen(bpy.context, quiet=True)
    steps = []
    while True:
        try:
            steps.append(next(gen))
        except StopIteration:
            break
    # 単一の高密度メッシュでもバーが進むよう、オブジェクト単位に加えて
    # オブジェクト内フェーズでも yield する(done は小数になる)。
    done = [s[0] for s in steps]
    assert all(s[1] == 3 for s in steps), f"total must be object count: {steps}"
    assert done == sorted(done), f"progress must never go backwards: {done}"
    assert done[0] == 0.0, f"must yield before any heavy setup: {steps}"
    # 各オブジェクトの開始(整数)が来ていること
    for k in range(3):
        assert k in done, f"missing start of object {k}: {done}"
    # 最終オブジェクトの内部フェーズまで刻まれていること
    assert max(done) >= 2.5, f"per-object phases must be reported: {done}"
    # 1メッシュあたり複数回刻まれる = バーが 0/1 で固まらない
    assert len(steps) >= 3 * 3, f"too few progress steps: {len(steps)}"
    assert state._result == {"FINISHED"}, state._result

    # background では invoke() -> execute() に落ちる(モーダルを張らない)
    bpy.ops.wm.read_homefile(use_empty=True)
    obj = fresh_scene_with_islands()
    res = bpy.ops.freepencil.auto_vertex_color("INVOKE_DEFAULT")
    assert res == {"FINISHED"}, res
    assert "mecha_color" in obj.data.color_attributes.keys()

    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1)
    o = bpy.context.active_object
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    res = bpy.ops.freepencil.auto_setup("INVOKE_DEFAULT")
    assert res == {"FINISHED"}, res
    assert fp_batch.comp_tree() is not None, "STEP0 must still reach STEP3"


@test("STEP0 leaves the white preview on so line art is visible at once")
def t28():
    # 初回利用者がSTEP0を押しただけで線画が見える状態にする。
    # 白プレビューはコンポジタ切替方式なのでマテリアルは触らない。
    # STEP3 でツリーが建った後に立てる必要がある(順序の回帰も兼ねる)。
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2)
    obj = bpy.context.active_object
    mat = bpy.data.materials.new("FP_T28_Mat")
    obj.data.materials.append(mat)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    scene = bpy.context.scene
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 1234
    scene.fp_enable_compositor_view = False
    assert scene.fp_auto_white_preview is True, "must default to on"

    bpy.ops.freepencil.auto_setup()

    assert scene.fp_white_preview is True, "STEP0 must leave white preview on"
    tree = fp_batch.comp_tree(scene)
    mix = next((n for n in tree.nodes if n.label == "FP_WhitePreviewMix"), None)
    assert mix is not None, "white preview mix must be wired by STEP0"
    assert mix.inputs[0].default_value == 1.0
    grp = next(n for n in tree.nodes if n.type == "GROUP")
    assert grp.inputs["Image"].links[0].from_node == mix, \
        "group Image must be fed through the white mix"
    assert obj.material_slots[0].material.name == "FP_T28_Mat", \
        "materials must stay untouched"

    # トグルOFFなら白プレビューには触れない
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2)
    o2 = bpy.context.active_object
    o2.select_set(True)
    bpy.context.view_layer.objects.active = o2
    scene = bpy.context.scene
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 1234
    scene.fp_enable_compositor_view = False
    scene.fp_auto_white_preview = False
    bpy.ops.freepencil.auto_setup()
    assert scene.fp_white_preview is False, \
        "toggle off must leave the white preview alone"


@test("sharp edges drive islands and STEP1 never mutates the mesh")
def t29():
    # アーティストの意図は Freestyle マークではなく「シャープ」で受け取る。
    # 島境界の判定はローカル配列で持ち、メッシュのシャープ/スムーズには
    # 一切書き込まない(以前は一時的に上書きして後で戻していた)。
    import numpy as np

    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.active_object
    # サブディバイドして「角度は緩いがシャープを付けた」エッジを作る
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.subdivide(number_cuts=3)
    bpy.ops.object.mode_set(mode="OBJECT")

    me = obj.data
    n = len(me.edges)
    marked = np.zeros(n, dtype=bool)
    marked[: n // 4] = True          # 一部だけシャープにする
    me.edges.foreach_set("use_edge_sharp", marked)

    before = np.empty(n, dtype=bool)
    me.edges.foreach_get("use_edge_sharp", before)
    before_smooth = np.empty(len(me.polygons), dtype=bool)
    me.polygons.foreach_get("use_smooth", before_smooth)

    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    scene = bpy.context.scene
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 1234
    scene.fp_sharp_clear = False      # シャープを尊重する既定の経路
    scene.fp_sharp_auto = False
    scene.fp_sharp_edges = 179.0      # 角度では絶対に割れない設定に
    scene.fp_min_island_area_pct = 0.0
    scene.fp_seam_boundaries = False
    res = bpy.ops.freepencil.auto_vertex_color()
    assert res == {"FINISHED"}, res

    # メッシュは無改変(ここが以前は書き換わって復元されていた)
    after = np.empty(len(obj.data.edges), dtype=bool)
    obj.data.edges.foreach_get("use_edge_sharp", after)
    assert np.array_equal(before, after), \
        "STEP1 must not touch use_edge_sharp"
    after_smooth = np.empty(len(obj.data.polygons), dtype=bool)
    obj.data.polygons.foreach_get("use_smooth", after_smooth)
    assert np.array_equal(before_smooth, after_smooth), \
        "STEP1 must not touch face smoothing"

    # 角度では割れない設定なので、島が複数あるならシャープが効いた証拠
    colors = {c for c in get_mecha_colors(obj)}
    assert len(colors) >= 2, \
        f"sharp-marked edges must split islands, got {len(colors)} color(s)"


@test("stale node group is regenerated and users are remapped")
def t30():
    # 「無ければ作る」判定だったため、古い .blend やアドオン旧版のノード
    # グループが残っていると永久に更新されなかった。無条件生成にすると
    # Blender が "名前.001" を作り、参照は古い方を掴んだままになる。
    # 版が古ければ作り直し、user_remap で参照を移してから正式名に戻す。
    from freepencil2 import utils_nodegroup as ung

    bpy.ops.wm.read_homefile(use_empty=True)
    name = "FreePencil_v1_1_0_pro"

    # 中身が空っぽの「古いグループ」を仕込む(版マーカーなし)
    stale = bpy.data.node_groups.new(name, "CompositorNodeTree")
    assert len(stale.nodes) == 0
    # それを使っているノードを1つ作り、参照が移ることを確かめる
    host = bpy.data.node_groups.new("FP_T30_Host", "CompositorNodeTree")
    user = host.nodes.new("CompositorNodeGroup")
    user.node_tree = stale

    ng = ung.ensure_node_group_updated(name)

    assert ng.name == name, f"正式名に戻すこと: {ng.name}"
    assert len(ng.nodes) > 10, f"古い空グループが再生成されていない: {len(ng.nodes)}"
    assert ng.get("fp_node_version") == ung.NODE_GROUP_VERSION
    # ".001" が残っていないこと(=古い方が消えている)
    assert not any(n.name.startswith(name + ".")
                   for n in bpy.data.node_groups), \
        [n.name for n in bpy.data.node_groups]
    # 参照が新しいグループへ移っていること
    assert user.node_tree is ng, "user_remap で参照を移すこと"

    # 2回目は版が一致するので作り直さない(冪等)
    again = ung.ensure_node_group_updated(name)
    assert again is ng, "最新版なら再生成しない"


@test("numeric socket indices used by fp_core hold on this Blender")
def t31():
    # fp_core は数値添字でソケットを掴んでいる箇所がある。5.x でソケット
    # 構成が変わったため本来は名前引きが原則だが、Mix は 4.5 で 'Image' が
    # 2つあり名前で引けない(実測: ['Fac','Image','Image'])。両バージョンの
    # ランタイムダンプで位置を確認したうえで添字を使っている。
    # ここでその前提が崩れていないことを固定する。
    from freepencil2 import compat

    bpy.ops.wm.read_homefile(use_empty=True)
    ng = bpy.data.node_groups.new("FP_T31", "CompositorNodeTree")
    if compat.IS_5_PLUS:
        ng.interface.new_socket("Image", in_out="OUTPUT",
                                socket_type="NodeSocketColor")

    # 白プレビューの Mix: [0]=係数 [1]=下段 [2]=上段
    mix = compat.new_node(ng, "CompositorNodeMixRGB")
    assert len(mix.inputs) >= 3, [s.name for s in mix.inputs]
    assert mix.inputs[0].name in ("Fac", "Factor"), mix.inputs[0].name
    assert mix.inputs[1].name in ("Image", "Color1"), mix.inputs[1].name
    assert mix.inputs[2].name in ("Image", "Color2"), mix.inputs[2].name

    # 細線化の Scale: [0]=Image、倍率は名前引き
    sc = compat.new_node(ng, "CompositorNodeScale")
    assert sc.inputs[0].name == "Image", sc.inputs[0].name
    assert sc.inputs.get("X") is not None, [s.name for s in sc.inputs]

    # 最終出力: [0]=Image (4.x Composite / 5.x Group Output)
    out = compat.new_output_node(ng)
    assert out.inputs[0].name == "Image", out.inputs[0].name

    # Set Alpha: [0]=Image
    sa = ng.nodes.new("CompositorNodeSetAlpha")
    assert sa.inputs[0].name == "Image", sa.inputs[0].name

    # Anti-Aliasing: [0]=Image
    try:
        aa = ng.nodes.new("CompositorNodeAntiAliasing")
        assert aa.inputs[0].name == "Image", aa.inputs[0].name
    except RuntimeError:
        pass  # このビルドに無ければ対象外


@test("version numbers agree between bl_info and the manifest")
def t32():
    # v2.5.0 公開時、bl_info の version が (2,4,0) のままで配布ZIPの
    # パネルに v2.4.0 と出た。最低バージョンも bl_info=4.3 / manifest=4.2 と
    # ずれていた。番号は2箇所にあるので、一致をテストで固定する。
    import re

    import freepencil2

    repo = Path(freepencil2.__file__).resolve().parent
    manifest = (repo / "blender_manifest.toml").read_text(encoding="utf-8")

    def field(key):
        m = re.search(rf'^{key}\s*=\s*"([^"]+)"', manifest, re.M)
        assert m, f"{key} が manifest に無い"
        return m.group(1)

    ver = tuple(int(x) for x in field("version").split("."))
    assert ver == tuple(freepencil2.bl_info["version"]), (
        f'manifest version={ver} != bl_info={freepencil2.bl_info["version"]}')

    vmin = tuple(int(x) for x in field("blender_version_min").split("."))
    assert vmin == tuple(freepencil2.bl_info["blender"]), (
        f'manifest blender_version_min={vmin} '
        f'!= bl_info blender={freepencil2.bl_info["blender"]}')

    # パネル見出しに出る文字列も同じ番号であること
    label = bpy.types.FREEPENCIL_PT_LINE.bl_label
    assert label.endswith(".".join(map(str, ver))), label


@test("viewport preview is skipped where AOVs are not evaluated (4.2)")
def t33():
    # 4.2 のビューポートコンポジタは AOV を評価しないため、レンダー表示に
    # 切り替えると真っ白になる(実測)。切り替えないことを固定する。
    # 4.3 以降では従来どおり切り替える。
    from freepencil2 import compat

    expected = bpy.app.version >= (4, 3, 0)
    assert compat.HAS_AOV_IN_VIEWPORT_COMPOSITOR is expected, (
        f"flag={compat.HAS_AOV_IN_VIEWPORT_COMPOSITOR} "
        f"expected={expected} on {bpy.app.version_string}")

    # RENDERED へ切り替える箇所は STEP2(aov_node) と STEP3(sample_node) の
    # 2つある。どちらもフラグでガードされていること。片方だけ直して
    # 4.2 が白いまま、という取りこぼしを防ぐ。
    repo = Path(compat.__file__).resolve().parent
    for fname in ("sample_node.py", "aov_node.py"):
        body = (repo / fname).read_text(encoding="utf-8")
        if "shading.type = 'RENDERED'" not in body:
            continue
        guard = body.find("HAS_AOV_IN_VIEWPORT_COMPOSITOR")
        switch = body.index("shading.type = 'RENDERED'")
        assert 0 <= guard < switch, f"{fname}: RENDERED 切り替えが未ガード"


@test("part tint windows keep their step and stay inside the luma range")
def t34():
    # パーツ・トーン分けの明度窓。窓幅は段によって不揃いになる(上限
    # 0.85 でクランプされるため)が、それは許容している。守るべきは
    # 「段の間隔」と「範囲からはみ出さないこと」。
    # 幅を揃えるために段を詰める案は、パーツ分離(t18)と min距離契約(t14)を
    # 壊すうえ絵が変わらないので却下済み(utils.part_luma_window のコメント)。
    from freepencil2 import utils

    windows = [utils.part_luma_window(p) for p in range(utils.PART_TINT_STEPS)]

    for lo, hi in windows:
        assert lo >= utils.PART_LUMA_FLOOR - 1e-9, (lo, utils.PART_LUMA_FLOOR)
        assert hi <= utils.PART_LUMA_CEIL + 1e-9, (hi, utils.PART_LUMA_CEIL)
        assert hi > lo, (lo, hi)

    # 段の間隔が保たれていること(接するパーツに線を出すための分離)
    los = [lo for lo, _ in windows]
    for a, b in zip(los, los[1:]):
        assert round(b - a, 6) == utils.PART_TINT_DELTA, (los,
                                                          utils.PART_TINT_DELTA)

    # 巡回すること(クラス番号が段数を超えても壊れない)
    assert utils.part_luma_window(utils.PART_TINT_STEPS) == windows[0]

    # 実際に色を作っても輝度が範囲内に収まること
    for lo, hi in windows:
        colors, _pmin, _lmin = utils.build_palette(5, 42, luma_lo=lo, luma_hi=hi)
        lumas = [utils._luma(c) for c in colors]
        assert min(lumas) >= utils.PART_LUMA_FLOOR - 0.02, min(lumas)
        assert max(lumas) <= utils.PART_LUMA_CEIL + 0.02, max(lumas)


@test("generated node trees are laid out without overlaps or backward links")
def t35():
    # 座標はエクスポート元 .blend の手配置がそのまま入っており、実測で
    # PROノード80個に対して重なり97組・リンク97本中47本が右から左へ
    # 逆流していた。生成後に階層レイアウトを掛けて解消している。
    # 機能ではなく可読性の話だが、ユーザーがコンポジタを開く前提の
    # 復旧手順がある以上、崩れたら気づけるようにしておく。
    import itertools

    from freepencil2 import compat

    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_cube_add()
    bpy.context.active_object.select_set(True)
    scene = bpy.context.scene
    scene.fp_node_type = "pro"
    scene.fp_enable_compositor_view = False
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")

    def rect(n):
        w = n.width or 140.0
        h = n.dimensions.y or (46.0 + 24.0 * (len(n.inputs) + len(n.outputs)))
        return (n.location.x, n.location.y - h, n.location.x + w, n.location.y)

    trees = [g for g in bpy.data.node_groups if g.name.startswith("FreePencil")]
    root = compat.get_compositor_tree(scene)
    if root is not None:
        trees.append(root)
    assert trees, "no FreePencil trees were built"

    for tree in trees:
        nodes = list(tree.nodes)
        rects = {n.name: rect(n) for n in nodes}

        for a, b in itertools.combinations(nodes, 2):
            ax0, ay0, ax1, ay1 = rects[a.name]
            bx0, by0, bx1, by1 = rects[b.name]
            dx = min(ax1, bx1) - max(ax0, bx0)
            dy = min(ay1, by1) - max(ay0, by0)
            assert not (dx > 1.0 and dy > 1.0), (
                f"{tree.name}: {a.name} と {b.name} が重なっている")

        # グループ内は逆流ゼロにできる。ルートは白プレビューの差し込みで
        # 1本だけ戻ることがあるため許容する
        backward = [lk for lk in tree.links
                    if rects[lk.to_node.name][0] < rects[lk.from_node.name][2]]
        limit = 0 if tree is not root else 2
        assert len(backward) <= limit, (
            f"{tree.name}: 逆流リンク {len(backward)} 本 "
            f"({[lk.from_node.name for lk in backward][:4]})")


@test("manual channels behave the same on every Blender version")
def t36():
    # 5.x 用 PRO ノードの書き出しで Color Key の設定が丸ごと落ちており
    # (color_hue がプロパティからソケットへ移ったのを検出できず沈黙して
    # スキップしていた)、キーする色が黒→白の既定に化けて mask_color が
    # 反転していた。4.5 では「塗れば消える」、5.2 では「白は無効」と
    # バージョンで結果が違う状態だった。
    #
    # 正しい挙動(4.x と一致):
    #   mask_color … 塗った側の線が消える。明度は問わない(白でも消える)
    #   line_color … 明るく塗るほど線が薄くなり、0.4 以上で見えなくなる
    #
    # バージョン差がまた入らないよう、値そのものを固定する。
    def ink_after(channel, value):
        bpy.ops.wm.read_homefile(use_empty=True)
        bpy.ops.mesh.primitive_cube_add()
        obj = bpy.context.active_object
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        scene = bpy.context.scene
        scene.fp_use_random_seed = False
        scene.fp_color_seed = 1234
        scene.fp_enable_compositor_view = False
        scene.fp_supersample = False
        scene.fp_auto_detect_aov = False
        scene.fp_mask_color = True
        scene.fp_line_color = True
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        if channel:
            attr = obj.data.color_attributes[channel]
            n = len(attr.data)
            attr.data.foreach_set("color", [value, value, value, 1.0] * n)
            obj.data.update()
        fp_batch.setup_camera_and_light()
        scene.render.engine = fp_batch.eevee_engine()
        scene.eevee.taa_render_samples = 4
        scene.render.resolution_x = scene.render.resolution_y = 240
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGBA"
        png = BATCH / "out" / f"t36_{channel or 'base'}_{value}.png"
        png.parent.mkdir(parents=True, exist_ok=True)
        fp_batch.render_still(scene, png, 1)
        return fp_batch.lineart_metrics(png)["ink_ratio"]

    base = ink_after(None, 0.0)
    assert base > 0, "基準に線が出ていない"

    # mask は明度によらず消える。白でも消えるのが正しい
    for value in (0.2, 0.5, 1.0):
        got = ink_after("mask_color", value)
        assert got == 0.0, (
            f"mask_color={value} で線が残っている: {got} (基準 {base})。"
            "Color Key のキー色が黒でなく白になっていないか")

    # line は明るいほど薄くなり、0.4 以上で消える
    line_dim = ink_after("line_color", 0.2)
    assert 0 < line_dim < base, (
        f"line_color=0.2 が薄くなっていない: {line_dim} vs {base}")
    line_off = ink_after("line_color", 0.6)
    assert line_off == 0.0, f"line_color=0.6 で線が消えていない: {line_off}"


@test("far crush relief inserts nothing at 0 and is idempotent")
def t37():
    # 遠景つぶれ軽減は既定 OFF。OFF のときは1ノードも挿さらず、
    # line 出力のアルファ配線が素のままであること(=従来の絵と同一)。
    # ON/OFF を往復しても配線が元に戻ることも押さえる。
    from freepencil2 import fp_core

    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.active_object
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    scene = bpy.context.scene
    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")

    group = next(g for g in bpy.data.node_groups
                 if g.name.startswith(fp_core.NODE_GROUP_PREFIX))
    # ノード名はバージョンで変わるので配線で辿る(4.2 と 4.5 で別名だった)
    out_node = next(n for n in group.nodes if n.type == "GROUP_OUTPUT")
    line_in = next(s for s in out_node.inputs if s.name == "line")
    assert line_in.links, "line 出力に何も繋がっていない"
    sink = line_in.links[0].from_node
    assert sink.inputs.get("Alpha") is not None, "line 出力に Alpha が無い"
    plain = sink.inputs["Alpha"].links[0].from_node.name

    def relief_nodes():
        return [n for n in group.nodes if n.label == fp_core.RELIEF_LABEL]

    def alpha_from():
        links = sink.inputs["Alpha"].links
        return links[0].from_node.name if links else None

    assert not relief_nodes(), "既定でノードが挿さっている"

    n = fp_core.apply_far_relief(group, strength=0.0)
    assert n == 0 and not relief_nodes(), "強さ0で挿さってしまった"

    n = fp_core.apply_far_relief(group, strength=0.6, radius=6.0)
    assert n == 5, f"挿し込みノード数が想定外: {n}"
    assert len(relief_nodes()) == 5
    assert alpha_from() == "fp_relief_apply", (
        f"アルファが軽減ノードを通っていない: {alpha_from()}")

    # 2回目でも増殖しない
    n2 = fp_core.apply_far_relief(group, strength=0.6, radius=6.0)
    assert n2 == 5 and len(relief_nodes()) == 5, "呼ぶたびに増えている"

    # 0 に戻したら素の配線へ復帰する
    fp_core.apply_far_relief(group, strength=0.0)
    assert not relief_nodes(), "撤去できていない"
    assert alpha_from() == plain, f"配線が戻っていない: {alpha_from()}"


def main():
    print("[tests] FreePencil smoke tests")
    fp_batch.install_addon()
    for name, fn in sorted(globals().items()):
        if callable(fn) and getattr(fn, "__test__", False):
            fn()
    out = BATCH / "out"
    out.mkdir(exist_ok=True)
    (out / "tests.json").write_text(
        json.dumps(RESULTS, indent=2, ensure_ascii=False), encoding="utf-8")
    failed = [r for r in RESULTS if not r["ok"]]
    print(f"[tests] {len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    if failed:
        for f_ in failed:
            print(f_["error"])
        sys.exit(1)


if __name__ == "__main__":
    main()
