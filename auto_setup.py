"""STEP0: One-button full-auto setup.

シーンを解析しておすすめ設定を適用し、STEP1(頂点カラー)→STEP2(AOV)→
STEP3(PROノード)まで一括実行する。判定内容:
  - 対象: 選択メッシュ、無ければレンダリング対象の全メッシュ
  - リグ(Armature)があれば bone AOV を自動ON
  - 島分割は自動しきい値+シーム境界+小島マージ、パーツ・トーン分けON
  - blend_method='BLEND' は EEVEE が AOV を書かないため、本物のガラス
    (Transmission/低Alpha)以外を HASHED へ変更
  - film_transparent はシーンの見た目を尊重して元の値を維持
"""

import re

import bpy

from . import leaf_clump
from . import utils
from . import vertex_color
from . import vrm
from .fp_core import is_real_glass as _is_real_glass


def _channel_painted(objs, name: str) -> bool:
    """頂点カラー name が実際に塗られているか(黒=既定値のみは未塗り扱い)。

    STEP1 が mask/line/bone を既定の黒で常に作成するため、属性の存在では
    判定できない。RGB のどこかが黒以外なら「塗ってある」。
    """
    import numpy as np
    # リンク複製は同じメッシュ実体を指すので、実体ごとに1回だけ読む。
    # 1,186オブジェクト/159メッシュのシーンでは読み取り量が8分の1になる。
    # 小さいものから見るのは、塗ってあるチャンネルなら早い段階で
    # 打ち切れて巨大メッシュの読み込み(1枚 678MB)を回避できるため
    meshes = {o.data.name: o.data for o in objs}
    for me in sorted(meshes.values(), key=lambda m: len(m.loops)):
        attr = me.color_attributes.get(name)
        if attr is None or len(attr.data) == 0:
            continue
        buf = np.empty(len(attr.data) * 4, dtype=np.float32)
        attr.data.foreach_get("color", buf)
        if buf.reshape(-1, 4)[:, :3].max() > 1e-4:
            return True
    return False


def _looks_like_ground(obj, targets) -> bool:
    """視界より大きい平面か。面が少なく、薄く、他のどの物よりも 2 倍以上広い。

    中央値の 5 倍で判定すると、小物の多い町では家の土台や階段(平たい
    板)まで地面になった(実測)。一番大きい物と比べる。
    """
    from mathutils import Vector
    if len(obj.data.polygons) > 8:
        return False

    def dims(o):
        pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
        return Vector((max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3)))
    d = dims(obj)
    xy = max(d.x, d.y)
    if xy <= 0.0 or d.z > xy * 0.02:
        return False
    others = [max(dims(o)) for o in targets if o is not obj]
    if not others:
        return False
    return xy >= max(others) * 2.0


# 半透明で上に重ねる材質(髪の影・頬の赤み)の見分け。面が実際に使う UV の所だけで絵の透けを
# 拾い、半端(0.05〜0.95)が 7 割以上で、透けない所がほぼ無ければ重ね物。絵全体で測ると、
# ミクの髪影(目や口と同じ絵を使う)やサーバルのカミカゲが見分けられなかった(実測)
OVERLAY_SOFT = 0.7
OVERLAY_OPAQUE = 0.1
CLIP_LABEL = "FreePencil_ai_clip"


def _alpha_links(m):
    """絵の Alpha から出ているつなぎ。"""
    if not m.use_nodes or m.node_tree is None:
        return []
    return [lk for lk in m.node_tree.links
            if lk.from_node.bl_idname == "ShaderNodeTexImage" and lk.from_socket.name == "Alpha"
            and lk.from_node.image is not None and lk.from_node.image.size[0] > 0]


def uv_alpha_stats(objs, mats):
    """材質 -> (半端の割合, 透けない割合)。面ごとに 4 点、UV の所の絵のアルファを拾う。"""
    import numpy as np
    w4 = np.array([[1/3, 1/3, 1/3], [.6, .2, .2], [.2, .6, .2], [.2, .2, .6]], dtype=np.float32)
    pix, got = {}, {}
    for me in {o.data.name: o.data for o in objs if o.type == "MESH"}.values():
        if not me.uv_layers or not me.polygons:
            continue
        slots = [mt for mt in me.materials]
        want = [i for i, mt in enumerate(slots) if mt is not None and mt.name in mats]
        if not want:
            continue
        me.calc_loop_triangles()
        nt = len(me.loop_triangles)
        tl = np.empty(nt * 3, dtype=np.int32)
        me.loop_triangles.foreach_get("loops", tl)
        tm = np.empty(nt, dtype=np.int32)
        me.loop_triangles.foreach_get("material_index", tm)
        uv = np.empty(len(me.loops) * 2, dtype=np.float32)
        me.uv_layers.active.data.foreach_get("uv", uv)
        uv = uv.reshape(-1, 2)[tl.reshape(-1, 3)]
        for i in want:
            sel = tm == i
            if not sel.any():
                continue
            im = mats[slots[i].name]
            if im.name not in pix:
                w, h = im.size
                buf = np.empty(w * h * 4, dtype=np.float32)
                im.pixels.foreach_get(buf)
                pix[im.name] = buf[3::4].reshape(h, w)
            a = pix[im.name]
            h, w = a.shape
            p = np.einsum("kj,tjc->tkc", w4, uv[sel]).reshape(-1, 2) % 1.0
            v = a[np.minimum((p[:, 1] * h).astype(int), h - 1), np.minimum((p[:, 0] * w).astype(int), w - 1)]
            got.setdefault(slots[i].name, []).append(v)
    out = {}
    for name, vs in got.items():
        v = np.concatenate(vs)
        vis = max(int((v > 0.02).sum()), 1)
        out[name] = (float(((v > 0.05) & (v < 0.95)).sum()) / vis, float((v >= 0.95).mean()))
    return out


def clip_material_alpha(m, threshold: float = 0.5) -> bool:
    """絵の透けを ある/ない に切る(GREATER_THAN を挟む)。前に挟んだものは外してから挟み直す。"""
    nt = m.node_tree
    for n in [n for n in nt.nodes if n.label == CLIP_LABEL]:
        src = n.inputs[0].links[0].from_socket if n.inputs[0].is_linked else None
        dsts = [lk.to_socket for lk in n.outputs[0].links]
        nt.nodes.remove(n)
        for d in dsts:
            if src is not None:
                nt.links.new(src, d)
    hit = False
    # 透明の BSDF を絵で混ぜて抜いた葉は、混ぜる割合(Fac)を切る
    for lk in _alpha_links(m) + leaf_clump.cutout_fac_links(m):
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
    return hit


def set_overlay(m):
    """線を出さない重ねの描き方(BLEND)に戻す。BLEND は AOV を書かないので、下の面の線と色が残る。"""
    try:
        m.blend_method = "BLEND"
    except (TypeError, AttributeError):
        pass
    if hasattr(m, "surface_render_method"):
        m.surface_render_method = "BLENDED"


def _const_alpha(m) -> float:
    """つながっていない Principled の Alpha の一番小さい値。無ければ 1。"""
    if not m.use_nodes or m.node_tree is None:
        return 1.0
    vals = [n.inputs["Alpha"].default_value for n in m.node_tree.nodes
            if n.type == "BSDF_PRINCIPLED" and "Alpha" in n.inputs and not n.inputs["Alpha"].is_linked]
    return min(vals, default=1.0)


def _upstream_has_image(sock) -> bool:
    """上流に絵があるか。法線の口はたどらない(角膜の縁の向きは法線マップを通っていた)。"""
    stack, seen = [lk.from_node for lk in sock.links], set()
    while stack:
        x = stack.pop()
        if x.name in seen:
            continue
        seen.add(x.name)
        if x.type == "TEX_IMAGE":
            return True
        stack += [lk.from_node for s in x.inputs if s.name != "Normal" for lk in s.links]
    return False


def _transparent_mix(m) -> bool:
    """透明(Transparent BSDF)を絵でない値で混ぜる材質か(目の角膜: 縁の向きで混ぜる)。

    HASHED だと角膜が深度をまだらに書き、目の中がざらざらの黒になった(woman_01)。
    絵で混ぜるもの(葉の形に抜いた板)は形を描くのに要るので入れない。
    透明を Add Shader で足すガラスも入れる。Mix しか見ず HASHED のまま残り、窓とライトが
    一面ざらざらの点になった(mercedes-benze-s: 屈折のガラス + 透明 0.02 を足していた)。
    """
    if not m.use_nodes or m.node_tree is None:
        return False
    for n in m.node_tree.nodes:
        if n.type == "ADD_SHADER" and any(lk.from_node.type == "BSDF_TRANSPARENT"
                                          for s in n.inputs for lk in s.links):
            return True
        if n.type != "MIX_SHADER":
            continue
        if not any(lk.from_node.type == "BSDF_TRANSPARENT" for s in n.inputs[1:] for lk in s.links):
            continue
        if not _upstream_has_image(n.inputs[0]):
            return True
    return False


def sort_alpha_materials(objs):
    """HASHED で絵の透けを使う材質を、重ね物(BLEND に戻す)とそれ以外(透けを 0.5 で切る)に分ける。

    HASHED は半透明の所をまだらに描き、髪の影や頬の赤みがざらざらの黒い点になって、板の縁に
    線も出た(MMD で発見。mmd_tools は読み込んだ時点で全部 HASHED にする)。前髪の先や
    まつ毛の縁の半透明も同じ点になるので、そちらは透けを切る。透けが一定の値の材質(窓ガラス)は
    重ね物にする。屈折(Transmission)だけのガラスは触らない。
    """
    mats = {}
    overlays, clipped = [], []
    for o in objs:
        for s in o.material_slots:
            m = s.material
            if m is None or m.name in mats or m.name in overlays \
                    or getattr(m, "blend_method", "") != "HASHED":
                continue
            lks = _alpha_links(m)
            if not lks and (_const_alpha(m) < 0.95 or _transparent_mix(m)):
                # 透けが一定の値の材質(窓ガラスなど)。HASHED だと窓が一面ざらざらの黒になった
                # (japan-apartment: ガラスのアルファ 0.7)。BLEND にすると奥のカーテンの線が出る
                set_overlay(m)
                overlays.append(m.name)
                continue
            if not lks and leaf_clump.cutout_by_image(m):
                # 透明の BSDF を絵で混ぜて抜いた葉(european-maple)。ガラスと見なさず、縁を 0.5 で切る
                if clip_material_alpha(m):
                    clipped.append(m.name)
                continue
            if _is_real_glass(m):
                continue
            if lks:
                mats[m.name] = lks[0].from_node.image
    stats = uv_alpha_stats(objs, mats)
    from . import cel_shade
    for name, (soft, opaque) in sorted(stats.items()):
        m = bpy.data.materials[name]
        if cel_shade.is_highlight_material(m):
            # 目の光は重ね物にしない(BLEND は色のパスを書かず、セルで消えた)。keep_highlights で描く
            continue
        if soft >= OVERLAY_SOFT and opaque < OVERLAY_OPAQUE:
            set_overlay(m)
            overlays.append(name)
        elif clip_material_alpha(m):
            # ほぼ透けない(アルファ 0.95〜0.999)材質も切る。「透けない」と数えて切らずにいたら、
            # HASHED がその数 % の画素を抜き、奥が見えた所が奥行きの線の点になった(サーバルの白目、0.97 前後)
            clipped.append(name)
    return overlays, clipped


def keep_highlights(scene, view_layer, objs) -> list:
    """目の光(ハイライト・瞳の星)を、セルでも消えないように描く。マスクで塗った物の名前を返す。

    重ね物(BLEND)は色のパスを書かないので、セルで目の光が消えた(ミク・アカリ・サーバル)。
    ふつうの描き方(HASHED)にして絵の透けを ある/ない に切り(半端な所がまだらの点や、絵の外の文字に
    なった)、まわりの線をマスクで消す。影は付けない(cel_shade.is_face_material)。
    STEP0 のほか、前に重ね物にした場面(v2.9 の soft_overlays)にもかけ直せる。
    """
    from . import cel_shade, fp_core
    mats = {}
    for o in objs:
        for s in getattr(o, "material_slots", ()):
            m = s.material
            if m is None or m.name in mats or not cel_shade.is_highlight_material(m):
                continue
            lks = _alpha_links(m)
            if not lks:
                continue
            if getattr(m, "blend_method", "") == "BLEND":
                m.blend_method = "HASHED"
                if hasattr(m, "surface_render_method"):
                    m.surface_render_method = "DITHERED"
            if getattr(m, "blend_method", "") == "HASHED":
                mats[m.name] = lks[0].from_node.image
    for name in uv_alpha_stats(objs, mats):
        clip_material_alpha(bpy.data.materials[name])     # ほぼ透けない絵も切る(sort_alpha_materials と同じ)
    done = highlight_mask(objs)
    if done:
        # マスクの色を線に届ける(STEP2 の自動判定より後に塗るので、ここで入れて組み直す)
        scene.fp_mask_color = True
        fp_core.setup_aov(scene, view_layer)
        from . import compat
        tree = compat.get_compositor_tree(scene)
        if tree is not None and any(n.type == "GROUP" and n.node_tree is not None
                                    and n.node_tree.name.startswith(fp_core.NODE_GROUP_PREFIX)
                                    for n in tree.nodes):
            fp_core.setup_compositor(scene, view_layer)
    return done


def highlight_mask(objs) -> list:
    """目の光(透けを切って描く)の面をマスクの白で塗り、まわりの線を消す。塗った物の名前。

    透けを切った目の光は色を書くので、瞳との境に黒い輪が出た(ミク・アカリ)。"""
    import numpy as np
    from . import cel_shade
    done = []
    for o in objs:
        if o.type != "MESH" or not o.data.polygons:
            continue
        slots = [i for i, s in enumerate(o.material_slots)
                 if s.material and getattr(s.material, "blend_method", "") == "HASHED"
                 and cel_shade.is_highlight_material(s.material)]
        if not slots:
            continue
        me = o.data
        mi = np.empty(len(me.polygons), dtype=np.int32)
        me.polygons.foreach_get("material_index", mi)
        faces = np.isin(mi, slots)
        if not faces.any():
            continue
        utils.ensure_vertex_color(o, "mask_color", (0.0, 0.0, 0.0, 1.0))
        attr = me.color_attributes["mask_color"]
        if attr.domain != "CORNER":
            continue
        buf = np.empty(len(attr.data) * 4, dtype=np.float32)
        attr.data.foreach_get("color", buf)
        buf = buf.reshape(-1, 4)
        loop_poly = np.repeat(np.arange(len(me.polygons)), [p.loop_total for p in me.polygons])
        buf[faces[loop_poly]] = (1.0, 1.0, 1.0, 1.0)
        attr.data.foreach_set("color", buf.ravel())
        me.update()
        done.append(o.name)
    return done


# 白目と顔(肌)。白目と顔の境に目のふちの黒い線が出た(サーバル・ミク・アカリ)。アニメの目は
# ふちを描かず、瞳の丸だけが線になる。そこで白目を顔と同じ塗りにする(瞳・まつげは別のまま)
EYE_WHITE_RE = re.compile(r"白目|しろめ|(?<![a-z])sclera|white.?eyes?|eyes?.?white", re.IGNORECASE)
SKIN_FACE_RE = re.compile(r"(?<![a-z])face|顔|かお|フェイス", re.IGNORECASE)


def merge_eye_whites(objs) -> list:
    """白目の面の塗り分け(メカの塗り・ボーンの塗り)を、同じ物の顔の色にそろえる。そろえた物の名前。

    顔の材質が同じ物に無ければ何もしない(白目だけ別の物のモデルは、物の境で線が出る)。"""
    import numpy as np
    from . import cel_shade
    done = []
    for o in objs:
        if o.type != "MESH" or not o.data.polygons:
            continue
        whites, skins = [], []
        for i, s in enumerate(o.material_slots):
            m = s.material
            if m is None:
                continue
            if EYE_WHITE_RE.search(m.name):
                whites.append(i)
            elif SKIN_FACE_RE.search(m.name) and not cel_shade.is_highlight_material(m):
                skins.append(i)
        if not whites or not skins:
            continue
        me = o.data
        mi = np.empty(len(me.polygons), dtype=np.int32)
        me.polygons.foreach_get("material_index", mi)
        lt = np.empty(len(me.polygons), dtype=np.int64)
        me.polygons.foreach_get("loop_total", lt)
        loop_poly = np.repeat(np.arange(len(me.polygons)), lt)
        w_loops = np.isin(mi, whites)[loop_poly]
        s_loops = np.isin(mi, skins)[loop_poly]
        if not w_loops.any() or not s_loops.any():
            continue
        changed = False
        for layer in ("mecha_color", "bone_color"):
            a = me.color_attributes.get(layer)
            if a is None or a.domain != "CORNER":
                continue
            buf = np.empty(len(a.data) * 4, dtype=np.float32)
            a.data.foreach_get("color", buf)
            buf = buf.reshape(-1, 4)
            # 顔で一番多い色(肌の島の色)
            vals, cnt = np.unique(np.round(buf[s_loops, :3], 3), axis=0, return_counts=True)
            buf[w_loops, :3] = vals[cnt.argmax()]
            a.data.foreach_set("color", buf.ravel())
            changed = True
        if changed:
            me.update()
            done.append(o.name)
    return done


def outline_shells(objs):
    """トゥーン用の殻(裏返しの Solidify と、VRM の MToon の輪郭)。[(物, モディファイア)]

    MToon の輪郭はジオメトリノードで作る裏返しの殻。キャラの日をさえぎって体じゅうが影の色に
    なった(デルタもん)。"""
    from . import vrm
    return [(o, m) for o in objs for m in o.modifiers
            if m.show_render and ((m.type == "SOLIDIFY" and (m.use_flip_normals or m.material_offset))
                                  or vrm.is_outline_modifier(m))]


LOD_KEY = "fp_lod_hidden"      # STEP0 が隠した LOD。値は元の hide_viewport
_LOD_RE = re.compile(r"^(.*?)[_.\- ]?LOD(\d+)$", re.I)


def _lod_name(name: str):
    """'ball_LOD2' / 'ball_LOD2.001' -> ('ball', 2)。LOD の名前でなければ None。"""
    mt = _LOD_RE.match(re.sub(r"\.\d{3}$", "", name))
    return (mt.group(1).lower(), int(mt.group(2))) if mt else None


def hide_extra_lods(objs) -> list:
    """同じ場所に重ねてある粗い LOD を隠し、いちばん細かい LOD だけを描く。

    LOD0〜3 が全部見えていたボールで、重なった面が場所ごとに交互に顔を出し、物ごとに
    違う色で塗られるので、ボール一面にぎざぎざの線が出た(dirty_football)。
    名前の頭が同じで、中心がいちばん細かい LOD の箱の中にある物だけを隠す(並べて
    見せている LOD は残す)。隠した物には元の値を控え、「FreePencil を外す」で戻す。
    """
    from mathutils import Vector
    groups = {}
    for o in objs:
        got = _lod_name(o.name)
        if got is not None:
            groups.setdefault(got[0], []).append((got[1], o))

    def box(o):
        pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
        return (Vector([min(p[i] for p in pts) for i in range(3)]),
                Vector([max(p[i] for p in pts) for i in range(3)]))
    hidden = []
    for members in groups.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda t: t[0])
        lo, hi = box(members[0][1])
        pad = (hi - lo) * 0.05
        for _, o in members[1:]:
            a, b = box(o)
            c = (a + b) / 2
            if all(lo[i] - pad[i] <= c[i] <= hi[i] + pad[i] for i in range(3)):
                o[LOD_KEY] = int(o.hide_viewport)
                try:
                    o.select_set(False)
                except RuntimeError:
                    pass  # ビューレイヤー外
                o.hide_render = o.hide_viewport = True
                hidden.append(o)
    return hidden


def shells_off(objs) -> list:
    """トゥーン用の殻を切る。FreePencil の線と殻の縁の両方が出て、髪などの線が全部二重に
    なった(anime-girl)。切った名前は物に控え、「FreePencil を外す」と ai.shells(False) で戻す。"""
    found = outline_shells(objs)
    for o, m in found:
        m.show_render = m.show_viewport = False
        names = set(filter(None, str(o.get("fp_ai_shells_off", "")).split("|"))) | {m.name}
        o["fp_ai_shells_off"] = "|".join(sorted(names))
    return [f"{o.name}.{m.name}" for o, m in found]


def weld_seams(objs, distance: float = 0.0005, max_angle: float = 180.0, bone: bool = True) -> int:
    """切れ目(縁の頂点が同じ位置で重なっている所)をまたいで、塗り分けをつなぐ。

    MMD のメッシュは UV の切れ目で頂点が分かれていて(ミクで 7,900 点)、STEP1 は
    つながった部品ごとに色を変えるので、太もも・手首に線が出た。骨の色(bone_color)も
    辺に沿ってぼかすため、切れ目を越えられずに段差が残り、そこも線になった。
    - max_angle を 180 未満にすると、両側の法線の差がそれ未満の切れ目だけにする。既定は見ない:
      MMD は面の表裏がそろっておらず、ミクの太ももの切れ目では両側の面の向きが 50 度以上
      ずれていた(実測)。リグ付きのキャラにだけ使うので、角で切ったメカの線は消えない
    - mecha_color: 切れ目で触れ合う色の島どうしだけを同じ色にする(体の中の塗り分けは残す)
    - bone_color: 切れ目のまわりだけ、切れ目をまたいでぼかし、段差を坂にする
      (ai.weld のように骨の色を部品ごと 1 色にすると、腕と体の線まで消えた)
    """
    import math
    import numpy as np
    from .ai import _components
    cos_t = math.cos(math.radians(max_angle))
    joined = 0
    for me in {o.data.name: o.data for o in objs if o.type == "MESH"}.values():
        ca = me.color_attributes
        if "mecha_color" not in ca or not me.polygons:
            continue
        nv = len(me.vertices)
        co = np.empty(nv * 3, dtype=np.float32)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        vn = np.empty(nv * 3, dtype=np.float32)
        me.vertices.foreach_get("normal", vn)
        vn = vn.reshape(-1, 3)
        ed = np.empty(len(me.edges) * 2, dtype=np.int32)
        me.edges.foreach_get("vertices", ed)
        ed = ed.reshape(-1, 2)
        part = _components(nv, ed)
        npoly = len(me.polygons)
        mi = np.empty(npoly, dtype=np.int32)
        me.polygons.foreach_get("material_index", mi)
        lt = np.empty(npoly, dtype=np.int32)
        me.polygons.foreach_get("loop_total", lt)
        lv = np.empty(len(me.loops), dtype=np.int32)
        me.loops.foreach_get("vertex_index", lv)
        vmat = np.full(nv, -1, dtype=np.int32)
        vmat[lv] = np.repeat(mi, lt)
        le = np.empty(len(me.loops), dtype=np.int32)
        me.loops.foreach_get("edge_index", le)
        border = np.zeros(nv, dtype=bool)
        border[ed[np.bincount(le, minlength=len(me.edges)) == 1].ravel()] = True
        idx = np.nonzero(border)[0]
        if not len(idx):
            continue
        # 同じ升目・同じ材質の、縁の頂点の組。升目の境をまたぐ組も拾うよう半升ずらしても見る
        pairs = []
        for off in (0.0, 0.5):
            key = np.c_[np.floor(co[idx] / distance + off).astype(np.int64), vmat[idx]]
            _u, inv = np.unique(key, axis=0, return_inverse=True)
            inv = inv.ravel()
            order = np.argsort(inv, kind="stable")
            same = inv[order][1:] == inv[order][:-1]
            va, vb = idx[order[:-1][same]], idx[order[1:][same]]
            # 同じ部品の中の切れ目(裂け目)も拾う。別の部品どうしに限ると、ミクの左の太ももが残った
            ok = va != vb
            if max_angle < 180.0:
                ok &= np.abs((vn[va] * vn[vb]).sum(1)) > cos_t
            pairs.append(np.c_[va[ok], vb[ok]])
        pairs = np.unique(np.concatenate(pairs), axis=0) if pairs else np.zeros((0, 2), dtype=np.int64)
        if not len(pairs):
            continue
        # mecha_color: 角ごとの (部品, 色) を色の島とみなし、切れ目の組の両側の島をつなぐ
        a = ca["mecha_color"]
        if a.domain == "CORNER":
            buf = np.empty(len(a.data) * 4, dtype=np.float32)
            a.data.foreach_get("color", buf)
            buf = buf.reshape(-1, 4)
            _k, isl = np.unique(np.c_[part[lv], np.round(buf[:, :3] * 255).astype(np.int64)],
                                axis=0, return_inverse=True)
            isl = isl.ravel()
            n_isl = int(isl.max()) + 1
            # 頂点 -> その頂点の角の島(先頭の 1 つ)。縁の頂点はふつう 1 つの島にしか属さない
            v_isl = np.full(nv, -1, dtype=np.int64)
            v_isl[lv[::-1]] = isl[::-1]
            ie = np.c_[v_isl[pairs[:, 0]], v_isl[pairs[:, 1]]]
            ie = ie[(ie >= 0).all(1) & (ie[:, 0] != ie[:, 1])]
            grp = _components(n_isl, ie)
            size = np.bincount(isl, minlength=n_isl)
            # まとまりごとに、角のいちばん多い島の色にそろえる
            best = {}
            for i in np.unique(ie.ravel()):
                g = int(grp[i])
                if g not in best or size[i] > size[best[g]]:
                    best[g] = int(i)
            col_of = np.zeros((n_isl, 3), dtype=np.float32)
            first = np.full(n_isl, -1, dtype=np.int64)
            first[isl[::-1]] = np.arange(len(isl))[::-1]
            col_of[:] = buf[first, :3]
            hit = np.zeros(n_isl, dtype=bool)
            for i in np.unique(ie.ravel()):
                hit[i] = True
            sel = hit[isl]
            buf[sel, :3] = col_of[[best[int(g)] for g in grp[isl[sel]]]]
            a.data.foreach_set("color", buf.ravel())
            joined += len(best)
        # bone_color: 切れ目から 16 輪までを、切れ目もつないだ辺で 64 回ぼかす。3 輪 12 回・8 輪 24 回
        # では、ミクの左の太もも(両側で骨の色が大きく違う)の坂が急なままで線が出た
        b = ca.get("bone_color") if bone else None
        if b is not None and b.domain == "CORNER":
            bb = np.empty(len(b.data) * 4, dtype=np.float32)
            b.data.foreach_get("color", bb)
            bb = bb.reshape(-1, 4)
            vc = np.zeros((nv, 3), dtype=np.float64)
            vc[lv] = bb[:, :3]
            ee = np.concatenate([ed, pairs]).astype(np.int64)
            near = np.zeros(nv, dtype=bool)
            near[pairs.ravel()] = True
            for _ in range(16):
                near[ee[near[ee[:, 0]], 1]] = True
                near[ee[near[ee[:, 1]], 0]] = True
            deg = np.bincount(ee.ravel(), minlength=nv).astype(np.float64) + 1.0
            for _ in range(64):
                acc = vc.copy()
                np.add.at(acc, ee[:, 0], vc[ee[:, 1]])
                np.add.at(acc, ee[:, 1], vc[ee[:, 0]])
                vc[near] = (acc / deg[:, None])[near]
            bb[:, :3] = vc[lv]
            b.data.foreach_set("color", bb.ravel())
        me.update()
    return joined


class FP_OT_AUTO_SETUP(vertex_color.FPProgressModalMixin, bpy.types.Operator):
    """Analyze the scene, apply recommended settings and run STEP1-3."""
    bl_idname = "freepencil.auto_setup"
    bl_label = "Auto Setup"
    bl_description = (
        "Analyze the scene, apply recommended settings and run "
        "STEP1 (vertex colors), STEP2 (AOV) and STEP3 (PRO node) at once"
    )
    bl_options = {'REGISTER', 'UNDO'}

    # STEP0 の所要時間はほぼ STEP1(塗り分け)なので、そこだけ進捗を出す
    _progress_label = "FreePencil STEP1/3"

    def _prepare(self, context):
        """STEP1 の前段(対象メッシュの決定・おすすめ設定・AOV判定)。

        続行できない場合は None を返す。戻り値は _finish() に渡す。
        """
        # 「FreePencil を外す」ための元の値を、何かを変える前に控える
        from . import undo_setup
        undo_setup.snapshot(context)
        scene = context.scene
        view_layer = context.view_layer

        # --- 対象メッシュ: 選択があれば選択、無ければ表示中の全メッシュ ---
        targets = [o for o in context.selected_objects if o.type == "MESH"]
        if not targets:
            for o in context.selected_objects:
                o.select_set(False)
            for o in scene.objects:
                if o.type != "MESH" or o.hide_render:
                    continue
                try:
                    o.select_set(True)
                except RuntimeError:
                    continue  # ビューレイヤー外
                targets.append(o)
        if not targets:
            self.report({'ERROR'}, "No mesh objects")
            return None
        # 手描き背景: 地面(視界より大きい平面)は塗らない。塗ると地平線が
        # 太い輪郭になり、黒い帯が出る(実測: 町のデモは手で外していた)
        if getattr(scene, "fp_auto_style", 'PRECISE') == 'BACKGROUND':
            ground = [o for o in targets if _looks_like_ground(o, targets)]
            if ground and len(ground) < len(targets):
                for o in ground:
                    o.select_set(False)
                    print(f"[freepencil.auto_setup] 地面とみなして塗らない: {o.name}")
                targets = [o for o in targets if o not in ground]
        # 同じ場所に重ねた粗い LOD は隠す(重なりが交互に出て一面に線が出た)
        lods = hide_extra_lods(targets)
        if lods:
            targets = [o for o in targets if o not in lods]
            print(f"[freepencil.auto_setup] 重ねた LOD を隠した: {[o.name for o in lods]}")
        view_layer.objects.active = targets[0]
        # VRM の材質(MToon)をセルで描ける形に(vrm.py)。セルの色の元を読むより前に
        vrm_mats = vrm.prepare(targets)
        if vrm_mats:
            print(f"[freepencil.auto_setup] VRM の材質を直した: {len(vrm_mats)} 個")
        # トゥーン用の殻は線の測り直し(強弱のしきい値)より前に切る
        shells = shells_off(targets) if getattr(scene, "fp_auto_shells", True) else []
        if shells:
            print(f"[freepencil.auto_setup] トゥーン用の殻を切った: {shells}")

        # --- 仕上がり。精密 = v2.7 の出力そのまま、キャラ = AO の強弱、
        # 背景 = キャラ + 特殊処理(奥の扱い・葉の房) ---
        style = getattr(scene, "fp_auto_style", 'PRECISE')
        # キャラを選んでも、写る骨付きの物がメカ(ザク)なら精密にする。キャラの強弱では
        # 細かい部品が黒く詰まった(dev/batch/out/report_lw_strength)
        mecha = False
        if style == 'WEIGHTED' and getattr(scene, "fp_auto_mecha", True):
            from . import figures
            mecha = figures.rigged_mecha(targets)
            if mecha:
                scene.fp_auto_style = style = 'PRECISE'
                print("[freepencil.auto_setup] 骨付きのメカ: 仕上がりを精密に")
        weighted = style in ('WEIGHTED', 'BACKGROUND')
        background = style == 'BACKGROUND'
        # 人工分割の下限。14 の根拠は utils.ARTIFICIAL_SPLIT_FLOOR
        scene.fp_auto_split_floor = 14.0 if weighted else 5.0
        scene.fp_line_weight = weighted
        # 奥の扱い(値の根拠は dev/note_assets/eval_far_ideas.py の 24案比較)
        scene.fp_lw_far = 1.0 if background else 0.0
        # 奥の線減らしは 2.0(3.0 だと町の奥のビルの窓が消えすぎた。
        # dev/note_assets/eval_density_options.py の案 ABC)
        scene.fp_lw_far_sens = 2.0 if background else 1.0
        # 奥を薄くするのは 0.15(2026-10 に変更)。0.35 では詰まった線を薄くする段と重なって
        # 「色を薄くしただけ」に見えた(並木道で 精密と比べて確認)
        scene.fp_lw_far_fade = 0.15 if background else 0.0
        # 詰まった線を薄く(つぶれ軽減)。密度の高い町で、手すり・網戸・外階段が
        # 黒い塊になった。0.6 で塊が灰色の調子になり、輪郭は黒のまま(1.0 は薄すぎ)。
        # 2026-10 に 0.3: 0.6 は並木を灰色の面にし、白プレビューで「色を薄くしただけ」
        # に見えた。0.3 で葉の陰に黒が残り、町の手すりも黒い塊にはならない(画像で確認)
        scene.fp_lw_dense = 0.3 if background else 0.0
        # 細かすぎる縞を奥ほど薄く。低い視点から水平の線の多い面を見ると、奥が
        # つぶれて動かすとちらついた(試験場 test_grazing で総当り)
        # v2.8.3 で既定を切った(0)。カメラが動くと、遠くの窓の格子が画素とのずれで
        # コマごとに見え方を変え、薄める範囲と灰色の濃さが揺れて灰色のまだらが
        # ちらついた。縁石のような近い 2 本の線も細い二重線になった(大通りの飛行で
        # 確認、dev/note_assets/flicker_compare.py)。低い視点の横縞のモアレには効くので、
        # STEP3 の詳細のつまみで入れられる
        scene.fp_lw_stripe_fade = 0.0
        # パネルのつまみ(上の5つをまとめた2本)。1.0 が上の値と同じ。更新フック
        # を動かすと STEP0 の途中で STEP3 を作り直すので、フックを止めて書く
        from .props import _write_quiet
        _write_quiet(scene, {"fp_lw_far_amount": 1.0 if background else 0.0,
                             "fp_lw_relief": 1.0 if background else 0.0})
        # 葉を房に(カエデは 4〜8、ヤシは 1 が良い。既定は 4)
        scene.fp_foliage_clumps = 4 if background else 0
        # 遠い区画をまとめる 500px(v2.8.3)。150 ではほとんど効かず、500 で奥の高層が
        # 輪郭と帯になった(dev/note_assets/far_lod_proto.py)。手前は変わらない
        scene.fp_far_lod_px = 500.0 if background else 0.0
        # 細い線(精密の分割)を重ねる。線を太くせず本数で戻す(0.35 ではアパートの
        # 窓枠が精密より明らかに少なかった)。2026-10 に 0.6 -> 1.0: 0.6 は細い線が
        # 灰色になり、精密と並べると「色を薄くしただけ」に見えた。1.0 で並木の陰と
        # 枝が黒く入り、町の手すりも塊にならない(並木道と町で確認)
        scene.fp_fine_lines = 1.0 if background else 0.0
        # 細い線を使うときは、STEP1 を 2 回塗る。1 回目はここで精密の値に
        # しておき(この後のモーダルが塗る)、_finish で fine_color へ写して
        # から手描きの値で塗り直す
        if background and scene.fp_fine_lines > 0.0:
            scene.fp_auto_split_floor = 5.0
            # 1 回目はメカの塗り。切れすぎの抑え(島/面の上限)を外して
            # 線を全部出す。_finish で外す
            scene["fp_fine_pass"] = True
        elif "fp_fine_pass" in scene:
            del scene["fp_fine_pass"]
        # キャラ(リグ付き)は手描き系ではざっくり塗り + ボーンの塗り。
        # 精密は v2.7 のまま(リグ付きでも角度で分ける)
        if weighted:
            scene["fp_rig_coarse"] = True
        elif "fp_rig_coarse" in scene:
            del scene["fp_rig_coarse"]
        # 葉の隙間埋め 6px(200% 基準 = 1080p で 3px)。線の濃さは 1.0(黒)。
        # v2.8.2 までは 0.75(濃い灰色)で、精密と並べると薄く見えた
        # 背景は線を細く(強さ 0.5 = 最大 6px、1080p で 3px)。太いのは
        # 近くに寄ったときだけでよい
        scene.fp_gap_fill = 6 if background else 0
        scene.fp_lw_ink = 1.0
        # キャラは 0.35(ほんのり強弱)。1.0 は輪郭が太すぎ、細かいメカを小さく
        # 写すと黒く詰まった(リグ付きロボット)。2026-10 に 0.6 -> 0.35: 0.6 は
        # デモ向けの強調で、標準には影の側の輪郭が太かった。0.45 / 0.35 を並べて
        # 0.35 に決めた(dev/batch/out/report_lw_strength)。さらに 0.25 へ: 0.35 も線が太めと
        # 言われた(ユーザー)。0.35 / 0.25 / 0.2 を顔のアップと 4 体の並びで見て、0.2 は並びで
        # 輪郭がかすれたので 0.25(dev/batch/out/v30_demo/lw_check)。
        # 太くしたいときはスライダーで上げればその場で効く
        scene.fp_lw_strength = 0.5 if background else (0.25 if weighted else 1.0)
        # 深度チャンネルは地面と空の境(深度の段差)を太い帯にする(実測)。
        # 背景では切る。奥の距離の計測もその帯を線に数えて狂っていた
        # (奥の終わり 238 -> 切ると 71)
        if background:
            scene.fp_ch_depth = 0.0

        # --- おすすめ設定(STEP0 のチェックが入っている項目のみ適用) ---
        if scene.fp_auto_sharp:
            scene.fp_sharp_auto = True
        if scene.fp_auto_seam:
            scene.fp_seam_boundaries = True
        if scene.fp_auto_merge:
            # 0.02% は「小島の掃除」の値で、塗りの粒度には効かなかった。
            # 実測(スザンヌ適用済み 7,872面): 0% -> 429色 / 0.5% -> 9色 /
            # 1% -> 6色 / 2% -> 4色。1% で頭が1色にまとまり、目と口だけが
            # 残る。メカも 1% ならパネルの区別を保ったまま粒が落ちる
            scene.fp_min_island_area_pct = 1.0
            # 広くまとめると島の中の線が消えるので、稜線の起伏で補う。
            # 平らな面では残差がほぼゼロなのでメカには足されない。
            #
            # 0.45 にする根拠(BlenderKit・2026-09): 0.25/0.35/0.45/0.50 を
            # 10体で振ったところ、どの値でもどのモデルも内側の線が減らず
            # (最小 99.9%)、中央は 100/111/123/132% と増える一方だった。
            # 0.50 は上限で調整の余地が無く、ハンガーの屋根が詰まりはじめる。
            # メカと壺は全域で1画素も変わらない(平らな面では残差ゼロ)。
            # スザンヌの口の輪郭は 0.45 でないと戻らない(下限14度と役割が別)。
            # 精密(v2.7)は 0.25 のまま
            scene.fp_ridge_amount = 0.45 if weighted else 0.25
            # 細い線の 1 回目は本当の精密(稜線 0.25)で塗る。_finish で
            # fine_color へ写したあと 0.45 に戻して塗り直す
            if background and scene.fp_fine_lines > 0.0:
                scene.fp_ridge_amount = 0.25
            scene.fp_ridge_radius = 0.08
        if scene.fp_auto_part_tint:
            scene.fp_part_tint = True
        scene.fp_bone_grouping_mode = 'basename'
        has_rig = any(
            m.type == 'ARMATURE' and m.show_viewport and m.object
            for o in targets for m in o.modifiers)
        if scene.fp_auto_bone:
            scene.fp_bone_color = has_rig
        # 線の強さも自動化に含める。ここを触らないと、古いファイルに
        # 残った 1.0 がそのまま使われて線が弱いままになる
        scene.fp_line_sensitivity = 0.5
        scene.fp_node_type = 'pro'
        if scene.fp_auto_aa:
            scene.fp_include_antialiasing = True
        if scene.fp_auto_supersample:
            # 細線化はFreePencilの品質の要(縮小しないと線が太い)
            scene.fp_supersample = True
        if scene.fp_auto_file_output:
            scene.fp_file_output = True

        # AOVの完全自動設定: STEP2 の手動チェックには依存せず、
        # シーンから判定して ON/OFF 両方を決める(自動がAOV構成を所有)。
        #   gen/mask/line = その頂点カラーが塗られているか
        #   mat          = マテリアルID加算が有効か
        #   (mecha=常時、bone=リグ検出は上で設定済み)
        detected = []
        if scene.fp_auto_detect_aov:
            from .fp_core import texture_plugged
            for ch in ("gen_color", "mask_color", "line_color"):
                on = _channel_painted(targets, ch)
                if ch == "mask_color" and not on:
                    # マスクを絵(AOV グループの mask_texture)でつないでいる(v2.9)
                    on = texture_plugged("mask_texture")
                setattr(scene, f"fp_{ch}", on)
                if on:
                    detected.append(ch)
            scene.fp_mat_color = bool(scene.fp_mat_count)
            if scene.fp_mat_color:
                detected.append("mat_color")

        # STEP2 が film_transparent を True にするが、マテリアル/背景を
        # 残すシーンでは見た目が変わるため元の値を維持する
        film_transparent = scene.render.film_transparent

        return {"targets": targets, "has_rig": has_rig,
                "detected": detected, "film_transparent": film_transparent, "mecha": mecha}

    def _finish(self, context, info):
        """STEP1 完了後: STEP2(AOV)/STEP3(PROノード)と後始末。"""
        scene = context.scene

        # 細い線: 1 回目(精密の分割)の結果を fine_color へ写し、手描きの
        # 値で塗り直す。線の検出はどちらも同じ仕組みなので、塗り分けだけ
        # 2 枚持てば、合成の割合をスライダーで変えられる
        if getattr(scene, "fp_fine_lines", 0.0) > 0.0 and scene.fp_line_weight:
            from . import utils as _utils
            n = 0
            for obj in info["targets"]:
                if _utils.copy_vertex_color(obj, "mecha_color", "fine_color"):
                    n += 1
            scene.fp_auto_split_floor = 14.0
            if scene.fp_auto_merge:
                scene.fp_ridge_amount = 0.45
            if "fp_fine_pass" in scene:
                del scene["fp_fine_pass"]       # 2 回目(手描き)は抑える
            bpy.ops.freepencil.auto_vertex_color("EXEC_DEFAULT")
            print(f"[freepencil.auto_setup] 細い線: fine_color を {n} 個に写して塗り直した")

        bpy.ops.freepencil4.link_button()
        # STEP0 の中は背景を透過にして進める(線の強弱の計測が透過の前提で合わせてある)。
        # 終わりに元の値へ戻す。v2.9 で STEP2 が透過にしなくなったので、ここで明示する
        scene.render.film_transparent = True
        # セルの下ごしらえ(影の AOV と光のパス)を STEP3 より前に済ませる。セルに切り替えた
        # ときに材質とビューレイヤーの AOV が変わり、全部のシェーダーを組み直していた
        # (ランボルギーニで初回のセルが 56.8 秒、2 回目からは 4.4 秒。白は 3.8 秒)
        from . import cel_shade
        cel_shade.ensure_shade_aov(scene, context.view_layer)
        cel_shade.ensure_light_passes(context.view_layer)
        bpy.ops.freepencil2.link_button()

        # 強弱: しきい値はカットごとに違う(実モデル11体で15倍ひらく)ので、
        # STEP3 が建った後に1回測って固定し、STEP3 を組み直す。
        # ここで測らないと、使う人が「しきい値を測る」を押すまで既定値の
        # まま動く
        measured = None
        if scene.fp_line_weight:
            from . import line_weight
            edges = line_weight.measure_edges(scene, context.view_layer)
            if edges is not None:
                for i, v in enumerate(edges, start=1):
                    setattr(scene, f"fp_lw_e{i}", v)
                bpy.ops.freepencil2.link_button()
                measured = edges
        info["measured"] = measured

        # 角度が一様で分割線を作らなかった物(卵)があれば、境目を奥行きの線で出す(強さ 2)。
        # 卵を盛った鉢は、しまは消えたが卵どうしの境目まで消えて 1 つの塊になった(同じメッシュの
        # 複製は同じ色になる)。奥行き 2 で卵が 1 個ずつ描けた(背景は既定で奥行きを切っている)。
        # 強弱の計測(奥の距離)は奥行きの線を数えて狂うので、計測の後で入れる
        if scene.get("fp_uniform_smooth") and scene.fp_ch_depth < 2.0:
            from .props import _write_quiet
            _write_quiet(scene, {"fp_ch_depth": 2.0})
            bpy.ops.freepencil2.link_button()
            print(f"[freepencil.auto_setup] 一様に滑らかな物 {scene['fp_uniform_smooth']} 個: "
                  "奥行きの線を 2 に")

        # 骨の無い人物(AI が作った人)。腕と胴が 1 つの形で同じ色になり、横から見ると腕が胴に
        # 溶けて消えた。顔や服は絵にしか無く、輪郭だけになった。絵の線を当てる(強さ 0.5・ぼかし 4。
        # 1.0 は濃い肌で鼻のまわりが黒く潰れた)。写るのが人物だけなら奥行きの線を 2 にして、
        # 胴の手前の腕の縁を拾う。地面や建物があるときは上げない(奥行きは地面と空の境を太い帯に
        # する)。boy で前後を画像で比べて決めた(dev/note_assets/build_boy_report.py)
        figs = []
        if getattr(scene, "fp_auto_figures", True):
            from . import figures
            figs = figures.rigless_figures(info["targets"])
        if figs:
            from . import ai
            ai.texture_lines({"objects": [o.name for o in figs]}, strength=0.5, blur=4, undo=False)
            shown = [o for o in scene.objects if o.type == 'MESH' and not o.hide_render
                     and o.visible_get() and len(o.data.polygons)]
            if len(figs) == len(shown) and scene.fp_ch_depth < 2.0:
                from .props import _write_quiet
                _write_quiet(scene, {"fp_ch_depth": 2.0})
                bpy.ops.freepencil2.link_button()
            print(f"[freepencil.auto_setup] 骨の無い人物 {[o.name for o in figs]}: 絵の線"
                  + (" + 奥行きの線 2" if scene.fp_ch_depth >= 2.0 else ""))
        info["figures"] = len(figs)

        scene.render.film_transparent = info["film_transparent"]

        # 白マテリアルでプレビュー。線画がすぐ見える状態にして終わる。
        # コンポジタ切替方式なのでマテリアル自体は触らない。必ず STEP3 で
        # コンポジタが建った後に立てること(先に立てても差し込む先が無い)
        # 種類で見る(旧トグルは v2.7 のファイルで立ったまま残っていることがあり、
        # それを見て「もう白だ」と飛ばしていた)
        if scene.fp_auto_white_preview and scene.fp_preview_mode not in ("WHITE", "CEL"):
            scene.fp_preview_mode = "WHITE"

        # BLEND は AOV が書かれない → 本物のガラス以外は HASHED へ
        hashed = 0
        if scene.fp_auto_hashed:
            for m in bpy.data.materials:
                if getattr(m, "blend_method", "OPAQUE") != "BLEND":
                    continue
                if _is_real_glass(m) and not leaf_clump.cutout_by_image(m):
                    continue
                m.blend_method = "HASHED"
                hashed += 1
        overlays, clipped = [], []
        highlights = []
        if getattr(scene, "fp_auto_overlays", True):
            overlays, clipped = sort_alpha_materials(info["targets"])
            highlights = keep_highlights(scene, context.view_layer, info["targets"])
        eye_whites = []
        vrm_fix = {}
        if scene.fp_auto_style == 'WEIGHTED':
            eye_whites = merge_eye_whites(info["targets"])
        # 葉の材質があれば、葉をかたまりの縁で描く(木が真っ黒な影絵になった。leaf_clump)
        leaves = leaf_clump.leaf_materials(info["targets"])
        scene.fp_leaf_clump = bool(leaves)
        # 切れ目の線はリグ付きのキャラだけ消す。精密(メカ)は UV の切れ目をわざと線にしている
        welded = 0
        if getattr(scene, "fp_auto_weld", True) and scene.fp_auto_style == 'WEIGHTED':
            welded = weld_seams(info["targets"], bone=not scene.fp_bone_hard_names.strip())
        # VRM: 目(物をまたぐ)・手の指の節・口の線(vrm.finish)。切れ目の色合わせ(weld_seams)の後に。
        # 前に置くと、口の中を黒く塗った色が周りの肌の色に合わされて口の線が消えた
        if scene.fp_auto_style == 'WEIGHTED':
            vrm_fix = vrm.finish(info["targets"])
            if vrm_fix:
                print(f"[freepencil.auto_setup] VRM の目・手・口: {vrm_fix}")

        style = getattr(scene, "fp_auto_style", 'PRECISE').lower()
        msg = (f"style={style}, meshes={len(info['targets'])}, "
               f"bone_aov={'ON' if info['has_rig'] else 'OFF'}, hashed={hashed}"
               + (f", overlays={len(overlays)}, clipped={len(clipped)}" if overlays or clipped else "")
               + (f", highlights={len(highlights)}" if highlights else "")
               + (f", eye_whites={len(eye_whites)}" if eye_whites else "")
               + (", vrm" if vrm_fix else "")
               + (f", welded={welded}" if welded else "")
               + (f", leaves={len(leaves)}" if leaves else "")
               + (f", figures={info['figures']}" if info.get("figures") else "")
               + (", mecha" if info.get("mecha") else "")
               + (f", lw_edges={'/'.join(f'{v:.3f}' for v in info['measured'])}"
                  if info.get("measured") else "")
               + (f", detected_aov={'+'.join(info['detected'])}"
                  if info["detected"] else ""))
        print(f"[freepencil.auto_setup] {msg}")
        self.report({'INFO'}, f"Auto setup done ({msg})")
        # ステータスバーだけだと見落とされる。STEP1〜3 を一気に走らせる
        # ボタンなので、終わったことをはっきり出す
        utils.show_message_box(f"STEP1-3 done. {msg}",
                               title="FreePencil STEP0", icon='CHECKMARK')
        return {'FINISHED'}

    @staticmethod
    def _clear_fine_pass(context):
        """メカの塗りの目印を外す(途中で止まっても次の STEP1 に残さない)。"""
        if "fp_fine_pass" in context.scene:
            del context.scene["fp_fine_pass"]

    def execute(self, context):
        """同期実行(スクリプト/バッチ/ヘッドレス用)。"""
        info = self._prepare(context)
        if info is None:
            self._clear_fine_pass(context)
            return {'CANCELLED'}
        bpy.ops.freepencil.auto_vertex_color()
        if not (getattr(context.scene, "fp_fine_lines", 0.0) > 0.0
                and context.scene.fp_line_weight):
            self._clear_fine_pass(context)
        return self._finish(context, info)

    def invoke(self, context, event):
        """GUI実行: STEP1 をモーダルで回して進捗バーを出し(応答なし対策)、
        終わってから STEP2/STEP3 を続ける。"""
        if bpy.app.background or context.window is None:
            return self.execute(context)
        info = self._prepare(context)
        if info is None:
            self._clear_fine_pass(context)
            return {'CANCELLED'}
        self._info = info
        gen, state = vertex_color.make_vertex_color_gen(context, quiet=True)
        if not self._progress_start(context, gen, state):
            self._clear_fine_pass(context)
            return state._result  # STEP1 が即失敗 → STEP2/3 は走らせない
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC':
            self._clear_fine_pass(context)
            self._progress_cancel(context)
            self.report({'INFO'}, "FreePencil: cancelled")
            return {'CANCELLED'}
        if event.type != 'TIMER':
            return {'RUNNING_MODAL'}  # 処理中は他の操作をブロック
        status = self._progress_step(context)
        if status == 'RUNNING':
            return {'RUNNING_MODAL'}
        if status == 'ERROR':
            self._clear_fine_pass(context)
            return {'CANCELLED'}
        self._progress_end(context)
        if self._state._result != {'FINISHED'}:
            self._clear_fine_pass(context)
            return self._state._result
        return self._finish(context, self._info)
