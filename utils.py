"""Utility helpers for UI interaction and vertex color handling."""

import array
import functools

import bpy
from collections import deque

# ──────────────────────────────────────────────
# UI ヘルパー
# ──────────────────────────────────────────────
def show_message_box(message: str,
                     title: str = "Message",
                     icon: str = "INFO") -> None:
    if bpy.app.background:
        # ヘッドレス実行時は popup_menu がクラッシュするためログ出力に切替
        print(f"[FreePencil] {title}: {message}")
        return
    def draw(self, _):
        self.layout.label(text=message)
    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)

# ──────────────────────────────────────────────
# 頂点カラーリスト取得
# ──────────────────────────────────────────────
def get_vertex_colors(obj: bpy.types.Object):
    if obj.type != 'MESH':
        return []
    if bpy.app.version < (3, 4, 0):
        return [v.name for v in obj.data.vertex_colors]
    return [v.name for v in obj.data.color_attributes]

# ──────────────────────────────────────────────
# アクティブ設定（ブラシ🖌️とカメラ🎥を常に同期）
# ──────────────────────────────────────────────
def set_active_vertex_color(obj: bpy.types.Object, color_name: str, index: int):
    """
    Color Attribute を選択するときに使用。
    ブラシ(🖌️)とカメラ(🎥)両方のインデックスを必ず同じにする。
    """
    # 3.4 未満: 旧 API
    if bpy.app.version < (3, 4, 0):
        vcols = obj.data.vertex_colors
        if not (0 <= index < len(vcols)):
            return
        obj.data.vertex_colors.active_index        = index
        obj.data.vertex_colors.active_render_index = index
        return

    # 3.4 以降: Color Attribute API
    attrs = obj.data.color_attributes

    # index 範囲外なら検索で補正
    if not (0 <= index < len(attrs)):
        index = next((i for i, v in enumerate(attrs) if v.name == color_name), None)
        if index is None:
            return  # 名前すら見つからないなら終了

    # ここで index は必ず正
    attrs.active_color_index  = index   # 🖌️
    attrs.render_color_index  = index   # 🎥

    # UI側のカメラアイコンを移動させる
    bpy.ops.geometry.color_attribute_render_set(name=color_name)

# ──────────────────────────────────────────────
# そのほかのユーティリティ（省略せず全文）
# ──────────────────────────────────────────────
def ensure_vertex_color(obj: bpy.types.Object,
                        color_name: str,
                        default_color=(0, 0, 0, 1)) -> int:
    """色属性が無ければ作り、その添字を返す。

    オペレータ(geometry.color_attribute_add)は使わない。オペレータは
    「アクティブオブジェクト」に対して働くうえ、呼ぶたびにモード切替と
    デプスグラフ更新が走る。STEP1 は1オブジェクトにつき4つ作るので、
    多パーツ・高密度モデルではここが支配的になっていた(実測: 138パーツ
    889k面で STEP1 の 93% が bpy.ops の呼び出し時間)。
    データAPIなら obj を直接指定でき、モード切替も不要。
    """
    vcols = obj.data.vertex_colors if bpy.app.version < (3, 4, 0) else obj.data.color_attributes
    for i, v in enumerate(vcols):
        if v.name == color_name:
            return i

    if bpy.app.version < (3, 4, 0):
        # 旧APIにはデータ側の追加手段が無いのでオペレータのまま
        prev_mode = obj.mode
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.mesh.vertex_color_add()
        vcols = obj.data.vertex_colors
        vcols[-1].name = color_name
        if prev_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode=prev_mode)
        return next(i for i, v in enumerate(vcols) if v.name == color_name)

    if obj.mode == 'EDIT':
        # 編集モード中はメッシュデータを直接いじれない。頻度は低いので
        # 従来どおりオペレータで通す
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.geometry.color_attribute_add(name=color_name,
                                             domain='CORNER',
                                             data_type='BYTE_COLOR',
                                             color=default_color)
        bpy.ops.object.mode_set(mode='EDIT')
        return next(i for i, v in enumerate(obj.data.color_attributes)
                    if v.name == color_name)

    attr = obj.data.color_attributes.new(name=color_name,
                                         type='BYTE_COLOR',
                                         domain='CORNER')
    # new() は初期色を取らないので自分で塗る。foreach_set は要素単位の
    # 代入よりはるかに速い。
    # バッファは array('f') で作る: Python の list だと要素ごとに
    # ポインタ8バイトを持つため、1000万面級のメッシュで 1.26GB を一瞬で
    # 掴む(実測)。array なら float32 そのままの 0.63GB で済み、
    # foreach_set 側も型変換なしで読める
    n = len(attr.data)
    if n:
        attr.data.foreach_set("color", array.array("f", default_color) * n)

    return next(i for i, v in enumerate(obj.data.color_attributes)
                if v.name == attr.name)


def find_connected_faces_bfs(bm, start_face, visited, is_boundary):
    """島(=境界エッジで囲まれた面の連結成分)を1つ取り出す。

    is_boundary は edge.index -> bool のシーケンスで、True のエッジは
    またがない。以前は edge.smooth を見ていたが、そのためにメッシュの
    シャープ属性を書き換えて後で戻す必要があった。判定を外から渡す形に
    してメッシュを一切触らないようにしている。
    """
    queue = deque([start_face])
    visited[start_face.index] = True
    island = [start_face]
    while queue:
        f = queue.popleft()
        for loop in f.loops:
            edge = loop.edge
            if is_boundary[edge.index]:
                continue
            for lf in edge.link_faces:
                if lf != f and not visited[lf.index]:
                    visited[lf.index] = True
                    queue.append(lf)
                    island.append(lf)
    return island


def merge_small_islands(islands, min_area_pct, face_area=None):
    """面積がメッシュ全体の min_area_pct% 未満の島を、隣接する最大の島に併合する。

    微小島は線として視認できないのに、色制約違反・線の断片化・
    処理時間をすべて悪化させるため、配色前に取り除く。
    面積比ベースなので低ポリメッシュ（立方体の1面など）は併合されない。

    face_area は face.index -> 面積 のシーケンス。渡されればそれを使う。
    BMFace.calc_area() は面ごとに幾何計算をやり直すため、320万面で
    240万回呼ぶと 0.7 秒かかる。Blender は polygon.area を既に持っている
    ので、呼び出し側が foreach_get で一括取得して渡せる。
    """
    if face_area is not None:
        areas = [sum(face_area[f.index] for f in faces) for faces in islands]
    else:
        areas = [sum(f.calc_area() for f in faces) for faces in islands]
    total = sum(areas)
    if total <= 0.0:
        return islands
    threshold = total * (min_area_pct / 100.0)

    face_island = {}
    for i, faces in enumerate(islands):
        for f in faces:
            face_island[f.index] = i

    neighbors = [set() for _ in islands]
    for i, faces in enumerate(islands):
        for f in faces:
            for edge in f.edges:
                for lf in edge.link_faces:
                    j = face_island.get(lf.index)
                    if j is not None and j != i:
                        neighbors[i].add(j)

    parent = list(range(len(islands)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    # 小さい島から順に、隣接する最大の島へ併合（決定論的）
    for i in sorted(range(len(islands)), key=lambda k: (areas[k], k)):
        ri = find(i)
        if areas[ri] >= threshold:
            continue
        best = -1
        best_area = -1.0
        for j in neighbors[i]:
            rj = find(j)
            if rj == ri:
                continue
            if areas[rj] > best_area or (areas[rj] == best_area and rj < best):
                best, best_area = rj, areas[rj]
        if best < 0:
            continue
        parent[ri] = best
        areas[best] += areas[ri]

    # ルート島の面を先頭に保ったまま組み立てる（色シードの安定性のため）
    merged = {}
    for i in range(len(islands)):
        if find(i) == i:
            merged[i] = list(islands[i])
    for i in range(len(islands)):
        r = find(i)
        if r != i:
            merged[r].extend(islands[i])
    return [merged[k] for k in sorted(merged)]


def count_loose_parts(mesh, stop_at: int = 0) -> int:
    """メッシュのルースパーツ(エッジ連結成分)数を数える。

    stop_at に正の値を渡すと、その個数に達した時点で数えるのをやめて
    stop_at を返す。呼び出し側が「N個以上あるか」しか見ないときに使う。
    正確な総数が要る場面では 0 (既定)のまま呼ぶこと。

    連結成分の数え上げは Python の union-find なので、300万面級では
    find() が1000万回以上走って数秒かかる(実測: 320万面のメッシュで
    5.6秒)。判定が閾値だけなら最後まで数える意味がない。
    """
    n = len(mesh.vertices)
    if n == 0:
        return 0

    # 辺は numpy で一括取得する。bpy のコレクションを Python で回すと
    # 要素アクセスのたびにラッパが作られて支配的なコストになる
    import numpy as np
    ne = len(mesh.edges)
    ev = np.empty(ne * 2, dtype=np.int32)
    mesh.edges.foreach_get("vertices", ev)

    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    ev = ev.tolist()
    for k in range(0, len(ev), 2):
        a, b = find(ev[k]), find(ev[k + 1])
        if a != b:
            parent[a] = b

    seen = set()
    for i in range(n):
        seen.add(find(i))
        if stop_at and len(seen) >= stop_at:
            return stop_at
    return len(seen)


# 人工分割の角度の下限。
#
# 「一様に滑らかで構造線が無い」枝に落ちたモデルは、p50×0.95 で
# 分割線を人工的に作る。下限が 5度 だと、なめらかに曲がる面のどこでも
# 超えてしまうので、切れ目が形と関係ない場所に落ちる。実測: サブサーフを
# 適用したスザンヌは 6.2度 が選ばれ、耳の裏がメカのパネルのように
# 面を横切って割れた(その境界がそのまま線画に出る)。
#
# 14度 にする根拠(BlenderKit 60体・2026-09):
#   この枝に落ちるのは 60体中4体だけ。残り56体は構造線・曲率・多パーツ・
#   リグ・サブサーフのどれかで先に決まるので、下限には届かない。
#   触れた4体を原寸で見た結果、4体とも同じか良くなった。
#     eggs_bowl    卵1個ごとの偽の同心円(輪切りのオリーブに見えた)が消え、
#                  卵の輪郭は残った
#     formal-shoe  舌革の階段状のギザギザが消えた
#     cleaver_knife 柄の余計な斜線が消えた
#     basketball   縫い目が強くなった(18度では消えるので上げすぎない)
#   スザンヌの耳が直るのが 13->14度 なので、これより下げると戻る。
#
# 既定は v2.7 と同じ 5.0。STEP0 の仕上がり「強弱(手描き)」が 14.0 を
# 渡す(auto_setup.py)。「精密(メカ)」は v2.7 の出力を変えない
ARTIFICIAL_SPLIT_FLOOR = 5.0


def choose_auto_threshold(angles_deg, has_armature=False, many_parts=False,
                          has_subsurf=False, split_floor=None):
    """二面角の分布から STEP1 のシャープしきい値を自動決定する。

    実測(車/メカ/塔/人物/イカ/球/樹木の7モデル)に基づくルール:
    - p90 > 100°: 交差ジオメトリ(葉カード等) → 85° + 強めの小島マージ
    - p95 > 75° : 90°付近に構造エッジの山     → 60°(安全な汎用値)
    - p99 > 45° : 曲率の連続分布のみ(有機系) → p99×0.9 (60〜85°)
    - それ以外  : 一様に滑らか(構造線なし)   → p50×0.95 で分割線を人工生成

    has_armature=True(リグ付きキャラ)の場合、線抽出の主役は bone_color
    (ボーン境界)なので、滑面への人工分割線は絶対に出さない。
    mecha 側はノイズを増やさない保守的な高しきい値に倒す。

    many_parts=True(ルースパーツの多い組立モデル: 骨格標本など)の場合も
    人工分割はしない。パーツ間のシルエット/深度線が既に十分な線源であり、
    細い部品への分割線は潰れの原因になるだけ(骨格モデルで実証)。

    has_subsurf=True(サブディビジョンが生きている)の場合も人工分割はしない。
    STEP1 が塗るのはモディファイア適用**前**のベースメッシュで、それは
    なめらかな形を作るための粗いケージにすぎない。ケージの稜線に沿って
    割ると、レンダリングでは存在しない格子がそのまま線として出る。

    実測: 野球ボール(サブディブ1個/ベース320面)は p50 が小さいため
    最後の枝に落ちて 9.9度 になり、球面全体にケージの格子が線で出た。
    猫の置物(同じくサブディブ付き)は 60度 が選ばれていて問題なく、
    手動で 20度 に下げると耳と顔にケージが出た。つまりサブディビジョンが
    ある側では「下げない」のが正しい。

    戻り値: (threshold_deg, min_island_area_pct への提案 or None)
    """
    if not angles_deg:
        return 60.0, None
    s = sorted(angles_deg)
    n = len(s)

    def pct(p):
        return s[min(n - 1, int(n * p / 100))]

    if has_armature:
        # キャラの肌・服は曲率連続。人工分割はせず、明確な構造エッジのみ拾う
        return (60.0 if pct(95) > 75.0 else max(60.0, min(85.0, pct(99) * 0.9))), None

    if pct(90) > 100.0:
        return 85.0, 0.5
    if pct(95) > 75.0:
        return 60.0, None
    p99 = pct(99)
    if p99 > 45.0:
        return max(60.0, min(85.0, p99 * 0.9)), None
    if many_parts:
        # 一様に滑らかでも、多パーツ組立ならパーツ境界の線で十分
        return 60.0, None
    if has_subsurf:
        # ベースメッシュは粗いケージ。ここで割るとケージが線になる
        return 60.0, None
    floor = ARTIFICIAL_SPLIT_FLOOR if split_floor is None else float(split_floor)
    return max(floor, pct(50) * 0.95), None


def _color_distance(c1, c2) -> float:
    return sum((a - b) ** 2 for a, b in zip(c1, c2)) ** 0.5


def build_island_adjacency(islands, face_to_island_id, is_boundary):
    """島の隣接グラフ(境界エッジを共有する島同士)を返す。

    is_boundary は find_connected_faces_bfs と同じ edge.index -> bool。
    島の切り方と隣接の見方が同じ基準でないと、隣り合う島が「隣接なし」と
    判定されて同じ色クラスになり、境界線が消える。
    """
    neighbors = [set() for _ in islands]
    for i, faces in enumerate(islands):
        for f in faces:
            for edge in f.edges:
                if not is_boundary[edge.index]:
                    continue  # 島内のエッジは見る必要がない
                for lf in edge.link_faces:
                    j = face_to_island_id.get(lf.index)
                    if j is not None and j != i:
                        neighbors[i].add(j)
                        neighbors[j].add(i)
    return neighbors


def color_graph_greedy(neighbors):
    """次数の大きい順の決定論的グリーディ彩色。色クラス番号のリストを返す。

    表面の島グラフはほぼ平面グラフなので、実用上クラス数は数個に収まる。
    """
    order = sorted(range(len(neighbors)), key=lambda i: (-len(neighbors[i]), i))
    classes = [-1] * len(neighbors)
    for i in order:
        used = {classes[j] for j in neighbors[i] if classes[j] >= 0}
        c = 0
        while c in used:
            c += 1
        classes[i] = c
    return classes


def _luma(c) -> float:
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


# 隣接に要求する最低の輝度差。
#
# 平面の格子に既知の色を置いて測ると、輝度差 0 でも RGB 距離があれば線は出た
# (dev/note_assets/probe_line_response.py)。しかし実モデルでは輝度が近いと
# 線が消える回帰が観測されている(woman の顔と服の線が消滅、tests_smoke t13)。
# 理想条件の実測より、実機で起きた失敗を優先する。
MIN_NEIGHBOR_LUMA = 0.12

# パレット選定時に輝度差へ持たせる余裕。ジッターで縮む分を見込む
JITTER_LUMA_MARGIN = 1.25


def palette_for_diversity(min_dist, max_k, seed_int, min_k=1,
                          min_luma=MIN_NEIGHBOR_LUMA,
                          luma_lo=0.25, luma_hi=0.75):
    """制約を守れる範囲で、いちばん色数の多いパレットを返す。

    彩色数(=隣接グラフの色数)ぶんしか作らないと、島同士がメッシュで
    繋がっていない形で色が足りなくなる。実測:

        "Text"        124島 / 隣接辺185 -> 彩色数 2
        "Text"(自動)   13島 / 隣接辺  0 -> 彩色数 1
        "FreePencil2" 237島 / 隣接辺340 -> 彩色数 4

    "Text" は全部が同じ黄色になっていた(1クラス + ジッターなので色相が
    ひとつしか無い)。そこで彩色数を下限として、色数を増やせるだけ増やす。

    増やす上限は2つの実測値で決まる。色数 k のときパレットは
    RGB最小距離 と 最小輝度差 が次のようになる。

        k    2      4      6      8     12     16     48
        RGB  1.204  0.750  0.534  0.456  0.371  0.317  0.203
        輝度 0.500  0.167  0.100  0.071  0.045  0.033  0.011

    輝度は [luma_lo, luma_hi] の幅を等分するので k を増やすほど縮む。
    既定の幅 0.5 では輝度差 0.12 を守れるのは5色まで。ここが天井。

    min_k(=彩色数)は制約より優先する。下回ると隣が同じ色になって
    塗り分けが成立しないため(立方体は6面が互いに隣接するので6色要る)。
    """
    # build_palette が返す dmin / lmin は **全ペア**の最小値だが、契約が
    # 要るのは **隣り合うペアだけ**。全ペアで縛ると色数が一気に落ちる
    # (既定の窓で4色が上限になり、文字の側面が同じ色になった)。
    #
    # パレットは「クラス番号が近いほど輝度が離れる」順に並んでいるので、
    # 先頭 min_k 色は必ずよく離れている。従来の割り当て(島 -> クラス番号)は
    # そこだけを使うため、パレットを大きくしても出発点は悪化しない。
    # 隣接の契約は diversify_island_colors が色を移すときに見る。
    #
    # ここでは「先頭 min_k 色が契約を満たすか」だけを確かめて、
    # 満たす中で最大の色数を採る。
    need_luma = min_luma * JITTER_LUMA_MARGIN
    lo = max(1, int(min_k))
    hi = max(lo, int(max_k))

    def head_ok(pal):
        """出発点に使う先頭 lo 色が契約を満たすか。"""
        for a in range(min(lo, len(pal))):
            for b in range(a + 1, min(lo, len(pal))):
                ca, cb = pal[a], pal[b]
                d = sum((ca[i] - cb[i]) ** 2 for i in range(3)) ** 0.5
                if d < min_dist or abs(_luma(ca) - _luma(cb)) < need_luma:
                    return False
        return True

    for k in range(hi, lo - 1, -1):
        pal, dmin, lmin = build_palette(k, seed_int, luma_lo=luma_lo,
                                        luma_hi=luma_hi)
        if head_ok(pal):
            return pal, dmin, lmin
    return build_palette(lo, seed_int, luma_lo=luma_lo, luma_hi=luma_hi)


def diversify_island_colors(neighbors, classes, palette,
                            min_rgb, min_luma=MIN_NEIGHBOR_LUMA):
    """彩色済みの割り当てを出発点に、制約を壊さない範囲で色を散らす。

    color_graph_greedy の結果(島 -> クラス番号)をそのまま色番号として使うと、
    パレットを増やしても先頭の数色しか使われない。かといって最初から貪欲に
    選び直すと、密なグラフ(立方体の6面など)で従来より悪い割り当てになり、
    距離の契約を割ってしまった(実測: 立方体で違反2件)。

    そこで**従来の割り当てから出発**して、次の場合だけ色を移す。

      - いまの色が隣との制約(RGB距離 min_rgb / 輝度差 min_luma)を
        満たしていない → 満たす色があれば移る(改善)
      - 満たしている → 使用回数がより少ない色で、かつ制約も満たす色が
        あれば移る(色を散らす。制約は保ったまま)

    どちらも制約を悪化させない。候補が無ければ動かさないので、
    最悪でも従来と同じ割り当てになる。
    """
    n = len(neighbors)
    k = len(palette)
    if n == 0 or k == 0:
        return list(classes), 0
    pal = [tuple(float(v) for v in c[:3]) for c in palette]
    lum = [_luma(c) for c in pal]

    def ok(a, b):
        d = ((pal[a][0] - pal[b][0]) ** 2 + (pal[a][1] - pal[b][1]) ** 2
             + (pal[a][2] - pal[b][2]) ** 2) ** 0.5
        return d >= min_rgb and abs(lum[a] - lum[b]) >= min_luma

    out = [min(c, k - 1) for c in classes]
    usage = [0] * k
    for c in out:
        usage[c] += 1

    # 制約の厳しい島から見る。次数が同じなら島番号順(決定論的)
    for i in sorted(range(n), key=lambda x: (-len(neighbors[x]), x)):
        nb = [out[j] for j in neighbors[i]]
        cur = out[i]
        cur_ok = all(ok(cur, u) for u in nb)
        cand = [c for c in range(k) if c != cur and all(ok(c, u) for u in nb)]
        if not cand:
            continue
        best = min(cand, key=lambda c: (usage[c], c))
        if not cur_ok or usage[best] + 1 < usage[cur]:
            usage[cur] -= 1
            usage[best] += 1
            out[i] = best
    return out, sum(1 for u in usage if u)


# パーツ・トーン分けで使う明度窓。
#
# 下限 0.25: これより暗くすると色同士の RGB 距離が縮み、塗り分けの区別が
#            崩れる(0.10 まで下げて実機で悪化を確認済み)。動かせない。
# 上限 0.85: 白背景(1.0)との差を残してシルエット線を保証する。
#
# 窓は上へずらす。3段目は上限に当たって幅が 0.26 まで潰れる
# (メカ155パーツ中50パーツが該当。実測で再現済み)。
#
# 【調査済みの行き止まり】幅を揃えて位置だけずらす案(幅0.40・段0.10)を
# 試したが、採用しない。理由は実測:
#   - 窓幅は揃う(最小 0.2514 -> 0.3801)し、机上の指標も良くなる
#   - しかし **レンダー結果が変わらない**。メカを線感度 1.0/0.6/0.4 で
#     比べて ink 差 -0.4%〜+0.1%、線画素の96%が同一、濃さの分布も同じ。
#     窓 0.26 でもエッジ検出のしきい値は十分に超えている
#   - 一方で段を 0.17 -> 0.10 に詰めた副作用で、接するパーツ間の輝度差が
#     0.12+ -> 0.076 に落ちて t18 が落ちる。min距離 0.85 の契約(t14)も破れる
# つまり「得るものが無く、パーツ分離だけ失う」。段 0.17 は動かせない。
#
# 旧コードには「窓幅が半減する = そのパーツの線が薄い」とあったが、
# 後半は推論で、絵では確認されていなかった。窓幅の偏り自体は事実だが、
# 見た目の不具合としては再現しない。ここを触っても改善は出ない。
# 線を濃くしたいなら STEP3 の線感度かチャンネル強度、
# 出ない線を増やしたいなら PRO ノード側(曲率ベースの抽出)が本筋。
PART_LUMA_FLOOR = 0.25
PART_LUMA_CEIL = 0.85
PART_TINT_STEPS = 3
PART_TINT_DELTA = 0.17


def part_luma_window(part_class: int) -> tuple[float, float]:
    """パーツ・トーン分けのクラス番号から明度窓 (lo, hi) を返す。

    上へずらす方式。上限 PART_LUMA_CEIL でクランプするので、段が上の
    クラスほど窓が狭くなる。狭くなること自体は許容している(上のコメント)。
    """
    step = (part_class % PART_TINT_STEPS) * PART_TINT_DELTA
    return PART_LUMA_FLOOR + step, min(PART_LUMA_CEIL, 0.75 + step)


def build_palette(k, seed_int, luma_lo=0.25, luma_hi=0.75):
    """輝度ラダー方式で k 色のパレットを決定論的に作る(_build_palette)。

    同じ引数なら同じ結果なので、作ったものを覚えて使い回す。物ごと・色数ごとに何百回も
    作り直していて、戦車(42 万面)の STEP0 101 秒のうち 18 秒がここだった。
    色のリストは呼ぶ側が書き換えてもよいよう、毎回写しを返す。
    """
    cols, pmin, lmin = _build_palette(int(k), int(seed_int), float(luma_lo), float(luma_hi))
    return list(cols), pmin, lmin


@functools.lru_cache(maxsize=1024)
def _build_palette(k, seed_int, luma_lo, luma_hi):
    """輝度ラダー方式で k 色のパレットを決定論的に作る。

    PROノードの線抽出は「白背景にプリミックス → エッジ検出 → ColorRamp
    (float入力=輝度)」なので、線が出るかどうかは **輝度差** で決まる
    (RGB距離ではない)。そこで:
    - 輝度レベルを [luma_lo, luma_hi] に等間隔配置(既定 0.25-0.75。
      上限は白背景との輝度差を確保しシルエット線を保証)
    - 連続するクラス番号(隣接しやすい)ほど輝度が離れるよう両端から
      交互に割り当てる(クラス0=最暗=シルエット最強)
    - 色相は視認性のための飾り(黄金比ステップ)。彩度は目標輝度を
      val<=1 で達成できる値に自動調整
    パーツ・トーン分けは luma_lo/hi の窓ずらしとして渡す(生成後の
    オフセット加算はクランプで距離保証を壊す — 実測でクランプ起因の
    min距離違反が出たため、制約は生成器の中で扱う)。
    戻り値: (colors, RGB最小ペア距離, 最小輝度差)
    """
    import colorsys

    if k <= 1:
        # 窓幅に比例させると狭い窓でパーツ間の明度差が縮む(t18 実測)ため
        # 絶対オフセット。既定窓では従来どおり 0.40
        levels = [min(luma_hi, luma_lo + 0.15)]
    else:
        span = (luma_hi - luma_lo) / (k - 1)
        levels = [luma_lo + i * span for i in range(k)]

    # 両端から交互に: 連続クラス番号の輝度差を最大化
    order = []
    lo, hi = 0, len(levels) - 1
    take_low = True
    while lo <= hi:
        if take_low:
            order.append(levels[lo]); lo += 1
        else:
            order.append(levels[hi]); hi -= 1
        take_low = not take_low

    # 各輝度スロット内では、既に選んだ色とのRGB距離を最大化する候補を選ぶ
    # (輝度差=線の検出性、RGB距離=ユーザー契約 min_neighbor_color_distance)。
    # 貪欲の近視眼を避けるため、開始色相12通りで全体を作り最良を採る
    def build_with_offset(offset: float):
        cols = []
        for target in order:
            best, best_d = None, -1.0
            for hj in range(12):
                hue = (offset + hj / 12.0) % 1.0
                for sat in (0.9, 0.7, 0.45, 0.2):
                    unit = colorsys.hsv_to_rgb(hue, sat, 1.0)
                    l1 = _luma(unit)
                    if l1 < target or l1 <= 1e-6:
                        continue  # この彩度では目標輝度に届かない(val>1)
                    val = target / l1
                    c = tuple(v * val for v in unit)
                    d = min((_color_distance(c, p) for p in cols),
                            default=float("inf"))
                    if d > best_d:
                        best, best_d = c, d
            cols.append(best if best is not None else (target, target, target))
        if len(cols) >= 2:
            score = min(_color_distance(a, b)
                        for i, a in enumerate(cols) for b in cols[i + 1:])
        else:
            score = float("inf")
        return cols, score

    base = (seed_int % 360) / 360.0
    colors, best_score = None, -1.0
    for restart in range(12):
        cols, score = build_with_offset((base + restart / 12.0) % 1.0)
        if score > best_score:
            colors, best_score = cols, score

    if len(colors) >= 2:
        pmin = min(_color_distance(a, b)
                   for i, a in enumerate(colors) for b in colors[i + 1:])
        lmin = min(abs(_luma(a) - _luma(b))
                   for i, a in enumerate(colors) for b in colors[i + 1:])
    else:
        pmin = float("inf")
        lmin = float("inf")
    return colors, pmin, lmin


def copy_vertex_color(obj, src_name: str, dst_name: str) -> bool:
    """色属性をまるごと複製する(細い線の 2 枚塗り用)。

    STEP1 は毎回 mecha_color を塗り直すので、1 回目(精密の分割)の結果を
    別の名前へ写しておく。戻り値は写したかどうか。
    """
    import numpy as np

    me = obj.data
    cols = getattr(me, "color_attributes", None)
    if cols is None:
        return False
    src = cols.get(src_name)
    if src is None:
        return False
    dst = cols.get(dst_name)
    if dst is not None and (dst.domain != src.domain or dst.data_type != src.data_type):
        cols.remove(dst)
        dst = None
    if dst is None:
        dst = cols.new(name=dst_name, type=src.data_type, domain=src.domain)
    n = len(src.data)
    buf = np.empty(n * 4, dtype=np.float32)
    src.data.foreach_get("color", buf)
    dst.data.foreach_set("color", buf)
    me.update()
    return True


def apply_face_colors(obj, vcol_index, face_r, face_g, face_b,
                      loop_offset=None):
    vcols = obj.data.vertex_colors if bpy.app.version < (3, 4, 0) else obj.data.color_attributes
    if not (0 <= vcol_index < len(vcols)):
        return
    vc_data = vcols[vcol_index].data
    me = obj.data
    n_loops = len(me.loops)
    if n_loops == 0:
        return

    # 面の色をループ(コーナー)へ展開する。Python で polygon.loop_indices を
    # 回すと、320万面のメッシュで 8.7 秒かかっていた(実測。うち
    # loop_indices の呼び出しだけで 1.5 秒)。
    # 各ループがどの面に属するかは loop_start/loop_total から作れるので、
    # numpy で一括展開して foreach_set で一度に書く
    import numpy as np

    n_polys = len(me.polygons)
    starts = np.empty(n_polys, dtype=np.int32)
    totals = np.empty(n_polys, dtype=np.int32)
    me.polygons.foreach_get("loop_start", starts)
    me.polygons.foreach_get("loop_total", totals)

    # loop -> polygon の対応。面ごとの loop_total 回だけ面番号を繰り返す
    loop_poly = np.repeat(np.arange(n_polys, dtype=np.int32), totals)

    buf = np.empty((n_loops, 4), dtype=np.float32)
    buf[:, 0] = np.asarray(face_r, dtype=np.float32)[loop_poly]
    buf[:, 1] = np.asarray(face_g, dtype=np.float32)[loop_poly]
    buf[:, 2] = np.asarray(face_b, dtype=np.float32)[loop_poly]
    buf[:, 3] = 1.0

    # 稜線の起伏(コーナーごと)。島の色は面ごとに一定なので、これを足すと
    # 島の**中だけ**がゆるく揺れる。島境界の段差はそのまま残るので、
    # パーツ線・鋭角線は影響を受けない
    if loop_offset is not None:
        off = np.asarray(loop_offset, dtype=np.float32)
        if off.shape == (n_loops, 3):
            np.clip(buf[:, :3] + off, 0.0, 1.0, out=buf[:, :3])

    # loop_start が昇順に詰まっていない(＝np.repeat の並びと一致しない)
    # メッシュは理論上ありうるので、そのときだけ並べ直す
    expected = np.concatenate(([0], np.cumsum(totals[:-1]))).astype(np.int32)
    if not np.array_equal(starts, expected):
        order = np.concatenate([np.arange(s, s + t, dtype=np.int32)
                                for s, t in zip(starts.tolist(),
                                                totals.tolist())])
        fixed = np.empty_like(buf)
        fixed[order] = buf
        buf = fixed

    vc_data.foreach_set("color", buf.ravel())
