"""骨の無い人物と、骨付きのメカを見分ける(v3.0)。メカは下の rigged_mecha。

AI が作った人物(Scenario など)は骨(アーマチュア)が無く、腕と胴が 1 つの形でつながっている。
骨で塗り分けられないので同じ色の塊になり、横から見ると腕が胴に溶けて消えた。顔や服は絵
(テクスチャ)にしか描かれておらず、輪郭だけになった。STEP0 はここで見分けた物に絵の線を当て、
人物だけのシーンなら奥行きの線を強くする(auto_setup._finish)。

見分け方(撮った 50 体で測って決めた。dev/note_assets/out/figstats.txt、legs.txt):
  - 骨が無い / 基本色の絵がある
  - 縦長(高さ ÷ 幅 ≥ 1.3)。鹿 1.26・井戸 1.24 で分かれないので、四つ足の動物は入れない
  - 角が少ない(30 度より折れた辺の長さが 4 割以下)。家や車は角が多い
  - 足元の 2 つの高さで輪切りにすると、どちらも 2 つ以上の塊に分かれる(脚)。
    ヤシ・ランタン・ピンクの家・地球儀は縦長で角も少ないが、足元が 1 つの塊
  当てはまったのは boy・chef・girl・medic の 4 体だけ(井戸は脚の輪切りで 2 つになるが縦長で外れる)。
"""

from collections import deque

import bpy

ASPECT_MIN = 1.3
SHARP_MAX = 0.4
SHARP_DEG = 30.0
LEG_SLABS = ((0.05, 0.15), (0.12, 0.25))


def _has_rig(o) -> bool:
    return any(m.type == 'ARMATURE' for m in o.modifiers) or (
        o.parent is not None and o.parent.type == 'ARMATURE')


def _has_image(o) -> bool:
    for s in o.material_slots:
        m = s.material
        if m and m.use_nodes and m.node_tree and any(
                n.type == 'TEX_IMAGE' and n.image for n in m.node_tree.nodes):
            return True
    return False


def _world_verts(o):
    import numpy as np
    me = o.data
    v = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", v)
    v = v.reshape(-1, 3)
    mw = np.array(o.matrix_world, dtype=np.float32)
    return v @ mw[:3, :3].T + mw[:3, 3]


def _blobs(xy, cell) -> int:
    """xy の点を格子に落とし、点の 8% 以上を持つつながった塊の数。"""
    import numpy as np
    if len(xy) < 20:
        return 0
    ij = np.floor((xy - xy.min(0)) / cell).astype(int) + 1
    g = np.zeros(ij.max(0) + 2, dtype=np.int32)
    np.add.at(g, (ij[:, 0], ij[:, 1]), 1)
    occ = g > 0
    lab = np.zeros(g.shape, dtype=bool)
    big = 0
    for s in zip(*np.nonzero(occ)):
        if lab[s]:
            continue
        lab[s] = True
        q = deque([s])
        n = 0
        while q:
            a, b = q.popleft()
            n += int(g[a, b])
            for da in (-1, 0, 1):
                for db in (-1, 0, 1):
                    c = (a + da, b + db)
                    if 0 <= c[0] < g.shape[0] and 0 <= c[1] < g.shape[1] and occ[c] and not lab[c]:
                        lab[c] = True
                        q.append(c)
        if n >= 0.08 * len(xy):
            big += 1
    return big


def _legs(p) -> bool:
    lo, hi = p.min(0), p.max(0)
    h = hi[2] - lo[2]
    cell = max(hi[0] - lo[0], hi[1] - lo[1]) / 40
    if h <= 0 or cell <= 0:
        return False
    for a, b in LEG_SLABS:
        m = (p[:, 2] > lo[2] + a * h) & (p[:, 2] < lo[2] + b * h)
        if _blobs(p[m][:, :2], cell) < 2:
            return False
    return True


def _sharp_fraction(o) -> float:
    """折れた辺(と開いた縁)の長さの割合。"""
    import math
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(o.data)
    lim = math.radians(SHARP_DEG)
    sharp = tot = 0.0
    for e in bm.edges:
        ln = e.calc_length()
        tot += ln
        if len(e.link_faces) != 2 or e.calc_face_angle(0.0) > lim:
            sharp += ln
    bm.free()
    return sharp / tot if tot > 0 else 1.0


def is_rigless_figure(o) -> bool:
    if o.type != 'MESH' or not len(o.data.polygons) or _has_rig(o) or not _has_image(o):
        return False
    p = _world_verts(o)
    d = p.max(0) - p.min(0)
    if d[2] < ASPECT_MIN * max(d[0], d[1]):
        return False
    if not _legs(p):
        return False
    # 角の割合は重いので最後に測る(縦長で脚のある物だけ)
    return _sharp_fraction(o) <= SHARP_MAX


def rigless_figures(objs) -> list:
    """骨の無い人物。複製はメッシュを共有するので、メッシュごとに 1 回だけ測る。"""
    seen = {}
    out = []
    for o in objs:
        key = (o.data, tuple(round(v, 4) for v in o.matrix_world.to_scale()))
        if key not in seen:
            seen[key] = is_rigless_figure(o)
        if seen[key]:
            out.append(o)
    return out


# ---------------------------------------------------------------- 骨付きのメカ
# 骨付きの人 9 体(MMD 2・BlenderKit 7)は、材質名にどれかが必ずあった。eye と body は入れない
# (ザクのモノアイや機体の body に当たる)
SKIN_WORDS = ("skin", "hair", "face", "肌", "髪", "顔")
MECHA_SHARP_DEG = 45.0
# 45 度より折れた辺の割合: 骨付きの人は 0.04〜0.26(最大は宇宙服の space_scavenger)、ザクは 0.38
MECHA_SHARP_MIN = 0.3


def _edge_lengths(o, lim):
    """(折れた辺と開いた縁の長さ, 全部の辺の長さ)。"""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.transform(o.matrix_world)
    sharp = tot = 0.0
    for e in bm.edges:
        ln = e.calc_length()
        tot += ln
        if len(e.link_faces) != 2 or e.calc_face_angle(0.0) > lim:
            sharp += ln
    bm.free()
    return sharp, tot


def rigged_mecha(objs) -> bool:
    """写る骨付きの物がメカ(ロボット)か。骨付きの物が無ければ False。

    人は材質名に肌・髪・顔のどれかがあり、面がなめらか。メカはそれが無く、角が多い。
    骨の無い物(AI が作った物)は角の多さで分からなかった(red_mecha 0.10、girl 0.29)ので見ない。
    """
    import math
    rigged = [o for o in objs if o.type == 'MESH' and len(o.data.polygons) and _has_rig(o)]
    if not rigged:
        return False
    for o in rigged:
        for s in o.material_slots:
            if s.material and any(w in s.material.name.lower() for w in SKIN_WORDS):
                return False
    lim = math.radians(MECHA_SHARP_DEG)
    sharp = tot = 0.0
    seen = set()
    for o in rigged:
        if o.data in seen:
            continue
        seen.add(o.data)
        a, b = _edge_lengths(o, lim)
        sharp += a
        tot += b
    return tot > 0 and sharp / tot >= MECHA_SHARP_MIN
