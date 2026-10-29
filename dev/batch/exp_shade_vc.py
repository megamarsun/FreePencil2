"""実験: 影用の法線を頂点カラーに書く(骨のカプセル・島の楕円体)と、セルの影はどう変わるか。ライトの当て方も比べる。

  blender -b --factory-startup --python exp_shade_vc.py -- <作例の .blend> <出力フォルダ> [--mix 0,0.6,1] [--lights cur,key,side,rim]

アニメの影は「腕は筒、頭は球」という大きな形で決まっている。その形(プロキシ)を手で作る代わりに、
  - 骨のあるモデル: 頂点を動かす骨を線分(カプセル)と見て、骨の軸から頂点への向きを、骨の重みで混ぜる
  - 骨の無い物: つながった塊ごとに主成分で楕円体を当て、その面の向き
を「形の法線」とし、面の法線(少しならした物)と mix で混ぜて、頂点カラー fp_shade_n(ワールドの向きを
0..1 に詰めた物)に書く。材質は BSDF の Normal にこの色を法線として入れる(ノーマルマップは外れる)。
髪(物か材質の名前に hair / 髪)は、毛束の骨の筒だとまだらになったので、頭の骨の中心からの球にする。
ライト: cur = いまの日 / key = カメラから見て左上前 / side = 真横寄り / rim = 斜め後ろ(縁が光る)。
アドオンには手を入れない。出力: <出力>/vc_mMM_<light>.png と vc.blend
"""
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

ARGV = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = Path(ARGV[0]), Path(ARGV[1])
MIXES = [float(v) for v in (ARGV[ARGV.index("--mix") + 1] if "--mix" in ARGV else "0,0.6,1").split(",")]
LIGHTS = (ARGV[ARGV.index("--lights") + 1] if "--lights" in ARGV else "cur").split(",")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fp_batch  # noqa: E402

fp_batch.install_addon()
bpy.ops.wm.open_mainfile(filepath=str(SRC))
sc = bpy.context.scene
OUT.mkdir(parents=True, exist_ok=True)
ATTR = "fp_shade_n"


def weld_graph(co):
    key = np.round(co / max(np.ptp(co, axis=0).max(), 1e-6) * 1e5).astype(np.int64)
    _, weld = np.unique(key, axis=0, return_inverse=True)
    return weld.ravel()


def blur(v, e, iters):
    for _ in range(iters):
        s = v.copy()
        np.add.at(s, e[:, 0], v[e[:, 1]])
        np.add.at(s, e[:, 1], v[e[:, 0]])
        v = s / np.maximum(np.linalg.norm(s, axis=1, keepdims=True), 1e-9)
    return v


def components(m, e):
    """溶接した頂点のつながった塊の番号。"""
    parent = np.arange(m)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for a, b in e:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    return np.array([find(i) for i in range(m)])


def ellipsoid_normals(p, comp):
    out = np.zeros_like(p)
    for c in np.unique(comp):
        idx = np.where(comp == c)[0]
        q = p[idx] - p[idx].mean(0)
        if len(idx) < 8:
            out[idx] = q
            continue
        w, vec = np.linalg.eigh(np.cov(q.T))
        s2 = np.maximum(w, w.max() * 1e-3)          # 平たい板は一番薄い向きを持ち上げすぎない
        loc = q @ vec
        out[idx] = (loc / s2) @ vec.T
    return out


HAIR = __import__("re").compile(r"hair|髪", __import__("re").I)


def hair_mask(o, nvert):
    """髪の頂点(物の名前が髪なら全部、そうでなければ髪の材質の面の頂点)。"""
    if HAIR.search(o.name):
        return np.ones(nvert, bool)
    hm = np.array([bool(sl.material and HAIR.search(sl.material.name)) for sl in o.material_slots] or [False])
    mask = np.zeros(nvert, bool)
    for poly in o.data.polygons:
        if hm[min(poly.material_index, len(hm) - 1)]:
            mask[list(poly.vertices)] = True
    return mask


def head_center(arm):
    bones = [pb for pb in arm.pose.bones if "head" in pb.name.lower() and pb.bone.use_deform]
    if not bones:
        return None
    pb = max(bones, key=lambda b: b.length)
    return np.array(arm.matrix_world @ ((pb.head + pb.tail) * 0.5))


def capsule_normals(o, p, nvert):
    """骨のカプセル: 各頂点を動かす骨の軸(線分)から頂点への向きを、重みで混ぜる。骨が無ければ None。"""
    arm = next((md.object for md in o.modifiers if md.type == "ARMATURE" and md.object), None)
    if arm is None:
        return None
    segs = {}
    for pb in arm.pose.bones:
        if pb.bone.use_deform and pb.name in o.vertex_groups:
            segs[o.vertex_groups[pb.name].index] = (np.array(arm.matrix_world @ pb.head), np.array(arm.matrix_world @ pb.tail))
    if not segs:
        return None
    acc = np.zeros((nvert, 3))
    wsum = np.zeros(nvert)
    for v in o.data.vertices:
        for g in v.groups:
            seg = segs.get(g.group)
            if seg is None or g.weight <= 0:
                continue
            a, b = seg
            ab = b - a
            t = np.clip(np.dot(p[v.index] - a, ab) / max(np.dot(ab, ab), 1e-12), 0.0, 1.0)
            d = p[v.index] - (a + t * ab)
            n = np.linalg.norm(d)
            if n > 1e-9:
                acc[v.index] += g.weight * d / n
                wsum[v.index] += g.weight
    hm = hair_mask(o, nvert)
    c = head_center(arm)
    if hm.any() and c is not None:
        acc[hm] = p[hm] - c
        wsum[hm] = 1.0
    return acc, wsum > 0


objs = [o for o in sc.objects if o.type == "MESH" and not o.hide_render and len(o.data.polygons)]
dg = bpy.context.evaluated_depsgraph_get()
data = {}
for o in objs:
    # 細分化などを止めて、シェイプキーとポーズだけ効いた形を取る(頂点の番号が元と同じになる)
    saved = [(md, md.show_viewport) for md in o.modifiers if md.type not in ("ARMATURE",)]
    for md, _ in saved:
        md.show_viewport = False
    dg.update()
    ev = o.evaluated_get(dg)
    me = ev.to_mesh()
    n = len(me.vertices)
    ok = n == len(o.data.vertices)
    co = np.empty(n * 3, np.float32)
    me.vertices.foreach_get("co", co)
    nr = np.empty(n * 3, np.float32)
    me.vertices.foreach_get("normal", nr)
    ev.to_mesh_clear()
    for md, s in saved:
        md.show_viewport = s
    if not ok:
        print("@@ skip (vertex count changed)", o.name)
        continue
    M = np.array(o.matrix_world)
    p = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
    nw = nr.reshape(-1, 3) @ np.linalg.inv(M[:3, :3])
    nw /= np.maximum(np.linalg.norm(nw, axis=1, keepdims=True), 1e-9)
    weld = weld_graph(p)
    m = weld.max() + 1
    e = np.empty(len(o.data.edges) * 2, np.int64)
    o.data.edges.foreach_get("vertices", e)
    e = weld[e.reshape(-1, 2)]
    e = e[e[:, 0] != e[:, 1]]
    pw = np.zeros((m, 3))
    pw[weld] = p
    g = np.zeros((m, 3))
    np.add.at(g, weld, nw)
    g /= np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-9)
    geo = blur(g, e, 10)
    shape = ellipsoid_normals(pw, components(m, e))[weld]
    cap = capsule_normals(o, p, n)
    if cap is not None:
        acc, has = cap
        shape[has] = acc[has]
    shape /= np.maximum(np.linalg.norm(shape, axis=1, keepdims=True), 1e-9)
    # 形の法線が面と逆を向く所(凹んだ所、骨の外の部品)は面の向きに寄せる
    flip = (shape * geo[weld]).sum(1) < 0
    shape[flip] = geo[weld][flip]
    data[o] = (geo[weld], shape)
    print("@@ prepared", o.name, n, "bones" if cap is not None else "ellipsoid", flush=True)


def write(mix):
    for o, (geo, shape) in data.items():
        v = (1 - mix) * geo + mix * shape
        v /= np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)
        a = o.data.color_attributes.get(ATTR) or o.data.color_attributes.new(ATTR, "FLOAT_COLOR", "POINT")
        rgba = np.concatenate([v * 0.5 + 0.5, np.ones((len(v), 1))], 1).astype(np.float32)
        a.data.foreach_set("color", rgba.ravel())
        o.data.update()


def hook_materials():
    for o in objs:
        if o not in data:              # 色の無い物は法線が壊れるので、その材質は触らない
            continue
    mats = {s.material for o in data for s in o.material_slots if s.material and s.material.use_nodes}
    bad = {s.material for o in objs if o not in data for s in o.material_slots if s.material}
    for mat in mats - bad:
        nt = mat.node_tree
        at = nt.nodes.new("ShaderNodeAttribute")
        at.attribute_name = ATTR
        mad = nt.nodes.new("ShaderNodeVectorMath")
        mad.operation = "MULTIPLY_ADD"
        mad.inputs[1].default_value = (2, 2, 2)
        mad.inputs[2].default_value = (-1, -1, -1)
        nn = nt.nodes.new("ShaderNodeVectorMath")
        nn.operation = "NORMALIZE"
        nt.links.new(at.outputs["Vector"], mad.inputs[0])
        nt.links.new(mad.outputs[0], nn.inputs[0])
        for nd in list(nt.nodes):
            sock = nd.inputs.get("Normal") if nd.type.startswith("BSDF") or nd.type in ("SUBSURFACE_SCATTERING",) else None
            if sock is not None:
                nt.links.new(nn.outputs["Vector"], sock)


def cel_module():
    return next(m for k, m in sys.modules.items() if k.endswith(".cel_shade"))


def aim_sun(kind):
    global cur_rot
    sun = cel_module().key_sun(sc)
    if sun is None:
        return
    if cur_rot is None:
        cur_rot = sun.matrix_world.to_quaternion()
    if kind == "cur":                       # 前のライトの向きが残らないよう、元の向きに戻す
        sun.rotation_mode = "QUATERNION"
        sun.rotation_quaternion = cur_rot
        bpy.context.view_layer.update()
        cel_module().update_sun(sc)
        return
    cam = sc.camera.matrix_world.to_3x3()
    right, up, back = cam.col[0], cam.col[1], cam.col[2]      # カメラの右・上・後ろ(ワールド)
    toward = {"key": -0.55 * right + 0.65 * up + 0.55 * back,     # 左上前から
              "side": -0.95 * right + 0.45 * up + 0.10 * back,    # ほぼ真横
              "rim": 0.75 * right + 0.45 * up - 0.60 * back}[kind]  # 右上うしろ(縁が光る)
    d = Vector(toward).normalized()
    sun.rotation_mode = "QUATERNION"
    sun.rotation_quaternion = d.to_track_quat("Z", "Y")      # 日の +Z が光の来る向き(sun_vector)
    bpy.context.view_layer.update()
    cel_module().update_sun(sc)


cur_rot = None
hook_materials()
sc.fp_preview_mode = "CEL"
for mix in MIXES:
    write(mix)
    for li in LIGHTS:
        aim_sun(li)
        sc.render.filepath = str(OUT / f"vc_m{int(mix * 100):02d}_{li}.png")
        bpy.ops.render.render(write_still=True)
        print("@@ shot", mix, li, flush=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "vc.blend"))
print("@@ done", flush=True)
