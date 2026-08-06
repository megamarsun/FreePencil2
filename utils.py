"""Utility helpers for UI interaction and vertex color handling."""

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
    # 代入よりはるかに速い
    n = len(attr.data)
    if n:
        attr.data.foreach_set("color", list(default_color) * n)

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


def merge_small_islands(islands, min_area_pct):
    """面積がメッシュ全体の min_area_pct% 未満の島を、隣接する最大の島に併合する。

    微小島は線として視認できないのに、色制約違反・線の断片化・
    処理時間をすべて悪化させるため、配色前に取り除く。
    面積比ベースなので低ポリメッシュ（立方体の1面など）は併合されない。
    """
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


def count_loose_parts(mesh) -> int:
    """メッシュのルースパーツ(エッジ連結成分)数を数える。"""
    n = len(mesh.vertices)
    if n == 0:
        return 0
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for e in mesh.edges:
        a, b = find(e.vertices[0]), find(e.vertices[1])
        if a != b:
            parent[a] = b
    return len({find(i) for i in range(n)})


def choose_auto_threshold(angles_deg, has_armature=False, many_parts=False):
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
    return max(5.0, pct(50) * 0.95), None


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


def apply_face_colors(obj, vcol_index, face_r, face_g, face_b):
    vcols = obj.data.vertex_colors if bpy.app.version < (3, 4, 0) else obj.data.color_attributes
    if not (0 <= vcol_index < len(vcols)):
        return
    vc_data = vcols[vcol_index].data
    for idx, poly in enumerate(obj.data.polygons):
        r, g, b = face_r[idx], face_g[idx], face_b[idx]
        for li in poly.loop_indices:
            vc_data[li].color = (r, g, b, 1.0)
