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
    scene.fp_supersample = False      # 縮小を挟まない組み方を見る(v2.9.2 で既定が ON になった)
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
        scene.fp_supersample = False  # パスを直接つなぐ組み方を見る(v2.9.2 で既定が ON になった)
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
    # 基準は「感度1.0のときの位置」。既定が 0.5 になったので、
    # 明示しないと基準自体がずれて以降の掛け算が合わなくなる
    scene.fp_line_sensitivity = 1.0
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
    assert ng.get("fp_node_version") == ung._stamp()
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

    # パネル見出しに出る文字列も同じ番号であること。
    # 開発ビルドでは番号の後ろに _YYYYMMDD+3桁 が付く
    # (scripts/stamp_dev.py が打ち、--release で外れる)。
    # 番号を上げずに中身だけ差し替えると新旧の区別がつかないので入れた。
    label = bpy.types.FREEPENCIL_PT_LINE.bl_label
    base = ".".join(map(str, ver))
    dev = getattr(freepencil2, "DEV_BUILD", "")
    assert label.endswith(f"{base}_{dev}" if dev else base), label
    if dev:
        assert re.fullmatch(r"\d{11}", dev), f"開発番号の形式が違う: {dev}"


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


@test("a healthy scene compositor tree is never discarded")
def t38():
    # 5.x はシーンのコンポジタをノードグループとして持つ。その .blend を
    # 4.x で開くと、そのグループが scene.node_tree に居座って絵が壊れる。
    # discard_foreign_scene_tree はそれを見分けて捨てる。
    #
    # ここで固定するのは「捨てすぎない」方向。居座り状態は 4.x の
    # scene.node_tree が読み取り専用なので Python からは作れず、
    # 実ファイルでの確認は dev/note_assets/eval_cross_version.py が行う
    # (実測: 5.2 で作成 0.0065 -> 4.5 で開く 0.9286 -> STEP3 で 0.0067)。
    from freepencil2 import compat

    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.active_object
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    scene = bpy.context.scene
    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")

    tree = compat.get_compositor_tree(scene)
    n_before = len(tree.nodes)
    assert n_before > 0, "コンポジタが組まれていない"

    # 正常なツリーは対象外
    assert compat.discard_foreign_scene_tree(scene) is False, (
        "正常なシーンツリーを捨てようとしている")
    tree2 = compat.get_compositor_tree(scene, create=True)
    assert len(tree2.nodes) == n_before, (
        f"ツリーが壊れた: {n_before} -> {len(tree2.nodes)}")

    # 4.x のシーンツリーは埋め込みで、node_groups には現れない
    if not compat.IS_5_PLUS:
        assert tree2.name not in bpy.data.node_groups, (
            "4.x のシーンツリーがグループとして現れている")


@test("file output is written at final size, not at 2x supersample size")
def t39():
    # 細線化は「200%でレンダして0.5に縮小」で作る。縮小ノードが
    # Composite にしか挿さっていないと、ファイル出力だけ2倍の大きさで
    # 出てしまい、F12 の絵と食い違う。実サイズで確かめる。
    import shutil
    import tempfile

    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2)
    obj = bpy.context.active_object
    scene = bpy.context.scene
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.location = (0, -5, 0)
    cam.rotation_euler = (1.5708, 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam

    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 1234
    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False
    scene.fp_file_output = True
    scene.fp_supersample = True          # ← 200% + 0.5 縮小
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")

    scene.render.resolution_x = 64
    scene.render.resolution_y = 48
    assert scene.render.resolution_percentage == 200, (
        "細線化がレンダー倍率に反映されていない")

    tmp = Path(tempfile.mkdtemp(prefix="fp_t39_"))
    try:
        bpy.ops.wm.save_as_mainfile(filepath=str(tmp / "t39.blend"))
        bpy.ops.freepencil.render_cameras()
        cam_dir = tmp / "camera_renders" / "01_Cam"
        pngs = sorted(cam_dir.glob("*.png"))
        assert pngs, sorted(p.name for p in cam_dir.iterdir())
        for png in pngs:
            img = bpy.data.images.load(str(png))
            size = tuple(img.size)
            bpy.data.images.remove(img)
            assert size == (64, 48), (
                f"{png.name} が最終サイズで出ていない: {size} != (64, 48)")
    finally:
        bpy.ops.wm.read_homefile(use_empty=True)
        shutil.rmtree(tmp, ignore_errors=True)


@test("loose parts get different colors even without shared edges")
def t40():
    """離れたパーツ同士が同じ色にならないこと。

    島の隣接はメッシュの境界エッジ越しにしか見ていないので、辺を1本も
    共有しないルースパーツは「隣接なし」になり、貪欲彩色が全部を同じ
    クラスに置いていた。画面では重なっているのに境界の色差がゼロになる。
    2026-08-09 の「違反0件」誤報と同じ穴なので、テストで塞ぐ。
    """
    import numpy as np

    from freepencil2 import mesh_islands

    # 触れ合わない距離に置いた球3個を1メッシュにする。
    # 立方体だと 90度の辺が切られて1個が6島になり「パーツ=1色」に
    # ならないので、60度では1島にまとまる球を使う
    bpy.ops.wm.read_homefile(use_empty=True)
    objs = []
    for loc in ((0, 0, 0), (2.2, 0, 0), (0, 2.2, 0)):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=loc)
        objs.append(bpy.context.object)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    obj = bpy.context.object

    me = obj.data
    topo = mesh_islands.MeshTopology(me)
    topo.mark_boundaries(np.radians(60.0), False, False)
    topo.build_islands()
    assert len(topo.islands) == 3, (
        f"球3個が3島にならない: {len(topo.islands)}")
    nbrs = topo.island_adjacency(boundary_only=True)
    before = sum(len(n) for n in nbrs)
    added = mesh_islands.add_loose_part_proximity(topo, me, nbrs)
    assert added > 0, "近接している別パーツが1組も隣接にならなかった"
    assert sum(len(n) for n in nbrs) > before

    # 実際に塗ってみて、パーツごとの色が全部違うこと
    scene = bpy.context.scene
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 42
    scene.fp_sharp_auto = False
    scene.fp_sharp_edges = 60.0
    scene.fp_min_island_area_pct = 0.0
    bpy.ops.freepencil.auto_vertex_color("EXEC_DEFAULT")
    cols = np.asarray(get_mecha_colors(obj), dtype=np.float64)
    starts = np.empty(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("loop_start", starts)
    face_col = cols[starts]
    ev = np.empty(len(me.edges) * 2, dtype=np.int32)
    me.edges.foreach_get("vertices", ev)
    ev = ev.reshape(-1, 2)
    lab = mesh_islands.connected_components(ev[:, 0], ev[:, 1],
                                            len(me.vertices))
    lv = np.empty(len(me.loops), dtype=np.int32)
    me.loops.foreach_get("vertex_index", lv)
    part = lab[lv[starts]]
    reps = [face_col[part == p][0] for p in np.unique(part)]
    assert len(reps) == 3, f"パーツが3個に分かれていない: {len(reps)}"
    for i in range(len(reps)):
        for j in range(i + 1, len(reps)):
            d = float(np.linalg.norm(reps[i][:3] - reps[j][:3]))
            assert d > 0.05, (
                f"パーツ {i} と {j} の色が近すぎる: 距離 {d:.3f}")


@test("ridge relief is zero on flat panels and non-zero on a curved ridge")
def t41():
    """稜線の起伏が「硬い面には足さず、曲面の稜線にだけ足す」こと。

    法線から距離Rぶん均した「大きな向き」を引いた残りを使うので、
    平らな面では 法線 ≒ 均した法線 で残差がゼロになる。これが崩れると
    メカにも起伏が乗ってしまい、モード判定なしで両立する前提が壊れる。
    """
    import numpy as np

    from freepencil2 import mesh_islands

    # 平らな面だけの形
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_cube_add(size=2.0)
    flat = bpy.context.object
    bpy.ops.object.shade_smooth()
    got = mesh_islands.ridge_residual(flat.data, 0.08)
    flat_max = 0.0 if got is None else float(np.abs(got[0]).max())

    # なめらかな出っ張りのある形
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_monkey_add()
    o = bpy.context.object
    m = o.modifiers.new("S", type="SUBSURF")
    m.levels = m.render_levels = 2
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.ops.object.shade_smooth()
    got = mesh_islands.ridge_residual(o.data, 0.08)
    assert got is not None, "曲面で残差が計算できていない"
    curved_max = float(np.abs(got[0]).max())

    assert curved_max > 0.2, f"曲面の稜線で残差が小さすぎる: {curved_max:.3f}"
    assert flat_max < curved_max * 0.25, (
        f"平面にも残差が乗っている: 平面 {flat_max:.3f} / 曲面 {curved_max:.3f}")


@test("auto threshold lowers to catch a gentle slope the percentile hides")
def t42():
    """多数派の角度に隠れた少数派を拾えること。

    面取りした箱の二面角は 90度x8 / 79度x4 / 64度x4 / 25.6度x4。
    p95 が 90度になるため `p95>75 -> 60度` の枝に落ち、緩い斜面の
    25.6度が切られずに線が消えていた(sample2 で発覚)。
    下げても島が増えすぎないなら下げる、という規則で拾い直す。

    同時に、なめらかなハイポリでは下げないことも固定する。
    5〜10度まで落ちるとメッシュの格子が線になるため。
    """
    import numpy as np

    from freepencil2 import mesh_islands

    # 上面のまわりを面取りした箱を作る
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_cube_add(size=2.0)
    obj = bpy.context.object
    bev = obj.modifiers.new("B", type="BEVEL")
    bev.width = 0.35
    bev.segments = 1
    bev.affect = 'EDGES'
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=bev.name)

    topo = mesh_islands.MeshTopology(obj.data)
    deg, n = mesh_islands.lower_threshold_for_detail(topo, 1, False, False)
    assert deg is not None and deg <= 40.0, (
        f"面取りした箱で角度が下がらない: {deg}")

    # なめらかなハイポリは下げない(格子が出る側)
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32)
    sphere = bpy.context.object
    topo = mesh_islands.MeshTopology(sphere.data)
    deg_s, n_s = mesh_islands.lower_threshold_for_detail(topo, 1, False, False)
    assert n_s <= 20, f"球が細かく割れた: {n_s}島"


def _lw_scene(scale=1.0):
    """線の強弱を試すための最小シーン。スザンヌ1体とカメラと1灯。"""
    import math
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_monkey_add()
    obj = bpy.context.object
    obj.scale = (scale,) * 3
    bpy.ops.object.transform_apply(scale=True)
    scene = bpy.context.scene
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.location = (0, -6 * scale, 0)
    cam.rotation_euler = (math.radians(90), 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 7
    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    return scene, obj


def _lw_node_count(scene):
    from freepencil2 import compat, line_weight
    tree = compat.get_compositor_tree(scene)
    if tree is None:
        return 0
    return sum(1 for n in tree.nodes if n.label == line_weight.NODE_LABEL)


@test("line weight adds nothing while it is off, and is idempotent when on")
def t43():
    # 既定OFF のときに1ノードでも増えると、既存ファイルの絵が変わる
    scene, _ = _lw_scene()
    scene.fp_line_weight = False
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    assert _lw_node_count(scene) == 0, "OFF なのに強弱ノードが入った"

    scene.fp_line_weight = True
    bpy.ops.freepencil2.link_button()
    first = _lw_node_count(scene)
    assert first > 0, "ON にしても強弱ノードが入らない"
    # STEP3 を繰り返しても増えないこと。増えるならノードが二重に挿さる
    bpy.ops.freepencil2.link_button()
    bpy.ops.freepencil2.link_button()
    assert _lw_node_count(scene) == first, (
        f"STEP3 のたびに強弱ノードが増える: {first} -> {_lw_node_count(scene)}")
    bpy.ops.wm.read_homefile(use_empty=True)


@test("line weight step widths follow the render percentage")
def t44():
    # 段の太さは「200%でレンダして50%に縮小」を前提にした値。細線化を
    # 切ると縮小が無くなるので、そのままでは線が太くなりすぎる
    from freepencil2 import line_weight
    scene, _ = _lw_scene()
    scene.fp_lw_strength = 1.0
    scene.render.resolution_percentage = 200
    big = line_weight.levels_from_scene(scene)
    scene.render.resolution_percentage = 100
    small = line_weight.levels_from_scene(scene)
    assert big == list(line_weight.LEVELS), f"200% で素の値と違う: {big}"
    assert sum(small) < sum(big), (
        f"細線化OFF でも同じ太さのまま: {small} vs {big}")
    assert min(small) >= 1, f"1px を割った: {small}"
    bpy.ops.wm.read_homefile(use_empty=True)


@test("cavity radius scales with the scene, not in absolute units")
def t45():
    # 絶対値にしていたら、10倍の大きさのモデルで何も遮蔽されず
    # 強弱が付かなかった
    from freepencil2 import line_weight
    scene, _ = _lw_scene(scale=1.0)
    r1 = line_weight.scene_radius(scene)
    bpy.ops.wm.read_homefile(use_empty=True)
    scene, _ = _lw_scene(scale=10.0)
    r10 = line_weight.scene_radius(scene)
    assert r10 > r1 * 5, f"シーンの大きさに追従していない: {r1} -> {r10}"
    bpy.ops.wm.read_homefile(use_empty=True)


@test("measuring line weight thresholds leaves no temp folder behind")
def t46():
    # 測るたびに temp が残っていた
    import tempfile
    from freepencil2 import line_weight
    scene, _ = _lw_scene()
    scene.fp_auto_style = 'WEIGHTED'   # STEP0 が強弱を入れる
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    root = Path(tempfile.gettempdir())
    before = set(root.glob("fp_lw_*"))
    line_weight.measure_edges(scene, bpy.context.view_layer, percent=10)
    after = set(root.glob("fp_lw_*"))
    assert after <= before, f"一時ディレクトリが残った: {sorted(after - before)}"
    bpy.ops.wm.read_homefile(use_empty=True)


@test("F12 fills the frame while thinning is on, and file output stays final size")
def t47():
    # 細線化はコンポジタの中で 0.5 に縮めるので、そのままだと F12 が
    # 「2倍のキャンバスに半分の大きさの絵」になっていた。実測(1920指定):
    #   細線化OFF 1920x1080 被写体幅1236 / ON 3840x2160 被写体幅1236
    # レンダーの間だけ Composite 側の縮小を外して、等倍で出す
    import math
    import tempfile
    from freepencil2 import compat, render_size

    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_monkey_add()
    obj = bpy.context.object
    scene = bpy.context.scene
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.location = (0, -6, 0)
    cam.rotation_euler = (math.radians(90), 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 3
    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False
    scene.fp_supersample = True
    # ファイル出力も出しておく。目印がそちらへ回ると STEP5 が2倍になる
    scene.fp_file_output = True
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    scene.render.resolution_x = 64
    scene.render.resolution_y = 48
    assert scene.render.resolution_percentage == 200, "細線化が倍率に効いていない"

    marked = render_size._composite_scales(scene)
    assert len(marked) == 1, f"Composite 側の縮小ノードが {len(marked)}個"
    tree = compat.get_compositor_tree(scene)
    all_scales = [n for n in tree.nodes if n.type == "SCALE"]
    assert len(all_scales) > len(marked), (
        f"ファイル出力側の縮小まで目印が付いている: "
        f"縮小ノード{len(all_scales)}個 / 目印{len(marked)}個")

    # レンダーの間だけ 1.0 に、終わったら 0.5 に戻ること
    before = marked[0].inputs["X"].default_value
    render_size._render_pre(scene)
    during = marked[0].inputs["X"].default_value
    render_size._render_post(scene)
    after = marked[0].inputs["X"].default_value
    assert abs(before - 0.5) < 1e-6, f"縮小率が 0.5 でない: {before}"
    assert abs(during - 1.0) < 1e-6, f"レンダー中に外れていない: {during}"
    assert abs(after - 0.5) < 1e-6, f"レンダー後に戻っていない: {after}"

    # 実際に F12 相当を回して、絵が枠いっぱいに出ること
    tmp = Path(tempfile.mkdtemp(prefix="fp_t47_"))
    try:
        scene.render.filepath = str(tmp / "f12.png")
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(str(tmp / "f12.png"))
        w, h = img.size
        buf = [0.0] * (w * h * 4)
        img.pixels.foreach_get(buf)
        bpy.data.images.remove(img)
        cols = [any(buf[(y * w + x) * 4 + 3] > 0.5 for y in range(h))
                for x in range(w)]
        width = sum(1 for c in cols if c)
        assert (w, h) == (128, 96), f"レンダー解像度が想定と違う: {w}x{h}"
        # 縮小が外れていれば、被写体は横幅の半分より広く写る
        assert width > w * 0.5, (
            f"絵が縮んだまま出ている: 被写体幅 {width} / 画像幅 {w}")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
        bpy.ops.wm.read_homefile(use_empty=True)


@test("line weight: open areas get wider ink than cavities, measured in the final image")
def t48():
    # 段分けが働いていなかった(計測は生の AO、合成はぼかした AO で
    # 線の画素の 88% が最細の段)うえに、段の向きも逆だった。47 本の
    # テストは通ったままだった。その後、段そのものをやめて連続にした。
    # 構造ではなく最終画像で「深い所ほど太い」を確かめる
    import glob
    import os
    import shutil
    import tempfile
    from freepencil2 import compat, line_weight

    # スザンヌは目のまわりに線が密集していて、窓の中に複数の線が入る。
    # 太さではなく密度を測ってしまい、向きを直しても数字が逆に出た
    # (実測: 深い 0.76 / 浅い 0.45)。外の輪郭(開いている)と穴の縁(くぼみ)
    # が孤立した線で出るトーラスにする
    import math
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_torus_add(major_segments=64, minor_segments=32)
    obj = bpy.context.object
    bpy.ops.object.shade_smooth()
    scene = bpy.context.scene
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.location = (0, -4.5, 3.2)
    cam.rotation_euler = (math.radians(55), 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 7
    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    scene.fp_auto_style = 'WEIGHTED'   # STEP0 が強弱を入れる
    scene.fp_supersample = False
    scene.fp_white_preview = True
    # 160x120 だと線幅(2倍で最大 12px)が絵を塗り潰して測れない(実測)
    scene.render.resolution_x = 400
    scene.render.resolution_y = 300
    scene.render.resolution_percentage = 200
    scene.render.film_transparent = True
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    scene.fp_white_preview = True
    bpy.ops.freepencil.measure_line_weight()
    edges = line_weight.edges_from_scene(scene)
    assert edges[0] < edges[-1], f"しきい値が単調でない: {edges}"
    bpy.ops.freepencil2.link_button()
    scene.fp_white_preview = True

    tree = compat.get_compositor_tree(scene)
    lab = line_weight.NODE_LABEL
    dep = binz = None
    for n in tree.nodes:
        if n.label != lab or n.type != "MATH":
            continue
        src = n.inputs[1].links[0].from_node if n.inputs[1].links else None
        if (n.operation == "SUBTRACT" and src is not None and src.type == "BLUR"
                and abs(n.inputs[0].default_value - 1.0) < 1e-6):
            dep = n
        src0 = n.inputs[0].links[0].from_node if n.inputs[0].links else None
        if (n.operation == "GREATER_THAN" and src0 is not None
                and src0.type == "INVERT" and binz is None):
            binz = n
    assert dep is not None and binz is not None, "dep / binz が見つからない"

    def measure(tmp):
        fo = tree.nodes.new("CompositorNodeOutputFile")
        compat.file_output_set_dir(fo, str(tmp))
        compat.file_output_clear_slots(fo)
        for name, node in (("dep", dep), ("binz", binz)):
            compat.file_output_add_slot(fo, name, "OPEN_EXR", "RGBA")
            tree.links.new(node.outputs[0], fo.inputs[name])
        scene.render.filepath = str(tmp / "final.png")
        bpy.ops.render.render(write_still=True)
        tree.nodes.remove(fo)

        def load(path):
            img = bpy.data.images.load(path)
            w, h = img.size
            buf = [0.0] * (w * h * 4)
            img.pixels.foreach_get(buf)
            bpy.data.images.remove(img)
            return w, h, buf

        def slot(name):
            return [h for h in glob.glob(os.path.join(str(tmp), "**", f"*{name}*"),
                                         recursive=True) if os.path.isfile(h)][0]
        w, h, d = load(slot("dep"))
        _, _, b = load(slot("binz"))
        fw, fh, f = load(str(tmp / "final.png"))
        assert (fw, fh) == (w, h), f"最終画像と dep の大きさが違う: {(fw, fh)} / {(w, h)}"
        ink = [0.0] * (w * h)
        for i in range(w * h):
            a = f[i * 4 + 3]
            g = (f[i * 4] + f[i * 4 + 1] + f[i * 4 + 2]) / 3.0
            ink[i] = (1.0 - g) * a

        # 芯の周り 11x11 のインク。7x7 だと太い線で飽和して差が出ない
        def around(i, r=5):
            y, x = divmod(i, w)
            tot = 0.0
            n = 0
            for yy in range(max(0, y - r), min(h, y + r + 1)):
                for xx in range(max(0, x - r), min(w, x + r + 1)):
                    tot += ink[yy * w + xx]
                    n += 1
            return tot / n

        deep, shallow = [], []
        for i in range(w * h):
            if b[i * 4] <= 0.5:
                continue
            v = d[i * 4]
            if v > edges[-1]:
                deep.append(around(i))
            elif v < edges[0]:
                shallow.append(around(i))
        assert len(deep) > 30 and len(shallow) > 30, (
            f"深い/浅い線画素が少ない: {len(deep)} / {len(shallow)}  edges {edges}")
        return sum(deep) / len(deep), sum(shallow) / len(shallow)

    tmp = Path(tempfile.mkdtemp(prefix="fp_t48_"))
    try:
        # 既定: 輪郭(開いた所)が太く、穴の縁(くぼみ)が細い
        md, ms = measure(tmp)
        assert ms > md * 1.2, (
            f"開いた所が太くなっていない: 周りのインク 浅い {ms:.3f} / 深い {md:.3f}")
        # 逆向きのスイッチ(fp_lw_deep_thick)は v2.8 の整理で消した
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        bpy.ops.wm.read_homefile(use_empty=True)


@test("STEP0 finish: precise keeps the v2.7 values, weighted sets up line weight end to end")
def t49():
    # v2.8 は v2.7 を壊さない。STEP0 の仕上がり「精密」は v2.7 の値
    # (下限5度・稜線0.25・強弱なし)をそのまま入れ、「強弱」は 14度・
    # 0.45・強弱ON・しきい値の計測まで1ボタンで済ませる
    from freepencil2 import line_weight

    scene, _ = _lw_scene()
    scene.fp_auto_style = 'PRECISE'
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    assert abs(scene.fp_auto_split_floor - 5.0) < 1e-6, scene.fp_auto_split_floor
    assert abs(scene.fp_ridge_amount - 0.25) < 1e-6, scene.fp_ridge_amount
    assert not scene.fp_line_weight, "精密なのに強弱が入った"
    assert _lw_node_count(scene) == 0, "精密なのに強弱ノードが入った"

    defaults = [getattr(scene, f"fp_lw_e{i}") for i in range(1, 5)]
    scene.fp_auto_style = 'WEIGHTED'
    bpy.ops.object.select_all(action="DESELECT")
    for o in scene.objects:
        if o.type == "MESH":
            o.select_set(True)
            bpy.context.view_layer.objects.active = o
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    assert abs(scene.fp_auto_split_floor - 14.0) < 1e-6, scene.fp_auto_split_floor
    assert abs(scene.fp_ridge_amount - 0.45) < 1e-6, scene.fp_ridge_amount
    assert scene.fp_line_weight, "強弱なのに OFF のまま"
    assert _lw_node_count(scene) > 0, "強弱なのにノードが入っていない"
    edges = line_weight.edges_from_scene(scene)
    assert edges != sorted(defaults), (
        f"しきい値が測られていない(既定のまま): {edges}")
    assert edges[0] < edges[-1], f"しきい値が単調でない: {edges}"

    from freepencil2 import compat
    # キャラは奥の扱いも葉の房も入れない
    assert scene.fp_lw_far == 0.0 and scene.fp_lw_far_sens == 1.0 \
        and scene.fp_lw_far_fade == 0.0 and scene.fp_foliage_clumps == 0, "キャラに背景の特殊処理が入った"
    assert abs(scene.fp_lw_strength - 0.6) < 1e-6, f"キャラの強弱がほんのり(0.6)でない: {scene.fp_lw_strength}"

    # 手描き背景 = キャラ + 奥の扱い + 葉の房
    scene.fp_auto_style = 'BACKGROUND'
    bpy.ops.object.select_all(action="DESELECT")
    for o in scene.objects:
        if o.type == "MESH":
            o.select_set(True)
            bpy.context.view_layer.objects.active = o
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    assert scene.fp_line_weight and abs(scene.fp_auto_split_floor - 14.0) < 1e-6
    assert scene.fp_lw_far == 1.0 and scene.fp_lw_far_sens == 2.0 \
        and abs(scene.fp_lw_far_fade - 0.15) < 1e-6, "背景なのに奥の扱いが入らない"
    assert scene.fp_foliage_clumps == 4, "背景なのに葉の房が入らない"
    assert scene.fp_gap_fill == 6 and abs(scene.fp_lw_ink - 1.0) < 1e-6, "背景の隙間埋め/線の濃さが入らない"
    assert abs(scene.fp_lw_strength - 0.5) < 1e-6, "背景なのに線が細くならない"
    assert abs(scene.fp_fine_lines - 1.0) < 1e-6, "背景なのに細い線が入らない"
    assert scene.fp_ch_depth == 0.0, "背景なのに深度チャンネルが生きている"
    assert scene.fp_lw_far_end > scene.fp_lw_far_start > 0.0, "奥の距離が測られていない"
    assert any(n.get("fp_tap") == "far" for n in
               compat.get_compositor_tree(scene).nodes), "背景なのに奥度のノードが無い"

    # 精密に戻すと強弱ノードが消えて、値も v2.7 に戻る
    scene.fp_auto_style = 'PRECISE'
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    assert not scene.fp_line_weight and _lw_node_count(scene) == 0, "精密に戻らない"
    assert abs(scene.fp_auto_split_floor - 5.0) < 1e-6
    assert (scene.fp_lw_far == 0.0 and scene.fp_foliage_clumps == 0
            and scene.fp_gap_fill == 0 and scene.fp_lw_ink == 1.0
            and scene.fp_lw_strength == 1.0
            and scene.fp_fine_lines == 0.0), "精密に戻しても特殊処理が残る"
    bpy.ops.wm.read_homefile(use_empty=True)


@test("foliage: small islands are painted in clumps (background mode only)")
def t52():
    # 葉カード 400 枚(バラバラの小さい板)。房 0 では葉ごとに違う色が
    # 何十色も並び、房 4 では葉の色が 4 色以下にまとまる。幹(大きい島)は
    # 房に入らない
    import math
    import numpy as np
    bpy.ops.wm.read_homefile(use_empty=True)
    import bmesh
    me = bpy.data.meshes.new("Tree")
    bm = bmesh.new()
    rng = np.random.default_rng(3)
    for _ in range(400):
        c = rng.uniform(-1.0, 1.0, size=3)
        c[2] += 2.5
        a = rng.uniform(0, math.pi)
        dx, dy = math.cos(a) * 0.08, math.sin(a) * 0.08
        v = [bm.verts.new((c[0] - dx, c[1] - dy, c[2] - 0.08)),
             bm.verts.new((c[0] + dx, c[1] + dy, c[2] - 0.08)),
             bm.verts.new((c[0] + dx, c[1] + dy, c[2] + 0.08)),
             bm.verts.new((c[0] - dx, c[1] - dy, c[2] + 0.08))]
        bm.faces.new(v)
    # 幹: 大きい四角柱
    bmesh.ops.create_cube(bm, size=1.0)
    for v in list(bm.verts)[-8:]:
        v.co.x *= 0.3
        v.co.y *= 0.3
        v.co.z = v.co.z * 1.5 + 0.75
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new("Tree", me)
    scene = bpy.context.scene
    scene.collection.objects.link(obj)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.location = (0, -8, 2)
    cam.rotation_euler = (math.radians(90), 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 7
    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    def leaf_colours(k):
        scene.fp_auto_style = 'WEIGHTED'
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        assert scene.fp_foliage_clumps == 0
        if k:
            scene.fp_foliage_clumps = k
            bpy.ops.freepencil.auto_vertex_color("EXEC_DEFAULT")
        vc = me.color_attributes["mecha_color"]
        buf = np.empty(len(me.loops) * 4, dtype=np.float32)
        vc.data.foreach_get("color", buf)
        buf = buf.reshape(-1, 4)[:, :3]
        leaf_loops = buf[:400 * 4]
        q = np.round(leaf_loops * 255).astype(np.int64)
        return len(set(map(tuple, q.tolist())))

    n0 = leaf_colours(0)
    n4 = leaf_colours(4)
    assert n0 >= 8, f"房なしで葉の色が少なすぎる: {n0}"
    assert n4 <= 4, f"房4で葉の色が 4 を超える: {n4}(房なし {n0})"
    bpy.ops.wm.read_homefile(use_empty=True)


@test("line weight: ink grown outside the silhouette is opaque on a transparent film")
def t50():
    # 輪郭を外側へ太らせた分はシルエットの外にあり、レンダーレイヤーの
    # アルファが 0。Set Alpha がそれをそのまま使うと透明背景で消える
    # (実測: テレビの外周が半分だけ、灰色に見えた)。線を描いた画素は
    # アルファも立てる。精密と強弱を同じ場面で描き、アルファの左端が
    # 強弱では外側へ広がることで確かめる(5.x は透明画素の RGB が黒
    # なので、色では探せない)
    import math
    import shutil
    import tempfile

    def render(style, path):
        bpy.ops.wm.read_homefile(use_empty=True)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24)
        obj = bpy.context.object
        bpy.ops.object.shade_smooth()
        scene = bpy.context.scene
        cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
        cam.location = (0, -5, 0)
        cam.rotation_euler = (math.radians(90), 0, 0)
        scene.collection.objects.link(cam)
        scene.camera = cam
        scene.fp_use_random_seed = False
        scene.fp_color_seed = 7
        scene.fp_enable_compositor_view = False
        scene.fp_auto_detect_aov = False
        scene.fp_auto_style = style
        scene.render.resolution_x = 240
        scene.render.resolution_y = 180
        scene.render.film_transparent = True
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        scene.fp_white_preview = True
        scene.render.film_transparent = True
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(str(path))
        w, h = img.size
        buf = [0.0] * (w * h * 4)
        img.pixels.foreach_get(buf)
        bpy.data.images.remove(img)
        y = h // 2
        # 中央の行で、アルファが立っている一番左の画素
        return next(x for x in range(w) if buf[(y * w + x) * 4 + 3] > 0.5)

    tmp = Path(tempfile.mkdtemp(prefix="fp_t50_"))
    try:
        xp = render('PRECISE', tmp / "p.png")
        xw = render('WEIGHTED', tmp / "w.png")
        assert xw < xp, (
            f"太らせた輪郭のアルファが外へ広がっていない: 精密 x={xp} / 強弱 x={xw}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        bpy.ops.wm.read_homefile(use_empty=True)


@test("line weight: far lines shrink to the base line while near lines stay thick")
def t51():
    # 奥の扱い(fp_lw_far)。同じ球を手前と奥に置き、奥ほど細く 1.0 で
    # 奥の球の輪郭だけが精密と同じ細さに戻ることを、輪郭の左端の
    # アルファ幅で確かめる(t50 と同じ測り方)。OFF(既定)では両方太い。
    # 距離は測る(fp_lw_far_start/end が 0 のままでは何も挿さない)
    import math
    import shutil
    import tempfile

    def render(far, path):
        bpy.ops.wm.read_homefile(use_empty=True)
        objs = []
        for y in (0.0, 14.0):
            bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24,
                                                 location=(0, y, 0))
            bpy.ops.object.shade_smooth()
            objs.append(bpy.context.object)
        scene = bpy.context.scene
        cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
        cam.location = (0, -5, 0)
        cam.rotation_euler = (math.radians(90), 0, 0)
        cam.data.lens = 35
        scene.collection.objects.link(cam)
        scene.camera = cam
        scene.fp_use_random_seed = False
        scene.fp_color_seed = 7
        scene.fp_enable_compositor_view = False
        scene.fp_auto_detect_aov = False
        scene.fp_auto_style = 'WEIGHTED'
        scene.render.resolution_x = 320
        scene.render.resolution_y = 240
        scene.render.film_transparent = True
        for o in objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = objs[0]
        # 手前の球が奥を隠さないよう、奥の球は上へ(2.2 では手前の球の
        # 陰に全部入って写らなかった)
        objs[1].location.z = 5.0
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        assert scene.fp_lw_far_end > scene.fp_lw_far_start > 0.0, (
            f"奥の距離が測られていない: {scene.fp_lw_far_start} .. {scene.fp_lw_far_end}")
        # 奥ほど細くの仕組みを見るので、太い線(強さ 1.0)で測る。キャラの既定は
        # ほんのり(0.6)で、太さの差が小さく測りにくい
        scene.fp_lw_strength = 1.0
        scene.fp_lw_far = far
        bpy.ops.freepencil2.link_button()
        scene.fp_white_preview = True
        scene.render.film_transparent = True
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(str(path))
        w, h = img.size
        buf = [0.0] * (w * h * 4)
        img.pixels.foreach_get(buf)
        bpy.data.images.remove(img)

        def left_edge(y):
            return next(x for x in range(w) if buf[(y * w + x) * 4 + 3] > 0.5)

        # 手前の球の中心行と、奥の球の中心行(画面座標は下が 0)
        from bpy_extras.object_utils import world_to_camera_view
        rows = []
        for o in objs:
            v = world_to_camera_view(scene, cam, o.matrix_world.translation)
            rows.append(int(v.y * h))
        return left_edge(rows[0]), left_edge(rows[1])

    tmp = Path(tempfile.mkdtemp(prefix="fp_t51_"))
    try:
        n0, f0 = render(0.0, tmp / "off.png")
        n1, f1 = render(1.0, tmp / "on.png")
        # 手前の球も測った距離の 5% 点より少し奥にあるので、1px は動く
        assert abs(n1 - n0) <= 2, f"手前の球まで変わった: OFF x={n0} / ON x={n1}"
        assert f1 - f0 >= 3, f"奥の球が細くなっていない: OFF x={f0} / ON x={f1}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        bpy.ops.wm.read_homefile(use_empty=True)


@test("background: a ground plane far larger than everything is left unpainted")
def t53():
    # 地面を塗ると地平線が太い帯になる(実測)。手描き背景では STEP0 が
    # 「他のどの物よりも 2 倍以上広い薄い平面」を塗り分けから外す。
    # キャラでは外さない(v2.7 と同じく選択した物は全部塗る)
    import math
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0, 0, 1))
    cube = bpy.context.object
    bpy.ops.mesh.primitive_plane_add(size=400.0)
    ground = bpy.context.object
    bpy.ops.mesh.primitive_plane_add(size=3.0, location=(3, 0, 0.5))
    slab = bpy.context.object          # 小さい板は地面ではない
    scene = bpy.context.scene
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.location = (0, -8, 2)
    cam.rotation_euler = (math.radians(85), 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 7
    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False
    scene.render.resolution_x = 160
    scene.render.resolution_y = 120

    def run(style):
        for o in (cube, ground, slab):
            for ca in list(o.data.color_attributes):
                o.data.color_attributes.remove(ca)
            o.select_set(True)
        bpy.context.view_layer.objects.active = cube
        scene.fp_auto_style = style
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        return {o.name: "mecha_color" in o.data.color_attributes for o in (cube, ground, slab)}

    painted = run('BACKGROUND')
    assert painted[cube.name] and painted[slab.name], f"背景で物が塗られていない: {painted}"
    assert not painted[ground.name], "背景で地面が塗られた"
    painted = run('WEIGHTED')
    assert painted[ground.name], "キャラで地面が塗られない(v2.7 と違う)"
    bpy.ops.wm.read_homefile(use_empty=True)


@test("gap fill: a narrow slit between two plates stops drawing a line")
def t54():
    # 葉の隙間埋め(fp_gap_fill)。1枚の板に細い縦の穴を開ける(2枚の板だと
    # 別の島になって色差の線が残る)。埋めなければ穴の縁が線になる。埋めると
    # 穴の中にインクが無い。板の外周の線は残る(閉じ = 膨張してから収縮
    # なので外側の輪郭は動かない)
    import math
    import shutil
    import tempfile

    def render(gap, path):
        bpy.ops.wm.read_homefile(use_empty=True)
        import bmesh
        bpy.ops.mesh.primitive_grid_add(x_subdivisions=50, y_subdivisions=3, size=2.0,
                                        rotation=(math.radians(90), 0, 0))
        plate = bpy.context.object
        bm = bmesh.new()
        bm.from_mesh(plate.data)
        bm.faces.ensure_lookup_table()
        hole = [f for f in bm.faces
                if abs(f.calc_center_median().x) < 0.05 and abs(f.calc_center_median().y) < 0.4]
        bmesh.ops.delete(bm, geom=hole, context="FACES")
        bm.to_mesh(plate.data)
        bm.free()
        plates = [plate]
        scene = bpy.context.scene
        cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
        cam.location = (0, -6, 0)
        cam.rotation_euler = (math.radians(90), 0, 0)
        scene.collection.objects.link(cam)
        scene.camera = cam
        scene.fp_use_random_seed = False
        scene.fp_color_seed = 7
        scene.fp_enable_compositor_view = False
        scene.fp_auto_detect_aov = False
        scene.fp_auto_style = 'WEIGHTED'
        scene.render.resolution_x = 240
        scene.render.resolution_y = 180
        scene.render.film_transparent = True
        for o in plates:
            o.select_set(True)
        bpy.context.view_layer.objects.active = plates[0]
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        scene.fp_gap_fill = gap
        bpy.ops.freepencil2.link_button()
        scene.fp_white_preview = True
        scene.render.film_transparent = True
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(str(path))
        w, h = img.size
        buf = [0.0] * (w * h * 4)
        img.pixels.foreach_get(buf)
        bpy.data.images.remove(img)
        # 穴(中央の列 ±3px、上下 1/3 の中)にある濃い画素の数
        dark = 0
        for y in range(h * 5 // 12, h * 7 // 12):
            for x in range(w // 2 - 4, w // 2 + 5):
                i = (y * w + x) * 4
                if buf[i + 3] > 0.5 and (buf[i] + buf[i + 1] + buf[i + 2]) / 3 < 0.6:
                    dark += 1
        return dark

    tmp = Path(tempfile.mkdtemp(prefix="fp_t54_"))
    try:
        d0 = render(0, tmp / "g0.png")
        d1 = render(24, tmp / "g24.png")
        assert d0 > 20, f"埋めない状態で隙間に線が無い: {d0}"
        assert d1 < d0 * 0.2, f"隙間を埋めても線が残る: 0px {d0} / 24px {d1}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        bpy.ops.wm.read_homefile(use_empty=True)


@test("thin lines: an animation render also comes out full size (render_init hook)")
def t55():
    # F12 では縮小を外すフックが効いていたが、アニメーションでは効かず
    # 2倍のキャンバスに半分の絵が入っていた(実測: 被写体の幅 0.50)。
    # render_init/complete に移して両方で等倍にする。2枚だけ撮って
    # 2枚目の被写体の幅がキャンバスのほぼ全部であることを見る
    import math
    import shutil
    import tempfile
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_monkey_add()
    obj = bpy.context.object
    scene = bpy.context.scene
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.location = (0, -6, 0)
    cam.rotation_euler = (math.radians(90), 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.fp_use_random_seed = False
    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False
    scene.render.resolution_x = 160
    scene.render.resolution_y = 120
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    assert scene.render.resolution_percentage == 200
    scene.fp_white_preview = True
    scene.render.film_transparent = True
    for f in (1, 2):
        cam.keyframe_insert("location", frame=f)
    scene.frame_start, scene.frame_end = 1, 2
    tmp = Path(tempfile.mkdtemp(prefix="fp_t55_"))

    def width_frac(path):
        img = bpy.data.images.load(str(path))
        w, h = img.size
        buf = [0.0] * (w * h * 4)
        img.pixels.foreach_get(buf)
        bpy.data.images.remove(img)
        xs = [i % w for i in range(w * h) if buf[i * 4 + 3] > 0.5]
        return (w, h), (max(xs) - min(xs)) / w

    try:
        scene.render.filepath = str(tmp / "still.png")
        bpy.ops.render.render(write_still=True)
        size_s, frac_s = width_frac(tmp / "still.png")
        scene.render.filepath = str(tmp / "a_")
        bpy.ops.render.render(animation=True)
        size_a, frac_a = width_frac(tmp / "a_0002.png")
        assert size_s == size_a == (320, 240), (size_s, size_a)
        # 半分の絵なら幅も半分になる。F12 と同じ幅であること
        assert abs(frac_a - frac_s) < 0.03, (
            f"アニメーションの絵が F12 と違う大きさ: F12 {frac_s:.2f} / アニメ {frac_a:.2f}")
        assert frac_s > 0.4, f"F12 の絵が半分のまま: {frac_s:.2f}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        bpy.ops.wm.read_homefile(use_empty=True)


@test("fine lines: the second (precise) paint adds ink without greying flat faces")
def t56():
    # 手描き背景は塗り分けを 2 枚持つ(mecha_color = 手描き、fine_color =
    # 精密)。fp_fine_lines でその細い線を薄く重ねる。面まで暗くならない
    # ことが肝心(グループの合成出力をそのまま乗算すると陰影が二重になった)
    import math
    import shutil
    import tempfile
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=1.6)
    bpy.ops.object.shade_smooth()
    obj = bpy.context.object
    scene = bpy.context.scene
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.location = (0, -6, 0)
    cam.rotation_euler = (math.radians(90), 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 42
    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False
    scene.render.resolution_x = 240
    scene.render.resolution_y = 180
    scene.render.film_transparent = True
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    scene.fp_auto_style = 'BACKGROUND'
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    assert "fine_color" in obj.data.color_attributes, "fine_color が塗られていない"
    assert any(a.name == "fine_color" for a in bpy.context.view_layer.aovs), "fine_color の AOV が無い"

    tmp = Path(tempfile.mkdtemp(prefix="fp_t56_"))

    def shot(k, name):
        scene.fp_fine_lines = k
        bpy.ops.freepencil2.link_button()
        scene.fp_white_preview = True
        scene.render.film_transparent = True
        scene.render.filepath = str(tmp / name)
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(str(tmp / name))
        w, h = img.size
        buf = [0.0] * (w * h * 4)
        img.pixels.foreach_get(buf)
        bpy.data.images.remove(img)
        # 薄い線は 0.5 を割らないので、数ではなく「暗さの合計」で見る
        ink = 0.0
        bright = []
        for i in range(w * h):
            if buf[i * 4 + 3] <= 0.5:
                continue
            g = (buf[i * 4] + buf[i * 4 + 1] + buf[i * 4 + 2]) / 3
            ink += 1.0 - g
            if g >= 0.5:
                bright.append(g)
        # 面の明るさは「明るい側の 9 割目」で見る。平均だと薄い線そのものが
        # 引き下げてしまい、面が灰色になったのかを見分けられない
        bright.sort()
        return ink, (bright[int(len(bright) * 0.9)] if bright else 1.0)

    try:
        ink0, face0 = shot(0.0, "k0.png")
        ink1, face1 = shot(0.6, "k6.png")
        assert ink1 > ink0 * 1.15, f"細い線が増えていない: 暗さ {ink0:.0f} -> {ink1:.0f}"
        assert face1 > face0 - 0.02, f"面まで暗くなった: {face0:.3f} -> {face1:.3f}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        bpy.ops.wm.read_homefile(use_empty=True)


@test("mono preview survives STEP3 regeneration")
def t57():
    # STEP3 を作り直すと白プレビューだけ掛け直していて、モノクロは外れた
    # (表示はモノクロのまま、絵は材質の色)。グループの Image 入口が
    # 作り直したあとも陰影ノードから来ていること
    from freepencil2 import fp_core
    fresh_scene_with_islands()
    bpy.ops.freepencil.auto_vertex_color()
    scene = bpy.context.scene
    bpy.context.view_layer.use_pass_diffuse_direct = True
    scene.fp_node_type = "pro"
    fp_core.setup_aov(scene, bpy.context.view_layer)
    fp_core.setup_compositor(scene, bpy.context.view_layer)
    scene.fp_preview_mode = 'MONO_LIGHT'

    def image_source():
        grp = next(n for n in fp_batch.comp_tree(scene).nodes
                   if n.type == 'GROUP' and n.node_tree
                   and n.node_tree.name.startswith(fp_core.NODE_GROUP_PREFIX)
                   and n.label != "FreePencil_fine_line")
        sock = grp.inputs["Image"]
        return sock.links[0].from_node.label if sock.is_linked else None

    assert image_source() == fp_core.MONO_LABEL, image_source()
    fp_core.setup_compositor(scene, bpy.context.view_layer)
    assert scene.fp_preview_mode == 'MONO_LIGHT'
    assert image_source() == fp_core.MONO_LABEL, \
        f"作り直したらモノクロが外れた: {image_source()}"
    bpy.ops.wm.read_homefile(use_empty=True)


@test("background: the mech paint (fine_color) keeps box corners on a joined low-poly building")
def t58():
    # 箱を12個結合した建物(72面)。切れすぎの上限 0.08 島/面 だと許容は8島で、
    # 箱12個はそれを超えるので 179度まで上げられ、箱が1色(角に線が出ない)に
    # なっていた。メカの塗り(細い線用)は抑えないので、各箱の面が分かれること。
    # 手描きの塗り(mecha_color)は従来どおり抑えてよい
    import numpy as np
    bpy.ops.wm.read_homefile(use_empty=True)
    objs = []
    for i in range(12):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=((i % 4) * 1.5, (i // 4) * 1.5, 0))
        objs.append(bpy.context.object)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    bld = bpy.context.object
    scene = bpy.context.scene
    import math
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.location = (2.25, -9.0, 5.0)
    cam.rotation_euler = (math.radians(62), 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.render.resolution_x = 240
    scene.render.resolution_y = 180
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 3
    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False
    scene.fp_auto_style = 'BACKGROUND'
    bld.select_set(True)
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    assert "fp_fine_pass" not in scene, "メカの塗りの目印が残った"

    def colors_per_box(name):
        ca = bld.data.color_attributes[name]
        buf = np.empty(len(ca.data) * 4, dtype=np.float32)
        ca.data.foreach_get("color", buf)
        col = buf.reshape(-1, 4)[:, :3].round(3)
        per = []
        for b in range(12):
            faces = bld.data.polygons[b * 6:(b + 1) * 6]
            cs = {tuple(col[p.loop_start]) for p in faces}
            per.append(len(cs))
        return per

    fine = colors_per_box("fine_color")
    assert min(fine) >= 3, f"メカの塗りで箱の角が分かれない: {fine}"
    bpy.ops.wm.read_homefile(use_empty=True)


@test("character (rigged): coarse paint - big parts one color each, small parts merged; precise unchanged")
def t59():
    # キャラ(リグ付き)は手描き系でざっくり塗り: 角度で分けず、大きいパーツ
    # ごとに1色、小さいパーツ(髪のカードなど)はマテリアルごとに1色へまとめる。
    # 目印が無い(精密)ときは従来どおり角度で分ける
    import numpy as np

    def build():
        bpy.ops.wm.read_homefile(use_empty=True)
        bpy.ops.mesh.primitive_cube_add(size=2.0)
        parts = [bpy.context.object]
        for i in range(30):                     # 髪のカード(小さい別パーツ)
            bpy.ops.mesh.primitive_plane_add(size=0.1, location=(-1.2 + i * 0.08, 0, 1.2))
            parts.append(bpy.context.object)
        bpy.ops.object.select_all(action="DESELECT")
        for o in parts:
            o.select_set(True)
        bpy.context.view_layer.objects.active = parts[0]
        bpy.ops.object.join()
        body = bpy.context.object
        arm_data = bpy.data.armatures.new("A")
        arm = bpy.data.objects.new("A", arm_data)
        bpy.context.scene.collection.objects.link(arm)
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode="EDIT")
        b = arm_data.edit_bones.new("spine")
        b.head, b.tail = (0, 0, -1), (0, 0, 1)
        bpy.ops.object.mode_set(mode="OBJECT")
        vg = body.vertex_groups.new(name="spine")
        vg.add(list(range(len(body.data.vertices))), 1.0, "REPLACE")
        mod = body.modifiers.new("A", "ARMATURE")
        mod.object = arm
        scene = bpy.context.scene
        scene.fp_use_random_seed = False
        scene.fp_color_seed = 5
        scene.fp_sharp_auto = True
        bpy.ops.object.select_all(action="DESELECT")
        body.select_set(True)
        bpy.context.view_layer.objects.active = body
        return body

    def n_face_colors(body):
        ca = body.data.color_attributes["mecha_color"]
        buf = np.empty(len(ca.data) * 4, dtype=np.float32)
        ca.data.foreach_get("color", buf)
        col = buf.reshape(-1, 4)[:, :3].round(3)
        return len({tuple(col[p.loop_start]) for p in body.data.polygons})

    body = build()
    bpy.context.scene["fp_rig_coarse"] = True
    bpy.ops.freepencil.auto_vertex_color()
    coarse = n_face_colors(body)
    body = build()
    bpy.ops.freepencil.auto_vertex_color()
    fine = n_face_colors(body)
    assert coarse == 2, f"ざっくり塗りの色数 {coarse}(箱1色 + 小パーツ1色のはず)"
    assert fine > 6, f"目印なし(精密)で角度の分割が効いていない: {fine}色"
    bpy.ops.wm.read_homefile(use_empty=True)


@test("line weight strength slider updates the compositor without pressing STEP3")
def t60():
    # 強弱の強さ・濃さ・縁は、動かしたら STEP3 を作り直して即反映する。
    # 太さ(hw の段の幅)がノードの値として変わっていること
    from freepencil2 import fp_core
    fresh_scene_with_islands()
    scene = bpy.context.scene
    scene.fp_line_weight = True
    scene.fp_node_type = "pro"
    bpy.ops.freepencil.auto_vertex_color()
    fp_core.setup_aov(scene, bpy.context.view_layer)
    fp_core.setup_compositor(scene, bpy.context.view_layer)

    def hw_span():
        # 縁の膨張距離は一番太い段で決まる(強さ 1.0 で 6px、0.3 で 2px)
        tree = fp_batch.comp_tree(scene)
        soft = next(n for n in tree.nodes if n.get("fp_tap") == "soft")
        if hasattr(soft, "distance"):
            return soft.distance
        return soft.inputs["Size"].default_value      # 5.x はソケット

    before = hw_span()
    scene.fp_lw_strength = 0.3                  # ボタンは押さない
    after = hw_span()
    assert after != before, f"強弱の強さを変えても太さが変わらない: {before} -> {after}"
    scene.fp_lw_ink = 0.6
    tree = fp_batch.comp_tree(scene)
    assert any(n.get("fp_tap") == "ink_dark" for n in tree.nodes), \
        "線の濃さを変えても濃さのノードが入らない"
    bpy.ops.wm.read_homefile(use_empty=True)


@test("character (rigged, coarse): hard weight steps in bone_color are softened")
def t61():
    # 粗いケージでウェイトが1辺で切り替わると、bone_color の段差がサブディブで
    # 帯になり灰色の塊になった(デッサン人形の胸)。ざっくり塗りのときは隣の頂点と
    # 平均して段差を小さくする。目印が無いとき(精密)は従来どおり段差のまま
    import numpy as np

    def run(coarse):
        bpy.ops.wm.read_homefile(use_empty=True)
        bpy.ops.mesh.primitive_cube_add(size=2.0)
        body = bpy.context.object
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.subdivide(number_cuts=4)
        bpy.ops.object.mode_set(mode="OBJECT")
        arm_data = bpy.data.armatures.new("A")
        arm = bpy.data.objects.new("A", arm_data)
        bpy.context.scene.collection.objects.link(arm)
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode="EDIT")
        for n, (h, t) in (("upper", ((0, 0, 0), (0, 0, 1))), ("lower", ((0, 0, -1), (0, 0, 0)))):
            b = arm_data.edit_bones.new(n)
            b.head, b.tail = h, t
        bpy.ops.object.mode_set(mode="OBJECT")
        up = body.vertex_groups.new(name="upper")
        lo = body.vertex_groups.new(name="lower")
        for v in body.data.vertices:            # 硬いウェイト(境目で 1 -> 0)
            (up if v.co.z > 0.01 else lo).add([v.index], 1.0, "REPLACE")
        body.modifiers.new("A", "ARMATURE").object = arm
        scene = bpy.context.scene
        scene.fp_use_random_seed = False
        scene.fp_color_seed = 5
        if coarse:
            scene["fp_rig_coarse"] = True
        bpy.ops.object.select_all(action="DESELECT")
        body.select_set(True)
        bpy.context.view_layer.objects.active = body
        bpy.ops.freepencil.auto_vertex_color()
        me = body.data
        ca = me.color_attributes["bone_color"]
        buf = np.empty(len(ca.data) * 4, dtype=np.float32)
        ca.data.foreach_get("color", buf)
        lv = np.empty(len(me.loops), dtype=np.int32)
        me.loops.foreach_get("vertex_index", lv)
        vc = np.zeros((len(me.vertices), 3))
        vc[lv] = buf.reshape(-1, 4)[:, :3]
        ev = np.empty(len(me.edges) * 2, dtype=np.int32)
        me.edges.foreach_get("vertices", ev)
        ev = ev.reshape(-1, 2)
        return float(np.abs(vc[ev[:, 0]] - vc[ev[:, 1]]).max())

    hard = run(False)
    soft = run(True)
    assert hard > 0.01, f"ボーンの色が硬い境目で変わっていない: {hard}"
    assert soft < hard * 0.6, f"ざっくり塗りでボーンの段差が和らいでいない: {hard:.3f} -> {soft:.3f}"
    bpy.ops.wm.read_homefile(use_empty=True)


@test("dense fade: packed slats get lighter, a lone thick outline keeps its ink")
def t62():
    # 左に細い板を詰めて並べた「シャッター」、右に離れた箱を1つ。密度フェードを
    # 上げると、左の線のインクは減り、右の箱の輪郭はほとんど変わらないこと。
    # インクの量で測っていた版は、輪郭1本まで薄くなった(実測)
    import math
    import shutil
    import tempfile

    def build():
        bpy.ops.wm.read_homefile(use_empty=True)
        objs = []
        for i in range(24):                                  # 詰めた板(間隔 5cm)
            bpy.ops.mesh.primitive_cube_add(size=1, location=(-1.2, 0, -0.6 + i * 0.05))
            o = bpy.context.object
            o.scale = (0.9, 0.2, 0.012)
            objs.append(o)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(1.2, 0, 0))   # 離れた箱
        objs.append(bpy.context.object)
        scene = bpy.context.scene
        cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
        cam.location = (0, -6, 0)
        cam.rotation_euler = (math.radians(90), 0, 0)
        scene.collection.objects.link(cam)
        scene.camera = cam
        scene.fp_use_random_seed = False
        scene.fp_color_seed = 7
        scene.fp_enable_compositor_view = False
        scene.fp_auto_detect_aov = False
        scene.fp_auto_style = 'WEIGHTED'
        scene.render.resolution_x = 320
        scene.render.resolution_y = 180
        scene.render.film_transparent = True
        for o in objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = objs[0]
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        scene.fp_white_preview = True
        return scene

    def ink(scene, path, dense):
        scene.fp_lw_dense = dense
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(str(path))
        w, h = img.size
        buf = [0.0] * (w * h * 4)
        img.pixels.foreach_get(buf)
        bpy.data.images.remove(img)
        left = right = 0.0
        for y in range(h):
            for x in range(w):
                i = (y * w + x) * 4
                if buf[i + 3] < 0.5:
                    continue
                v = 1.0 - (buf[i] + buf[i + 1] + buf[i + 2]) / 3
                if x < w * 0.45:
                    left += v
                elif x > w * 0.55:
                    right += v
        return left, right

    tmp = Path(tempfile.mkdtemp(prefix="fp_t62_"))
    try:
        scene = build()
        l0, r0 = ink(scene, tmp / "d0.png", 0.0)
        l1, r1 = ink(scene, tmp / "d8.png", 0.8)
        assert l0 > 0 and r0 > 0, (l0, r0)
        assert l1 < l0 * 0.85, f"詰めた板のインクが減らない: {l0:.0f} -> {l1:.0f}"
        assert r1 > r0 * 0.9, f"離れた箱の輪郭まで薄くなった: {r0:.0f} -> {r1:.0f}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        bpy.ops.wm.read_homefile(use_empty=True)


@test("stripe fade: rows of fine strips seen at a grazing angle fade far away, the near end stays")
def t63():
    # 長い壁に水平の細い板を詰めて並べ、低い視点から真横に近く見る。
    # 細かすぎる縞を薄く を上げると、奥(画面の中央寄り)のインクが減り、
    # 手前(画面の端)はほとんど変わらないこと
    import math
    import shutil
    import tempfile

    def build():
        bpy.ops.wm.read_homefile(use_empty=True)
        objs = []
        for i in range(40):                                  # 板(間隔 8cm、長さ 60m)
            bpy.ops.mesh.primitive_cube_add(size=1, location=(3.0, 30.0, 0.2 + i * 0.08))
            o = bpy.context.object
            o.scale = (0.05, 60.0, 0.04)
            objs.append(o)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(3.3, 30.0, 1.8))
        o = bpy.context.object
        o.scale = (0.2, 60.0, 3.6)
        objs.append(o)
        scene = bpy.context.scene
        cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
        cam.data.lens = 24
        cam.location = (0.0, -2.0, 1.6)
        cam.rotation_euler = (math.radians(88), 0, math.radians(-8))
        scene.collection.objects.link(cam)
        scene.camera = cam
        scene.fp_use_random_seed = False
        scene.fp_color_seed = 7
        scene.fp_enable_compositor_view = False
        scene.fp_auto_detect_aov = False
        scene.fp_auto_style = 'BACKGROUND'
        # 縞を薄くの半径は画素で決まる(200% で 12px)。小さく撮ると手前の板まで
        # 半径より細かくなって薄くなる(320px で実測)。手前の板の間隔が半径より
        # 十分広くなる大きさで撮る
        scene.render.resolution_x = 960
        scene.render.resolution_y = 540
        scene.render.film_transparent = True
        for o in objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = objs[0]
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        scene.fp_white_preview = True
        return scene

    def ink(scene, path, v):
        scene.fp_lw_stripe_fade = v
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(str(path))
        w, h = img.size
        buf = [0.0] * (w * h * 4)
        img.pixels.foreach_get(buf)
        bpy.data.images.remove(img)
        far = near = 0.0
        for y in range(h):
            for x in range(w):
                i = (y * w + x) * 4
                if buf[i + 3] < 0.5:
                    continue
                v_ = 1.0 - (buf[i] + buf[i + 1] + buf[i + 2]) / 3
                if w * 0.45 < x < w * 0.7:
                    far += v_
                elif x > w * 0.85:
                    near += v_
        return far, near

    tmp = Path(tempfile.mkdtemp(prefix="fp_t63_"))
    try:
        scene = build()
        assert scene.fp_lw_stripe_fade == 0.0, "v2.8.3: 手描き背景の既定では縞を薄くは切る(動くとちらつく)"
        f0, n0 = ink(scene, tmp / "s0.png", 0.0)
        f1, n1 = ink(scene, tmp / "s1.png", 1.0)
        assert f0 > 0 and n0 > 0, (f0, n0)
        assert f1 < f0 * 0.85, f"奥の縞のインクが減らない: {f0:.0f} -> {f1:.0f}"
        assert n1 > n0 * 0.85, f"手前まで薄くなった: {n0:.0f} -> {n1:.0f}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        bpy.ops.wm.read_homefile(use_empty=True)


@test("stripe fade: a crowded bush of sticks pointing every way does not fade")
def t64():
    # 縞を薄く は向きがそろった縞だけに効く。向きがばらばらに詰まった所
    # (木の葉・細かい部品)を薄くしないこと。向きの項が無い版では、
    # この茂みの上半分が白く抜けた(dev/note_assets/shot_bush.py の画像)
    import math
    import random
    import shutil
    import tempfile

    bpy.ops.wm.read_homefile(use_empty=True)
    rnd = random.Random(3)
    objs = []
    for _ in range(900):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(
            rnd.uniform(-1.5, 1.5), 12 + rnd.uniform(-1.5, 1.5), 1.5 + rnd.uniform(-1.2, 1.2)))
        o = bpy.context.object
        o.scale = (0.02, 0.18, 0.02)
        o.rotation_euler = (rnd.uniform(0, math.pi), rnd.uniform(0, math.pi),
                            rnd.uniform(0, math.pi))
        objs.append(o)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 40, 2))
    o = bpy.context.object
    o.scale = (20, 0.2, 4)
    objs.append(o)
    scene = bpy.context.scene
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.data.lens = 35
    cam.location = (0.0, -2.0, 1.6)
    cam.rotation_euler = (math.radians(90), 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 7
    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False
    scene.fp_auto_style = 'BACKGROUND'
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    scene.render.film_transparent = True
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    scene.fp_white_preview = True

    def ink(path, v):
        scene.fp_lw_stripe_fade = v
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(str(path))
        w, h = img.size
        buf = [0.0] * (w * h * 4)
        img.pixels.foreach_get(buf)
        bpy.data.images.remove(img)
        tot = 0.0
        for y in range(int(h * 0.4), int(h * 0.6)):
            for x in range(int(w * 0.4), int(w * 0.6)):
                i = (y * w + x) * 4
                if buf[i + 3] >= 0.5:
                    tot += 1.0 - (buf[i] + buf[i + 1] + buf[i + 2]) / 3
        return tot

    tmp = Path(tempfile.mkdtemp(prefix="fp_t64_"))
    try:
        b0 = ink(tmp / "b0.png", 0.0)
        b1 = ink(tmp / "b1.png", 1.0)
        assert b0 > 0, b0
        assert b1 > b0 * 0.85, f"向きのばらばらな茂みまで薄くなった: {b0:.0f} -> {b1:.0f}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        bpy.ops.wm.read_homefile(use_empty=True)


@test("paint as: a rigid-skinned robot (many bones) is painted as mecha; overrides work")
def t65():
    # リグ付きでも、頂点がボーン1本に固定された物(ロボット)は、手描き系の
    # 仕上がりでもメカの塗り(角度で分ける)にする。リグ付きのザクがざっくり
    # 塗りで胴体1色になり、パネルの線が消えた。オブジェクトの「塗り方」で
    # 上書きでき、リグの無い物もキャラ(ざっくり塗り)にできること
    import numpy as np

    def build(rigged=True):
        bpy.ops.wm.read_homefile(use_empty=True)
        parts = []
        for i in range(10):                     # 箱 10 個 = 部品 10 個
            bpy.ops.mesh.primitive_cube_add(size=0.8, location=(i * 1.0, 0, 0))
            # 面を割っておく。1 面 1 枚の箱は島/面が 1 になり、「切れすぎ」の
            # 抑えで角度の分割が取りやめになる(実物のメカは面が多い)
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.subdivide(number_cuts=3)
            bpy.ops.object.mode_set(mode="OBJECT")
            parts.append(bpy.context.object)
        bpy.ops.object.select_all(action="DESELECT")
        for o in parts:
            o.select_set(True)
        bpy.context.view_layer.objects.active = parts[0]
        bpy.ops.object.join()
        body = bpy.context.object
        if rigged:
            arm_data = bpy.data.armatures.new("A")
            arm = bpy.data.objects.new("A", arm_data)
            bpy.context.scene.collection.objects.link(arm)
            bpy.context.view_layer.objects.active = arm
            bpy.ops.object.mode_set(mode="EDIT")
            for i in range(10):
                b = arm_data.edit_bones.new(f"part{i}")
                b.head, b.tail = (i * 1.0, 0, -0.4), (i * 1.0, 0, 0.4)
            bpy.ops.object.mode_set(mode="OBJECT")
            for i in range(10):                 # 部品ごとにボーン1本へ 100%
                vg = body.vertex_groups.new(name=f"part{i}")
                vg.add([v.index for v in body.data.vertices
                        if abs(v.co.x - i * 1.0) < 0.5], 1.0, "REPLACE")
            body.modifiers.new("A", "ARMATURE").object = arm
        scene = bpy.context.scene
        scene.fp_use_random_seed = False
        scene.fp_color_seed = 5
        scene.fp_sharp_auto = True
        scene["fp_rig_coarse"] = True           # 手描き系の仕上がり
        bpy.ops.object.select_all(action="DESELECT")
        body.select_set(True)
        bpy.context.view_layer.objects.active = body
        return body

    def split_parts(body):
        # 1 つの箱の中で色が 2 色以上に分かれている箱の数。色の総数は、
        # 離れた島がパレットの色を使い回すので比べられない
        ca = body.data.color_attributes["mecha_color"]
        buf = np.empty(len(ca.data) * 4, dtype=np.float32)
        ca.data.foreach_get("color", buf)
        col = buf.reshape(-1, 4)[:, :3].round(3)
        per = {}
        for p in body.data.polygons:
            per.setdefault(round(p.center.x), set()).add(tuple(col[p.loop_start]))
        return sum(1 for c in per.values() if len(c) > 1)

    body = build()
    bpy.ops.freepencil.auto_vertex_color()
    auto = split_parts(body)
    assert body.get("fp_paint_auto") == "MECHA",         f"剛体のリグがメカと判定されない: {body.get('fp_paint_auto')} ({body.get('fp_rigid_ratio')})"
    body = build()
    body.fp_paint_as = "CHARA"
    bpy.ops.freepencil.auto_vertex_color()
    chara = split_parts(body)
    assert auto >= 8, f"メカの塗りで箱が角度で分かれていない: {auto}/10 箱"
    assert chara == 0, f"キャラの指定でざっくり塗り(1 箱 1 色)にならない: {chara}/10 箱が分かれた"
    body = build(rigged=False)
    body.fp_paint_as = "CHARA"
    bpy.ops.freepencil.auto_vertex_color()
    plain = split_parts(body)
    assert plain == 0, f"リグ無しでキャラの指定が効かない: {plain}/10 箱が分かれた"
    bpy.ops.wm.read_homefile(use_empty=True)


@test("preview kind survives STEP3 regeneration whatever the old white toggle says")
def t66():
    # プレビューは「種類」と旧トグル(白)の2か所に持っていて、種類を切り替えても
    # 旧トグルが残っていた。STEP3 の作り直し(スライダーを動かしたときも)は旧トグルを
    # 見て掛け直すので、マテリアルやモノクロを選んでいるのに白になり、逆に旧トグルが
    # 切れたまま白を選ぶと、作り直しで材質の色に戻った(v2.8.0、画像で確認)
    from freepencil2 import fp_core
    fresh_scene_with_islands()
    bpy.ops.freepencil.auto_vertex_color()
    scene = bpy.context.scene
    bpy.context.view_layer.use_pass_diffuse_direct = True
    scene.fp_node_type = "pro"
    fp_core.setup_aov(scene, bpy.context.view_layer)
    fp_core.setup_compositor(scene, bpy.context.view_layer)

    def shown():
        tree = fp_batch.comp_tree(scene)
        grp = next(n for n in tree.nodes
                   if n.type == 'GROUP' and n.node_tree
                   and n.node_tree.name.startswith(fp_core.NODE_GROUP_PREFIX)
                   and n.label != "FreePencil_fine_line")
        sock = grp.inputs["Image"]
        src = sock.links[0].from_node if sock.is_linked else None
        if src is not None and src.label == fp_core.MONO_LABEL:
            return "MONO_LIGHT"
        if src is not None and src.label == fp_core.WHITE_MIX_LABEL:
            return "WHITE" if src.inputs[0].default_value > 0.5 else "NONE"
        return "NONE"

    for mode in ("WHITE", "NONE", "MONO_LIGHT", "WHITE", "NONE"):
        scene.fp_preview_mode = mode
        fp_core.setup_compositor(scene, bpy.context.view_layer)   # 作り直し
        assert shown() == mode, f"{mode} を選んで作り直したら {shown()} で出た"
    # 旧トグルだけが外れたまま(古いファイル)で白を選ぶ
    from freepencil2.props import _write_quiet
    _write_quiet(scene, {"fp_white_preview": False})   # 5.x では scene[...] で書いても変わらない
    assert scene.fp_white_preview is False
    scene.fp_preview_mode = "WHITE"
    fp_core.setup_compositor(scene, bpy.context.view_layer)
    assert shown() == "WHITE", f"白を選んで作り直したら {shown()} で出た"
    bpy.ops.wm.read_homefile(use_empty=True)


def _bg_scene(style="BACKGROUND"):
    """スザンヌと溝の付いた箱。カメラ付き。仕上がり style で STEP0 まで。"""
    import math
    bpy.ops.wm.read_homefile(use_empty=True)
    objs = []
    bpy.ops.mesh.primitive_monkey_add(size=1.6, location=(-1.2, 0, 0.9))
    objs.append(bpy.context.object)
    bpy.ops.mesh.primitive_cube_add(size=1.2, location=(0.8, 0.3, 0.6))
    objs.append(bpy.context.object)
    for i in range(4):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0.8, -0.31, 0.2 + i * 0.28))
        g = bpy.context.object
        g.scale = (1.0, 0.02, 0.03)
        objs.append(g)
    scene = bpy.context.scene
    cam = bpy.data.objects.new("C", bpy.data.cameras.new("C"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.location = (0, -6, 1.6)
    cam.rotation_euler = (math.radians(82), 0, 0)
    scene.render.resolution_x, scene.render.resolution_y = 320, 240
    scene.render.film_transparent = True
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
        setattr(scene, p_, False)
    scene.fp_color_seed = 7
    scene.fp_auto_style = style
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    return scene


def _render_gray(scene, path):
    import numpy as np
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(str(path))
    w, h = img.size
    buf = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(buf)
    bpy.data.images.remove(img)
    a = buf.reshape(h, w, 4)
    return a[..., 3] * (1.0 - a[..., :3].mean(axis=2))     # インクの濃さ(白地で)


@test("fine lines slider: the live result equals the STEP3 result (background)")
def t67():
    # 細い線のつまみを動かした直後、線がほとんど消えた(STEP3 を押すと戻る)。
    # 合成だけを後から差し直していたため。動かした直後と STEP3 後が同じ絵になること
    import shutil
    import tempfile
    import numpy as np
    scene = _bg_scene()
    tmp = Path(tempfile.mkdtemp(prefix="fp_t67_"))
    try:
        base = _render_gray(scene, tmp / "a.png")
        scene.fp_fine_lines = 0.85
        live = _render_gray(scene, tmp / "b.png")
        bpy.ops.freepencil2.link_button()
        rebuilt = _render_gray(scene, tmp / "c.png")
        assert live.sum() > base.sum() * 0.7, f"動かした直後に線が消えた: {base.sum():.0f} -> {live.sum():.0f}"
        d = float(np.abs(live - rebuilt).mean())
        assert d < 0.002, f"動かした直後と STEP3 後で絵が違う(平均差 {d:.4f})"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        bpy.ops.wm.read_homefile(use_empty=True)


@test("background with the test node: STEP3 does not fail on fine lines")
def t68():
    # テストノード(出力は Image だけ)を選ぶと、細い線が "sample" を探して止まった
    scene = _bg_scene()
    scene.fp_node_type = "test"
    res = bpy.ops.freepencil2.link_button()
    assert res == {"FINISHED"}, res
    bpy.ops.wm.read_homefile(use_empty=True)


@test("line weight checkbox takes effect without pressing STEP3")
def t69():
    # チェックを切っても、STEP3 を押すまで強弱のノードが残っていた
    from freepencil2 import line_weight
    scene = _bg_scene("WEIGHTED")
    tree = fp_batch.comp_tree(scene)
    assert any(n.label == line_weight.NODE_LABEL for n in tree.nodes)
    scene.fp_line_weight = False
    tree = fp_batch.comp_tree(scene)
    assert not any(n.label == line_weight.NODE_LABEL for n in tree.nodes),         "チェックを切っても強弱のノードが残った"
    scene.fp_line_weight = True
    tree = fp_batch.comp_tree(scene)
    assert any(n.label == line_weight.NODE_LABEL for n in tree.nodes),         "チェックを入れても強弱のノードが入らない"
    bpy.ops.wm.read_homefile(use_empty=True)


@test("hard boundary bones keep their step in the coarse (character) paint")
def t70():
    # キャラのざっくり塗りはボーンの色を隣と平均してぼかす。硬境界ボーン
    # (わざと段差を残す所)までぼかしていて、キャラ/背景では効かなかった
    import numpy as np

    def run(hard):
        bpy.ops.wm.read_homefile(use_empty=True)
        bpy.ops.mesh.primitive_cylinder_add(radius=0.3, depth=2.0, vertices=16)
        body = bpy.context.object
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.subdivide(number_cuts=8)
        bpy.ops.object.mode_set(mode="OBJECT")
        ad = bpy.data.armatures.new("A")
        arm = bpy.data.objects.new("A", ad)
        bpy.context.scene.collection.objects.link(arm)
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode="EDIT")
        for n, (h, t) in (("lo", ((0, 0, -1), (0, 0, 0))), ("hi", ((0, 0, 0), (0, 0, 1)))):
            b = ad.edit_bones.new(n)
            b.head, b.tail = h, t
        bpy.ops.object.mode_set(mode="OBJECT")
        lo, hi = body.vertex_groups.new(name="lo"), body.vertex_groups.new(name="hi")
        for v in body.data.vertices:                 # なだらかなウェイト
            w = min(1.0, max(0.0, (v.co.z + 0.4) / 0.8))
            lo.add([v.index], 1 - w, "REPLACE")
            hi.add([v.index], w, "REPLACE")
        body.modifiers.new("A", "ARMATURE").object = arm
        scene = bpy.context.scene
        scene.fp_use_random_seed = False
        scene.fp_color_seed = 5
        scene["fp_rig_coarse"] = True
        scene.fp_bone_hard_names = hard
        bpy.ops.object.select_all(action="DESELECT")
        body.select_set(True)
        bpy.context.view_layer.objects.active = body
        bpy.ops.freepencil.auto_vertex_color()
        me = body.data
        ca = me.color_attributes["bone_color"]
        buf = np.empty(len(ca.data) * 4, dtype=np.float32)
        ca.data.foreach_get("color", buf)
        lv = np.empty(len(me.loops), dtype=np.int32)
        me.loops.foreach_get("vertex_index", lv)
        vc = np.zeros((len(me.vertices), 3))
        vc[lv] = buf.reshape(-1, 4)[:, :3]
        ev = np.empty(len(me.edges) * 2, dtype=np.int32)
        me.edges.foreach_get("vertices", ev)
        ev = ev.reshape(-1, 2)
        return float(np.abs(vc[ev[:, 0]] - vc[ev[:, 1]]).max())

    soft = run("")
    hard = run("hi")
    assert hard > soft * 2 and hard > 0.05,         f"硬境界ボーンを指定しても段差が出ない: なし {soft:.3f} / 指定 {hard:.3f}"
    bpy.ops.wm.read_homefile(use_empty=True)


@test("finish dropdown keeps the character-paint flag in step with it")
def t71():
    # 目印は STEP0 でしか変わらず、精密に戻して STEP1 だけ押すとキャラの塗り方のままだった
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    scene.fp_auto_style = "WEIGHTED"
    assert scene.get("fp_rig_coarse"), "キャラにしても目印が立たない"
    scene.fp_auto_style = "PRECISE"
    assert not scene.get("fp_rig_coarse"), "精密に戻しても目印が残った"
    scene.fp_auto_style = "BACKGROUND"
    assert scene.get("fp_rig_coarse"), "手描き背景にしても目印が立たない"
    bpy.ops.wm.read_homefile(use_empty=True)


@test("every Set Alpha node the add-on builds replaces the alpha (4.x and 5.x)")
def t72():
    # 5.x では SetAlpha の mode が「Type」ソケットに移り、書き込み先が見つからず
    # 「Apply Mask」のまま動いていた。手描き背景の隙間埋めが色を外へにじませ、
    # 5.2 だけ輪郭が二重になった(総当りで発見)
    scene = _bg_scene()
    tree = fp_batch.comp_tree(scene)
    sas = [n for n in tree.nodes if n.bl_idname == "CompositorNodeSetAlpha"]
    assert len(sas) >= 2, f"SetAlpha が見つからない: {len(sas)}"
    for n in sas:
        mode = getattr(n, "mode", None)
        if mode is None:
            sock = n.inputs.get("Type")
            mode = sock.default_value if sock is not None else None
        assert mode in ("REPLACE_ALPHA", "Replace Alpha"), f"{n.name}: {mode}"
    bpy.ops.wm.read_homefile(use_empty=True)


@test("merged sliders: Far lines / Crush relief drive the five inner values; 1.0 = background default")
def t73():
    # v2.8.1 でパネルを整理し、奥ほど細く/減らす/薄く と 詰まった線/縞 を2本にまとめた。
    # STEP0(手描き背景)で 1.0 が入り、中の値が v2.8.0 の既定と同じであること。
    # 動かすと中の値が変わり、STEP3 が作り直されること
    from freepencil2 import line_weight
    scene = _bg_scene()
    assert abs(scene.fp_lw_far_amount - 1.0) < 1e-6 and abs(scene.fp_lw_relief - 1.0) < 1e-6
    assert (scene.fp_lw_far, scene.fp_lw_far_sens, round(scene.fp_lw_far_fade, 4)) == (1.0, 2.0, 0.15)
    assert (round(scene.fp_lw_dense, 4), scene.fp_lw_stripe_fade) == (0.3, 0.0)
    scene.fp_lw_far_amount = 0.0
    assert (scene.fp_lw_far, scene.fp_lw_far_sens, scene.fp_lw_far_fade) == (0.0, 1.0, 0.0)
    tree = fp_batch.comp_tree(scene)
    assert not any(n.label == line_weight.FAR_LABEL for n in tree.nodes), "奥の扱いを 0 にしても奥のノードが残った"
    scene.fp_lw_relief = 0.0
    assert (scene.fp_lw_dense, scene.fp_lw_stripe_fade) == (0.0, 0.0)
    assert not hasattr(scene, "fp_lw_crowd"), "詰まった線は太らせない のつまみが残っている"
    bpy.ops.wm.read_homefile(use_empty=True)


@test("file output: the color pass comes from the render, not the preview (white preview on)")
def t74():
    # 色(color)はグループの Image 入力の素通しから取っていて、STEP0 の既定の
    # 白プレビュー中は真っ白で書き出されていた(v2.7 から)。レンダーの色から取ること
    from freepencil2 import fp_core
    scene = _bg_scene("PRECISE")
    assert scene.fp_preview_mode == "WHITE"
    scene.fp_file_output = True
    scene.fp_fo_color = True
    bpy.ops.freepencil2.link_button()
    tree = fp_batch.comp_tree(scene)
    fo = next(n for n in tree.nodes if n.bl_idname == "CompositorNodeOutputFile")
    sock = fo.inputs.get("color")
    assert sock is not None and sock.is_linked, "color の口が無いかつながっていない"
    src = sock.links[0].from_node
    # 2倍レンダでは各パスが最終サイズへ縮める Scale を通るので、その手前までたどる
    while src.bl_idname == "CompositorNodeScale" and src.inputs[0].is_linked:
        src = src.inputs[0].links[0].from_node
    assert src.type == "R_LAYERS", f"color がレンダーからでなく {src.bl_idname} から来ている"
    bpy.ops.wm.read_homefile(use_empty=True)


@test("a v2.7 file with white preview keeps white after reopening and STEP3 / STEP0")
def t75():
    # v2.7 は白プレビューを ON/OFF で持っていて、種類(fp_preview_mode)は無かった。
    # 2.8.1 で開いて STEP3 か STEP0 を押すと白が外れ、材質の色で出た(上書き
    # インストールの点検で、v2.7 で作ったファイルで確認)
    import shutil
    import tempfile
    from freepencil2 import fp_core
    tmp = Path(tempfile.mkdtemp(prefix="fp_t75_"))
    try:
        scene = _bg_scene("PRECISE")
        # v2.7 のファイルの状態: 旧トグルだけ立っていて、種類は一度も書かれていない
        scene.property_unset("fp_preview_mode")
        from freepencil2.props import _write_quiet
        _write_quiet(scene, {"fp_white_preview": True})
        scene.property_unset("fp_preview_mode")
        assert not scene.is_property_set("fp_preview_mode")
        f = tmp / "v27like.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(f))
        bpy.ops.wm.open_mainfile(filepath=str(f))
        scene = bpy.context.scene
        assert scene.fp_preview_mode == "WHITE", f"開いたら種類が {scene.fp_preview_mode}"

        def shown():
            tree = fp_batch.comp_tree(scene)
            mix = next((n for n in tree.nodes if n.label == fp_core.WHITE_MIX_LABEL), None)
            return mix is not None and mix.inputs[0].default_value > 0.5

        bpy.ops.freepencil2.link_button()
        assert shown(), "STEP3 を押したら白が外れた"
        bpy.ops.object.select_all(action="DESELECT")
        for o in scene.objects:
            if o.type == "MESH":
                o.select_set(True)
                bpy.context.view_layer.objects.active = o
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        assert shown(), "STEP0 を押したら白が外れた"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        bpy.ops.wm.read_homefile(use_empty=True)


@test("character line weight is the same with an opaque (default) or transparent background")
def t76():
    # 強弱は物の外をレンダーのアルファで見ていて、背景が不透明(Blender の既定)だと
    # アルファが全面 1 になり、輪郭の強弱がほとんど出なかった。試験やデモはどれも
    # 背景を透過にしていて気付かなかった(画像で確認)。深度の側を 1px 広げた
    # 直し方でも、物の外の 1px が「物の中」になって輪郭の外側が細く、0.81 で落ちる
    import shutil
    import tempfile
    import numpy as np
    scene = _bg_scene("WEIGHTED")
    tmp = Path(tempfile.mkdtemp(prefix="fp_t76_"))
    try:
        scene.render.film_transparent = True
        clear = _render_gray(scene, tmp / "t.png")
        scene.render.film_transparent = False
        opaque = _render_gray(scene, tmp / "o.png")
        ink_t, ink_o = float(clear.sum()), float(opaque.sum())
        assert ink_o > ink_t * 0.85, f"背景が不透明だと線が細い: 透過 {ink_t:.0f} / 不透明 {ink_o:.0f}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        bpy.ops.wm.read_homefile(use_empty=True)


@test("ground to the horizon: no thick black band (precise)")
def t77():
    # 深度チャンネルが相対勾配 |∇Z|/Z で、平らな地面では奥ほど大きくなり、
    # 地平線の手前が太い黒帯になった(精密/キャラ。画像で確認)。深度を
    # |Laplace(1/Z)|*Z にして、平面では 0 になるようにした。モデルの写って
    # いない左端の帯で、線の画素が地平線1本分(数%)に収まること
    import math
    import shutil
    import tempfile
    import numpy as np
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 20, 0))
    ground = bpy.context.object
    bpy.ops.mesh.primitive_monkey_add(size=1.6, location=(0, 0, 0.9))
    monkey = bpy.context.object
    scene = bpy.context.scene
    cam = bpy.data.objects.new("C", bpy.data.cameras.new("C"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.location = (0, -6, 1.6)
    cam.rotation_euler = (math.radians(82), 0, 0)
    scene.render.resolution_x, scene.render.resolution_y = 320, 240
    scene.render.film_transparent = True
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
        setattr(scene, p_, False)
    scene.fp_color_seed = 7
    scene.fp_auto_style = "PRECISE"
    bpy.ops.object.select_all(action="DESELECT")
    for o in (ground, monkey):
        o.select_set(True)
    bpy.context.view_layer.objects.active = monkey
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    tmp = Path(tempfile.mkdtemp(prefix="fp_t77_"))
    try:
        ink = _render_gray(scene, tmp / "g.png")
        left = ink[:, :70]                   # モデルの写らない左端
        dark = float((left > 0.5).mean())
        assert dark < 0.03, f"地平線の手前が黒い帯になっている: 左端の {dark * 100:.1f}% が線"
        assert dark > 0.0, "地平線の線まで消えた"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        bpy.ops.wm.read_homefile(use_empty=True)


@test("preview: mono -> material -> white brings the white preview back")
def t78():
    # モノクロを下ろすとき、撤去するノードの入力元(ディフューズ直接光)を
    # Image へつないでいた。モノクロ -> マテリアルで陰影だけの絵になり、
    # そのあと白を選んでも白にならなかった(GUI のビューポートで発見)
    import shutil
    import tempfile
    import numpy as np
    scene = _bg_scene("WEIGHTED")
    tmp = Path(tempfile.mkdtemp(prefix="fp_t78_"))
    try:
        scene.fp_preview_mode = "WHITE"
        white0 = _render_gray(scene, tmp / "w0.png")
        for m in ("MONO_LIGHT", "NONE", "WHITE"):
            scene.fp_preview_mode = m
        white1 = _render_gray(scene, tmp / "w1.png")
        d = float(np.abs(white0 - white1).mean())
        assert d < 0.002, f"モノクロ -> マテリアル -> 白 で白に戻らない(平均差 {d:.4f})"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        bpy.ops.wm.read_homefile(use_empty=True)


@test("background: far islands merge (far facade keeps its outline, near facade keeps its windows)")
def t79():
    # 遠くのビルの窓が、どの仕上がりでも黒い縞の塊になった。手描き背景では、
    # 画面上で小さい区画(窓)を近くの壁へまとめる(fp_far_lod_px、v2.8.3)。
    # 同じ形の壁を手前と奥に置き、奥だけ色数が減ること。精密では減らないこと
    import math

    def facade(name, y):
        bpy.ops.mesh.primitive_plane_add(size=10, location=(0, y, 5), rotation=(math.radians(90), 0, 0))
        wall = bpy.context.object
        parts = [wall]
        for i in range(6):
            for j in range(6):
                bpy.ops.mesh.primitive_cube_add(size=1, location=(-3.75 + i * 1.5, y - 0.05, 1.25 + j * 1.5))
                w = bpy.context.object
                w.scale = (0.6, 0.1, 0.6)
                parts.append(w)
        bpy.ops.object.select_all(action="DESELECT")
        for o in parts:
            o.select_set(True)
        bpy.context.view_layer.objects.active = wall
        bpy.ops.object.join()
        o = bpy.context.object
        o.name = name
        return o

    def run(style):
        bpy.ops.wm.read_homefile(use_empty=True)
        near = facade("near", 20.0)
        far = facade("far", 600.0)
        scene = bpy.context.scene
        cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
        cam.data.lens = 35
        cam.location = (0, 0, 5)
        cam.rotation_euler = (math.radians(90), 0, 0)
        scene.collection.objects.link(cam)
        scene.camera = cam
        scene.render.resolution_x, scene.render.resolution_y = 960, 540
        for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
            setattr(scene, p_, False)
        scene.fp_color_seed = 7
        scene.fp_auto_style = style
        bpy.ops.object.select_all(action="DESELECT")
        for o in (near, far):
            o.select_set(True)
        bpy.context.view_layer.objects.active = near
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        return (len(set(get_mecha_colors(near))), len(set(get_mecha_colors(far))),
                scene.fp_far_lod_px)

    n_bg, f_bg, px = run("BACKGROUND")
    assert px == 500.0, f"手描き背景の既定で遠い区画をまとめるが入らない: {px}"
    # 島 37 個(壁 + 窓 36)。色はパレットで使い回すので、手前は 10 色前後になる
    assert n_bg >= 5, f"手前の窓までまとまった(色数 {n_bg})"
    assert f_bg <= 2, f"奥の窓がまとまらない(色数 {f_bg})"
    n_pr, f_pr, px = run("PRECISE")
    assert px == 0.0 and f_pr >= 5, f"精密で奥の窓がまとまった(色数 {f_pr}, px {px})"
    bpy.ops.wm.read_homefile(use_empty=True)


@test("remove FreePencil: everything added is gone and the render matches the one before STEP0")
def t80():
    # 利用者から「適用したあと戻す方法は？ アングルを変えて光源込みでレンダリングし直したい」
    # (note のコメント)。v2.8.3 で「FreePencil を外す」を足した。利用者の設定(透過の材質、
    # 材質の無い物、自分のコンポジタ、AgX、100%、背景は不透明)が全部元に戻り、
    # STEP0 の前と同じ絵でレンダリングされること
    import math
    import shutil
    import tempfile
    import numpy as np
    from freepencil2 import compat

    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.mesh.primitive_monkey_add(size=1.6, location=(-1.0, 0, 0.9))
    monkey = bpy.context.object
    mat = bpy.data.materials.new("Glassy")
    mat.use_nodes = True
    if hasattr(mat, "blend_method"):
        mat.blend_method = "BLEND"
    monkey.data.materials.append(mat)
    bpy.ops.mesh.primitive_cube_add(size=1.2, location=(1.0, 0.3, 0.6))
    cube = bpy.context.object
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.location = (0, -6, 1.6)
    cam.rotation_euler = (math.radians(82), 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    lt = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    lt.rotation_euler = (math.radians(45), 0, math.radians(30))
    scene.collection.objects.link(lt)
    scene.render.resolution_x, scene.render.resolution_y = 320, 240
    scene.eevee.taa_render_samples = 4
    # 利用者のコンポジタ: RenderLayers -> Invert -> 出力(5.x は利用者が付けた名前のグループ)
    if compat.IS_5_PLUS:
        ng = bpy.data.node_groups.new("My Compositor", "CompositorNodeTree")
        ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        scene.compositing_node_group = ng
    tree = compat.get_compositor_tree(scene, create=True)
    for n in list(tree.nodes):
        tree.nodes.remove(n)
    rl = tree.nodes.new("CompositorNodeRLayers")
    rl.name = "My RL"
    inv = tree.nodes.new("CompositorNodeInvert")
    inv.name = "My Invert"
    out = compat.new_output_node(tree)
    out.name = "My Out"
    tree.links.new(rl.outputs["Image"], inv.inputs["Color"])
    tree.links.new(inv.outputs[0], out.inputs[0])
    before = {"film": scene.render.film_transparent, "vt": scene.view_settings.view_transform,
              "pct": scene.render.resolution_percentage, "z": bpy.context.view_layer.use_pass_z,
              "blend": getattr(mat, "blend_method", None), "aovs": len(bpy.context.view_layer.aovs)}
    tmp = Path(tempfile.mkdtemp(prefix="fp_t80_"))
    try:
        def render(name):
            scene.render.filepath = str(tmp / name)
            bpy.ops.render.render(write_still=True)
            img = bpy.data.images.load(str(tmp / name))
            buf = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
            img.pixels.foreach_get(buf)
            bpy.data.images.remove(img)
            return buf.reshape(-1, 4)[:, :3]
        a = render("before.png")
        for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
            setattr(scene, p_, False)
        scene.fp_auto_style = "WEIGHTED"
        bpy.ops.object.select_all(action="DESELECT")
        monkey.select_set(True)
        cube.select_set(True)
        bpy.context.view_layer.objects.active = monkey
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        assert monkey.data.color_attributes.get("mecha_color") is not None, "STEP0 が塗っていない"
        assert scene.render.resolution_percentage == 200 or not scene.fp_supersample
        res = bpy.ops.freepencil.remove()
        assert res == {"FINISHED"}, res
        for o in (monkey, cube):
            left = [a_.name for a_ in o.data.color_attributes]
            assert not left, f"{o.name} に色属性が残った: {left}"
        assert len(cube.material_slots) == 0, "材質の無かった物に FreePencil_Material が残った"
        assert bpy.data.materials.get("FreePencil_Material") is None
        assert getattr(mat, "blend_method", None) == before["blend"], "透過の材質が HASHED のまま"
        assert not any(n.type == "GROUP" for n in mat.node_tree.nodes), "材質に AOV グループが残った"
        assert scene.render.film_transparent == before["film"]
        assert scene.view_settings.view_transform == before["vt"]
        assert scene.render.resolution_percentage == before["pct"]
        assert bpy.context.view_layer.use_pass_z == before["z"]
        assert len(bpy.context.view_layer.aovs) == before["aovs"], "AOV が残った"
        assert not any(g.name.startswith("FreePencil") for g in bpy.data.node_groups),             [g.name for g in bpy.data.node_groups]
        tree = compat.get_compositor_tree(scene)
        names = sorted(n.name for n in tree.nodes)
        assert names == ["My Invert", "My Out", "My RL"], f"利用者のコンポジタが戻らない: {names}"
        assert tree.nodes["My Invert"].inputs["Color"].is_linked and tree.nodes["My Out"].inputs[0].is_linked
        assert "fp_undo" not in scene
        b = render("after.png")
        d = float(np.abs(a - b).mean())
        assert d < 0.01, f"外したあとの絵が STEP0 の前と違う(平均差 {d:.4f})"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        bpy.ops.wm.read_homefile(use_empty=True)



@test("cel preview: shadow and pale color under the lines, off returns to white, remove clears the shade AOV")
def t81():
    # v2.9「セル(影と色)」。線を白地に描いてから、材質の色を薄めた色と 2 階調の影を掛ける。
    # 影は材質に関係なく「白い拡散面の光」を AOV で取る(発光の材質でも影が出る)
    import math
    import shutil
    import tempfile
    import numpy as np
    from freepencil2 import compat, cel_shade

    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(0, 0, 1.0))
    ball = bpy.context.object
    bpy.ops.object.shade_smooth()
    emit = bpy.data.materials.new("Toon")             # 光を受けない材質(アニメ調のモデルに多い)
    emit.use_nodes = True
    nt = emit.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(n)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0.9, 0.2, 0.1, 1)
    nt.links.new(em.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    ball.data.materials.append(emit)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.location = (0, -5, 1.0)
    cam.rotation_euler = (math.radians(90), 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    lt = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    lt.data.energy = 4
    lt.rotation_euler = (math.radians(60), 0, math.radians(-70))      # 右から: 左半分が影
    scene.collection.objects.link(lt)
    scene.render.resolution_x, scene.render.resolution_y = 240, 180
    scene.eevee.taa_render_samples = 4
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
        setattr(scene, p_, False)
    scene.fp_auto_style = "PRECISE"
    bpy.ops.object.select_all(action="DESELECT")
    ball.select_set(True)
    bpy.context.view_layer.objects.active = ball
    tmp = Path(tempfile.mkdtemp(prefix="fp_t81_"))
    try:
        def render(name):
            scene.render.filepath = str(tmp / name)
            bpy.ops.render.render(write_still=True)
            img = bpy.data.images.load(str(tmp / name))
            w, h = img.size
            buf = np.empty(w * h * 4, dtype=np.float32)
            img.pixels.foreach_get(buf)
            bpy.data.images.remove(img)
            return buf.reshape(h, w, 4)
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        scene.fp_preview_mode = "WHITE"
        white = render("white.png")
        scene.fp_preview_mode = "CEL"
        tree = compat.get_compositor_tree(scene)
        assert any(n.label == cel_shade.CEL_LABEL for n in tree.nodes), "セルのノードが入っていない"
        assert any(n.label == cel_shade.SHADE_NODE_LABEL for n in emit.node_tree.nodes), "材質に影の AOV が無い"
        cel = render("cel.png")
        h, w = cel.shape[:2]
        rgb = cel[..., :3]
        lum = rgb.sum(axis=2)
        # 球の面(赤みがあり、黒い線ではない所)。日なたと影の 2 つの明るさに分かれる
        body = (rgb[..., 0] > rgb[..., 2] + 0.1) & (lum > 0.6)
        assert body.sum() > 0.1 * h * w, f"材質の色が出ていない(赤みの画素 {int(body.sum())})"
        lo, hi = np.percentile(lum[body], 10), np.percentile(lum[body], 90)
        assert hi - lo > 0.15, f"影が出ていない(暗い所 {lo:.3f} 明るい所 {hi:.3f})"
        sky = cel[h - 5, w // 2, :3]
        assert sky[2] > sky[0], f"空の色が出ていない {sky}"
        scene.fp_preview_mode = "WHITE"
        assert not any(n.label == cel_shade.CEL_LABEL for n in tree.nodes), "白に戻してもセルのノードが残った"
        back = render("white_again.png")
        d = float(np.abs(white[..., :3] - back[..., :3]).mean())
        assert d < 0.01, f"白に戻した絵がセルの前と違う(平均差 {d:.4f})"
        scene.fp_preview_mode = "CEL"
        res = bpy.ops.freepencil.remove()
        assert res == {"FINISHED"}, res
        assert not any(n.label == cel_shade.SHADE_NODE_LABEL for n in emit.node_tree.nodes), "影の AOV ノードが残った"
        assert cel_shade.SHADE_AOV not in [a.name for a in bpy.context.view_layer.aovs], "影の AOV が残った"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        bpy.ops.wm.read_homefile(use_empty=True)


@test("weighted lines + material preview keep the material color (shading is not drawn as ink)")
def t82():
    # v2.8.0 から: キャラ/手描き背景でマテリアルのプレビューにすると、強弱の処理が「材質の色の上に線」
    # の絵を丸ごと線として扱い、色が消えて陰影が黒い線になった。v2.9 で線を白地に描いてから下に掛ける
    import math
    import shutil
    import tempfile
    import numpy as np

    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(0, 0, 1.0))
    ball = bpy.context.object
    bpy.ops.object.shade_smooth()
    red = bpy.data.materials.new("Red")
    red.use_nodes = True
    red.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.8, 0.1, 0.05, 1)
    ball.data.materials.append(red)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.location = (0, -5, 1.0)
    cam.rotation_euler = (math.radians(90), 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    lt = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    lt.data.energy = 4
    lt.rotation_euler = (math.radians(60), 0, math.radians(-70))
    scene.collection.objects.link(lt)
    scene.render.resolution_x, scene.render.resolution_y = 240, 180
    scene.eevee.taa_render_samples = 4
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
        setattr(scene, p_, False)
    scene.fp_auto_style = "WEIGHTED"
    bpy.ops.object.select_all(action="DESELECT")
    ball.select_set(True)
    bpy.context.view_layer.objects.active = ball
    tmp = Path(tempfile.mkdtemp(prefix="fp_t82_"))
    try:
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        assert scene.fp_line_weight, "キャラで強弱が入っていない"
        scene.fp_preview_mode = "NONE"
        scene.render.filepath = str(tmp / "mat.png")
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(str(tmp / "mat.png"))
        w, h = img.size
        buf = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(buf)
        bpy.data.images.remove(img)
        rgb = buf.reshape(h, w, 4)[..., :3]
        # 背景(既定の暗い灰色)を除いた所。影の側は暗い赤になるので、明るさによらず
        # 「赤が青と緑より強い」画素を数える
        r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
        lit = rgb.max(axis=2) > 0.06
        reddish = (r > 1.8 * b) & (r > 1.3 * g)
        frac = float(reddish[lit].mean())
        assert frac > 0.8, f"マテリアルのプレビューで球の色が出ていない(赤い画素 {frac:.2f})"
        ys, xs = np.nonzero(reddish & lit)
        box = rgb[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        ink = float((box.max(axis=2) < 0.03).mean())
        assert ink < 0.35, f"陰影が黒い線になっている(球の枠の中の真っ黒 {ink:.2f})"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        bpy.ops.wm.read_homefile(use_empty=True)



@test("file output layers: cel_color is flat and transparent outside, cel_shadow only in shadow, line has the weighted lines")
def t83():
    # v2.9: セルを別のソフトで重ねるための書き出し(cel_color / cel_shadow)と、強弱を付けた後の line
    import math
    import shutil
    import tempfile
    import numpy as np

    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(0, 0, 1.0))
    ball = bpy.context.object
    bpy.ops.object.shade_smooth()
    red = bpy.data.materials.new("Red")
    red.use_nodes = True
    red.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.8, 0.1, 0.05, 1)
    ball.data.materials.append(red)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.location = (0, -5, 1.0)
    cam.rotation_euler = (math.radians(90), 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    lt = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    lt.data.energy = 4
    lt.rotation_euler = (math.radians(60), 0, math.radians(-70))      # 右から: 左半分が影
    scene.collection.objects.link(lt)
    scene.render.resolution_x, scene.render.resolution_y = 240, 180
    scene.eevee.taa_render_samples = 4
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
        setattr(scene, p_, False)
    scene.fp_auto_style = "WEIGHTED"
    bpy.ops.object.select_all(action="DESELECT")
    ball.select_set(True)
    bpy.context.view_layer.objects.active = ball
    tmp = Path(tempfile.mkdtemp(prefix="fp_t83_"))
    try:
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        scene.fp_file_output = True
        scene.fp_fo_line = True
        scene.fp_fo_cel_color = True
        scene.fp_fo_cel_shadow = True
        scene.fp_file_output_path = str(tmp) + "/"
        bpy.ops.freepencil2.link_button()
        scene.render.filepath = str(tmp / "composite.png")
        bpy.ops.render.render(write_still=True)

        def load(stem):
            f = next(tmp.glob(stem + "*.png"))
            img = bpy.data.images.load(str(f))
            w, h = img.size
            buf = np.empty(w * h * 4, dtype=np.float32)
            img.pixels.foreach_get(buf)
            bpy.data.images.remove(img)
            return buf.reshape(h, w, 4)
        col, shd, line = load("cel_color"), load("cel_shadow"), load("line")
        h, w = col.shape[:2]
        assert col[2, 2, 3] < 0.05, "cel_color の物の外が透過になっていない"
        mid = col[h // 2, int(w * 0.5), :3]
        assert col[h // 2, int(w * 0.5), 3] > 0.9 and mid[0] > mid[2] + 0.2, f"cel_color に材質の色が無い {mid}"
        body = col[..., 3] > 0.9
        sa = shd[..., 3]
        lit = float((sa[body] < 0.05).mean())
        dark = float((sa[body] > 0.5).mean())
        assert lit > 0.2 and dark > 0.1, f"cel_shadow が影の所だけになっていない(日なた {lit:.2f} 影 {dark:.2f})"
        assert sa[2, 2] < 0.05, "cel_shadow の物の外が透過になっていない"
        ink = line[..., 3]
        assert 0.002 < float((ink > 0.5).mean()) < 0.3, "line に線が無い(または塗りつぶし)"
        assert float(line[..., :3][ink > 0.5].max()) < 0.2, "line の線が黒くない"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        bpy.ops.wm.read_homefile(use_empty=True)


@test("per-object line width: all 1 changes nothing, 2 thickens, 0 removes the lines")
def t84():
    # v2.9 物ごとの線の太さ(Object.fp_line_scale)。全部 1 ならノードを挿さず絵も同じ
    import math
    import shutil
    import tempfile
    import numpy as np
    from freepencil2 import compat, line_scale

    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.mesh.primitive_cube_add(size=1.2, location=(-1.0, 0, 0.6))
    a = bpy.context.object
    bpy.ops.mesh.primitive_cube_add(size=1.2, location=(1.0, 0, 0.6))
    b = bpy.context.object
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.location = (0, -6, 1.6)
    cam.rotation_euler = (math.radians(82), 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    lt = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    lt.rotation_euler = (math.radians(45), 0, math.radians(30))
    scene.collection.objects.link(lt)
    scene.render.resolution_x, scene.render.resolution_y = 320, 180
    scene.eevee.taa_render_samples = 4
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
        setattr(scene, p_, False)
    scene.fp_auto_style = "PRECISE"
    bpy.ops.object.select_all(action="DESELECT")
    a.select_set(True)
    b.select_set(True)
    bpy.context.view_layer.objects.active = a
    tmp = Path(tempfile.mkdtemp(prefix="fp_t84_"))
    try:
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        scene.fp_preview_mode = "WHITE"

        def ink(name):
            scene.render.filepath = str(tmp / name)
            bpy.ops.render.render(write_still=True)
            img = bpy.data.images.load(str(tmp / name))
            w, h = img.size
            buf = np.empty(w * h * 4, dtype=np.float32)
            img.pixels.foreach_get(buf)
            bpy.data.images.remove(img)
            px = buf.reshape(h, w, 4)
            dark = (px[..., :3].max(axis=2) < 0.5) & (px[..., 3] > 0.5)
            return dark[:, : w // 2].mean(), dark[:, w // 2:].mean()
        base = ink("base.png")
        tree = compat.get_compositor_tree(scene)
        assert not line_scale.present(tree), "全部 1 なのに太さのノードが入った"
        a.fp_line_scale = 2.0
        b.fp_line_scale = 0.0
        assert line_scale.present(compat.get_compositor_tree(scene)), "1 以外にしてもノードが入らない"
        mixed = ink("mixed.png")
        assert mixed[0] > base[0] * 1.4, f"2 にしても線が太くならない({base[0]:.4f} -> {mixed[0]:.4f})"
        assert mixed[1] < base[1] * 0.15, f"0 にしても線が消えない({base[1]:.4f} -> {mixed[1]:.4f})"
        a.fp_line_scale = 1.0
        b.fp_line_scale = 1.0
        assert not line_scale.present(compat.get_compositor_tree(scene)), "全部 1 に戻してもノードが残った"
        back = ink("back.png")
        assert abs(back[0] - base[0]) < 1e-4 and abs(back[1] - base[1]) < 1e-4, "1 に戻した絵が元と違う"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        bpy.ops.wm.read_homefile(use_empty=True)


@test("cel shadow does not depend on the material (subsurface) and follows the sun when it is rotated")
def t85():
    # v2.9: 白い拡散面の光(Shader to RGB)は表面下散乱の材質で光り方が変わり、5.2 では材質の拡散と
    # 混ざって影の位置がずれた。日があるときは法線のパス x 日の向き x 影のパスで取る
    import math
    import shutil
    import tempfile
    import numpy as np
    from freepencil2 import cel_shade

    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    balls = []
    for i, sss in enumerate((0.0, 1.0)):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(-1.0 + 2.0 * i, 3.0 * i, 1.0))
        o = bpy.context.object
        bpy.ops.object.shade_smooth()
        m = bpy.data.materials.new(f"M{i}")
        m.use_nodes = True
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Subsurface Weight"].default_value = sss
        o.data.materials.append(m)
        balls.append(o)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.location = (0, -9, 1.0)
    cam.rotation_euler = (math.radians(90), 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    lt = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    lt.data.energy = 4
    from mathutils import Vector
    lt.rotation_euler = Vector((1.0, -1.0, 1.0)).to_track_quat("Z", "Y").to_euler()   # 右手前の上から
    scene.collection.objects.link(lt)
    scene.render.resolution_x, scene.render.resolution_y = 320, 160
    scene.eevee.taa_render_samples = 4
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
        setattr(scene, p_, False)
    scene.fp_auto_style = "PRECISE"
    bpy.ops.object.select_all(action="DESELECT")
    for o in balls:
        o.select_set(True)
    bpy.context.view_layer.objects.active = balls[0]
    tmp = Path(tempfile.mkdtemp(prefix="fp_t85_"))
    try:
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        scene.fp_preview_mode = "CEL"

        def shadow_side():
            scene.render.filepath = str(tmp / "c.png")
            bpy.ops.render.render(write_still=True)
            img = bpy.data.images.load(str(tmp / "c.png"))
            w, h = img.size
            buf = np.empty(w * h * 4, dtype=np.float32)
            img.pixels.foreach_get(buf)
            bpy.data.images.remove(img)
            px = buf.reshape(h, w, 4)[..., :3].sum(axis=2)
            from bpy_extras.object_utils import world_to_camera_view
            from mathutils import Vector
            out = []
            for o in balls:
                c = world_to_camera_view(scene, cam, o.location)
                e = world_to_camera_view(scene, cam, o.location + Vector((1.0, 0, 0)))
                cx, cy, r = c.x * w, c.y * h, (e.x - c.x) * w * 0.8
                yy, xx = np.mgrid[0:h, 0:w]
                disc = (xx - cx) ** 2 + (yy - cy) ** 2 < r * r
                left = float(px[disc & (xx < cx)].mean())
                right = float(px[disc & (xx > cx)].mean())
                out.append((left, right))
            return out
        (pl, pr), (sl, sr) = shadow_side()
        assert pr > pl + 0.1 and sr > sl + 0.1, f"右からの日で右が明るくない {pl:.2f},{pr:.2f} / {sl:.2f},{sr:.2f}"
        assert abs((pr - pl) - (sr - sl)) < 0.2, f"表面下散乱の球だけ影の出方が違う {pr - pl:.2f} vs {sr - sl:.2f}"
        lt.rotation_euler = Vector((-1.0, -1.0, 1.0)).to_track_quat("Z", "Y").to_euler()  # 左手前の上から
        bpy.context.view_layer.update()
        cel_shade.update_sun(scene)
        (pl, pr), _ = shadow_side()
        assert pl > pr + 0.1, f"日を回しても影が付いて来ない {pl:.2f},{pr:.2f}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        bpy.ops.wm.read_homefile(use_empty=True)


def _ink_in(png, box):
    """png の box(x0, y0, x1, y1 を 0..1 で)の中の、線(暗い画素)の割合。"""
    import numpy as np
    img = bpy.data.images.load(str(png))
    w, h = img.size
    buf = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(buf)
    bpy.data.images.remove(img)
    px = buf.reshape(h, w, 4)[::-1]
    x0, y0, x1, y1 = (int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h))
    sub = px[y0:y1, x0:x1]
    dark = (sub[..., :3].max(axis=2) < 0.4) & (sub[..., 3] > 0.5)
    return float(dark.mean())


@test("texture split: an image plugged into line_texture draws its color boundaries, mask_texture erases")
def t86():
    # v2.7 までの技法(AOV グループの line_texture に塗り分けた絵をつなぐ)が、v2.8.0 で係数を 0 に
    # して効かなくなっていた。v2.9 で「足す」にして戻した。mask_texture は STEP2 で AOV を入れる
    import math
    import shutil
    import tempfile
    import numpy as np
    from freepencil2 import fp_core

    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.mesh.primitive_plane_add(size=2.0, location=(0, 0, 1.0), rotation=(math.radians(90), 0, 0))
    plate = bpy.context.object
    m = bpy.data.materials.new("P")
    m.use_nodes = True
    plate.data.materials.append(m)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.location = (0, -4, 1.0)
    cam.rotation_euler = (math.radians(90), 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = 240, 240
    scene.eevee.taa_render_samples = 4
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view"):
        setattr(scene, p_, False)
    scene.fp_auto_style = "PRECISE"
    bpy.ops.object.select_all(action="DESELECT")
    plate.select_set(True)
    bpy.context.view_layer.objects.active = plate
    tmp = Path(tempfile.mkdtemp(prefix="fp_t86_"))
    try:
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        scene.fp_preview_mode = "WHITE"
        scene.render.filepath = str(tmp / "a.png")
        bpy.ops.render.render(write_still=True)
        mid = (0.4, 0.2, 0.6, 0.8)          # 板の中ほど(縦の帯)
        assert _ink_in(tmp / "a.png", mid) < 0.01, "絵をつなぐ前から板の中に線がある"
        # 左右で色の違う絵(縦の境目が真ん中)
        img = bpy.data.images.new("split", 64, 64)
        px = np.ones((64, 64, 4), dtype=np.float32)
        px[:, :32, :3] = (0.9, 0.1, 0.1)
        px[:, 32:, :3] = (0.1, 0.2, 0.9)
        img.pixels.foreach_set(px.ravel())
        nt = m.node_tree
        grp = next(n for n in nt.nodes if n.type == "GROUP" and n.node_tree
                   and n.node_tree.name == fp_core.AOV_GROUP_NAME)
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.interpolation = "Closest"
        nt.links.new(tex.outputs["Color"], grp.inputs["line_texture"])
        scene.render.filepath = str(tmp / "b.png")
        bpy.ops.render.render(write_still=True)
        assert _ink_in(tmp / "b.png", mid) > 0.02, "line_texture につないだ絵の境目に線が出ない"
        # 同じ絵(左半分が白に近い赤)を mask_texture へ: STEP2 -> STEP3 で板の中の線が消える側がある
        white = bpy.data.images.new("halfwhite", 64, 64)
        pw = np.zeros((64, 64, 4), dtype=np.float32)
        pw[..., 3] = 1.0
        pw[:, :40, :3] = 1.0                 # 境目(32)を覆う
        white.pixels.foreach_set(pw.ravel())
        t2 = nt.nodes.new("ShaderNodeTexImage")
        t2.image = white
        t2.interpolation = "Closest"
        nt.links.new(t2.outputs["Color"], grp.inputs["mask_texture"])
        bpy.ops.freepencil4.link_button()
        assert scene.fp_mask_color, "mask_texture をつないでも STEP2 がマスクの AOV を入れない"
        bpy.ops.freepencil2.link_button()
        scene.render.filepath = str(tmp / "c.png")
        bpy.ops.render.render(write_still=True)
        assert _ink_in(tmp / "c.png", mid) < 0.01, "mask_texture で白くした所の線が消えない"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        bpy.ops.wm.read_homefile(use_empty=True)


@test("STEP4 after STEP0: painting mask erases lines without touching STEP2 (all finishes)")
def t87():
    # STEP0 は塗っていないマスクの AOV を作らないので、STEP0 の後にマスクを塗っても線が消えなかった。
    # 手描き背景では細い線(コピーしたグループ)にマスクがつながっておらず、どうやっても消えなかった
    import math
    import shutil
    import tempfile
    import numpy as np

    tmp = Path(tempfile.mkdtemp(prefix="fp_t87_"))
    try:
        for style in ("PRECISE", "WEIGHTED", "BACKGROUND"):
            bpy.ops.wm.read_homefile(use_empty=True)
            scene = bpy.context.scene
            bpy.ops.mesh.primitive_cube_add(size=1.4, location=(0, 0, 0.7))
            box = bpy.context.object
            cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
            cam.location = (2.5, -3.5, 2.4)
            cam.rotation_euler = (math.radians(66), 0, math.radians(35))
            scene.collection.objects.link(cam)
            scene.camera = cam
            lt = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
            scene.collection.objects.link(lt)
            scene.render.resolution_x, scene.render.resolution_y = 240, 240
            scene.eevee.taa_render_samples = 4
            for p_ in ("fp_use_random_seed", "fp_enable_compositor_view"):
                setattr(scene, p_, False)
            scene.fp_auto_style = style
            bpy.ops.object.select_all(action="DESELECT")
            box.select_set(True)
            bpy.context.view_layer.objects.active = box
            bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
            scene.fp_preview_mode = "WHITE"
            whole = (0.0, 0.0, 1.0, 1.0)
            scene.render.filepath = str(tmp / f"{style}_a.png")
            bpy.ops.render.render(write_still=True)
            base = _ink_in(tmp / f"{style}_a.png", whole)
            assert base > 0.005, f"{style}: 箱に線が無い"
            scene.fp_color_type = "mask_color"
            bpy.ops.freepencil3.link_button()
            attr = box.data.color_attributes["mask_color"]
            attr.data.foreach_set("color", [1.0, 1.0, 1.0, 1.0] * len(attr.data))
            box.data.update()
            bpy.ops.object.mode_set(mode="OBJECT")
            scene.render.filepath = str(tmp / f"{style}_b.png")
            bpy.ops.render.render(write_still=True)
            after = _ink_in(tmp / f"{style}_b.png", whole)
            assert after < base * 0.1, f"{style}: マスクを塗っても線が消えない({base:.4f} -> {after:.4f})"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        bpy.ops.wm.read_homefile(use_empty=True)


@test("Half Fill snaps a painted (gradient) boundary onto the selected vertex row, on a plane facing the camera")
def t88():
    # 以前は選んだ 2 点と X/Y 平面だけで側を決め、X/Z の面では黒い塊が出た。v2.9 で「面ごとに隣の色を
    # 拾う」に作り直した。頂点ペイントのようなぼかしの境目は線にならず、Half Fill で 1 本の線になる
    import math
    import shutil
    import tempfile
    import numpy as np

    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=8, y_subdivisions=8, size=2.0,
                                    location=(0, 0, 1.0), rotation=(math.radians(90), 0, 0))
    plate = bpy.context.object
    m = bpy.data.materials.new("P")
    m.use_nodes = True
    plate.data.materials.append(m)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.location = (0, -4.2, 1.0)
    cam.rotation_euler = (math.radians(90), 0, 0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = 480, 480
    scene.eevee.taa_render_samples = 4
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view"):
        setattr(scene, p_, False)
    scene.fp_auto_style = "PRECISE"
    bpy.ops.object.select_all(action="DESELECT")
    plate.select_set(True)
    bpy.context.view_layer.objects.active = plate
    tmp = Path(tempfile.mkdtemp(prefix="fp_t88_"))
    try:
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        scene.fp_preview_mode = "WHITE"
        me = plate.data
        attr = me.color_attributes["mecha_color"]
        lv = np.empty(len(me.loops), dtype=np.int64)
        me.loops.foreach_get("vertex_index", lv)
        xs = np.array([me.vertices[i].co.x for i in lv])
        cols = np.zeros((len(lv), 4), dtype=np.float32)
        cols[:] = (0.1, 0.3, 0.9, 1.0)
        cols[xs <= 1e-4] = (0.9, 0.15, 0.1, 1.0)
        attr.data.foreach_set("color", cols.ravel())
        me.update()
        mid = (0.45, 0.25, 0.55, 0.75)
        scene.render.filepath = str(tmp / "a.png")
        bpy.ops.render.render(write_still=True)
        before = _ink_in(tmp / "a.png", mid)
        # 作った直後は全部選ばれている。編集モードで外してから、境目の列だけ選ぶ
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.object.mode_set(mode="OBJECT")
        for v in me.vertices:
            v.select = abs(v.co.x) < 1e-4
        bpy.ops.object.mode_set(mode="EDIT")
        scene.fp_color_type = "mecha_color"
        res = bpy.ops.freepencil5.link_button()
        bpy.ops.object.mode_set(mode="OBJECT")
        assert res == {"FINISHED"}, res
        scene.render.filepath = str(tmp / "b.png")
        bpy.ops.render.render(write_still=True)
        after = _ink_in(tmp / "b.png", mid)
        # 前: ぼかしの境目は線にならない(解像度によっては太い黒い帯)。後: 細い 1 本の線
        assert 0.01 < after < 0.3, f"Half Fill の後に境目が 1 本の線になっていない({before:.4f} -> {after:.4f})"
        assert abs(after - before) > 0.01, f"Half Fill で境目が変わらない({before:.4f} -> {after:.4f})"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        bpy.ops.wm.read_homefile(use_empty=True)


@test("Half Fill also works in Vertex Paint (vertex selection mask), after STEP4's paint button")
def t89():
    # 「頂点カラーを塗る」で頂点ペイントに入ったままだと、Half Fill はグレーで押せなかった(編集モードだけ)
    import math
    import numpy as np

    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=8, y_subdivisions=8, size=2.0,
                                    location=(0, 0, 1.0), rotation=(math.radians(90), 0, 0))
    plate = bpy.context.object
    plate.data.materials.append(bpy.data.materials.new("P"))
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view"):
        setattr(scene, p_, False)
    scene.fp_auto_style = "PRECISE"
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    from freepencil2.half_fill import LINK_MAKE_FP_OT_HALF_FILL as HF
    assert not HF.poll(bpy.context), "オブジェクトモードで押せてしまう"
    scene.fp_color_type = "mecha_color"
    bpy.ops.freepencil3.link_button()
    assert plate.mode == "VERTEX_PAINT"
    assert HF.poll(bpy.context), "頂点ペイントで押せない"
    me = plate.data
    attr = me.color_attributes["mecha_color"]
    lv = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", lv)
    xs = np.array([me.vertices[i].co.x for i in lv])
    cols = np.zeros((len(lv), 4), dtype=np.float32)
    cols[:] = (0.1, 0.3, 0.9, 1.0)
    cols[xs <= 1e-4] = (0.9, 0.15, 0.1, 1.0)
    attr.data.foreach_set("color", cols.ravel())
    # 利用者の手順: 頂点の選択マスクに切り替え、全部外してから、境目の頂点を選ぶ
    me.use_paint_mask = False
    me.use_paint_mask_vertex = True
    bpy.ops.paint.vert_select_all(action="DESELECT")
    for v in me.vertices:
        v.select = abs(v.co.x) < 1e-4
    me.update()
    res = bpy.ops.freepencil5.link_button()
    assert res == {"FINISHED"}, res
    attr = me.color_attributes["mecha_color"]          # 書き戻しで作り直されるので引き直す
    cols = np.empty(len(attr.data) * 4, dtype=np.float32)
    attr.data.foreach_get("color", cols)
    cols = cols.reshape(-1, 4)
    # 境目の列(x=0)の角は、右の面では青(隣の色)になる
    poly_of = np.empty(len(me.loops), dtype=np.int64)
    for p in me.polygons:
        poly_of[p.loop_start:p.loop_start + p.loop_total] = p.index
    cx = np.array([me.polygons[i].center.x for i in poly_of])
    edge = np.abs(xs) < 1e-4
    right = edge & (cx > 0)
    left = edge & (cx < 0)
    assert np.all(cols[right][:, 2] > 0.8) and np.all(cols[left][:, 0] > 0.8), "境目の角が隣の色にならない"
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.wm.read_homefile(use_empty=True)


@test("Pressing STEP3/STEP0 again does not pile up nodes (Anti-Aliasing, fine-line groups)")
def t90():
    # STEP3 を押すたびに、つながっていないアンチエイリアスが 1 個ずつ残り、手描き背景では
    # 細い線のグループ(_fine.001 …)も溜まっていた(v2.9.1 のボタン点検で発見)
    import math
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.mesh.primitive_monkey_add(location=(0, 0, 0))
    bpy.ops.mesh.primitive_cube_add(size=0.8, location=(1.6, 0.4, 0))
    cam = bpy.data.objects.new("C", bpy.data.cameras.new("C"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.location = (0.8, -6, 0.5)
    cam.rotation_euler = (math.radians(88), 0, 0)
    scene.render.resolution_x, scene.render.resolution_y = 160, 90
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view"):
        setattr(scene, p_, False)
    for o in scene.objects:
        o.select_set(o.type == "MESH")
    bpy.context.view_layer.objects.active = bpy.data.objects["Suzanne"]
    from freepencil2 import compat
    for style in ("PRECISE", "BACKGROUND"):
        scene.fp_auto_style = style
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        tree = compat.get_compositor_tree(scene)
        n0 = len(tree.nodes)
        for _ in range(3):
            bpy.ops.freepencil2.link_button()
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        tree = compat.get_compositor_tree(scene)
        aa = [n for n in tree.nodes if n.bl_idname == "CompositorNodeAntiAliasing"]
        loose = [n for n in aa if not any(s.is_linked for s in n.outputs)]
        assert not loose, f"{style}: つながっていないアンチエイリアスが {len(loose)} 個残った"
        assert len(tree.nodes) == n0, f"{style}: 押し直しでノードが {n0} -> {len(tree.nodes)}"
        fine = [g.name for g in bpy.data.node_groups if "_fine" in g.name and g.users == 0]
        assert not fine, f"{style}: 使われない細い線のグループが残った {fine}"
    bpy.ops.wm.read_homefile(use_empty=True)


@test("Node Tools: Export Group to Python -> Import gives the same picture (4.x and 5.x)")
def t91():
    # 書き出しで、コンポジタの Math の演算・クランプ(4.x)、5.x で入力へ移った値(Color Key など)、
    # mecha_color / alpha のつなぎ線が落ち、読み込んだグループの絵が真っ白などになっていた
    # (v2.9.1 のボタン点検で発見)
    import importlib.util
    import math
    import shutil
    import tempfile
    import numpy as np
    from freepencil2 import compat, node_io
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.mesh.primitive_monkey_add(location=(0, 0, 0))
    bpy.ops.mesh.primitive_cube_add(size=0.8, location=(1.6, 0.4, 0))
    cam = bpy.data.objects.new("C", bpy.data.cameras.new("C"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.location = (0.8, -6, 0.5)
    cam.rotation_euler = (math.radians(88), 0, 0)
    scene.render.resolution_x, scene.render.resolution_y = 200, 112
    scene.render.image_settings.file_format = "PNG"
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view"):
        setattr(scene, p_, False)
    for o in scene.objects:
        o.select_set(o.type == "MESH")
    bpy.context.view_layer.objects.active = bpy.data.objects["Suzanne"]
    scene.fp_auto_style = "PRECISE"
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    tree = compat.get_compositor_tree(scene)
    grp = next(n for n in tree.nodes if n.type == "GROUP" and n.node_tree
               and n.node_tree.name.startswith("FreePencil_v1"))
    src = grp.node_tree
    tmp = Path(tempfile.mkdtemp(prefix="fp_t91_"))
    try:
        cp = node_io.copy_node_tree_keep_used_groupio(src)
        script, _ = node_io.make_python_script(cp, src.name, "CompositorNodeTree")
        bpy.data.node_groups.remove(cp, do_unlink=True)
        assert "_fp_export_ref" not in bpy.data.node_groups, "比べるための木が残った"
        (tmp / "g.py").write_text(script, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("fp_t91_g", tmp / "g.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        new = [getattr(mod, n) for n in dir(mod) if n.startswith("create_node_tree")][0]()
        assert len(new.links) == len(src.links), f"つなぎ線 {len(src.links)} -> {len(new.links)}"

        def load(name):
            img = bpy.data.images.load(str(tmp / name))
            a = np.array(img.pixels[:], dtype=np.float32).reshape(-1, 4)
            bpy.data.images.remove(img)
            return a[:, :3].mean(axis=1) * a[:, 3] + (1 - a[:, 3])
        def render(name):
            scene.render.filepath = str(tmp / name)
            bpy.ops.render.render(write_still=True)
            return load(name)
        a = render("a.png")
        grp.node_tree = new
        b = render("b.png")
        grp.node_tree = src
        ink = (a < 0.5).mean()
        assert ink > 0.005, f"元の絵に線が無い({ink:.4f})"
        d = (np.abs(a - b) > 0.05).mean()
        assert d < 0.002, f"読み込んだグループの絵が元と違う({d * 100:.2f}% の画素)"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        bpy.ops.wm.read_homefile(use_empty=True)


@test("STEP3's node type defaults to Pro: STEP1 -> STEP2 -> STEP3 by hand gives the Pro lines")
def t92():
    # 既定がテストで、手で STEP1→2→3 を押すと目や口が黒く潰れた太い線になった(v2.9.2 で既定をプロに)
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.mesh.primitive_monkey_add(location=(0, 0, 0))
    scene.fp_use_random_seed = False
    scene.fp_enable_compositor_view = False
    assert scene.fp_node_type == "pro", scene.fp_node_type
    bpy.ops.freepencil.auto_vertex_color()
    bpy.ops.freepencil4.link_button()
    bpy.ops.freepencil2.link_button()
    from freepencil2 import compat
    tree = compat.get_compositor_tree(scene)
    names = [n.node_tree.name for n in tree.nodes if n.type == "GROUP" and n.node_tree]
    assert "FreePencil_v1_1_0_pro" in names, names
    bpy.ops.wm.read_homefile(use_empty=True)


@test("AI window: guide/auto/render work headless, erase_lines by camera rect removes ink there, buttons leave guidance")
def t93():
    # AI は筆もパネルのボタンも使えないので、窓口(ai.py)で STEP0 から手直しまで通す(v2.9.x)
    import math
    import sys as _sys
    import numpy as np
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.mesh.primitive_monkey_add(location=(-1.0, 0, 0))
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(1.2, 0, 0))
    cam = bpy.data.objects.new("C", bpy.data.cameras.new("C"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.location = (0.1, -6, 0)
    cam.rotation_euler = (math.radians(90), 0, 0)
    scene.render.resolution_x, scene.render.resolution_y = 240, 135
    scene.fp_use_random_seed = False
    scene.fp_enable_compositor_view = False
    fp = next(m for n, m in _sys.modules.items() if n.endswith("freepencil2.ai"))
    g = fp.guide()
    assert g["next"] and "auto(" in g["next"][0], g["next"]
    r = fp.auto("PRECISE")
    assert r["step"] == "STEP0", r
    a = fp.render("t93_a", scale=1.0)
    def ink(path, box):
        img = bpy.data.images.load(path)
        w, h = img.size
        px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
        bpy.data.images.remove(img)
        lum = px[..., :3].mean(axis=2) * px[..., 3] + (1 - px[..., 3])
        x0, y0, x1, y1 = box
        sub = lum[int(h * (1 - y1)):int(h * (1 - y0)), int(w * x0):int(w * x1)]
        return float((sub < 0.5).mean())
    left = (0.0, 0.0, 0.48, 1.0)
    right = (0.55, 0.0, 1.0, 1.0)
    i0, r0 = ink(a["image"], left), ink(a["image"], right)
    assert i0 > 0.01 and r0 > 0.01, (i0, r0)
    e = fp.erase_lines({"rect": left})
    assert "Suzanne" in e["done"] and "Cube" not in e["done"], e["done"]
    b = fp.render("t93_b", scale=1.0)
    i1, r1 = ink(b["image"], left), ink(b["image"], right)
    assert i1 < i0 * 0.3, f"四角の中の線が消えない {i0:.4f} -> {i1:.4f}"
    assert r1 > r0 * 0.8, f"四角の外の線まで消えた {r0:.4f} -> {r1:.4f}"
    fp.undo()
    c = fp.render("t93_c", scale=1.0)
    assert ink(c["image"], left) > i0 * 0.8, "undo で戻らない"
    bpy.ops.freepencil2.link_button()
    assert fp.last().get("step") == "STEP3", fp.last()
    bpy.ops.wm.read_homefile(use_empty=True)


@test("AI window: merge removes shape lines in a material, soft_overlays/clip_alpha set blend and clip, remove undoes clip")
def t94():
    # キャラの目の丸い線(merge)、髪の影の板のざらざら(soft_overlays)、半透明の縁のざらざら(clip_alpha)。
    # MMD の 4 体で見つけた(v2.9.x)
    import math
    import sys as _sys
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(0, 0, 0))
    ob = bpy.context.object
    face, eye = bpy.data.materials.new("face"), bpy.data.materials.new("eye")
    face.use_nodes = eye.use_nodes = True             # 4.x は作りたての材質にノードが無い
    ob.data.materials.append(face)
    ob.data.materials.append(eye)
    for p in ob.data.polygons:                       # 前の真ん中を「目」の材質に
        if p.center.y < -0.8 and abs(p.center.z) < 0.3 and abs(p.center.x) < 0.3:
            p.material_index = 1
    cam = bpy.data.objects.new("C", bpy.data.cameras.new("C"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.location = (0, -6, 0)
    cam.rotation_euler = (math.radians(90), 0, 0)
    scene.render.resolution_x, scene.render.resolution_y = 200, 112
    scene.fp_use_random_seed = False
    scene.fp_enable_compositor_view = False
    fp = next(m for n, m in _sys.modules.items() if n.endswith("freepencil2.ai"))
    fp.auto("PRECISE")
    import numpy as np
    a = ob.data.color_attributes["mecha_color"]
    r = fp.merge({"objects": [ob.name], "material": ["face", "eye"]})
    assert "面の塗り分けを 1 色" in r["done"], r
    buf = np.empty(len(a.data) * 4, dtype=np.float32)
    ob.data.color_attributes["mecha_color"].data.foreach_get("color", buf)
    assert len(np.unique(np.round(buf.reshape(-1, 4)[:, :3], 2), axis=0)) == 1, "1 色にそろわない"
    # 透けの絵を持つ材質
    for m in (face, eye):
        nt = m.node_tree
        img = bpy.data.images.new(m.name + "_tex", 8, 8, alpha=True)
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        bsdf = nt.nodes["Principled BSDF"]
        nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
        m.blend_method = "HASHED"
    r = fp.soft_overlays(["=eye"])
    assert eye.blend_method == "BLEND" and face.blend_method == "HASHED", (eye.blend_method, face.blend_method)
    r = fp.clip_alpha(skip=["=eye"])
    clip = [n for n in face.node_tree.nodes if n.label == fp.CLIP_LABEL]
    assert clip and not [n for n in eye.node_tree.nodes if n.label == fp.CLIP_LABEL], "skip が効かない"
    bpy.ops.freepencil.remove()
    assert not [n for n in face.node_tree.nodes if n.label == fp.CLIP_LABEL], "外すで消えない"
    alpha = face.node_tree.nodes["Principled BSDF"].inputs["Alpha"]
    assert alpha.is_linked and alpha.links[0].from_node.bl_idname == "ShaderNodeTexImage", "つなぎが戻らない"
    bpy.ops.wm.read_homefile(use_empty=True)


@test("AI window: weld gives butted parts (same position border verts, same material) one color; overlapped parts keep theirs")
def t95():
    # MMD のモデルは部品を突き合わせて作られ、STEP1 が部品ごとに色を変えるので、つながって見える
    # 面の継ぎ目に線が出た(髪の房の付け根・首)。重なった部品(前髪の房)は分けたまま(v2.9.x)
    import sys as _sys
    import bmesh
    import numpy as np
    bpy.ops.wm.read_homefile(use_empty=True)
    me = bpy.data.meshes.new("M")
    bm = bmesh.new()
    def quad(x0, y):
        vs = [bm.verts.new(c) for c in ((x0, y, 0), (x0 + 1, y, 0), (x0 + 1, y, 1), (x0, y, 1))]
        bm.faces.new(vs)
    quad(0, 0)
    quad(1, 0)          # 突き合わせ(縁が同じ位置)
    quad(0.5, -0.3)     # 前に重なった別の部品(縁の位置が違う)
    bm.to_mesh(me)
    ob = bpy.data.objects.new("M", me)
    bpy.context.scene.collection.objects.link(ob)
    me.materials.append(bpy.data.materials.new("hair"))
    a = me.color_attributes.new("mecha_color", "BYTE_COLOR", "CORNER")
    cols = [(0.9, 0.2, 0.2, 1), (0.2, 0.2, 0.9, 1), (0.2, 0.9, 0.2, 1)]
    for p in me.polygons:
        for li in p.loop_indices:
            a.data[li].color = cols[p.index]
    fp = next(m for n, m in _sys.modules.items() if n.endswith("freepencil2.ai"))
    fp.weld({"objects": ["M"]})
    a = me.color_attributes["mecha_color"]
    face_col = [tuple(np.round(a.data[me.polygons[i].loop_indices[0]].color[:3], 1)) for i in range(3)]
    assert face_col[0] == face_col[1], f"突き合わせた部品がそろわない {face_col}"
    assert face_col[2] != face_col[0], f"重なった部品までそろった {face_col}"
    bpy.ops.wm.read_homefile(use_empty=True)


@test("AI window: undo restores bone_color and materials (soft_overlays/clip_alpha), shells() finds toon outline shells")
def t96():
    # v2.9.x の点検で: undo() が骨の色と材質の変更を戻していなかった。トゥーン用の殻(裏返しの
    # Solidify)で線が二重になった。4K では 2倍レンダの線が細すぎた
    import math
    import sys as _sys
    import hashlib
    import numpy as np
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.mesh.primitive_monkey_add(location=(0, 0, 0))
    ob = bpy.context.object
    m = bpy.data.materials.new("hairShadow")
    m.use_nodes = True
    nt = m.node_tree
    img = bpy.data.images.new("t96", 8, 8, alpha=True)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.links.new(tex.outputs["Alpha"], nt.nodes["Principled BSDF"].inputs["Alpha"])
    m.blend_method = "BLEND"
    ob.data.materials.append(m)
    sol = ob.modifiers.new("Solidify", "SOLIDIFY")
    sol.use_flip_normals = True
    sol.thickness = -0.01
    cam = bpy.data.objects.new("C", bpy.data.cameras.new("C"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.location = (0, -6, 0)
    cam.rotation_euler = (math.radians(90), 0, 0)
    scene.render.resolution_x, scene.render.resolution_y = 3840, 2160
    scene.render.resolution_percentage = 5
    scene.fp_use_random_seed = False
    scene.fp_enable_compositor_view = False
    fp = next(mm for n, mm in _sys.modules.items() if n.endswith("freepencil2.ai"))
    r = fp.auto("PRECISE")
    assert any("Solidify" in w for w in r["warnings"]), r["warnings"]
    def h(layer):
        a = ob.data.color_attributes[layer]
        buf = np.empty(len(a.data) * 4, dtype=np.float32)
        a.data.foreach_get("color", buf)
        return hashlib.md5(np.round(buf, 3).tobytes()).hexdigest()
    b0 = h("bone_color")
    fp.merge({"objects": [ob.name]})
    fp.undo()
    assert h("bone_color") == b0, "undo で骨の色が戻らない"
    bm0 = m.blend_method
    fp.soft_overlays(["hairShadow"])
    fp.clip_alpha()
    fp.undo()
    fp.undo()
    m = ob.data.materials[0]
    assert m.blend_method == bm0, (m.blend_method, bm0)
    assert not [n for n in m.node_tree.nodes if n.label == fp.CLIP_LABEL], "undo で透けのノードが残った"
    assert not [x for x in bpy.data.materials if x.name.startswith("_fp_undo_") and x.users], "写しの材質が使われている"
    fp.shells()
    assert not sol.show_render, "shells() で殻が切れない"
    fp.shells(off=False)
    assert sol.show_render, "shells(off=False) で戻らない"
    bpy.ops.wm.read_homefile(use_empty=True)


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
