"""生成したコンポジタノードの配置を検査する。

「見た目が汚い」を主観で終わらせないための計測。次を数える:
  - 重なり: ノード同士の矩形が重複している組
  - 逆流リンク: 出力元が接続先より右にある(線が左へ戻る)
  - 交差: リンク同士が視覚的に交差している組
  - 密集: 隣接ノードの水平間隔のばらつき

  blender -b --factory-startup --python inspect_node_layout.py -- [--json out.json]
"""
from __future__ import annotations

import itertools
import json
import statistics
import sys
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))

import fp_batch  # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

bpy.ops.wm.read_homefile(use_empty=True)
fp_batch.install_addon()

# 立方体1つで STEP0 まで通し、生成されたツリーを見る
bpy.ops.mesh.primitive_cube_add()
bpy.context.active_object.select_set(True)
bpy.context.scene.fp_node_type = "pro"
bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")


def rect(node):
    """ノードの概略矩形 (x0, y0, x1, y1)。y は下向きが負。"""
    w = node.width or 140.0
    # dimensions はUIが無いと 0 になることがあるので、ソケット数から概算
    h = node.dimensions.y
    if not h:
        h = 40.0 + 22.0 * (len(node.inputs) + len(node.outputs))
    x, y = node.location
    return (x, y - h, x + w, y)


def overlap(a, b) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    dx = min(ax1, bx1) - max(ax0, bx0)
    dy = min(ay1, by1) - max(ay0, by0)
    return dx * dy if dx > 0 and dy > 0 else 0.0


def segments_cross(p1, p2, p3, p4) -> bool:
    def ccw(a, b, c):
        return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])
    return (ccw(p1, p3, p4) != ccw(p2, p3, p4)
            and ccw(p1, p2, p3) != ccw(p1, p2, p4))


def analyse(tree, label) -> dict:
    nodes = [n for n in tree.nodes]
    rects = {n.name: rect(n) for n in nodes}

    overlaps = []
    for a, b in itertools.combinations(nodes, 2):
        area = overlap(rects[a.name], rects[b.name])
        if area > 1.0:
            overlaps.append({"a": a.name[:28], "b": b.name[:28],
                             "area": round(area)})

    backward, segs = [], []
    for lk in tree.links:
        fx = rects[lk.from_node.name][2]     # 出力側の右端
        tx = rects[lk.to_node.name][0]       # 入力側の左端
        fy = (rects[lk.from_node.name][1] + rects[lk.from_node.name][3]) / 2
        ty = (rects[lk.to_node.name][1] + rects[lk.to_node.name][3]) / 2
        segs.append(((fx, fy), (tx, ty)))
        if tx < fx:
            backward.append({"from": lk.from_node.name[:26],
                             "to": lk.to_node.name[:26],
                             "back": round(fx - tx)})

    crossings = sum(1 for (s1, s2) in itertools.combinations(segs, 2)
                    if segments_cross(s1[0], s1[1], s2[0], s2[1]))

    xs = sorted(r[0] for r in rects.values())
    gaps = [round(b - a) for a, b in zip(xs, xs[1:]) if b - a > 1]

    same_pos = {}
    for n in nodes:
        key = (round(n.location.x), round(n.location.y))
        same_pos.setdefault(key, []).append(n.name)
    stacked = {f"{k[0]},{k[1]}": v for k, v in same_pos.items() if len(v) > 1}

    return {
        "tree": label,
        "nodes": len(nodes),
        "links": len(tree.links),
        "overlapping_pairs": len(overlaps),
        "worst_overlaps": sorted(overlaps, key=lambda o: -o["area"])[:6],
        "exactly_stacked": stacked,
        "backward_links": len(backward),
        "worst_backward": sorted(backward, key=lambda b: -b["back"])[:5],
        "link_crossings": crossings,
        "x_span": round(max(xs) - min(xs)) if xs else 0,
        "x_gap_median": statistics.median(gaps) if gaps else 0,
        "x_gap_max": max(gaps) if gaps else 0,
    }


report = []
scene = bpy.context.scene
root = scene.compositing_node_group if hasattr(
    scene, "compositing_node_group") else scene.node_tree
if root is not None:
    report.append(analyse(root, "scene root"))
for ng in bpy.data.node_groups:
    if ng.name.startswith("FreePencil"):
        report.append(analyse(ng, ng.name))

print("[layout] " + json.dumps(report, ensure_ascii=False))
if "--json" in ARGV:
    Path(ARGV[ARGV.index("--json") + 1]).resolve().write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
