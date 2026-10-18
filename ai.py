"""AI(エージェント)が FreePencil を使うための窓口と、ボタンごとの指示(v2.9.x)。

なぜ要るか
  線画をきれいに仕上げる最後の手直し(どこの線を消す・どこに線を足す)は、絵を見て判断する
  仕事で、ツールの設定では決まらない。人は筆で塗って直すが、AI は筆を持てず、パネルのボタンも
  画面の文脈が無いと押せない。どの設定が最適かも知らない。そこで:

  1. ボタンを Python から押すと、押した後のシーンを見て「次の一手」をコンソールに出す
     (人には見えない出力)。中身は、何が変わったか・どこを見るべきか・次にどうするか。
     各ボタンの execute を包んで出すので、ボタンのコードは変えない(install_hooks)。
  2. AI 用のボタン bpy.ops.freepencil.ai_guide() は、シーンを調べて進め方と次の一手を返す。
  3. 筆の代わり: 塗る場所を言葉で指定する(物・材質・頂点グループ・カメラ画面上の四角)。
     erase_lines / fade_lines / add_lines / crisp / line_width。
  4. render() は小さく撮って、目盛り付きの画像の場所を返す。AI はそれを目で見て次を決める。

AI から使うとき(Blender の Python。MCP の execute_blender_code など):
    import bpy
    bpy.ops.freepencil.ai_guide()              # 進め方と次の一手がコンソールに出る
    import sys; fp = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.ai"))
    print(fp.guide())
どの関数も dict を返し、同じ内容を "[FreePencil AI]" で始まる行でコンソールにも出す。
"""
from __future__ import annotations

import json
import math
import os
import tempfile
import time
from pathlib import Path

import bpy

PREFIX = "[FreePencil AI]"
LAST: dict = {}          # 最後に出した指示(ボタンを押した後に fp.last() で読める)


# ---------------------------------------------------------------- 出力
def _emit(title: str, info: dict) -> dict:
    """指示を dict で返し、同じ内容をコンソールに出す。"""
    info = {"step": title, **info}
    LAST.clear()
    LAST.update(info)
    lines = [f"{PREFIX} ==== {title} ===="]
    for k in ("done", "state", "changed", "image", "grid_image", "warnings", "look_for", "next"):
        v = info.get(k)
        if not v:
            continue
        if isinstance(v, (list, tuple)):
            lines.append(f"{PREFIX} {k}:")
            lines += [f"{PREFIX}   - {x}" for x in v]
        elif isinstance(v, dict):
            lines.append(f"{PREFIX} {k}: {json.dumps(v, ensure_ascii=False)}")
        else:
            lines.append(f"{PREFIX} {k}: {v}")
    print("\n".join(lines), flush=True)
    return info


def last() -> dict:
    """最後に出した指示。ボタン(bpy.ops)を押した直後に読む。"""
    return dict(LAST)


# ---------------------------------------------------------------- シーンを調べる
def _meshes(scene=None):
    scene = scene or bpy.context.scene
    return [o for o in scene.objects if o.type == "MESH" and not o.hide_render]


def _tree(scene):
    from . import compat
    return compat.get_compositor_tree(scene)


def _applied(scene) -> bool:
    from . import fp_core
    t = _tree(scene)
    return t is not None and any(n.type == "GROUP" and n.node_tree is not None
                                 and n.node_tree.name.startswith(fp_core.NODE_GROUP_PREFIX)
                                 for n in t.nodes)


def _has_rig(o) -> bool:
    return any(m.type == "ARMATURE" and m.object is not None for m in o.modifiers)


def state() -> dict:
    """シーンの要点(AI が判断に使う事実だけ)。"""
    sc = bpy.context.scene
    vl = bpy.context.view_layer
    ms = _meshes(sc)
    painted = [o.name for o in ms if "mecha_color" in o.data.color_attributes]
    r = sc.render
    st = {
        "blender": bpy.app.version_string.split()[0],
        "file": bpy.data.filepath or "(未保存)",
        "camera": sc.camera.name if sc.camera else None,
        "meshes": len(ms),
        "rigged_meshes": [o.name for o in ms if _has_rig(o)][:12],
        "painted_meshes": len(painted),
        "freepencil_applied": _applied(sc),
        "style": getattr(sc, "fp_auto_style", None),
        "preview": getattr(sc, "fp_preview_mode", None),
        "aovs": [a.name for a in vl.aovs],
        "resolution": f"{r.resolution_x}x{r.resolution_y} {r.resolution_percentage}%",
        "supersample": getattr(sc, "fp_supersample", None),
        "line_weight": getattr(sc, "fp_line_weight", None),
        "selected": [o.name for o in bpy.context.selected_objects][:12],
        "mode": bpy.context.object.mode if bpy.context.object else None,
    }
    return st


def _suggest_style(ms) -> str:
    if any(_has_rig(o) for o in ms):
        return "WEIGHTED"
    if len(ms) >= 40:
        return "BACKGROUND"
    return "PRECISE"


WORKFLOW = [
    "1. state を見る。カメラが無ければ先に置く(線はカメラから見た絵で決まる)",
    "2. auto(style) で STEP0。style: キャラ(リグ付き)=WEIGHTED / メカ・車・小物=PRECISE / "
    "町・建物・木の多い背景=BACKGROUND。迷ったら auto() が選ぶ",
    "3. render('step0') で撮り、返ってきた image を必ず目で見る(数値で判断しない)。"
    "grid_image は 10% ごとの目盛り付き。直す場所は目盛りで (x0,y0,x1,y1) を読む(左上が 0,0)",
    "4. 気になる所を 1 つずつ直し、そのたびに render して前後を見比べる:",
    "   - 余計な線・黒い塊を消す → erase_lines(where)",
    "   - 線が濃すぎる・うるさい → fade_lines(where, amount=0.2〜0.4)",
    "   - 欲しい線が無い(髪と顔の境目、服の切り替え) → add_lines(where)。その範囲の外周に線が出る",
    "   - 境目がぼやけて太い帯になる → crisp(where)",
    "   - 物ごとに太く・細く → line_width(objects, x)  (2=太く, 0.5=薄く, 0=消す)",
    "   キャラ(アニメの絵)にするとき、まずこの 4 つ(MMD の 4 体と BlenderKit のキャラで確かめた順):",
    "   - 髪の影・頬の赤み・目の光の半透明の板がざらざらの点になる → soft_overlays([材質の名前の一部])",
    "   - 前髪の先・まつ毛の縁がざらざら → clip_alpha(skip=[soft_overlays に渡した名前])",
    "   - 目のまわりに眼球の丸い線 → merge({'objects':[顔のメッシュ], 'material':[顔・白目・黒目・まつ毛・眉]})"
    "(アニメの目は線で描かない。目は絵の色で出る)",
    "   - モデルに外側の殻(Solidify)があると線が二重 → その Solidify を切る",
    "   - セルの顔は日を正面から(カメラの向きから少し上)、cel(threshold=0.2〜0.25, cast_shadows=False)",
    "   - 口・ボタンなど絵に描いた物 → texture_lines(where, strength=0.3〜0.7)。範囲(rect)で絞る",
    "5. 仕上げ: preview('WHITE') で線だけ、preview('CEL') でセル。最終は render('final', scale=1)",
    "6. 失敗したら undo() で 1 手戻す。全部やめるなら remove()(STEP0 の前に戻る)",
    "where の書き方: {'objects':[名前]} / {'material':'名前の一部'} / {'vertex_group':'名前'} / "
    "{'rect':(x0,y0,x1,y1)}(カメラ画面の割合、左上 0,0、見えている面だけ) を組み合わせる(全部満たす面)",
]


def guide() -> dict:
    """AI 用のボタンの中身。今のシーンを見て、進め方と次の一手を返す。"""
    st = state()
    warnings, nxt = [], []
    if st["camera"] is None:
        warnings.append("カメラがありません。線はカメラから見た絵で出ます")
        nxt.append("カメラを置いて scene.camera にする")
    if not st["meshes"]:
        warnings.append("メッシュがありません")
    if st["mode"] not in (None, "OBJECT"):
        warnings.append(f"今 {st['mode']} モードです。auto() はオブジェクトモードに戻して進めます")
    if not st["freepencil_applied"]:
        style = _suggest_style(_meshes())
        nxt.append(f"auto(style='{style}') で STEP0 を通す(リグ付きが"
                   f"{'ある' if st['rigged_meshes'] else '無い'}ので {style})")
        nxt.append("そのあと render('step0') で撮って目で見る")
    else:
        nxt.append("render('check') で今の絵を撮って目で見る")
        nxt.append("直したい所があれば WORKFLOW の 4 の道具で 1 つずつ直し、そのたびに撮る")
    return _emit("guide", {"state": st, "warnings": warnings, "next": nxt,
                           "look_for": WORKFLOW,
                           "done": "使い方: fp = sys.modules で末尾が freepencil2.ai のモジュール。"
                                   "関数は guide/state/auto/render/erase_lines/fade_lines/add_lines/"
                                   "merge/texture_lines/soft_overlays/clip_alpha/crisp/line_width/"
                                   "preview/cel/undo/remove/last"})


# ---------------------------------------------------------------- 押す
def _select(objs):
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for o in bpy.context.scene.objects:
        try:
            o.select_set(o in objs)
        except RuntimeError:
            pass
    if objs:
        bpy.context.view_layer.objects.active = objs[0]


def _objs(names):
    if names is None:
        return _meshes()
    if isinstance(names, str):
        names = [names]
    out = []
    for n in names:
        o = bpy.data.objects.get(n)
        if o is None:
            out += [x for x in _meshes() if n.lower() in x.name.lower()]
        elif o.type == "MESH":
            out.append(o)
    return list(dict.fromkeys(out))


def auto(style: str | None = None, objects=None) -> dict:
    """STEP0(全自動)。style: PRECISE / WEIGHTED / BACKGROUND / None(選ばせる)。"""
    sc = bpy.context.scene
    objs = _objs(objects)
    if not objs:
        return _emit("auto", {"warnings": ["対象のメッシュがありません"]})
    style = style or _suggest_style(objs)
    sc.fp_auto_style = style
    _select(objs)
    t0 = time.time()
    _DEPTH[0] += 1                  # ボタンの指示はここでまとめて出す(二重に出さない)
    try:
        res = bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    finally:
        _DEPTH[0] -= 1
    return _after_step0(style, res, time.time() - t0)


def _after_step0(style, res, sec) -> dict:
    sc = bpy.context.scene
    st = state()
    warnings = []
    if st["rigged_meshes"] and style == "PRECISE":
        warnings.append("リグ付きのメッシュがあるのに精密です。キャラなら auto('WEIGHTED')")
    if not st["rigged_meshes"] and style == "WEIGHTED":
        warnings.append("リグがありません。キャラ以外なら精密(PRECISE)の方が線が均一です")
    if sc.camera is None:
        warnings.append("カメラがありません。render() の前に置いてください")
    return _emit("STEP0", {
        "done": f"STEP0 {style} {sorted(res)} {sec:.1f} 秒。塗り分け・AOV・線画のコンポジタができた",
        "state": st, "warnings": warnings,
        "look_for": [
            "輪郭が閉じているか(髪・手・服の外周)",
            "顔: 目・口・鼻の線が黒い塊になっていないか、太すぎないか",
            "髪と顔、服の切り替えなど、欲しい境目に線があるか",
            "服のしわ・模様に余計な線がうるさく出ていないか",
            "遠くの物が黒く潰れていないか",
        ],
        "next": ["render('step0') で撮って image を見る",
                 "直す所が無ければ preview('WHITE') のまま render('final', scale=1)"],
    })


# ---------------------------------------------------------------- 撮る
def _out_dir():
    if bpy.data.filepath:
        d = Path(bpy.path.abspath("//fp_ai"))
    else:
        d = Path(tempfile.gettempdir()) / "fp_ai"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _grid_copy(src: Path, dst: Path):
    """10% ごとの目盛り線を引いた写し(25/50/75% は濃く)。AI が場所を読むため。"""
    import numpy as np
    img = bpy.data.images.load(str(src), check_existing=False)
    try:
        w, h = img.size
        px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
        a = px[..., 3:4]
        px[..., :3] = px[..., :3] * a + (1 - a)          # 透過は白に
        px[..., 3] = 1.0
        for k in range(1, 10):
            strong = k == 5                                  # 真ん中は濃く太く
            col = np.array([0.95, 0.15, 0.15]) if strong else np.array([1.0, 0.6, 0.6])
            x = int(round(w * k / 10))
            row = h - 1 - int(round(h * k / 10))             # 画像の行は下から数える
            px[:, max(0, x - 1):x + (1 if strong else 0), :3] = col
            px[max(0, row - 1):row + (1 if strong else 0), :, :3] = col
        out = bpy.data.images.new("fp_ai_grid", w, h, alpha=True)
        out.pixels.foreach_set(px.ravel())
        out.filepath_raw = str(dst)
        out.file_format = "PNG"
        out.save()
        bpy.data.images.remove(out)
    finally:
        bpy.data.images.remove(img)


def render(name: str = "check", scale: float = 0.5, grid: bool = True) -> dict:
    """F12 で撮って PNG を書き、場所を返す。scale は書き出す大きさ(最終の大きさに対して)。

    返った image を必ず目で見ること。数値(線の量など)は補助で、判断は絵で行う。
    """
    sc = bpy.context.scene
    if sc.camera is None:
        return _emit("render", {"warnings": ["カメラがありません"]})
    d = _out_dir()
    path = d / f"{name}.png"
    obj = bpy.context.object
    mode = obj.mode if obj else "OBJECT"
    if mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    # セルの日の向きを先に合わせる。日を Python で回した直後の F12 は、前の向きの影で出た
    # (日の向きはハンドラで追うが、レンダーの直前に変えた値はそのレンダーに間に合わない)
    try:
        from . import cel_shade
        bpy.context.view_layer.update()
        cel_shade.update_sun(sc)
    except Exception:              # noqa: BLE001
        pass
    keep = (sc.render.filepath, sc.render.image_settings.file_format)
    sc.render.filepath = str(path)
    sc.render.image_settings.file_format = "PNG"
    t0 = time.time()
    bpy.ops.render.render(write_still=True)
    sec = time.time() - t0
    sc.render.filepath, sc.render.image_settings.file_format = keep
    if mode != "OBJECT":
        bpy.ops.object.mode_set(mode=mode)
    # 書き出す大きさを最終の大きさ × scale にそろえる(2倍レンダ中は F12 が 2 倍で出る)
    final = sc.render.resolution_x * sc.render.resolution_percentage / 100
    if getattr(sc, "fp_supersample", False) and sc.render.resolution_percentage >= 200:
        final /= 2
    w = max(16, int(final * scale))
    img = bpy.data.images.load(str(path), check_existing=False)
    try:
        if img.size[0] != w:
            img.scale(w, max(16, int(img.size[1] * w / img.size[0])))
            img.save()
        size = tuple(img.size)
    finally:
        bpy.data.images.remove(img)
    info = {"done": f"{sec:.1f} 秒で撮った({size[0]}x{size[1]})", "image": str(path)}
    if grid:
        gp = d / f"{name}_grid.png"
        _grid_copy(path, gp)
        info["grid_image"] = str(gp)
    info["next"] = ["image を目で見る。直す所があれば grid_image の目盛りで rect を読み、"
                    "erase_lines / fade_lines / add_lines / crisp で直す",
                    "直したら同じ name で撮り直さず、別の name(例 'fix1')で撮って前後を見比べる"]
    return _emit("render", info)


# ---------------------------------------------------------------- 場所を決める(筆の代わり)
_DEFORM = {"ARMATURE", "LATTICE", "CURVE", "MESH_DEFORM", "SIMPLE_DEFORM", "HOOK", "SMOOTH",
           "LAPLACIANSMOOTH", "CORRECTIVE_SMOOTH", "CAST", "WAVE", "DISPLACE", "SURFACE_DEFORM",
           "WARP", "SHRINKWRAP", "LAPLACIANDEFORM", "MESH_CACHE", "MESH_SEQUENCE_CACHE"}


def _deformed_points(obj):
    """形を変えないモディファイア(ボーンなど)だけ効かせた、頂点と面の中心(ワールド座標)。

    ポーズを付けたキャラは、元の形と見えている形が違うので、見えている形で場所を決める。
    面の数が変わるモディファイア(細分化など)は一時的に切る。
    """
    import numpy as np
    keep = []
    for m in obj.modifiers:
        if m.type not in _DEFORM and m.show_viewport:
            keep.append(m)
            m.show_viewport = False
    try:
        dg = bpy.context.evaluated_depsgraph_get()
        dg.update()
        ev = obj.evaluated_get(dg)
        me = ev.to_mesh()
        try:
            src = me if len(me.vertices) == len(obj.data.vertices) else obj.data
            v = np.empty(len(src.vertices) * 3, dtype=np.float32)
            src.vertices.foreach_get("co", v)
            v = v.reshape(-1, 3)
        finally:
            ev.to_mesh_clear()
    finally:
        for m in keep:
            m.show_viewport = True
    mw = np.array(obj.matrix_world, dtype=np.float32)
    v = v @ mw[:3, :3].T + mw[:3, 3]
    me = obj.data
    c = np.empty(len(me.polygons) * 3, dtype=np.float32)
    # 面の中心は、動かした頂点の平均で取り直す
    ls = np.empty(len(me.polygons), dtype=np.int32)
    lt = np.empty(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("loop_start", ls)
    me.polygons.foreach_get("loop_total", lt)
    lv = np.empty(len(me.loops), dtype=np.int32)
    me.loops.foreach_get("vertex_index", lv)
    sums = np.zeros((len(me.polygons), 3), dtype=np.float64)
    owner = np.repeat(np.arange(len(me.polygons)), lt)
    np.add.at(sums, owner, v[lv])
    c = (sums / lt[:, None]).astype(np.float32)
    return v, c, owner, lv


def _project(sc, cam, pts):
    """ワールド座標 → カメラ画面の割合(左上 0,0)と、前にあるか。"""
    import numpy as np
    from bpy_extras.object_utils import world_to_camera_view
    import mathutils
    out = np.empty((len(pts), 3), dtype=np.float32)
    for i, p in enumerate(pts):
        q = world_to_camera_view(sc, cam, mathutils.Vector(p))
        out[i] = (q.x, 1.0 - q.y, q.z)
    return out


def _faces(obj, where: dict):
    """where を満たす面の番号(numpy の bool 配列)。"""
    import numpy as np
    from bpy_extras.object_utils import world_to_camera_view
    me = obj.data
    n = len(me.polygons)
    sel = np.ones(n, dtype=bool)
    if "material" in where:
        keys = where["material"]
        keys = [keys] if isinstance(keys, str) else list(keys)
        slots = [i for i, ms in enumerate(obj.material_slots)
                 if ms.material and any(k.lower() in ms.material.name.lower() for k in keys)]
        mi = np.empty(n, dtype=np.int32)
        me.polygons.foreach_get("material_index", mi)
        sel &= np.isin(mi, slots)
    if "vertex_group" in where:
        vg = obj.vertex_groups.get(where["vertex_group"])
        if vg is None:
            cand = [g for g in obj.vertex_groups if where["vertex_group"].lower() in g.name.lower()]
            vg = cand[0] if cand else None
        if vg is None:
            sel &= False
        else:
            inside = np.zeros(len(me.vertices), dtype=bool)
            for v in me.vertices:
                for g in v.groups:
                    if g.group == vg.index and g.weight >= 0.5:
                        inside[v.index] = True
                        break
            for p in me.polygons:
                if sel[p.index] and not all(inside[i] for i in p.vertices):
                    sel[p.index] = False
    if "rect" in where:
        x0, y0, x1, y1 = where["rect"]
        sc = bpy.context.scene
        cam = sc.camera
        verts, cent, owner, lv = _deformed_points(obj)
        pv = _project(sc, cam, verts)
        vin = (pv[:, 0] >= x0) & (pv[:, 0] <= x1) & (pv[:, 1] >= y0) & (pv[:, 1] <= y1) & (pv[:, 2] > 0)
        # 面の頂点の半分以上が四角の中にある面だけ。中心だけで決めると、地面のような大きな
        # 面がまるごと入り、四角の外まで効いた(試しに使って発見)
        frac = np.zeros(n, dtype=np.float64)
        np.add.at(frac, owner, vin[lv].astype(np.float64))
        cnt = np.bincount(owner, minlength=n).astype(np.float64)
        cand = sel & (frac >= 0.5 * np.maximum(cnt, 1))
        ok = np.zeros(n, dtype=bool)
        import mathutils
        dg = bpy.context.evaluated_depsgraph_get()
        cam_pos = cam.matrix_world.translation
        view_dir = (cam.matrix_world.to_quaternion() @ mathutils.Vector((0, 0, -1))).normalized()
        visible = where.get("visible_only", True)
        for i in np.nonzero(cand)[0]:
            p = mathutils.Vector(cent[i])
            if visible:
                if cam.data.type == "ORTHO":
                    origin = p - view_dir * 1000.0
                    d = view_dir
                else:
                    origin = cam_pos
                    d = (p - cam_pos).normalized()
                hit, loc, _nrm, _idx, hobj, _m = sc.ray_cast(dg, origin, d)
                if not hit:
                    continue
                dist = (p - origin).length
                if (loc - origin).length < dist - 0.03 * dist - 0.01:
                    continue                     # 手前に別の物か、自分の表の面がある(裏の面)
            ok[i] = True
        sel &= ok
    return sel


def _targets(where: dict):
    where = dict(where or {})
    objs = _objs(where.get("objects"))
    out = []
    for o in objs:
        if "mecha_color" not in o.data.color_attributes:
            continue
        f = _faces(o, where)
        if f.any():
            out.append((o, f))
    return out


def _paint(obj, layer, faces, color):
    """選んだ面の角を全部 color にする(面ごとなので境目はくっきり)。"""
    import numpy as np
    from . import utils
    utils.ensure_vertex_color(obj, layer, (0.0, 0.0, 0.0, 1.0))
    me = obj.data
    attr = me.color_attributes[layer]
    if attr.domain != "CORNER":
        raise RuntimeError(f"{obj.name}.{layer} は角(CORNER)の色ではありません")
    buf = np.empty(len(attr.data) * 4, dtype=np.float32)
    attr.data.foreach_get("color", buf)
    buf = buf.reshape(-1, 4)
    ls = np.empty(len(me.polygons), dtype=np.int32)
    lt = np.empty(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("loop_start", ls)
    me.polygons.foreach_get("loop_total", lt)
    idx = np.concatenate([np.arange(s, s + t) for s, t in zip(ls[faces], lt[faces])]) \
        if faces.any() else np.zeros(0, dtype=np.int64)
    if callable(color):
        buf[idx] = color(buf[idx])
    else:
        buf[idx] = color
    attr.data.foreach_set("color", buf.ravel())
    me.update()
    return int(faces.sum())


def _refresh(channel: str | None):
    """塗った色を線に届ける(その色の AOV を入れてコンポジタを組み直す)。"""
    from . import fp_core
    sc = bpy.context.scene
    if channel and hasattr(sc, f"fp_{channel}") and not getattr(sc, f"fp_{channel}"):
        setattr(sc, f"fp_{channel}", True)
    fp_core.setup_aov(sc, bpy.context.view_layer)
    if _applied(sc):
        fp_core.setup_compositor(sc, bpy.context.view_layer)


def _undo_push(msg):
    try:
        bpy.ops.ed.undo_push(message=f"FreePencil AI: {msg}")
    except Exception:              # noqa: BLE001  ヘッドレスでは取り消しが無い
        pass
    _SNAP.append(_snapshot_colors())
    del _SNAP[:-8]


_SNAP: list = []


def _snapshot_colors():
    """undo() 用に、触る前の色を控える(ヘッドレスでも戻せるように)。"""
    import numpy as np
    snap = {}
    for o in _meshes():
        for layer in ("mecha_color", "mask_color", "line_color"):
            a = o.data.color_attributes.get(layer)
            if a is None or a.domain != "CORNER":
                continue
            buf = np.empty(len(a.data) * 4, dtype=np.float32)
            a.data.foreach_get("color", buf)
            snap[(o.name, layer)] = buf
    return snap


def undo() -> dict:
    """直前の erase_lines / fade_lines / add_lines / crisp を 1 手戻す。"""
    if not _SNAP:
        return _emit("undo", {"warnings": ["戻せる手がありません"]})
    snap = _SNAP.pop()
    for (name, layer), buf in snap.items():
        o = bpy.data.objects.get(name)
        if o is None or layer not in o.data.color_attributes:
            continue
        o.data.color_attributes[layer].data.foreach_set("color", buf)
        o.data.update()
    _refresh(None)
    return _emit("undo", {"done": "1 手戻した", "next": ["render で戻ったか見る"]})


def _where_text(where):
    return json.dumps(where, ensure_ascii=False) if where else "全部"


def erase_lines(where: dict) -> dict:
    """where の範囲の線を消す(STEP4 のマスクを白で塗るのと同じ)。

    使う所: 余計な線、黒い塊、しわや模様のうるさい線。範囲のすぐ外の線も少し消える
    (マスクは 3px ほど広げて効かせる)。
    """
    tg = _targets(where)
    if not tg:
        return _emit("erase_lines", {"warnings": [f"where に当たる面がありません: {_where_text(where)}"],
                                     "next": ["rect を広げる、material / objects の名前を state() で確かめる"]})
    _undo_push("erase_lines")
    n = sum(_paint(o, "mask_color", f, (1.0, 1.0, 1.0, 1.0)) for o, f in tg)
    _refresh("mask_color")
    return _emit("erase_lines", {
        "done": f"{[o.name for o, _ in tg]} の {n} 面にマスクを塗った({_where_text(where)})",
        "next": ["render('fixN') で撮って、消したい線が消え、要る線(輪郭など)が残っているか見る",
                 "消えすぎたら undo()。要る輪郭まで消えたら rect を小さくする"]})


def fade_lines(where: dict, amount: float = 0.3) -> dict:
    """where の範囲の線を薄くする(STEP4 のラインを塗るのと同じ)。

    amount: 0.2 = 少し薄く、0.3〜0.4 = だいぶ薄く、0.4 以上 = ほぼ消える(実測の段差は粗い)。
    """
    amount = max(0.0, min(1.0, float(amount)))
    tg = _targets(where)
    if not tg:
        return _emit("fade_lines", {"warnings": [f"where に当たる面がありません: {_where_text(where)}"]})
    _undo_push("fade_lines")
    n = sum(_paint(o, "line_color", f, (amount, amount, amount, 1.0)) for o, f in tg)
    _refresh("line_color")
    return _emit("fade_lines", {
        "done": f"{n} 面の線を {amount:.2f} で薄くした({_where_text(where)})",
        "next": ["render で見る。足りなければ amount を上げる(0.4 以上はほぼ消える)"]})


def _lum(c):
    return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]


def add_lines(where: dict, strength: float = 0.4) -> dict:
    """where の範囲を別の色で塗り分け、その外周に線を出す(STEP4 で塗り分けを塗るのと同じ)。

    使う所: 髪と顔の境目、服の切り替え、ポケットなど、欲しいのに線が無い所。
    線は塗った範囲の「縁」に出る。範囲の中には線は出ない。strength は明るさの差(0.3〜0.5)。
    """
    import numpy as np
    tg = _targets(where)
    if not tg:
        return _emit("add_lines", {"warnings": [f"where に当たる面がありません: {_where_text(where)}"]})
    _undo_push("add_lines")
    total = 0
    for o, f in tg:
        a = o.data.color_attributes["mecha_color"]
        buf = np.empty(len(a.data) * 4, dtype=np.float32)
        a.data.foreach_get("color", buf)
        buf = buf.reshape(-1, 4)
        cur = float(_lum(buf).mean())          # 周りの明るさ(物全体の平均)

        def shift(c, cur=cur):
            # 線は輝度の段差で出るので、明るさを strength だけずらす(色相はそのまま)
            out = c.copy()
            d = -strength if cur > 0.5 else strength
            out[:, :3] = np.clip(out[:, :3] + d, 0.0, 1.0)
            return out
        total += _paint(o, "mecha_color", f, shift)
    _refresh(None)
    return _emit("add_lines", {
        "done": f"{total} 面を塗り分けた({_where_text(where)})。その範囲の縁に線が出る",
        "next": ["render で、縁に 1 本の線が出たか見る。出ないときは strength を 0.5 に上げる",
                 "要らない所まで線が出たら undo()、範囲(material / vertex_group)を絞る"]})


def merge(where: dict) -> dict:
    """where の範囲の塗り分けを 1 色にそろえ、範囲の中に形の線を出さない。

    使う所: 目のまわりの眼球の丸い線のように、形(メッシュ)の境目から出る要らない線。
    erase_lines(マスク)と違い、範囲の中の絵の線(texture_lines)や、手前に重なった別の物
    (前髪など)の線は消えない。範囲の外との境目には線が出ることがあるので、範囲は部品より
    少し広く取る。
    """
    import numpy as np
    tg = _targets(where)
    if not tg:
        return _emit("merge", {"warnings": [f"where に当たる面がありません: {_where_text(where)}"]})
    _undo_push("merge")
    total = 0
    for o, f in tg:
        for layer in ("mecha_color", "bone_color"):
            a = o.data.color_attributes.get(layer)
            if a is None or a.domain != "CORNER":
                continue
            buf = np.empty(len(a.data) * 4, dtype=np.float32)
            a.data.foreach_get("color", buf)
            buf = buf.reshape(-1, 4)
            me = o.data
            idx = np.array([i for p in me.polygons if f[p.index] for i in p.loop_indices], dtype=np.int64)
            if not len(idx):
                continue
            # 範囲の中で一番多い色(顔なら肌の島の色)にそろえる
            q = np.round(buf[idx, :3], 2)
            vals, cnt = np.unique(q, axis=0, return_counts=True)
            c = vals[cnt.argmax()]
            buf[idx, :3] = c
            a.data.foreach_set("color", buf.ravel())
            me.update()
        total += int(f.sum())
    _refresh(None)
    return _emit("merge", {"done": f"{total} 面の塗り分けを 1 色にそろえた({_where_text(where)})",
                           "next": ["render で、要らない形の線が消え、前髪などの線が残っているか見る",
                                    "目なら続けて texture_lines(where, dark_only=0.3) でまつ毛と瞳の線を絵から出す"]})


def soft_overlays(materials) -> dict:
    """半透明で上に重ねる材質(髪の影・頬の赤み・目の光など)を、線を出さない元の描き方に戻す。

    STEP0 は、半透明(BLEND)の材質を HASHED にする(BLEND は AOV が書かれず線が出ないため)。
    MMD などのキャラは、髪の影や頬の赤みを半透明の板で重ねていて、HASHED にするとざらざらの
    黒い点になり、板の縁に線も出た。こういう材質は BLEND に戻す(見た目はそのまま、線は出ない)。
    materials は名前の一部のリスト(例 ["hairShadow", "髪影", "チーク", "ハイライト"])。
    """
    keys = [materials] if isinstance(materials, str) else list(materials)

    def hit(name):
        # "=U" は名前がちょうど U のものだけ(1 文字の名前を部分一致にすると、ほかの材質まで当たる)
        return any((name == k[1:]) if k.startswith("=") else (k.lower() in name.lower()) for k in keys)
    done = []
    for m in bpy.data.materials:
        if not hit(m.name):
            continue
        try:
            m.blend_method = "BLEND"
        except (TypeError, AttributeError):
            pass
        if hasattr(m, "surface_render_method"):
            m.surface_render_method = "BLENDED"
        done.append(m.name)
    return _emit("soft_overlays", {"done": f"線を出さない重ねの材質にした: {done}" if done else "当たる材質がありません",
                                   "next": ["render で、ざらざらの点と板の縁の線が消えたか見る"]})


CLIP_LABEL = "FreePencil_ai_clip"


def clip_alpha(materials=None, threshold: float = 0.5, skip=None) -> dict:
    """絵の透け(アルファ)を、ある/ない の 2 つに切る(半透明の縁を無くす)。

    HASHED(STEP0 が半透明の材質に使う描き方)は、半透明の所をまだらに描く。前髪の先やまつ毛の
    縁が半透明の絵だと、そこがざらざらの黒い点になり、線にも出た(MMD のキャラで発見)。
    materials: 名前の一部のリスト。None なら HASHED の材質すべて(skip に挙げたものを除く)。
    """
    keys = None if materials is None else ([materials] if isinstance(materials, str) else list(materials))
    skips = [] if skip is None else ([skip] if isinstance(skip, str) else list(skip))
    done = []
    for m in bpy.data.materials:
        if not m.use_nodes or m.node_tree is None:
            continue
        if keys is not None and not any(k.lower() in m.name.lower() for k in keys):
            continue
        if any((m.name == k[1:]) if k.startswith("=") else (k.lower() in m.name.lower()) for k in skips):
            continue
        if keys is None and getattr(m, "blend_method", "") != "HASHED":
            continue
        nt = m.node_tree
        for n in [n for n in nt.nodes if n.label == CLIP_LABEL]:
            src = n.inputs[0].links[0].from_socket if n.inputs[0].is_linked else None
            dsts = [lk.to_socket for lk in n.outputs[0].links]
            nt.nodes.remove(n)
            for d in dsts:
                if src is not None:
                    nt.links.new(src, d)
        hit = False
        for lk in list(nt.links):
            if lk.from_node.bl_idname == "ShaderNodeTexImage" and lk.from_socket.name == "Alpha":
                c = nt.nodes.new("ShaderNodeMath")
                c.label = CLIP_LABEL
                c.operation = "GREATER_THAN"
                c.inputs[1].default_value = float(threshold)
                c.location = (lk.to_node.location.x - 180, lk.to_node.location.y - 120)
                src, dst = lk.from_socket, lk.to_socket
                nt.links.remove(lk)
                nt.links.new(src, c.inputs[0])
                nt.links.new(c.outputs[0], dst)
                hit = True
        if hit:
            done.append(m.name)
    return _emit("clip_alpha", {"done": f"透けを切った材質 {len(done)} 個: {done[:12]}",
                                "next": ["render で、前髪の先やまつ毛のざらざらが消えたか見る",
                                         "髪の影や頬の赤みは soft_overlays(切ると消えてしまう)"]})


def crisp(where: dict) -> dict:
    """where の範囲で、面の中の色の段差(ぼかし)を無くす。境目がくっきり 1 本の線になる。

    使う所: 頂点ペイントで塗った境目が、太くぼやけた帯になっている所。面ごとに、
    その面で一番多い色にそろえる(Half Fill を範囲でまとめてやるのと同じ効き目)。
    """
    import numpy as np
    tg = _targets(where)
    if not tg:
        return _emit("crisp", {"warnings": [f"where に当たる面がありません: {_where_text(where)}"]})
    _undo_push("crisp")
    total = 0
    for o, f in tg:
        me = o.data
        a = me.color_attributes["mecha_color"]
        buf = np.empty(len(a.data) * 4, dtype=np.float32)
        a.data.foreach_get("color", buf)
        buf = buf.reshape(-1, 4)
        for p in me.polygons:
            if not f[p.index]:
                continue
            ids = list(p.loop_indices)
            q = [tuple(np.round(buf[i], 2)) for i in ids]
            best = max(set(q), key=q.count)
            j = ids[q.index(best)]
            buf[ids] = buf[j]
            total += 1
        a.data.foreach_set("color", buf.ravel())
        me.update()
    _refresh(None)
    return _emit("crisp", {"done": f"{total} 面の色をそろえた({_where_text(where)})",
                           "next": ["render で、太い帯が細い 1 本になったか見る"]})


TEX_LABEL = "FreePencil_ai_texture"


def _base_image_node(mat):
    """材質の色になっている画像テクスチャ(基本色・発光の色につながっているもの)。"""
    best = None
    for n in mat.node_tree.nodes:
        if n.bl_idname != "ShaderNodeTexImage" or n.image is None:
            continue
        to = [lk.to_socket.name for o in n.outputs for lk in o.links]
        score = sum(t in ("Base Color", "Color") for t in to) - sum(t in ("Fac", "Alpha") for t in to)
        if best is None or score > best[0]:
            best = (score, n)
    return best[1] if best and best[0] > 0 else None


TEX_AREA = "fp_tex_area"


def _soft_area(obj, faces, rings: int = 5):
    """選んだ面に 1、外へ rings 段かけてなだらかに 0 へ落ちる値を、角の色 fp_tex_area に書く。

    FreePencil はなだらかな色の変化には線を出さない。範囲の縁で絵の効き目をなだらかに落とすと、
    縁に段差の線が出ない(くっきり 0/1 で切ると、頬を横切るギザギザの線が出た)。
    """
    import numpy as np
    me = obj.data
    nv = len(me.vertices)
    lv = np.empty(len(me.loops), dtype=np.int32)
    me.loops.foreach_get("vertex_index", lv)
    ls = np.empty(len(me.polygons), dtype=np.int32)
    lt = np.empty(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("loop_start", ls)
    me.polygons.foreach_get("loop_total", lt)
    core = np.zeros(nv, dtype=np.float64)
    for s_, t_ in zip(ls[faces], lt[faces]):
        core[lv[s_:s_ + t_]] = 1.0
    ed = np.empty(len(me.edges) * 2, dtype=np.int32)
    me.edges.foreach_get("vertices", ed)
    ed = ed.reshape(-1, 2)
    deg = np.bincount(ed.ravel(), minlength=nv).astype(np.float64)
    val = core.copy()
    for _ in range(max(1, int(rings))):
        acc = np.zeros(nv)
        np.add.at(acc, ed[:, 0], val[ed[:, 1]])
        np.add.at(acc, ed[:, 1], val[ed[:, 0]])
        avg = np.divide(acc, deg, out=np.zeros(nv), where=deg > 0)
        val = np.maximum(core, 0.5 * val + 0.5 * avg)       # 中は 1 のまま、外へ広がって落ちる
    # 外側の 1 段目からなだらかに。いちばん外は 0 に寄せる
    val = np.clip(val, 0.0, 1.0)
    from . import utils
    utils.ensure_vertex_color(obj, TEX_AREA, (0.0, 0.0, 0.0, 1.0))
    a = me.color_attributes[TEX_AREA]
    buf = np.ones((len(me.loops), 4), dtype=np.float32)
    buf[:, :3] = val[lv][:, None]
    a.data.foreach_set("color", buf.ravel())
    me.update()


def _area_median_color(objs_faces, img_node):
    """範囲の面が絵の中で使っている所の、色の中央値(範囲の外に足す色)。"""
    import numpy as np
    img = img_node.image
    w, h = img.size
    if not w or not h:
        return (0.5, 0.5, 0.5, 1.0)
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    samples = []
    for o, f in objs_faces:
        uv = o.data.uv_layers.active
        if uv is None:
            continue
        me = o.data
        loops = [i for p in me.polygons if f[p.index] for i in p.loop_indices]
        if not loops:
            continue
        co = np.empty(len(me.loops) * 2, dtype=np.float32)
        uv.data.foreach_get("uv", co)
        co = co.reshape(-1, 2)[loops] % 1.0
        xs = np.clip((co[:, 0] * w).astype(int), 0, w - 1)
        ys = np.clip((co[:, 1] * h).astype(int), 0, h - 1)
        samples.append(px[ys, xs, :3])
    if not samples:
        return (0.5, 0.5, 0.5, 1.0)
    m = np.median(np.concatenate(samples), axis=0)
    # 8bit の sRGB の絵は、pixels で読むと sRGB のまま。材質の中のテクスチャは線形の値を出すので
    # 線形に直す(直さないと外に足す色だけ明るく、範囲の縁に段差の線が出た)
    if not img.is_float and img.colorspace_settings.name.lower().startswith("srgb"):
        m = np.where(m <= 0.04045, m / 12.92, ((m + 0.055) / 1.055) ** 2.4)
    return (float(m[0]), float(m[1]), float(m[2]), 1.0)


def texture_lines(where: dict, strength: float = 1.0, dark_only: float | None = None,
                  blur: int = 1) -> dict:
    """材質の絵(テクスチャ)の色の境目も線にする(AOV グループの line_texture に絵をつなぐ)。

    使う所: 目・口・眉・服の模様など、形ではなく絵に描いてあるもの。FreePencil は形の境目から
    線を作るので、絵に描いた口は線にならない。
    where: {'objects': [...]} / {'material': ...} だけなら材質全体。rect や vertex_group を足すと、
    その面だけで絵を使う(瞳のように絵が細かすぎて黒い塊になる所を避けて、口だけ、など)。
    strength(0〜1)を下げると、絵の淡い色の差は線になりにくくなる。
    dark_only(0〜1、例 0.3): 絵の暗い所(明るさがこの値より下)だけを線にする。目なら、まつ毛と
    瞳の縁だけが線になり、瞳の中の模様や光は線にならない(アニメの目の描き方)。
    blur(1, 2, 4, 8): 線に使う絵を 1/blur に縮めた写しにする(材質の見た目は変わらない)。
    まつ毛のつぶつぶや瞳の中の細い輪が消え、太い 1 本の線にまとまる。
    """
    from . import fp_core
    objs = _objs((where or {}).get("objects"))
    keys = (where or {}).get("material")
    keys = [keys] if isinstance(keys, str) else (list(keys) if keys else None)
    mats = []
    for o in objs:
        for ms in o.material_slots:
            m = ms.material
            if m and m.use_nodes and m.node_tree and m not in mats and (
                    keys is None or any(k.lower() in m.name.lower() for k in keys)):
                mats.append(m)
    # 場所を絞るときは、その面に印の色(fp_tex_area)を塗り、材質の中で絵に掛ける
    area = any(k in (where or {}) for k in ("rect", "vertex_group"))
    if area:
        tg = _targets(where)
        if not tg:
            return _emit("texture_lines", {"warnings": [f"where に当たる面がありません: {_where_text(where)}"]})
        _undo_push("texture_lines")
        for o in objs:
            from . import utils
            utils.ensure_vertex_color(o, TEX_AREA, (0.0, 0.0, 0.0, 1.0))
        for o, f in tg:
            _soft_area(o, f, rings=int((where or {}).get("soft", 5)))
    done, skipped = [], []
    for m in mats:
        nt = m.node_tree
        grp = next((n for n in nt.nodes if n.type == "GROUP" and n.node_tree is not None
                    and n.node_tree.name == fp_core.AOV_GROUP_NAME), None)
        img = _base_image_node(m)
        if grp is None or img is None or "line_texture" not in grp.inputs:
            skipped.append(m.name)
            continue
        for n in [n for n in nt.nodes if n.label == TEX_LABEL]:
            nt.nodes.remove(n)
        mix = nt.nodes.new("ShaderNodeMix")
        mix.label = TEX_LABEL
        mix.data_type = "RGBA"
        mix.blend_type = "MIX"
        mix.location = (grp.location.x - 220, grp.location.y - 260)
        fac = next(i for i in mix.inputs if i.type == "VALUE")
        fac.default_value = 1.0
        a = next(i for i in mix.inputs if i.type == "RGBA" and i.name == "A")
        b = next(i for i in mix.inputs if i.type == "RGBA" and i.name == "B")
        a.default_value = (0.0, 0.0, 0.0, 1.0)
        if area:
            # 範囲の外には、範囲の絵の中央値(肌の色など)を足す。黒(何も足さない)だと、
            # 範囲の縁で明るさが段差になり、頬を横切るギザギザの線が出た(試しに使って発見)
            a.default_value = _area_median_color([(o, f) for o, f in tg if m.name in
                                                  [ms.material.name for ms in o.material_slots if ms.material]],
                                                 img)
            kk = max(0.0, min(1.0, float(strength)))    # 中の絵と同じ強さを掛ける
            a.default_value = tuple(c * kk for c in a.default_value[:3]) + (1.0,)
            if dark_only is not None:
                a.default_value = (kk, kk, kk, 1.0)     # 暗い所だけのときは、外は明るい側と同じ
        # 強さ: 絵を黒へ寄せる(淡い差は線にならなくなる)
        k = max(0.0, min(1.0, float(strength)))
        src_out = img.outputs["Color"]
        if int(blur) > 1:
            name = f"{img.image.name}__fp_blur{int(blur)}"
            small = bpy.data.images.get(name)
            if small is None:
                small = img.image.copy()
                small.name = name
                w_, h_ = img.image.size
                small.scale(max(8, w_ // int(blur)), max(8, h_ // int(blur)))
                small.pack()
            tex = nt.nodes.new("ShaderNodeTexImage")
            tex.label = TEX_LABEL
            tex.image = small
            tex.interpolation = "Cubic"
            tex.location = (mix.location.x - 640, mix.location.y + 200)
            vec = img.inputs["Vector"]
            if vec.is_linked:
                nt.links.new(vec.links[0].from_socket, tex.inputs["Vector"])
            src_out = tex.outputs["Color"]
        if dark_only is not None:
            # 明るさを、しきい値のまわりで 0(暗い線)/ k(明るい地)の 2 値に近くする
            bw = nt.nodes.new("ShaderNodeRGBToBW")
            bw.label = TEX_LABEL
            bw.location = (mix.location.x - 420, mix.location.y)
            mr = nt.nodes.new("ShaderNodeMapRange")
            mr.label = TEX_LABEL
            mr.location = (mix.location.x - 220, mix.location.y + 120)
            th = max(0.02, min(0.98, float(dark_only)))
            mr.inputs["From Min"].default_value = th - 0.03
            mr.inputs["From Max"].default_value = th + 0.03
            mr.inputs["To Min"].default_value = 0.0
            mr.inputs["To Max"].default_value = k
            mr.clamp = True
            nt.links.new(src_out, bw.inputs["Color"])
            nt.links.new(bw.outputs["Val"], mr.inputs["Value"])
            nt.links.new(mr.outputs["Result"], b)
        elif k < 1.0:
            sc_ = nt.nodes.new("ShaderNodeMix")
            sc_.label = TEX_LABEL
            sc_.data_type = "RGBA"
            sc_.blend_type = "MULTIPLY"
            sc_.location = (mix.location.x - 200, mix.location.y)
            next(i for i in sc_.inputs if i.type == "VALUE").default_value = 1.0
            next(i for i in sc_.inputs if i.type == "RGBA" and i.name == "B").default_value = (k, k, k, 1.0)
            nt.links.new(src_out, next(i for i in sc_.inputs if i.type == "RGBA" and i.name == "A"))
            nt.links.new(next(o for o in sc_.outputs if o.type == "RGBA"), b)
        else:
            nt.links.new(src_out, b)
        if area:
            attr = nt.nodes.new("ShaderNodeVertexColor")
            attr.label = TEX_LABEL
            attr.layer_name = TEX_AREA
            attr.location = (mix.location.x - 200, mix.location.y - 200)
            nt.links.new(attr.outputs["Color"], fac)
        out = next(o for o in mix.outputs if o.type == "RGBA")
        nt.links.new(out, grp.inputs["line_texture"])
        done.append(f"{m.name}({img.image.name})")
    _refresh(None)
    return _emit("texture_lines", {
        "done": f"絵をつないだ: {done}" if done else "つなげる絵がありません",
        "warnings": [f"AOV グループか基本色の絵が無い材質: {skipped}"] if skipped else [],
        "next": ["render で、目・口など絵に描いた線が出たか見る",
                 "絵の細かい色の差がノイズになったら strength を下げる(0.5)。消したい所は erase_lines"]})


def line_width(objects, x: float) -> dict:
    """物ごとの線の太さ(STEP0 の「線の太さ(倍)」)。1=そのまま 2/3=太く 0.5=薄く 0=消す。"""
    objs = _objs(objects)
    for o in objs:
        o.fp_line_scale = float(x)
    from . import fp_core
    sc = bpy.context.scene
    if _applied(sc):
        fp_core.setup_compositor(sc, bpy.context.view_layer)
    return _emit("line_width", {"done": f"{[o.name for o in objs]} の線を {x} 倍にした",
                                "next": ["render で見る。輪郭だけ太くしたいキャラは本体だけ 1.5〜2"]})


def preview(mode: str = "WHITE") -> dict:
    """線の下に敷く絵: WHITE(線だけ) / NONE(材質の色) / MONO_LIGHT(モノクロの陰) / CEL(セル)。"""
    bpy.context.scene.fp_preview_mode = mode
    return _emit("preview", {"done": f"プレビューを {mode} にした", "next": ["render で見る"]})


def cel(cast_shadows: bool | None = None, **kw) -> dict:
    """セルのつまみ: threshold / softness / pale / shadow_color / sky / sky_color / shadow_line …

    cast_shadows=False: 日の落とす影(髪の影が顔に落ちる等)を切り、面の向きだけで陰を付ける。
    キャラの顔に大きなまだらの影が出るときに使う。
    """
    sc = bpy.context.scene
    if cast_shadows is not None:
        for o in sc.objects:
            if o.type == "LIGHT" and o.data.type == "SUN":
                o.data.use_shadow = bool(cast_shadows)
    sc.fp_preview_mode = "CEL"
    done = []
    for k, v in kw.items():
        name = f"fp_cel_{k}"
        if hasattr(sc, name):
            setattr(sc, name, v)
            done.append(f"{k}={v}")
    return _emit("cel", {"done": "セルにした " + " ".join(done),
                         "next": ["render で影の形を見る。影が多すぎれば threshold を下げる(0.4)"]})


def remove() -> dict:
    """FreePencil を外す(STEP0 の前に戻る)。"""
    res = bpy.ops.freepencil.remove("EXEC_DEFAULT")
    return _emit("remove", {"done": f"外した {sorted(res)}", "next": ["もう一度やるなら auto()"]})


# ---------------------------------------------------------------- ボタンごとの指示
# ボタン(オペレーター)を Python から押したあとに出す。人がパネルで押したときも
# コンソールにだけ出る(画面には出ない)
def _note_step0(op, res):
    return _after_step0(bpy.context.scene.fp_auto_style, res, 0.0)


BUTTON_SKILLS = {
    "freepencil.auto_setup": _note_step0,
    "freepencil.auto_vertex_color": lambda op, res: _emit("STEP1", {
        "done": f"STEP1(塗り分け) {sorted(res)}。色が変わっただけで、線はまだ変わらない",
        "next": ["STEP3(bpy.ops.freepencil2.link_button)を押すと線に出る。普通は auto() で通す方が良い",
                 "色を見たいときはビューポートを頂点カラー表示に"]}),
    "freepencil4.link_button": lambda op, res: _emit("STEP2", {
        "done": f"STEP2(AOV) {sorted(res)}", "state": {"aovs": [a.name for a in bpy.context.view_layer.aovs]},
        "next": ["STEP3(bpy.ops.freepencil2.link_button)で線画のコンポジタを組む"]}),
    "freepencil2.link_button": lambda op, res: _emit("STEP3", {
        "done": f"STEP3(線画のコンポジタ) {sorted(res)}",
        "warnings": ([] if "mecha_color" in [a.name for a in bpy.context.view_layer.aovs]
                     else ["mecha_color の AOV がありません。STEP1 → STEP2 が先"]),
        "next": ["render('check') で撮って目で見る"]}),
    "freepencil.measure_line_weight": lambda op, res: _emit("しきい値を測る", {
        "done": f"{sorted(res)}。線の強弱のしきい値をこのカメラで測り直した",
        "next": ["カメラを変えたときだけ押す。render で強弱を見る"]}),
    "freepencil3.link_button": lambda op, res: _emit("STEP4 頂点カラーを塗る", {
        "done": f"{sorted(res)}。頂点ペイントに入った(人が筆で塗る所)",
        "warnings": ["AI は筆で塗れないので、代わりに erase_lines / fade_lines / add_lines を使う"],
        "next": ["bpy.ops.object.mode_set(mode='OBJECT') で戻ってから窓口の道具を使う"]}),
    "freepencil5.link_button": lambda op, res: _emit("Half Fill", {
        "done": f"{sorted(res)}",
        "warnings": ["Half Fill は選んだ頂点の列が要る(人の操作向け)。AI は crisp(where) の方が確実"],
        "next": ["render で境目を見る"]}),
    "freepencil.render_cameras": lambda op, res: _emit("STEP5 カメラ一括", {
        "done": f"{sorted(res)}。//camera_renders/NN_カメラ名/ に final.png と各パス",
        "next": ["各カメラの final.png を目で見る"]}),
    "freepencil.remove": lambda op, res: _emit("外す", {
        "done": f"{sorted(res)}。STEP0 の前の絵に戻った", "next": ["もう一度やるなら auto()"]}),
    "freepencil.randomize_seed": lambda op, res: _emit("種を変える", {
        "done": "配色の種を変えた(線の位置は同じ、色だけ変わる)",
        "next": ["STEP1 → STEP3 を押すまで絵は変わらない"]}),
    "freepencil.ai_guide": None,
}


_DEPTH = [0]


def install_hooks(classes):
    """各ボタンの execute を包み、押した後に指示を出す。ボタンのコードは変えない。

    ボタンの中で別のボタンを押す(STEP0 は STEP1〜3 を中で押す)ときは、外側の指示だけ出す。
    """
    for cls in classes:
        idn = getattr(cls, "bl_idname", "")
        fn = BUTTON_SKILLS.get(idn)
        if fn is None or getattr(cls, "_fp_ai_wrapped", False) or "execute" not in cls.__dict__:
            continue
        # Blender は execute の引数が (self, context) の 2 個であることを確かめて登録する。
        # 既定値で引数を足すと登録が断られる(「already registered」と出て気づきにくい)
        cls.execute = _wrap(cls.execute, fn)
        cls._fp_ai_wrapped = True


def _wrap(orig, fn):
    def execute(self, context):
        _DEPTH[0] += 1
        try:
            res = orig(self, context)
        finally:
            _DEPTH[0] -= 1
        if _DEPTH[0] == 0:
            try:
                fn(self, res)
            except Exception as e:          # noqa: BLE001  指示が出せなくてもボタンは止めない
                print(f"{PREFIX} (指示を出せなかった: {e})")
        return res
    return execute


class FP_OT_AI_GUIDE(bpy.types.Operator):
    """For AI agents: print how to use FreePencil and what to do next in this scene"""
    bl_idname = "freepencil.ai_guide"
    bl_label = "AI guide"
    bl_description = ("For AI agents (and people using one): print the FreePencil workflow and the "
                      "next step for this scene to the console, and copy it to the clipboard")
    bl_options = {"REGISTER"}

    def execute(self, context):
        info = guide()
        text = "\n".join([
            "FreePencil (Blender add-on) AI guide",
            "Run in Blender Python:  import sys; fp = next(m for n, m in sys.modules.items() "
            "if n.endswith('freepencil2.ai'))",
            "Then follow:  print(fp.guide())",
            json.dumps(info, ensure_ascii=False, indent=1),
        ])
        try:
            context.window_manager.clipboard = text
        except Exception:                   # noqa: BLE001
            pass
        self.report({"INFO"}, bpy.app.translations.pgettext(
            "AI guide printed to the console and copied to the clipboard"))
        return {"FINISHED"}
