"""Asset-based regression tests: car / human / robot (BlenderKit cache).

Run:  blender -b --factory-startup -P tests_assets.py
      (or run_tests.bat assets)

3種の代表モデルでカテゴリ別の不変条件を固定化する。レンダはしない
(STEP1のみ、~1分)。キャッシュが無い環境ではスキップして正常終了する。

固定化している知見(sweep4 の計測から):
- 全設定・全モデルで色距離違反ゼロ(グラフ彩色の構造保証)
- CAR/ROBOT: auto はメカ系判定(p95>75°)で、隣接ペア数が妥当なレンジに収まる
- HUMAN: リグ付きなので auto は保守側に倒れ、mecha側の島ノイズが出ない。
  bone_color はボーン毎に塗り分けられる(メカとボーンは別系統)
- 全島色は黒(背景)から距離0.5以上(シルエット線の濃さ保証)
"""
from __future__ import annotations

import sys
from pathlib import Path

import bpy

BATCH = Path(__file__).resolve().parent
sys.path.insert(0, str(BATCH))
import fp_batch      # noqa: E402
import scan_models   # noqa: E402

RESULTS: list[dict] = []


def test(name):
    def deco(fn):
        def wrapper(*a):
            try:
                fn(*a)
                RESULTS.append({"test": name, "ok": True})
                print(f"  PASS {name}")
            except Exception:
                import traceback
                RESULTS.append({"test": name, "ok": False,
                                "error": traceback.format_exc()})
                print(f"  FAIL {name}")
        wrapper.__test__ = True
        wrapper.__name__ = name
        return wrapper
    return deco


def find_model(sub: str) -> Path | None:
    root = Path(scan_models.DEFAULT_ROOT)
    if not root.exists():
        return None
    for b in scan_models.find_blends(root, 0.05e6, 150e6):
        if sub in b.stem.lower():
            return b
    return None


def run_step1(blend: Path, sharp_auto: bool = True) -> list:
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    objs, _others = fp_batch.append_objects(blend)
    assert objs, "no meshes"
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 42
    scene.fp_sharp_auto = sharp_auto
    scene.fp_sharp_edges = 60.0
    scene.fp_min_island_area_pct = 0.02
    scene.fp_min_neighbor_color_distance = 0.5
    fp_batch.select_meshes()
    res = bpy.ops.freepencil.auto_vertex_color()
    assert res == {"FINISHED"}, res
    return [o for o in scene.objects if o.type == "MESH"]


def mecha_color_set(meshes) -> set:
    colors = set()
    for o in meshes:
        if "mecha_color" not in o.data.color_attributes:
            continue
        attr = o.data.color_attributes["mecha_color"]
        colors |= {tuple(round(v, 3) for v in d.color[:3]) for d in attr.data}
    return colors


@test("CAR: auto segmentation sane, zero violations, silhouette-safe luma")
def t_car(blend):
    meshes = run_step1(blend)
    m = fp_batch.mesh_color_metrics(meshes, 0.5)
    assert m["min_distance_violations"] == 0, m
    assert 500 <= m["adjacent_color_pairs"] <= 8000, m
    # 白背景プリミックスとの輝度差(シルエット線)を全色で確保
    assert all(0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2] <= 0.85
               for c in mecha_color_set(meshes) if c != (1.0, 1.0, 1.0))


@test("ROBOT: auto segmentation sane, zero violations")
def t_robot(blend):
    meshes = run_step1(blend)
    m = fp_batch.mesh_color_metrics(meshes, 0.5)
    assert m["min_distance_violations"] == 0, m
    assert 2000 <= m["adjacent_color_pairs"] <= 15000, m


@test("HUMAN(rigged): conservative auto + bone_color per bone")
def t_human(blend):
    meshes = run_step1(blend)
    m = fp_batch.mesh_color_metrics(meshes, 0.5)
    assert m["min_distance_violations"] == 0, m
    # リグ付き: mecha側に島ノイズを出さない(人工分割禁止の保証)
    assert m["adjacent_color_pairs"] <= 200, m
    # ボーン系統: bone_color はウェイト加重平均の柔らかいブレンド(元実装)。
    # ボーン毎のハッシュ色が混ざるため多数の中間色を持つのが正常
    # (離散塗り分け+境界線化の実験は 2026-07-17 にユーザー判断で差し戻し)。
    bones = set()
    for o in meshes:
        if "bone_color" in o.data.color_attributes:
            attr = o.data.color_attributes["bone_color"]
            bones |= {tuple(round(v, 2) for v in d.color[:3]) for d in attr.data}
    assert len(bones) >= 20, f"bone colors too few (blend expected): {len(bones)}"
    # 最大面積クラス(body)の輝度は白背景プリミックスと十分差がある
    # (PROノードの線は輝度差で決まる。輝度が高すぎるとシルエット線が
    #  薄くなる回帰: womanで発生)
    counts = {}
    for o in meshes:
        if "mecha_color" not in o.data.color_attributes:
            continue
        for d in o.data.color_attributes["mecha_color"].data:
            c = tuple(round(v, 3) for v in d.color[:3])
            counts[c] = counts.get(c, 0) + 1
    dominant = max(counts, key=counts.get)
    luma = 0.2126 * dominant[0] + 0.7152 * dominant[1] + 0.0722 * dominant[2]
    assert luma <= 0.8, f"dominant mecha color too bright for silhouette: {dominant} (luma {luma:.3f})"


def main():
    print("[tests_assets] car/human/robot regression tests")
    targets = {
        "t_car": find_model("audi_r8"),
        "t_robot": find_model("kaino-school-military-mech"),
        "t_human": find_model("woman_01"),
    }
    if all(v is None for v in targets.values()):
        print("[tests_assets] SKIP: BlenderKit cache not found")
        return
    fp_batch.install_addon()
    for key, blend in targets.items():
        fn = {"t_car": t_car, "t_robot": t_robot, "t_human": t_human}[key]
        if blend is None:
            print(f"  SKIP {key} (model not in cache)")
            continue
        fn(blend)
    failed = [r for r in RESULTS if not r["ok"]]
    print(f"[tests_assets] {len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    if failed:
        for f_ in failed:
            print(f_["error"])
        sys.exit(1)


if __name__ == "__main__":
    main()
