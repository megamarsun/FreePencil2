"""生成したノードツリーを読める配置に整える。

ノードの座標はエクスポート元 .blend の手配置がそのまま入っており、
実測すると PRO ノード(80個)で重なり97組・リンクの半数近く(97本中47本)が
右から左へ逆流していた。機能には影響しないが、ユーザーがコンポジタを
開いたときに何が起きているか読めない。

階層レイアウト(いわゆる Sugiyama 風)で組み直す:
  1. 入力から見た最長経路で「層」を決める -> 逆流リンクが構造的に消える
  2. 層の中では前段ノードの重心順に並べる -> 交差を減らす
  3. 層の実幅・実高から座標を振る -> 重なりが構造的に消える

配置しか触らないので、リンクもソケット値も変わらない。
"""

from __future__ import annotations

import bpy

# 層と層の間隔、同じ層の縦間隔
X_GAP = 90.0
Y_GAP = 40.0
# dimensions は UI が無いと 0 になるので、ソケット数から高さを見積もる
BASE_HEIGHT = 46.0
SOCKET_HEIGHT = 24.0


def _height(node: bpy.types.Node) -> float:
    h = getattr(node.dimensions, "y", 0.0)
    if h:
        return float(h)
    return BASE_HEIGHT + SOCKET_HEIGHT * (len(node.inputs) + len(node.outputs))


def _width(node: bpy.types.Node) -> float:
    return float(node.width or 140.0)


def _assign_layers(nodes, links) -> dict:
    """各ノードの層番号。入力側からの最長経路で決める。"""
    preds = {n.name: set() for n in nodes}
    succs = {n.name: set() for n in nodes}
    for lk in links:
        a, b = lk.from_node.name, lk.to_node.name
        if a == b or a not in preds or b not in preds:
            continue
        preds[b].add(a)
        succs[a].add(b)

    layer = {n.name: 0 for n in nodes}
    # 反復緩和。ノード数ぶん回せば DAG なら必ず収束する。
    # 万一循環があっても回数で打ち切るので固まらない
    for _ in range(len(nodes) + 1):
        changed = False
        for name, ps in preds.items():
            if not ps:
                continue
            want = max(layer[p] for p in ps) + 1
            if want > layer[name]:
                layer[name] = want
                changed = True
        if not changed:
            break
    return layer


def _count_crossings(order: dict, edges: list) -> int:
    """隣接層間のリンク交差数。順位だけで数える(座標は不要)。"""
    total = 0
    for i in range(len(edges)):
        a1, b1 = edges[i]
        for j in range(i + 1, len(edges)):
            a2, b2 = edges[j]
            if (order[a1] - order[a2]) * (order[b1] - order[b2]) < 0:
                total += 1
    return total


def _order_layers(by_layer: dict, links) -> dict:
    """層内の並び順を重心法の反復で決める。

    前段の重心で並べる -> 後段の重心で並べる、を往復し、交差が
    いちばん少なかった並びを採用する。1回で止めると交差が減らない。
    """
    layers = sorted(by_layer)
    order = {}
    for li in layers:
        for pos, n in enumerate(sorted(by_layer[li], key=lambda x: x.name)):
            order[n.name] = pos

    preds: dict[str, list] = {}
    succs: dict[str, list] = {}
    pair_edges: dict[int, list] = {li: [] for li in layers}
    layer_of = {n.name: li for li in layers for n in by_layer[li]}
    for lk in links:
        a, b = lk.from_node.name, lk.to_node.name
        if a not in layer_of or b not in layer_of or a == b:
            continue
        preds.setdefault(b, []).append(a)
        succs.setdefault(a, []).append(b)
        if layer_of[b] - layer_of[a] == 1:
            pair_edges[layer_of[b]].append((a, b))

    def total_crossings() -> int:
        return sum(_count_crossings(order, es) for es in pair_edges.values())

    def renumber(li):
        group = sorted(by_layer[li], key=lambda n: (order[n.name], n.name))
        for pos, n in enumerate(group):
            order[n.name] = pos

    best = dict(order)
    best_score = total_crossings()

    for sweep in range(8):
        side = preds if sweep % 2 == 0 else succs
        seq = layers if sweep % 2 == 0 else list(reversed(layers))
        for li in seq:
            for n in by_layer[li]:
                ref = [order[m] for m in side.get(n.name, []) if m in order]
                if ref:
                    order[n.name] = sum(ref) / len(ref)
            renumber(li)
        score = total_crossings()
        if score < best_score:
            best, best_score = dict(order), score
        else:
            order = dict(best)

    return best


def layout_tree(tree: bpy.types.NodeTree) -> dict:
    """ツリーの配置を組み直し、結果の要約を返す。"""
    nodes = [n for n in tree.nodes]
    if not nodes:
        return {"nodes": 0}

    layer = _assign_layers(nodes, tree.links)
    by_layer: dict[int, list] = {}
    for n in nodes:
        by_layer.setdefault(layer[n.name], []).append(n)

    order = _order_layers(by_layer, tree.links)

    x = 0.0
    for li in sorted(by_layer):
        group = sorted(by_layer[li], key=lambda n: (order[n.name], n.name))
        y = 0.0
        for n in group:
            n.location = (x, y)
            y -= _height(n) + Y_GAP
        x += max(_width(n) for n in group) + X_GAP

    return {"nodes": len(nodes), "layers": len(by_layer)}


def layout_freepencil_trees(scene: bpy.types.Scene | None = None) -> list:
    """FreePencil が作ったツリーをまとめて整列する。"""
    done = []
    for ng in bpy.data.node_groups:
        if ng.name.startswith("FreePencil"):
            done.append((ng.name, layout_tree(ng)))
    if scene is not None:
        root = getattr(scene, "compositing_node_group", None)
        if root is None:
            root = getattr(scene, "node_tree", None)
        if root is not None:
            done.append(("scene", layout_tree(root)))
    return done
