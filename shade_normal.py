"""影の形(v3.0 試作): セルの影を、面の向きでなく「体の大きな形」で取る。

いまのセルの影は面の向き(法線のパス)そのままで、服のシワ・三角形・ノーマルマップが
影の形になり、まだらになった。アニメの影は描く人が「腕は筒、頭は球」と決めた形で付く。
その形(プロキシ)を手で作る代わりに、STEP0 が持っている骨と塊から作り、頂点カラーに書く。

  - 骨のある物: 骨ごとに、その骨が動かす頂点に筒を当て、筒の軸から頂点への向きを骨の重みで混ぜる。
    髪(材質の名前)は、毛束の骨の筒だとまだらになったので、頭の中心からの球
  - 骨の無い物: つながった塊が丸い物(角がほぼ無く、薄い板でない)なら、主成分で当てた楕円体の向き
  - どちらも、角(SHARP_DEG より折れた辺)で切ってからならした面の向きと混ぜる。
    形と面が食い違う所は面の向きに戻す
    (切らずにならすと建物の壁の面ごとの明暗が消えた、dev/batch/out/report_shade_survey)

書き方: 物の向きで頂点カラー fp_shade_o(角ごと)に書く。材質はこれを AOV(fp_shade_n = 向き、
fp_shade_k = 書いてある印)に出すだけで、法線のパスも絵も変えない。ポーズを大きく変えたら書き直す。
接空間(UV の向き)で書けばポーズに付いてくるが、描くときの基準が細分化の後の面になり、
シワと UV の左右の継ぎ目の線が影に戻った(woman_01 のシャツ)。
セルの光(cel_shade.light_socket)が fp_cel_shape の割合でこちらの向きを使う。

メッシュに直接カスタム法線を書く方法は、細分化モディファイアが捨てて効かなかった(woman_01)。
"""
from __future__ import annotations

import logging
import math
import re

import bpy
import numpy as np

logger = logging.getLogger(__name__)

ATTR_O = "fp_shade_o"          # 物の向き(0..1 に詰めた物)、角ごと
AOV_N = "fp_shade_n"
AOV_K = "fp_shade_k"
NODE_LABEL = "FreePencil_shade_n"
SHARP_DEG = 35.0               # これより折れた辺で切る(試作で 4 体を見て決めた)
SHAPE_MIX = 0.9                # 形の向きの割合(残りは面の向きをならした物)。0.75 ではズボンの影の縁がシワでぎざぎざ
SMOOTH_R = 0.04                # 面の向きをならす半径(物の対角に対する割合)
SHORT_LEAF = 0.08              # 背丈に対してこれより短い末端の骨(胸・目・指先)は親の骨に寄せる
FLAT = 0.2                     # 一番薄い向きの厚みがこれ(一番長い向きに対する割合)未満の塊は板として楕円体にしない
BONE_FIT = 0.5                 # 骨の筒の向きと面の向きの内積の平均がこれ未満の骨は使わない
AGREE = (0.2, 0.6)             # 形の向きと面の向きの内積がこの間で、形の割合を 0 から 1 へ(食い違う所は面の向き)
HAIR_RE = re.compile(r"hair|髪|ヘア|かみ", re.IGNORECASE)


# ---------------------------------------------------------------- 形の向き

def _weld(p):
    """同じ位置の頂点(UV の切れ目で分かれた物)を 1 つにまとめた番号。"""
    span = max(float(np.ptp(p, axis=0).max()), 1e-6)
    key = np.round(p / span * 1e5).astype(np.int64)
    _, w = np.unique(key, axis=0, return_inverse=True)
    return w.ravel()


def _union(n, pairs):
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for a, b in pairs:
        ra, rb = find(int(a)), find(int(b))
        if ra != rb:
            parent[ra] = rb
    return np.array([find(i) for i in range(n)])


def _norm(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-9)


def _ellipsoid(p, comp, use):
    """塊ごとに主成分で楕円体を当て、その面の向き。use の塊だけ。薄い板は当てない
    (家の壁板の面の上で向きが変わり、平らな板にまだらの影が出た)。"""
    out = np.zeros_like(p)
    for c in np.unique(comp[use]):
        idx = np.where(comp == c)[0]
        q = p[idx] - p[idx].mean(0)
        if len(idx) < 8:
            continue
        w, vec = np.linalg.eigh(np.cov(q.T))
        if w[0] < (FLAT * FLAT) * w[2]:
            continue
        out[idx] = ((q @ vec) / np.maximum(w, 1e-12)) @ vec.T
    return out


HEAD_RE = re.compile(r"head|頭", re.IGNORECASE)
END_RE = re.compile(r"end|top|tip|nub|先", re.IGNORECASE)


def _head_bone(arm):
    """頭の骨。Mixamo の HeadTop_End や MMD の頭先(頭の上の飾りの骨)は除く。"""
    heads = [pb for pb in arm.pose.bones if pb.bone.use_deform and HEAD_RE.search(pb.name)]
    heads = [pb for pb in heads if not END_RE.search(pb.name)] or heads
    return max(heads, key=lambda b: b.length) if heads else None


def _hair_mask(o, me, poly_of_loop, loop_vert):
    n = len(me.vertices)
    if HAIR_RE.search(o.name):
        return np.ones(n, bool)
    names = [bool(sl.material and HAIR_RE.search(sl.material.name)) for sl in o.material_slots]
    hair_v = np.zeros(n, bool)
    if any(names):
        mi = np.empty(len(me.polygons), np.int64)
        me.polygons.foreach_get("material_index", mi)
        hm = np.array(names)[np.minimum(mi, len(names) - 1)]
        hair_v[loop_vert[hm[poly_of_loop]]] = True
    return hair_v


def _capsules(o, me, p, poly_of_loop, loop_vert, geo_v):
    """骨の筒の向き(頂点ごと)と、その強さ(0..1)。骨が無ければ None。

    筒の軸は、その骨が動かす頂点の重心を通る線。向きは頂点が細長く並んでいればその並び、
    そうでなければ骨の向き。骨そのものの位置は使わない: MMD の骨はメッシュの外や妙な向きの物があり、
    影が服の上で斑になった(Alicia)。端を丸めた球(カプセル)にすると、短い骨の端に小さな球ができて
    明るい塊が出た(woman_01 の胸、Akari の胴)ので、ただの筒にする。
    筒の向きが面の向きと平均で合わない骨(布の 1 枚だけを動かすスカートの骨: 軸が布の上に来る)は使わない
    (Alicia のスカートが影に沈んだ)。
    髪は頭の中心からの球。頭から離れた所(ポニーテールの先)は面の向きに戻す。
    """
    arm = next((md.object for md in o.modifiers if md.type == "ARMATURE" and md.object
                and md.object.type == "ARMATURE"), None)
    if arm is None or not o.vertex_groups:
        return None
    deform = [pb for pb in arm.pose.bones if pb.bone.use_deform]
    if not deform:
        return None
    ends = np.array([arm.matrix_world @ v for pb in deform for v in (pb.head, pb.tail)])
    height = max(float(np.ptp(ends, axis=0).max()), 1e-6)
    head = _head_bone(arm)

    def owner(pb):
        # 短い末端の骨(胸・目・指先)は親の骨の筒に入れる
        while (pb.parent is not None and pb.parent.bone.use_deform and pb.length < SHORT_LEAF * height
               and pb is not head and not any(c.bone.use_deform for c in pb.children)):
            pb = pb.parent
        return pb
    owners, gid2own = [], {}
    for pb in deform:
        vg = o.vertex_groups.get(pb.name)
        if vg is None:
            continue
        ob = owner(pb)
        if ob not in owners:
            owners.append(ob)
        gid2own[vg.index] = owners.index(ob)
    if not gid2own:
        return None
    rows, own, wts = [], [], []
    for v in me.vertices:
        for g in v.groups:
            k = gid2own.get(g.group)
            if k is not None and g.weight > 0.0:
                rows.append(v.index)
                own.append(k)
                wts.append(g.weight)
    if not rows:
        return None
    rows, own, wts = np.array(rows), np.array(own), np.array(wts)
    n = len(me.vertices)
    cen = np.zeros((len(owners), 3))
    axis = np.zeros((len(owners), 3))
    good = np.zeros(len(owners), bool)
    for k, pb in enumerate(owners):
        m = own == k
        if m.sum() < 6:
            continue
        idx, w = rows[m], wts[m]
        c = (p[idx] * w[:, None]).sum(0) / w.sum()
        q = p[idx] - c
        lam, vec = np.linalg.eigh((q * w[:, None]).T @ q / w.sum())
        bone_dir = np.array(arm.matrix_world.to_3x3() @ (pb.tail - pb.head))
        if lam[2] >= 6.25 * max(lam[1], 1e-12) or np.linalg.norm(bone_dir) < 1e-9:
            d = vec[:, 2]                       # 細長い(2.5 倍以上): 頂点の並び
        else:
            d = bone_dir / np.linalg.norm(bone_dir)
        cen[k], axis[k], good[k] = c, d, True
    m = good[own]
    rows, own, wts = rows[m], own[m], wts[m]
    q = p[rows] - cen[own]
    r = q - (q * axis[own]).sum(1, keepdims=True) * axis[own]
    fit = np.bincount(own, weights=wts * (_norm(r) * geo_v[rows]).sum(1), minlength=len(owners))         / np.maximum(np.bincount(own, weights=wts, minlength=len(owners)), 1e-12)
    m = fit[own] >= BONE_FIT
    rows, own, wts, r = rows[m], own[m], wts[m], r[m]
    # 骨の軸のすぐそばの頂点は向きが定まらない(丸い点になる)ので、その骨の太さの半分より内側は弱める
    rl = np.linalg.norm(r, axis=1)
    med = np.zeros(len(owners))
    for k in np.unique(own):
        med[k] = np.median(rl[own == k])
    wts = wts * np.clip(rl / np.maximum(0.5 * med[own], 1e-9), 0.0, 1.0)
    acc = np.zeros((n, 3))
    np.add.at(acc, rows, wts[:, None] * _norm(r))
    wsum = np.zeros(n)
    np.add.at(wsum, rows, wts)
    strength = np.minimum(wsum, 1.0)
    hair = _hair_mask(o, me, poly_of_loop, loop_vert)
    if head is not None and hair.any():
        # 頭の中心: 頭の骨が動かす髪でない頂点(顔・頭)の重心。無ければ骨の中ほど
        hk = owners.index(head) if head in owners else -1
        sel = rows[(own == hk) & ~hair[rows]] if hk >= 0 else np.array([], np.int64)
        c = p[sel].mean(0) if len(sel) >= 20 else np.array(arm.matrix_world @ ((head.head + head.tail) * 0.5))
        d = p[hair] - c
        dist = np.linalg.norm(d, axis=1)
        r0 = max(float(np.percentile(dist, 30)), 1e-6)     # 頭の丸み(髪の下の方 3 割の距離)
        fade = np.clip((2.5 * r0 - dist) / r0, 0.0, 1.0)
        acc[hair] = d
        strength[hair] = fade
    return acc, strength


def _shade_vectors(o, me, M):
    """角ごとの影の向き(ワールド)を返す。me はポーズとシェイプキーだけ効いた形。"""
    nv, nl, nf = len(me.vertices), len(me.loops), len(me.polygons)
    co = np.empty(nv * 3)
    me.vertices.foreach_get("co", co)
    M3 = np.array(M)[:3, :3]
    p = co.reshape(-1, 3) @ M3.T + np.array(M)[:3, 3]
    loop_vert = np.empty(nl, np.int64)
    me.loops.foreach_get("vertex_index", loop_vert)
    start = np.empty(nf, np.int64)
    total = np.empty(nf, np.int64)
    me.polygons.foreach_get("loop_start", start)
    me.polygons.foreach_get("loop_total", total)
    poly_of_loop = np.repeat(np.arange(nf), total)
    nxt = np.arange(nl) + 1
    last = start + total - 1
    nxt[last] = start
    fn = np.empty(nf * 3)
    me.polygons.foreach_get("normal", fn)
    fn = _norm(fn.reshape(-1, 3) @ np.linalg.inv(M3))
    area = np.empty(nf)
    me.polygons.foreach_get("area", area)
    weld = _weld(p)
    wl = weld[loop_vert]
    a, b = np.minimum(wl, wl[nxt]), np.maximum(wl, wl[nxt])
    _, eid = np.unique(a * (weld.max() + 1) + b, return_inverse=True)
    eid = eid.ravel()
    order = np.argsort(eid, kind="stable")
    es, fs = eid[order], poly_of_loop[order]
    cnt = np.bincount(eid)
    two = cnt[es] == 2
    first = np.r_[True, es[1:] != es[:-1]]
    i0 = np.where(first & two)[0]
    f1, f2 = fs[i0], fs[i0 + 1]
    smooth = (fn[f1] * fn[f2]).sum(1) > math.cos(math.radians(SHARP_DEG))
    pairs = np.stack([f1[smooth], f2[smooth]], 1)
    region = _union(nf, pairs)
    # 面の向きを、角を越えずにならす。回数は「物の大きさに対する半径」から(細かいメッシュほど多く)
    elen = np.linalg.norm(p[loop_vert] - p[loop_vert[nxt]], axis=1)
    e = max(float(np.median(elen)), 1e-6)
    diag = float(np.linalg.norm(np.ptp(p, axis=0)))
    iters = int(min(max((SMOOTH_R * diag / e) ** 2, 4), 400))
    v = fn * np.maximum(area, 1e-12)[:, None]
    v = _norm(v)
    for _ in range(iters):
        s = v.copy()
        np.add.at(s, pairs[:, 0], v[pairs[:, 1]])
        np.add.at(s, pairs[:, 1], v[pairs[:, 0]])
        v = _norm(s)
    # 角ごと: 同じ頂点で同じ面のまとまりにある面の向きの平均(面の大きさで重み)
    key = wl * (nf + 1) + region[poly_of_loop]
    _, kinv = np.unique(key, return_inverse=True)
    kinv = kinv.ravel()
    acc = np.zeros((kinv.max() + 1, 3))
    np.add.at(acc, kinv, v[poly_of_loop] * area[poly_of_loop, None])
    geo = _norm(acc)[kinv]
    # 形の向き
    shape = np.zeros((nl, 3))
    strength = np.zeros(nl)
    geo_v = np.zeros((nv, 3))
    np.add.at(geo_v, loop_vert, geo)
    cap = _capsules(o, me, p, poly_of_loop, loop_vert, _norm(geo_v))
    kind = "bones"
    if cap is not None:
        accv, sv = cap
        shape = accv[loop_vert]
        strength = sv[loop_vert]
    else:
        kind = "ellipsoid"
        # 角がほぼ無い塊だけ楕円体にする(建物の壁は平らなまま)
        comp_f = _union(nf, np.stack([f1, f2], 1))
        sharp_f = np.zeros(nf)
        np.add.at(sharp_f, f1[~smooth], 1)
        np.add.at(sharp_f, f2[~smooth], 1)
        edges_f = np.zeros(nf)
        np.add.at(edges_f, f1, 1)
        np.add.at(edges_f, f2, 1)
        cs = np.bincount(comp_f, weights=sharp_f)
        ce = np.bincount(comp_f, weights=edges_f)
        soft_f = (cs < 0.02 * np.maximum(ce, 1))[comp_f]
        if soft_f.any():
            comp_v = np.zeros(weld.max() + 1, np.int64)
            comp_v[wl] = comp_f[poly_of_loop]
            pw = np.zeros((weld.max() + 1, 3))
            pw[weld] = p
            use = np.zeros(weld.max() + 1, bool)
            use[wl[soft_f[poly_of_loop]]] = True
            shape = _ellipsoid(pw, comp_v, use)[wl]
            strength = (soft_f[poly_of_loop] & (np.linalg.norm(shape, axis=1) > 1e-9)).astype(float)
    shape = _norm(shape)
    # 形と面が食い違う所(凹み・骨の外の部品・頭から離れた髪)は、だんだん面の向きに戻す
    agree = np.clip(((shape * geo).sum(1) - AGREE[0]) / (AGREE[1] - AGREE[0]), 0.0, 1.0)
    k = SHAPE_MIX * strength * agree
    ok = k > 0.0
    out = _norm((1.0 - k)[:, None] * geo + k[:, None] * shape)
    return out, kind, int(ok.sum())


# ---------------------------------------------------------------- 書く

def _write(o, vals):
    ca = o.data.color_attributes
    a = ca.get(ATTR_O)
    if a is not None and (a.domain != "CORNER" or a.data_type != "FLOAT_COLOR"):
        ca.remove(a)
        a = None
    if a is None:
        a = ca.new(ATTR_O, "FLOAT_COLOR", "CORNER")
    rgba = np.concatenate([vals * 0.5 + 0.5, np.ones((len(vals), 1))], 1).astype(np.float32)
    a.data.foreach_set("color", rgba.ravel())


def bake_object(o, depsgraph) -> str:
    """1 つの物に影の向きを書く。書いた方式("bones" / "ellipsoid" / "flat")か、飛ばした理由を返す。"""
    base = o.data
    # 細分化などを止めて、ポーズとシェイプキーだけ効いた形を取る(頂点と角の番号が元と同じになる)
    saved = [(md, md.show_viewport) for md in o.modifiers if md.type != "ARMATURE"]
    for md, _ in saved:
        md.show_viewport = False
    try:
        depsgraph.update()
        ev = o.evaluated_get(depsgraph)
        me = ev.to_mesh()
        try:
            if len(me.vertices) != len(base.vertices) or len(me.loops) != len(base.loops):
                return "skip: topology"
            vals, kind, n_shape = _shade_vectors(o, me, o.matrix_world)
            M3 = np.array(o.matrix_world)[:3, :3]
            _write(o, _norm(vals @ M3))            # ワールドの向き -> 物の向き(法線の変換)
            return kind if n_shape else "flat"
        finally:
            ev.to_mesh_clear()
    finally:
        for md, s in saved:
            md.show_viewport = s


def bake(scene, view_layer, objects=None) -> dict:
    """影の向きを物に書き、材質と AOV を用意する。数を返す。"""
    objs = objects if objects is not None else [
        o for o in scene.objects if o.type == "MESH" and o.data is not None and len(o.data.polygons)
        and not o.hide_render]
    dg = bpy.context.evaluated_depsgraph_get()
    done, why = {}, {}
    seen = set()
    for o in objs:
        if o.data.name in seen:                     # 同じメッシュを使う物は 1 度だけ
            continue
        seen.add(o.data.name)
        try:
            r = bake_object(o, dg)
        except Exception:
            logger.exception(f"Shadow shape: failed on {o.name}")
            r = "skip: error"
        (why if r.startswith("skip") else done).setdefault(r, []).append(o.name)
    dg.update()
    ensure_scene(scene, view_layer)
    return {"done": {k: len(v) for k, v in done.items()}, "skipped": {k: v for k, v in why.items()}}


def clear(scene) -> int:
    n = 0
    for o in scene.objects:
        if o.type == "MESH" and o.data is not None:
            a = o.data.color_attributes.get(ATTR_O)
            if a is not None:
                o.data.color_attributes.remove(a)
                n += 1
    return n


def has_bake(scene) -> bool:
    return any(o.type == "MESH" and o.data is not None and ATTR_O in o.data.color_attributes
               for o in scene.objects)


# ---------------------------------------------------------------- 材質と AOV

def _ensure_material(m) -> bool:
    nt = m.node_tree
    nodes = nt.nodes
    have = any(n.label == NODE_LABEL and n.type == "OUTPUT_AOV" and n.aov_name == AOV_N for n in nodes)
    if not have:
        for n in [n for n in nodes if n.label == NODE_LABEL]:
            nodes.remove(n)
        made = []

        def add(t, **kw):
            n = nodes.new(t)
            for k, v in kw.items():
                setattr(n, k, v)
            n.label = NODE_LABEL
            n.hide = True
            n.location = (10 + 160 * (len(made) % 6), 1100 + 40 * (len(made) // 6))
            made.append(n)
            return n
        L = nt.links

        def decoded(attr_name):
            at = add("ShaderNodeAttribute", attribute_name=attr_name, attribute_type="GEOMETRY")
            v = add("ShaderNodeVectorMath", operation="MULTIPLY_ADD")
            v.inputs[1].default_value = (2.0, 2.0, 2.0)
            v.inputs[2].default_value = (-1.0, -1.0, -1.0)
            L.new(at.outputs["Vector"], v.inputs[0])
            # 書いていない物は (0,0,0) -> 長さ 1.73。書いた向きは長さ 1
            ln = add("ShaderNodeVectorMath", operation="LENGTH")
            L.new(v.outputs[0], ln.inputs[0])
            has = add("ShaderNodeMath", operation="LESS_THAN")
            L.new(ln.outputs["Value"], has.inputs[0])
            has.inputs[1].default_value = 1.3
            return at, v, has
        _ao, v_o, has_o = decoded(ATTR_O)
        tr = add("ShaderNodeVectorTransform", vector_type="NORMAL", convert_from="OBJECT", convert_to="WORLD")
        L.new(v_o.outputs[0], tr.inputs[0])
        nn = add("ShaderNodeVectorMath", operation="NORMALIZE")
        L.new(tr.outputs[0], nn.inputs[0])
        enc = add("ShaderNodeVectorMath", operation="MULTIPLY_ADD")
        enc.inputs[1].default_value = (0.5, 0.5, 0.5)
        enc.inputs[2].default_value = (0.5, 0.5, 0.5)
        L.new(nn.outputs[0], enc.inputs[0])
        out_n = add("ShaderNodeOutputAOV", aov_name=AOV_N)
        L.new(enc.outputs[0], out_n.inputs["Color"])
        k = has_o
        out_k = add("ShaderNodeOutputAOV", aov_name=AOV_K)
        L.new(k.outputs[0], out_k.inputs["Value"])
        # 日の無い場面は白い拡散面の光(cel_shade の Shader to RGB)を使う。その法線もこちらに
        geo = add("ShaderNodeNewGeometry")
        mixn = add("ShaderNodeMix", data_type="VECTOR")
        L.new(k.outputs[0], mixn.inputs["Factor"])
        L.new(geo.outputs["Normal"], mixn.inputs[4])
        L.new(nn.outputs[0], mixn.inputs[5])
    mixn = next((n for n in nodes if n.label == NODE_LABEL and n.type == "MIX"), None)
    from . import cel_shade
    dif = next((n for n in nodes if n.label == cel_shade.SHADE_NODE_LABEL and n.type == "BSDF_DIFFUSE"), None)
    if mixn is not None and dif is not None and not dif.inputs["Normal"].is_linked:
        nt.links.new(mixn.outputs[1], dif.inputs["Normal"])
    return not have


def ensure_scene(scene, view_layer) -> int:
    """影の向きを書いた物があれば、材質の AOV とビューレイヤーの AOV を用意する。足した材質の数。"""
    if not has_bake(scene):
        return 0
    for name, typ in ((AOV_N, "COLOR"), (AOV_K, "VALUE")):
        a = next((a for a in view_layer.aovs if a.name == name), None)
        if a is None:
            a = view_layer.aovs.add()
            a.name = name
        a.type = typ
    from . import cel_shade
    n = sum(_ensure_material(m) for m in cel_shade._iter_materials(scene))
    if n:
        view_layer.update()
    return n


def remove_material_nodes() -> None:
    for m in bpy.data.materials:
        if m.use_nodes and m.node_tree is not None:
            for n in [n for n in m.node_tree.nodes if n.label == NODE_LABEL]:
                m.node_tree.nodes.remove(n)


# ---------------------------------------------------------------- ボタン

class FREEPENCIL_OT_shade_shape(bpy.types.Operator):
    """Write shadow shapes (bone capsules, rounded parts) into vertex colors."""

    bl_idname = "freepencil.shade_shape"
    bl_label = "Make shadow shapes"
    bl_description = (
        "Shade by the big shapes of the body instead of every wrinkle: arms and "
        "legs as tubes, the head and hair as a ball (from the bones), round "
        "parts as an ellipsoid. Written into vertex colors. Run again after "
        "changing the pose a lot"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        r = bake(scene, context.view_layer)
        total = sum(r["done"].values())
        if not total:
            self.report({"WARNING"}, bpy.app.translations.pgettext("No mesh to write shadow shapes on"))
            return {"CANCELLED"}
        if scene.fp_preview_mode == "CEL":          # 光のノードを作り直す
            from . import cel_shade
            cel_shade.set_cel(scene, True)
        self.report({"INFO"}, " ".join(f"{k}:{v}" for k, v in r["done"].items()))
        return {"FINISHED"}


class FREEPENCIL_OT_shade_shape_clear(bpy.types.Operator):
    """Remove the shadow shapes and go back to the surface direction."""

    bl_idname = "freepencil.shade_shape_clear"
    bl_label = "Remove shadow shapes"
    bl_description = "Remove the shadow shapes from the vertex colors"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        clear(scene)
        remove_material_nodes()
        if scene.fp_preview_mode == "CEL":
            from . import cel_shade
            cel_shade.set_cel(scene, True)
        return {"FINISHED"}
