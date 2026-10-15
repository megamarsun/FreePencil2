"""C62(1 枚のメッシュ)を部品に分けて、走らせられるようにする。

  rig = c62_rig.build(obj)     読み込んだ C62 を、車体・輪軸・連結棒・主連棒・クロスヘッドに分ける
  c62_rig.pose(rig, d)         走った距離 d(m、前へ)に合わせて、車輪を回し、棒を動かす

モデルのローカル座標: 長手が y、前(煙室)が -y、車輪の軸は x、レール面が z=0。
各部品は親(rig["root"])の子にする。列車を走らせるのは root を動かす(前 = ローカル -y)。

  - 輪軸: 車輪(タイヤとスポーク)と、その円の中に収まる部品(ハブ・クランクピン・釣り合いおもり・
    車軸)。前へ d 進むと x 軸まわりに d / 半径 だけ回る
  - 連結棒: 動輪のクランクピンと同じ円を描いて平行移動(向きは変わらない)
  - 主連棒: 大端は中の動輪のクランクピン、小端はクロスヘッドと一緒に水平に滑る
  - クロスヘッドとピストン棒: 小端と一緒に水平に滑る
  - 弁装置(細かいリンク)は動かさない
"""
from __future__ import annotations

import math

import bpy
import numpy as np


def _parts(me):
    """頂点の連結成分。戻り値: 頂点ごとの部品番号, 部品の bbox(lo, hi), 頂点数。"""
    n = len(me.vertices)
    co = np.empty(n * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    e = np.empty(len(me.edges) * 2, dtype=np.int64)
    me.edges.foreach_get("vertices", e)
    e = e.reshape(-1, 2)
    parent = np.arange(n)

    def find(a):
        r = a
        while parent[r] != r:
            r = parent[r]
        while parent[a] != r:
            parent[a], a = r, parent[a]
        return r
    for a, b in e:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    roots = np.array([find(i) for i in range(n)])
    _, inv, cnt = np.unique(roots, return_inverse=True, return_counts=True)
    k = cnt.size
    lo = np.full((k, 3), 1e9)
    hi = np.full((k, 3), -1e9)
    np.minimum.at(lo, inv, co)
    np.maximum.at(hi, inv, co)
    return co, inv, lo, hi, cnt


def _classify(co, inv, lo, hi, cnt):
    dim = hi - lo
    ctr = (lo + hi) / 2
    k = cnt.size
    # 車輪: 長手(y)と高さ(z)がほぼ等しい薄い円(直径 0.5..2.0m)
    disc = [p for p in range(k)
            if 0.5 < dim[p][1] < 2.0 and abs(dim[p][1] - dim[p][2]) < 0.08 * dim[p][1]
            and dim[p][0] < 0.35 and cnt[p] > 200]
    # 輪軸はレールに載っている円(タイヤ)で決める。スポークの円板はレールから浮いているので
    # 同じ中心のタイヤに付ける(付けないとタイヤだけ回った)
    rail = [p for p in disc if abs(lo[p][2]) < 0.06]
    wheel = list(rail)
    for p in disc:
        if p in rail:
            continue
        if any(abs(ctr[p][1] - ctr[q][1]) < 0.05 and abs(ctr[p][2] - ctr[q][2]) < 0.05 for q in rail):
            wheel.append(p)
    # 輪軸ごとにまとめる(軸の y がそろうもの)。半径は一番大きいタイヤ
    axles = []
    for p in sorted(wheel, key=lambda p: ctr[p][1]):
        for a in axles:
            if abs(a["y"] - ctr[p][1]) < 0.05:
                a["parts"].append(p)
                a["r"] = max(a["r"], dim[p][1] / 2)
                break
        else:
            axles.append({"y": float(ctr[p][1]), "z": float(ctr[p][2]), "r": float(dim[p][1] / 2), "parts": [p]})
    drivers = [a for a in axles if a["r"] > 0.8]
    used = set(wheel)

    # 主連棒・連結棒: 動輪の高さの細長い棒(x の外側)
    def rodlike(p):
        return (abs(ctr[p][0]) > 0.5 and dim[p][0] < 0.12 and dim[p][1] > 1.6
                and dim[p][2] < 0.7 and 0.25 < ctr[p][2] < 1.2 and cnt[p] > 60)
    d_lo = min(a["y"] for a in drivers) - 0.2
    d_hi = max(a["y"] for a in drivers) + 0.2
    rods = [p for p in range(k) if p not in used and rodlike(p)]
    # 連結棒: 両端とも動輪の間にある。主連棒: 前(-y)へ動輪の外まで伸びる
    coupling = [p for p in rods if lo[p][1] > d_lo and hi[p][1] < d_hi and dim[p][2] < 0.35]
    main = [p for p in rods if lo[p][1] < d_lo - 0.5 and p not in coupling and dim[p][1] > 2.5]
    used |= set(coupling) | set(main)

    # 輪軸に付く部品: 円の中に収まる(外の側: 車輪の面より外 / 車軸: 左右にまたがる)
    for a in axles:
        R = a["r"]
        wx = [abs(ctr[p][0]) for p in a["parts"]]
        xin = min(wx) - 0.08
        for p in range(k):
            if p in used:
                continue
            dy0, dy1 = lo[p][1] - a["y"], hi[p][1] - a["y"]
            dz0, dz1 = lo[p][2] - a["z"], hi[p][2] - a["z"]
            far = max(math.hypot(dy, dz) for dy in (dy0, dy1) for dz in (dz0, dz1))
            if far > R * 0.92:
                continue
            # 軸と同じ中心の部品(ハブ・車軸の端・タイヤの内側)か、円の中の小さな部品(クランクピン)。
            # 円の中に収まるだけでは、台枠や上の覆いの一部まで回った(画像で確認)
            off = math.hypot(ctr[p][1] - a["y"], ctr[p][2] - a["z"])
            concentric = off < 0.06 * R and abs(ctr[p][0]) >= xin - 0.15
            pin = max(dim[p][1], dim[p][2]) < 0.3 and off < 0.5 * R and abs(ctr[p][0]) >= xin
            outside = concentric or pin
            axle = abs(ctr[p][0]) < 0.05 and dim[p][0] > 0.9 and max(dim[p][1], dim[p][2]) < 0.4
            if outside or axle:
                a["parts"].append(p)
                used.add(p)

    # 主連棒の両端: 大端 = 中の動輪のクランクピン(ピンの部品の中心)、小端 = 反対の端
    mains = []
    for p in main:
        vv = co[inv == p]
        side = 1.0 if ctr[p][0] > 0 else -1.0
        back = vv[vv[:, 1] > hi[p][1] - 0.15]
        front = vv[vv[:, 1] < lo[p][1] + 0.15]
        big = back[:, 1:].mean(axis=0)
        small = front[:, 1:].mean(axis=0)
        drv = min(drivers, key=lambda a: abs(a["y"] - big[0]))
        pins = [q for q in drv["parts"] if max(dim[q][1], dim[q][2]) < 0.3
                and np.sign(ctr[q][0]) == side
                and 0.15 < math.hypot(ctr[q][1] - drv["y"], ctr[q][2] - drv["z"]) < 0.5 * drv["r"]]
        if pins:
            q = min(pins, key=lambda q: math.hypot(ctr[q][1] - big[0], ctr[q][2] - big[1]))
            big = np.array([ctr[q][1], ctr[q][2]])
        mains.append({"part": p, "side": side, "big": big, "small": small, "axle": drv})
    # クロスヘッドとピストン棒: 小端の近くで、小端と同じ高さを前へ伸びる小さな部品
    for m in mains:
        sy, sz = m["small"]
        cross = []
        for p in range(k):
            if p in used or np.sign(ctr[p][0]) != m["side"] or abs(ctr[p][0]) < 0.45:
                continue
            near = abs(ctr[p][2] - sz) < 0.2 and lo[p][1] > sy - 2.6 and hi[p][1] < sy + 0.45
            small_part = dim[p][2] < 0.45 and dim[p][0] < 0.45
            if near and small_part and (dim[p][1] < 0.8 or (dim[p][1] < 2.6 and dim[p][2] < 0.15)):
                cross.append(p)
        m["cross"] = cross
        used |= set(cross)
    # 偏心棒: 片方の端が動輪の軸の近く(返りクランク)、もう片方が前の弁装置。返りクランクと一緒に
    # 回る端を追い、前の端を中心に振る(弁装置そのものは動かさない)
    eccs = []
    for p in range(k):
        if p in used or abs(ctr[p][0]) < 0.5 or not (1.2 < dim[p][1] < 2.8) or dim[p][2] > 0.6 or dim[p][0] > 0.15:
            continue
        vv = co[inv == p]
        b_end = vv[vv[:, 1] > hi[p][1] - 0.12][:, 1:].mean(axis=0)
        f_end = vv[vv[:, 1] < lo[p][1] + 0.12][:, 1:].mean(axis=0)
        drv = min(drivers, key=lambda a: math.hypot(a["y"] - b_end[0], a["z"] - b_end[1]))
        if math.hypot(drv["y"] - b_end[0], drv["z"] - b_end[1]) < 0.4:
            eccs.append({"part": p, "back": b_end, "front": f_end, "axle": drv})
            used.add(p)
    # 連結棒の側とクランクピンの向き(同じ側の動輪はそろっている)
    couplings = []
    for p in coupling:
        side = 1.0 if ctr[p][0] > 0 else -1.0
        drv = min(drivers, key=lambda a: abs(a["y"] - lo[p][1]))
        couplings.append({"part": p, "side": side, "axle": drv})
    return axles, couplings, mains, eccs


def _crank(axle, side, mains, couplings):
    """その側のクランクピンの位置(動輪の中心からのずれ)。主連棒の大端から取る。"""
    for m in mains:
        if m["side"] == side:
            return np.array(m["big"]) - np.array([m["axle"]["y"], m["axle"]["z"]])
    return np.array([0.0, -0.33])


def _split(obj, groups):
    """部品番号の組ごとに、別のオブジェクトへ分ける。戻り値: 名前 -> オブジェクト。

    部品番号は頂点の属性(fp_part)に持たせる。分けても頂点と一緒に移るので、引き直さなくてよい。
    """
    me = obj.data
    inv = groups["_inv"]
    a = me.attributes.new("fp_part", "INT", "POINT")
    a.data.foreach_set("value", inv.astype(np.int32))
    made = {}
    for name, parts in groups.items():
        if name.startswith("_") or not parts:
            continue
        me = obj.data
        vp = np.empty(len(me.vertices), dtype=np.int32)
        me.attributes["fp_part"].data.foreach_get("value", vp)
        vsel = np.isin(vp, np.array(sorted(parts), dtype=np.int32))
        if not vsel.any():
            continue
        ev = np.empty(len(me.edges) * 2, dtype=np.int64)
        me.edges.foreach_get("vertices", ev)
        esel = vsel[ev.reshape(-1, 2)[:, 0]]
        ls = np.empty(len(me.polygons), dtype=np.int64)
        me.polygons.foreach_get("loop_start", ls)
        lv = np.empty(len(me.loops), dtype=np.int64)
        me.loops.foreach_get("vertex_index", lv)
        fsel = vsel[lv[ls]]
        me.vertices.foreach_set("select", vsel)
        me.edges.foreach_set("select", esel)
        me.polygons.foreach_set("select", fsel)
        me.update()
        bpy.ops.object.select_all(action="DESELECT")
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        before = set(bpy.data.objects)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.separate(type="SELECTED")
        bpy.ops.object.mode_set(mode="OBJECT")
        new = [o for o in bpy.data.objects if o not in before]
        if new:
            new[0].name = f"C62_{name}"
            made[name] = new[0]
    bpy.ops.object.select_all(action="DESELECT")
    for o in [obj] + list(made.values()):
        if "fp_part" in o.data.attributes:
            o.data.attributes.remove(o.data.attributes["fp_part"])
    return made


def _set_origin(o, y, z):
    """オブジェクトの原点を (x=0, y, z) へ(メッシュの中身は動かさない)。"""
    from mathutils import Matrix, Vector
    o.data.transform(Matrix.Translation(Vector((0.0, -y, -z))))
    o.location = (0.0, y, z)


def build(obj):
    """読み込んだ C62(ローカルの向きのまま、変換なし)を分ける。戻り値は pose() に渡す辞書。"""
    me = obj.data
    co, inv, lo, hi, cnt = _parts(me)
    axles, couplings, mains, eccs = _classify(co, inv, lo, hi, cnt)
    groups = {"_co": co, "_inv": inv}
    for i, a in enumerate(axles):
        groups[f"axle{i}"] = a["parts"]
    for i, c in enumerate(couplings):
        groups[f"coupling{i}"] = [c["part"]]
    for i, m in enumerate(mains):
        groups[f"mainrod{i}"] = [m["part"]]
        groups[f"cross{i}"] = m["cross"]
    for i, e in enumerate(eccs):
        groups[f"ecc{i}"] = [e["part"]]
    made = _split(obj, groups)
    root = bpy.data.objects.new("C62_root", None)
    bpy.context.scene.collection.objects.link(root)
    obj.name = "C62_body"
    rig = {"root": root, "body": obj, "axles": [], "couplings": [], "mains": [], "eccs": []}
    for o in [obj] + list(made.values()):
        o.parent = root
    for i, a in enumerate(axles):
        o = made.get(f"axle{i}")
        if o is None:
            continue
        _set_origin(o, a["y"], a["z"])
        rig["axles"].append({"obj": o, "y": a["y"], "z": a["z"], "r": a["r"]})
    for i, c in enumerate(couplings):
        o = made.get(f"coupling{i}")
        if o is None:
            continue
        crank = _crank(c["axle"], c["side"], mains, couplings)
        rig["couplings"].append({"obj": o, "crank": crank.tolist(), "r": c["axle"]["r"]})
    for i, m in enumerate(mains):
        o = made.get(f"mainrod{i}")
        if o is None:
            continue
        big = np.array(m["big"])
        _set_origin(o, big[0], big[1])
        crank = big - np.array([m["axle"]["y"], m["axle"]["z"]])
        rec = {"obj": o, "big": big.tolist(), "small": list(map(float, m["small"])),
               "axle": [m["axle"]["y"], m["axle"]["z"]], "r": m["axle"]["r"],
               "crank": crank.tolist(), "cross": made.get(f"cross{i}")}
        rig["mains"].append(rec)
    for i, e in enumerate(eccs):
        o = made.get(f"ecc{i}")
        if o is None:
            continue
        f = np.array(e["front"])
        _set_origin(o, f[0], f[1])
        rig["eccs"].append({"obj": o, "front": f.tolist(), "back": list(map(float, e["back"])),
                            "axle": [e["axle"]["y"], e["axle"]["z"]], "r": e["axle"]["r"]})
    print(f"@@@ C62 rig: 偏心棒 {len(rig['eccs'])}", flush=True)
    print(f"@@@ C62 rig: 輪軸 {len(rig['axles'])}  連結棒 {len(rig['couplings'])}  主連棒 {len(rig['mains'])}"
          f"  クロスヘッド {sum(1 for m in rig['mains'] if m['cross'] is not None)}", flush=True)
    return rig


def _rot(v, th):
    """yz の向き v を x 軸まわりに th 回す(Blender の rotation_euler.x と同じ向き)。"""
    c, s = math.cos(th), math.sin(th)
    return np.array([v[0] * c - v[1] * s, v[0] * s + v[1] * c])


def pose(rig, d):
    """前(ローカル -y)へ d m 進んだときの車輪と棒。root の移動は呼び出し側でする。"""
    for a in rig["axles"]:
        a["obj"].rotation_euler = (d / a["r"], 0.0, 0.0)
    for c in rig["couplings"]:
        th = d / c["r"]
        crank = np.array(c["crank"])
        dv = _rot(crank, th) - crank
        c["obj"].location = (0.0, dv[0], dv[1])
    for m in rig["mains"]:
        th = d / m["r"]
        crank = np.array(m["crank"])
        axle = np.array(m["axle"])
        big0, small0 = np.array(m["big"]), np.array(m["small"])
        L = float(np.linalg.norm(small0 - big0))
        big = axle + _rot(crank, th)
        dz = small0[1] - big[1]
        sy = big[0] - math.sqrt(max(L * L - dz * dz, 0.0))       # 小端は前(-y)へ
        small = np.array([sy, small0[1]])
        a0 = math.atan2(small0[1] - big0[1], small0[0] - big0[0])
        a1 = math.atan2(small[1] - big[1], small[0] - big[0])
        m["obj"].location = (0.0, big[0], big[1])
        m["obj"].rotation_euler = (a1 - a0, 0.0, 0.0)
        if m["cross"] is not None:
            m["cross"].location = (0.0, sy - small0[0], 0.0)
    for e in rig.get("eccs", []):
        th = d / e["r"]
        axle = np.array(e["axle"])
        f, b0 = np.array(e["front"]), np.array(e["back"])
        b = axle + _rot(b0 - axle, th)
        a0 = math.atan2(b0[1] - f[1], b0[0] - f[0])
        a1 = math.atan2(b[1] - f[1], b[0] - f[0])
        e["obj"].rotation_euler = (a1 - a0, 0.0, 0.0)
