"""島(=境界エッジで囲まれた面の連結成分)の抽出を numpy でやる。

STEP1 はもともと bmesh を作って、辺と面を Python で1つずつ触っていた。
それが速度とメモリの両方の壁になっていた。実測(デパートのシーン、
1000万面のメッシュ1個):

    bmesh.from_mesh                +5.65 GB
    BMFace ラッパ 1060万個          +0.85 GB
    合計                           +16.5 GB / 201 秒

必要なのは「ループ→辺」「ループ→面」「面法線」「面積」「面の中心」
「シャープ/シーム/マテリアル番号」だけで、全部 foreach_get で配列として
一括で取れる。bmesh は要らない。

出力は bmesh 版と1ビットも変わらないように作ってある。要点は2つ:

  * 連結成分のラベルは必ず「その島に属する最小の面インデックス」になる
    (常に小さい方へ繋ぐため)。bmesh 版は面を昇順に走査して未訪問の面から
    BFS していたので、島の順序も代表面(islands[i][0])も同じものになる。
  * 島の中の面は昇順に並べる。bmesh 版は BFS 順だったが、下流が見るのは
    先頭要素だけで、それは両者とも「最小の面インデックス」で一致する。
"""
from __future__ import annotations

import numpy as np


def _zero_normal_mask(mesh, totals, starts, loop_vert, vco):
    """BMesh が法線ゼロと判断する面(退化面)を洗い出す。

    Mesh 側の polygon.normal は法線を出せない面に (0,0,1) を返すが、
    BMFace.normal は (0,0,0) を持つ。この違いを放置すると、その面に接する
    辺の二面角が変わって島の切れ方がずれる。

    判定は Blender の normalize_v3 と同じ「法線ベクトルの二乗長が
    1e-35 以下ならゼロ」。法線の作り方も BMesh に合わせる:
    三角形と四角は外積、五角形以上は Newell。
    """
    nf = len(totals)
    zero = np.zeros(nf, dtype=bool)
    if nf == 0:
        return zero

    def co(sel_start, k):
        return vco[loop_vert[sel_start + k]]

    for n_verts in np.unique(totals).tolist():
        sel = np.flatnonzero(totals == n_verts)
        if not len(sel):
            continue
        st = starts[sel].astype(np.intp)
        if n_verts == 3:
            a = co(st, 0) - co(st, 1)
            b = co(st, 1) - co(st, 2)
            nrm = np.cross(a, b)
        elif n_verts == 4:
            a = co(st, 0) - co(st, 2)
            b = co(st, 1) - co(st, 3)
            nrm = np.cross(a, b)
        elif n_verts < 3:
            zero[sel] = True
            continue
        else:
            nrm = np.zeros((len(sel), 3), dtype=np.float32)
            prev = co(st, n_verts - 1)
            for k in range(n_verts):
                cur = co(st, k)
                nrm[:, 0] += (prev[:, 1] - cur[:, 1]) * (prev[:, 2] + cur[:, 2])
                nrm[:, 1] += (prev[:, 2] - cur[:, 2]) * (prev[:, 0] + cur[:, 0])
                nrm[:, 2] += (prev[:, 0] - cur[:, 0]) * (prev[:, 1] + cur[:, 1])
                prev = cur
        d = np.einsum("ij,ij->i", nrm.astype(np.float32), nrm.astype(np.float32))
        zero[sel] = d <= np.float32(1.0e-35)
    return zero


def _compress(p: np.ndarray) -> np.ndarray:
    """親配列が星型(全員が根を直接指す)になるまで縮める。"""
    while True:
        q = p[p]
        if np.array_equal(q, p):
            return p
        p = q


def connected_components(ea: np.ndarray, eb: np.ndarray, n: int) -> np.ndarray:
    """辺リストから連結成分ラベルを返す。ラベル = 成分内の最小の頂点番号。

    Shiloach-Vishkin。ノードではなく「根」同士を繋ぐのが肝で、そこを
    間違えると収束が桁で悪くなる(実測: 320万面のメッシュで 96ラウンド
    5.66秒 → 3ラウンド 0.24秒)。決着した辺は毎回捨てて問題を縮める。
    """
    p = np.arange(n, dtype=np.int32)
    if len(ea) == 0:
        return p
    ea = ea.astype(np.int32, copy=True)
    eb = eb.astype(np.int32, copy=True)
    # 実測では 1000万面のメッシュでも 3〜4 ラウンドで決着する。
    # 上限は暴走よけで、ここに当たったら結果が正しくないので黙って返さない
    limit = 200
    for _ in range(limit):
        if len(ea) == 0:
            return p
        ra, rb = p[ea], p[eb]
        np.minimum.at(p, ra, rb)
        np.minimum.at(p, rb, ra)
        p = _compress(p)
        ra, rb = p[ea], p[eb]
        live = ra != rb
        ea, eb = ra[live], rb[live]
    raise RuntimeError(
        f"連結成分が {limit} ラウンドで収束しなかった "
        f"(残り辺 {len(ea)} / 頂点 {n})")



# 島が細かすぎる = メッシュの網目がそのまま線になっている状態。
# 面いくつに1島までなら「線」として見られるか、の上限。
# 実測(BlenderKit 40モデル): 健全なモデルは 0.00〜0.10 に収まり、
# 壊れているものは 0.20〜0.81 だった。0.08 はその谷間に置いている。
MAX_ISLANDS_PER_FACE = 0.08
BISECT_TRIES = 6      # 上限を満たす中で最も細かい角度を詰める回数
MIN_ISLANDS = 8       # これを下回るまでまとめない(線が消えるため)


def resolve_threshold(topo, start_deg: float, seam: bool, clear: bool,
                      max_ratio: float = MAX_ISLANDS_PER_FACE,
                      tries: int = 6, max_deg: float = 179.0) -> tuple:
    """実際に切ってみて、細かすぎたら閾値を上げ直す。

    二面角の分布だけで系統を当てにいく方式は、実測で 39モデル中 9モデルが
    切れすぎになった(野球ボール 島/面 0.81、本 0.66、カエデ 0.41 など)。
    分類を当てるより、切った結果を見て直すほうが確実で外れない。

    島検出は numpy 化で 1000万面でも 0.24 秒なので、数回試しても実用速度に
    収まる。戻り値は (採用した角度, 試行回数, 最終的な島/面)。
    """
    nf = max(topo.n_faces, 1)
    # 判定は比率ではなく「島の数」で行う。比率だけだと面数の少ないメッシュが
    # 壊れる: 立方体は6面なので上限0.08 = 許容0.48島となり、179度まで上げて
    # 1島に潰れた。6面が別色になるのは塗り分けの最も基本的な動作なので、
    # 少ない側は下限で守る
    limit = max(int(max_ratio * nf), MIN_ISLANDS)

    def cut(d):
        topo.mark_boundaries(np.radians(d), seam, clear)
        topo.build_islands()
        return len(topo.islands)

    deg = float(start_deg)
    used = deg
    cnt = nf
    n = 0
    lo = None            # まだ切れすぎている角度(=島が多い側)
    for i in range(tries):
        cnt = cut(deg)
        used = deg
        n = i + 1
        if cnt <= limit:
            break
        lo = deg
        if deg >= max_deg:
            return used, n, cnt / nf
        # 上げ幅は「まだ遠いほど大きく」。1回で行き過ぎないよう頭打ちも置く
        over = min(8.0, cnt / max(limit, 1))
        deg = min(max_deg, deg + max(8.0, deg * 0.35 * over))
    else:
        return used, n, cnt / nf

    if lo is not None:
        # 上げ幅が粗いので上限を飛び越していることがある。上限を守る中で
        # 最も細かい角度を二分探索で拾い直す
        hi = used
        for _ in range(BISECT_TRIES):
            if hi - lo < 0.5:
                break
            mid = (lo + hi) * 0.5
            n += 1
            if cut(mid) <= limit:
                hi = mid
            else:
                lo = mid
        used = hi
        cnt = cut(used)

    # 二面角が一様なメッシュ(なめらかな球など)は「全面が別島」か「1島」の
    # 二択しかなく、中間が存在しない。ここで1島を選ぶと分割線が全部消えて
    # のっぺりしたシルエットになる。塗り分け法は角の無い物体こそ人工的に
    # 割る必要があるので、下限を割るくらいなら元の細かい方を採る
    if cnt < MIN_ISLANDS and cut(start_deg) >= MIN_ISLANDS:
        used = float(start_deg)
        cnt = cut(used)
    return used, n, cnt / nf

# 角度を下げる方向の探索。1パーツあたり何島まで許すか。
#
# 実測(角度を 5〜75度で振って島の数を数えた):
#   sample2の箱(10面)  25度で10島 / 5度でも10島
#   円柱32(34面)       15度で3島  / 10度で34島
#   スザンヌ適用(7872面) 20度で29島 / 15度で146島 / 5度で2894島
#   UV球64(2048面)     10度で1島  / 5度で662島
# つまり格子が出るのは 5〜10度で、25度ではハイポリは1つも割れない。
# 「メカだから下げる/ハイポリだから下げない」ではなく、下げた結果の
# 島の数を見れば同じ規則で扱える。20 はこの4形状の谷に置いた仮の値。
LOWER_ISLANDS_PER_PART = 20
LOWER_CAND_DEG = (75.0, 60.0, 50.0, 40.0, 30.0, 25.0, 20.0, 15.0)


def lower_threshold_for_detail(topo, n_parts: int, seam: bool, clear: bool,
                               cap_per_part: int = LOWER_ISLANDS_PER_PART):
    """角度を下げて拾える線があるなら下げる。無ければ元のまま。

    分位点だけで決めると、多数派の角度が少数派を隠す。実測: 面取りした
    箱(10面)の二面角は 90度x8 / 79度x4 / 64度x4 / 25.6度x4 で、
    p95 が 90度になるため `p95>75 -> 60度` の枝に落ち、緩い斜面の
    25.6度が切られずに線が消えていた。

    そこで候補角を高い方から順に切ってみて、
      * 島の数が上限(パーツ数 x cap_per_part)を超えない範囲で
      * 島がいちばん多くなる、最も高い角度
    を採る。同じ島数なら高い方を採るのは、情報が増えないのに下げると
    不安定になるため(上の箱は25度以下で島数が変わらない)。

    戻り値は (採用した角度, その島数)。
    """
    cap = max(1, n_parts) * cap_per_part
    best_deg, best_n = None, -1
    for d in LOWER_CAND_DEG:
        topo.mark_boundaries(np.radians(d), seam, clear)
        topo.build_islands()
        n = len(topo.islands)
        if n <= cap and n > best_n:
            best_deg, best_n = d, n
    return best_deg, best_n


class MeshTopology:
    """1つのメッシュから、島の判定に要るものを全部配列で持つ。"""

    __slots__ = ("n_faces", "n_edges", "face_a", "face_b", "two_face",
                 "angle", "sharp", "seam", "crease", "material", "area",
                 "center",
                 "is_boundary", "labels", "islands", "_island_of_face",
                 "_inc_faces", "_inc_first", "_inc_count", "_degenerate")

    def __init__(self, mesh):
        nf = self.n_faces = len(mesh.polygons)
        ne = self.n_edges = len(mesh.edges)
        nl = len(mesh.loops)

        if nf == 0:
            # 面が無いメッシュ(辺だけ、頂点だけ、空)。辺の配列は辺の本数に
            # 合わせておかないと mark_boundaries で形が合わなくなる
            self.face_a = np.full(ne, -1, dtype=np.int32)
            self.face_b = np.full(ne, -1, dtype=np.int32)
            self.two_face = np.zeros(ne, dtype=bool)
            self.angle = np.full(ne, np.nan, dtype=np.float32)
            self.sharp = np.zeros(ne, dtype=bool)
            self.seam = np.zeros(ne, dtype=bool)
            self.material = np.empty(0, dtype=np.int32)
            self.area = np.empty(0, dtype=np.float32)
            self.center = np.empty((0, 3), dtype=np.float32)
            self.is_boundary = np.ones(ne, dtype=bool)
            self.labels = np.empty(0, dtype=np.int32)
            self.islands = []
            self._island_of_face = np.empty(0, dtype=np.int32)
            self._inc_faces = np.empty(0, dtype=np.int32)
            self._inc_first = np.zeros(ne, dtype=np.int64)
            self._inc_count = np.zeros(ne, dtype=np.int64)
            self._degenerate = np.zeros(0, dtype=bool)
            return

        loop_edge = np.empty(nl, dtype=np.int32)
        mesh.loops.foreach_get("edge_index", loop_edge)
        totals = np.empty(nf, dtype=np.int32)
        mesh.polygons.foreach_get("loop_total", totals)
        starts = np.empty(nf, dtype=np.int32)
        mesh.polygons.foreach_get("loop_start", starts)

        # ループが面の順に隙間なく並んでいるか。現在の Blender では常に
        # そうなるが、そこに寄りかかった書き方と、明示的に starts を使う
        # 書き方が混在していると、片方だけ間違う。判定はここ1か所で持つ
        expected = np.zeros(nf, dtype=np.int32)
        np.cumsum(totals[:-1], out=expected[1:])
        packed = bool(np.array_equal(starts, expected))

        # 各ループがどの面のものか
        face_ids = np.repeat(np.arange(nf, dtype=np.int32), totals)
        if packed:
            loop_poly = face_ids
        else:
            # 並びが飛んでいる場合は、面ごとの開始位置から書き戻す
            within = np.arange(nl, dtype=np.int64) - np.repeat(
                expected.astype(np.int64), totals)
            pos = np.repeat(starts.astype(np.int64), totals) + within
            loop_poly = np.empty(nl, dtype=np.int32)
            loop_poly[pos] = face_ids

        normals = np.empty(nf * 3, dtype=np.float32)
        mesh.polygons.foreach_get("normal", normals)
        normals = normals.reshape(nf, 3)

        self.area = np.empty(nf, dtype=np.float32)
        mesh.polygons.foreach_get("area", self.area)

        loop_vert = np.empty(nl, dtype=np.int32)
        mesh.loops.foreach_get("vertex_index", loop_vert)
        vco = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
        mesh.vertices.foreach_get("co", vco)
        vco = vco.reshape(-1, 3)

        # 退化面の法線を BMesh に合わせてゼロにする。面積ゼロだけを見ると
        # 足りない(面積 3e-08 の四角でも BMesh はゼロ法線を持つ実例あり)
        self._degenerate = _zero_normal_mask(mesh, totals, starts,
                                             loop_vert, vco)
        if self._degenerate.any():
            normals[self._degenerate] = 0.0
        # 面の中心は BMFace.calc_center_median() と同じ手順で出す。
        # polygon.center と比べると三角形で最下位1ビットずれることがある
        # (Blender 側は (a+b+c)/3、BMesh 側は「頂点を足してから 1/n 倍」で
        # 丸めが違う)。この座標は色ジッターのハッシュに入るので、
        # 1ビット違うだけで島の色が総入れ替えになる(実測: アウディの
        # 三角形 86枚中65枚がずれ、12メッシュの色が変わった)
        # 差が出るのは三角形だけ:
        #   四角  … Blender は (a+b+c+d)/4。1/4 は2の冪なので誤差なし
        #   n角形 … 足してから 1/n 倍。BMesh と同じ手順
        #   三角形… Blender は /3.0f、BMesh は ×(1.0f/3.0f) で丸めが違う
        # なので三角形だけ BMesh と同じ「足してから 1/3 倍」で作り直す
        self.center = np.empty(nf * 3, dtype=np.float32)
        mesh.polygons.foreach_get("center", self.center)
        self.center = self.center.reshape(nf, 3)

        other = totals != 4
        if other.any():
            idx = np.flatnonzero(other)
            st = starts[idx].astype(np.intp)
            tn = totals[idx]
            # ループ順に1つずつ足す。まとめて総和を取ると足す順序が変わって
            # 丸めがずれる(numpy の総和は対分割で足すため)
            acc = np.zeros((len(idx), 3), dtype=np.float32)
            for k in range(int(tn.max())):
                sel = tn > k
                acc[sel] += vco[loop_vert[st[sel] + k]]
            self.center[idx] = acc * (
                np.float32(1.0) / tn.astype(np.float32))[:, None]
        self.material = np.empty(nf, dtype=np.int32)
        mesh.polygons.foreach_get("material_index", self.material)

        self.sharp = np.zeros(ne, dtype=bool)
        self.seam = np.zeros(ne, dtype=bool)
        if ne:
            mesh.edges.foreach_get("use_edge_sharp", self.sharp)
            mesh.edges.foreach_get("use_seam", self.seam)

        # クリース。サブディビジョンで「丸めない」と作者が指定した辺。
        # 4.x 以降は属性に移り、しかも**使ったときだけ作られる**ので、
        # 無ければ全部ゼロ扱いでよい
        self.crease = np.zeros(ne, dtype=np.float32)
        if ne:
            attr = mesh.attributes.get("crease_edge")
            if attr is not None and attr.domain == 'EDGE':
                try:
                    attr.data.foreach_get("value", self.crease)
                except (TypeError, RuntimeError):
                    pass

        # --- 辺 -> 面2枚。ループを辺で並べ替えて、2回出てくる辺だけ拾う。
        # BMEdge.is_manifold は「面がちょうど2枚」と同義なので、
        # この判定がそのまま bmesh 版の分岐と一致する
        order = np.argsort(loop_edge, kind="stable")
        e_sorted = loop_edge[order]
        f_sorted = loop_poly[order]
        counts = np.bincount(e_sorted, minlength=ne)
        first = np.zeros(ne, dtype=np.int64)
        np.cumsum(counts[:-1], out=first[1:])
        self.two_face = counts == 2
        self.face_a = np.full(ne, -1, dtype=np.int32)
        self.face_b = np.full(ne, -1, dtype=np.int32)
        idx = first[self.two_face]
        self.face_a[self.two_face] = f_sorted[idx]
        self.face_b[self.two_face] = f_sorted[idx + 1]

        # 辺 -> それに接する全ての面(CSR)。島の隣接を出すときに要る。
        # 旧実装は edge.link_faces を素直に全部見ていたので、1本の辺に
        # 3枚以上ぶら下がる非多様体でも隣接が取れていた。面2枚だけを
        # 見ると、そこで隣接を取りこぼして色クラスが変わる(実測: 車や
        # 格納庫など21メッシュで mecha_color が変化した)
        self._inc_faces = f_sorted
        self._inc_first = first
        self._inc_count = counts

        # --- 二面角。BMEdge.calc_face_angle() は2枚の面法線のなす角を
        # Blender の angle_normalized_v3v3 で出す。acos(dot) と数学的には
        # 同じだが、退化面のゼロ法線に対する結果が違う(この式だと
        # 2*asin(0.5)=60度が返り、旧実装はその値で判定していた)ので
        # 同じ式を使う
        self.angle = np.full(ne, np.nan, dtype=np.float32)
        if self.two_face.any():
            n1 = normals[self.face_a[self.two_face]].astype(np.float64)
            n2 = normals[self.face_b[self.two_face]].astype(np.float64)
            d = np.einsum("ij,ij->i", n1, n2)
            half_pos = np.linalg.norm(n1 - n2, axis=1) * 0.5
            half_neg = np.linalg.norm(-n1 - n2, axis=1) * 0.5
            np.clip(half_pos, -1.0, 1.0, out=half_pos)
            np.clip(half_neg, -1.0, 1.0, out=half_neg)
            self.angle[self.two_face] = np.where(
                d >= 0.0,
                2.0 * np.arcsin(half_pos),
                np.pi - 2.0 * np.arcsin(half_neg))

        self.is_boundary = np.ones(ne, dtype=bool)
        self.labels = np.arange(nf, dtype=np.int32)
        self.islands = []
        self._island_of_face = None

    # ------------------------------------------------------------------
    def angle_samples_deg(self) -> list:
        """自動しきい値の判定に使う二面角(度)。面が2枚ある辺のぶんだけ。"""
        if not len(self.angle):
            return []
        a = self.angle[self.two_face]
        return np.degrees(a[~np.isnan(a)]).tolist()

    def mark_boundaries(self, threshold_rad: float, seam_boundaries: bool,
                        clear_sharps: bool) -> None:
        """どの辺が島境界かを決める。bmesh 版の判定順をそのまま写している。"""
        ne = self.n_edges
        if ne == 0:
            return
        b = np.ones(ne, dtype=bool)          # 既定は境界
        # 面が2枚ない辺・角度が出せない辺は常に境界のまま
        ok = self.two_face & ~np.isnan(self.angle)

        if seam_boundaries:
            # UVシームとマテリアル境界は角度に関係なく境界
            mat_diff = np.zeros(ne, dtype=bool)
            mat_diff[self.two_face] = (
                self.material[self.face_a[self.two_face]]
                != self.material[self.face_b[self.two_face]])
            ok &= ~(self.seam | mat_diff)

        if not clear_sharps:
            # アーティストの付けたシャープは尊重する(=常に境界)
            ok &= ~self.sharp

        b[ok] = self.angle[ok] > threshold_rad
        self.is_boundary = b

    def build_islands(self) -> None:
        """境界でない辺で面を繋いで島にする。昇順に整列した面番号の配列。"""
        nf = self.n_faces
        if nf == 0:
            self.islands = []
            return
        inner = self.two_face & ~self.is_boundary
        self.labels = connected_components(
            self.face_a[inner], self.face_b[inner], nf)
        # ラベル = 島内の最小面番号。昇順に並べれば bmesh 版の島順と一致する
        uniq, island_of_face = np.unique(self.labels, return_inverse=True)
        island_of_face = island_of_face.astype(np.int32)
        self._island_of_face = island_of_face
        order = np.argsort(island_of_face, kind="stable")
        counts = np.bincount(island_of_face, minlength=len(uniq))
        cuts = np.cumsum(counts)[:-1]
        self.islands = np.split(order.astype(np.int32), cuts)

    # ------------------------------------------------------------------
    def _pairs(self, mask: np.ndarray) -> np.ndarray:
        """mask の辺について、島同士の (i, j) 対を重複なしで返す。

        面がちょうど2枚の辺はベクトル化で一気に処理し、3枚以上ぶら下がる
        非多様体の辺だけ Python で総当たりする。後者は普通のモデルでは
        ごく少数なので、全体の速度には響かない。
        """
        io = self._island_of_face
        out = []

        sel2 = mask & self.two_face
        if sel2.any():
            a = io[self.face_a[sel2]]
            b = io[self.face_b[sel2]]
            diff = a != b
            if diff.any():
                a, b = a[diff], b[diff]
                out.append(np.stack([np.minimum(a, b), np.maximum(a, b)],
                                    axis=1))

        many = mask & (self._inc_count > 2)
        if many.any():
            first = self._inc_first
            count = self._inc_count
            faces = self._inc_faces
            extra = []
            for e in np.flatnonzero(many).tolist():
                s = int(first[e])
                isl = np.unique(io[faces[s:s + int(count[e])]])
                for x in range(len(isl)):
                    for y in range(x + 1, len(isl)):
                        extra.append((int(isl[x]), int(isl[y])))
            if extra:
                out.append(np.array(extra, dtype=np.int32))

        if not out:
            return np.empty((0, 2), dtype=np.int32)
        return np.unique(np.concatenate(out).astype(np.int32), axis=0)

    def island_adjacency(self, boundary_only: bool) -> list:
        """島の隣接リスト。boundary_only=True なら境界エッジ越しだけ見る。"""
        n = len(self.islands)
        neighbors = [set() for _ in range(n)]
        mask = self.is_boundary if boundary_only \
            else np.ones(self.n_edges, dtype=bool)
        for i, j in self._pairs(mask).tolist():
            neighbors[i].add(j)
            neighbors[j].add(i)
        return neighbors

    def set_islands(self, islands) -> None:
        """マージ後の島で置き換え、面→島の対応も作り直す。"""
        self.islands = islands
        io = np.empty(self.n_faces, dtype=np.int32)
        for i, faces in enumerate(islands):
            io[faces] = i
        self._island_of_face = io


# ルースパーツ同士の近接判定。隙間が「小さいほうの島の対角線」の
# この割合以内なら隣と見なす = ほぼ接している、とみなす範囲。
#
# 全体サイズ基準(2%)は駄目だった。同じ隙間でもモデルが小さいと繋がらず、
# 一辺1.8の立方体を2.2間隔で置くと1組も隣接にならなかった(t40)。
# かといって 0.5 まで広げると離れた島まで繋がり、隣接色距離の契約を
# 割った(既存の t14/t19 が落ちた)。0.2 はその間で、
#   隙間/自分の対角 = 0.13 の対を繋ぎ、0.29 の対は繋がない
# という実測の谷に置いている。離れている側はシルエット線が担う。
LOOSE_PROXIMITY_TOL = 0.2
# 総当たりの上限。これを超えたら諦める(線が出ないより遅いほうが困る)
LOOSE_PROXIMITY_MAX_ISLANDS = 1500
# 稜線の起伏を作るときの拡散回数の上限
MAX_RIDGE_ITERS = 400
# 稜線の起伏を弱める「向きのそろい」(均した法線の正規化前の長さ)の範囲。LO 以下で 0、HI 以上でそのまま
RIDGE_ALIGN_LO = 0.3
RIDGE_ALIGN_HI = 0.7


def add_loose_part_proximity(topo: MeshTopology, mesh, neighbors: list,
                             tol_frac: float = LOOSE_PROXIMITY_TOL,
                             max_islands: int = LOOSE_PROXIMITY_MAX_ISLANDS
                             ) -> int:
    """メッシュの辺で繋がっていない島同士を、近ければ隣として足す。

    島の隣接は境界エッジ越しにしか見ていない。別のルースパーツ
    (スザンヌの目、バラバラの文字)はメッシュの辺を共有しないので
    「隣接なし」と判定され、貪欲彩色が全部を同じクラスに置く。画面では
    重なって見えているのに境界に色差が生まれず、線が出ない。
    2026-08-09 の「違反0件」誤報の原因もこれ(CLAUDE.md)。

    オブジェクト単位では fp_part_tint がバウンディングボックスの近接で
    同じことをしている。ここは1つのメッシュの中のルースパーツに
    同じ考え方を持ち込む。足すのは**別パーツ同士**だけ。同じパーツの中は
    辺で繋がっているので既存の隣接判定で足りる。

    戻り値は足した隣接の本数。
    """
    n = len(topo.islands)
    nf = topo.n_faces
    if n < 2 or n > max_islands or nf == 0:
        return 0
    nv = len(mesh.vertices)
    ne = len(mesh.edges)
    nl = len(mesh.loops)
    if nv == 0 or ne == 0 or nl == 0:
        return 0

    # --- 面 -> ルースパーツ番号 ---
    ev = np.empty(ne * 2, dtype=np.int32)
    mesh.edges.foreach_get("vertices", ev)
    ev = ev.reshape(-1, 2)
    part_of_vert = connected_components(ev[:, 0], ev[:, 1], nv)

    loop_v = np.empty(nl, dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", loop_v)
    totals = np.empty(nf, dtype=np.int32)
    mesh.polygons.foreach_get("loop_total", totals)
    face_of_loop = np.repeat(np.arange(nf, dtype=np.int32), totals)

    io = topo._island_of_face
    isl_of_loop = io[face_of_loop]

    # 島 -> パーツ番号(島は必ず1つのパーツに収まる)
    part_of_island = np.zeros(n, dtype=np.int64)
    part_of_island[isl_of_loop] = part_of_vert[loop_v]
    if len(np.unique(part_of_island)) < 2:
        return 0

    # --- 島ごとのバウンディングボックス ---
    co = np.empty(nv * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", co)
    vco = co.reshape(-1, 3)[loop_v]
    lo = np.full((n, 3), np.inf, dtype=np.float32)
    hi = np.full((n, 3), -np.inf, dtype=np.float32)
    np.minimum.at(lo, isl_of_loop, vco)
    np.maximum.at(hi, isl_of_loop, vco)

    # 許容する隙間は**その2つの島自身の大きさ**を基準にする。
    #
    # 物体全体の 2% にしていたが、これだと同じ隙間でもモデルが小さいと
    # 繋がらない。実測: 一辺1.8の立方体3個を2.2間隔(隙間0.4)で並べると
    # 全体4.0の2% = 0.08 にしか届かず、1組も隣接にならなかった。
    # 「近いかどうか」は本来まわりの大きさに左右されないので、
    # 小さいほうの島の対角線に対する割合で見る
    size = np.linalg.norm(np.where(np.isfinite(hi - lo), hi - lo, 0.0), axis=1)

    # --- 別パーツ同士で、隙間が許容以内の対を拾う ---
    added = 0
    step = 256
    for s in range(0, n, step):
        e = min(s + step, n)
        gap = np.zeros((e - s, n), dtype=np.float32)
        for ax in range(3):
            d = np.maximum(lo[s:e, ax][:, None] - hi[None, :, ax],
                           lo[None, :, ax] - hi[s:e, ax][:, None])
            np.maximum(gap, d, out=gap)
        tol = tol_frac * np.minimum(size[s:e][:, None], size[None, :])
        near = gap <= tol
        near &= part_of_island[s:e][:, None] != part_of_island[None, :]
        for r, c in zip(*np.nonzero(near)):
            i, j = s + int(r), int(c)
            if j in neighbors[i]:
                continue
            neighbors[i].add(j)
            neighbors[j].add(i)
            added += 1
    # 対は既に1回しか数えていない(2周目は上の in 判定で弾かれる)
    return added


def ridge_residual(mesh, radius_frac: float):
    """法線から「その場所の大きな向き」を引いた残りを、角ごとに返す。

    島の切り方は面の縁でしか色を変えられないので、なめらかな出っ張り
    (まぶたの上の稜線など)に線が出せない。細分すると1つの60度の折れが
    4つの15度に割れて、辺ごとの二面角では拾えなくなるためでもある。

    法線そのものを色にすると今度は凸面が一様にしきい値を超えて真っ黒に
    潰れる。だから**引き算**する。

        m = 法線を距離 R ぶん均したもの   … その場所の大きな向き
        d = 法線 - m                      … 大きな向きからのズレだけ

    なめらかな凸面は 法線 ≒ m なので d ≒ 0 で、色が動かない。稜線だけが
    ズレを持つ。平らなパネル(メカ)でも d ≒ 0 なので、硬い形には何も
    足されない。形のほうが勝手に決めるので、モードの切り替えが要らない。

    均す回数は距離から出す。拡散が届く距離は およそ sqrt(回数) x 辺長
    なので、回数 = (目標距離 / 辺長)^2 なら面の細かさによらず同じ距離に
    なる。回数を固定にすると、粗いケージだけ頭全体が均されて稜線が消えた
    (実測: 8回固定でケージの眉が消滅)。

    戻り値は (loops, 3) の配列。値域は概ね ±0.5。
    """
    nv = len(mesh.vertices)
    nl = len(mesh.loops)
    ne = len(mesh.edges)
    if nv == 0 or nl == 0 or ne == 0 or radius_frac <= 0.0:
        return None

    co = np.empty(nv * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3).astype(np.float64)
    vn = np.empty(nv * 3, dtype=np.float32)
    mesh.vertices.foreach_get("normal", vn)
    vn = vn.reshape(-1, 3).astype(np.float64)
    ev = np.empty(ne * 2, dtype=np.int32)
    mesh.edges.foreach_get("vertices", ev)
    ev = ev.reshape(-1, 2)

    size = float(np.linalg.norm(co.max(axis=0) - co.min(axis=0)))
    el = np.linalg.norm(co[ev[:, 0]] - co[ev[:, 1]], axis=1)
    mean_edge = float(np.mean(el)) if len(el) else size
    iters = int(round((size * radius_frac / max(mean_edge, 1e-9)) ** 2))
    # 上限を置く。1回あたり全頂点を2度なめるので、細かいメッシュで
    # 回数が数千に膨らむと STEP1 が体感で止まる
    iters = min(iters, MAX_RIDGE_ITERS)
    if iters <= 0:
        return None

    a = ev[:, 0].astype(np.int64)
    b = ev[:, 1].astype(np.int64)
    deg = np.bincount(np.concatenate([a, b]), minlength=nv).astype(np.float64)
    deg[deg == 0] = 1.0
    den = (deg + 1.0)[:, None]
    m = vn.copy()
    for _ in range(iters):
        acc = m.copy()
        np.add.at(acc, a, m[b])
        np.add.at(acc, b, m[a])
        m = acc / den
    ln = np.linalg.norm(m, axis=1)
    # 細い所では起伏を弱める。均す距離が太さより大きいと(木を 1 つのメッシュにした物の枝)、
    # まわりの法線が打ち消し合って均した向きがでたらめになり、法線そのものが色に乗って枝の中が
    # 線で真っ黒に潰れた(european-maple)。正規化前の長さは「まわりの向きのそろい」で、平らな面や
    # 大きな凸面で 1 近く、細い筒で 0 近く
    align = np.clip((ln - RIDGE_ALIGN_LO) / (RIDGE_ALIGN_HI - RIDGE_ALIGN_LO), 0.0, 1.0)
    ln[ln < 1e-12] = 1.0
    m /= ln[:, None]

    d = np.clip((vn - m) * 0.5, -1.0, 1.0) * align[:, None]
    lv = np.empty(nl, dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", lv)
    return d[lv], iters


def merge_small_islands(topo: MeshTopology, min_area_pct: float) -> None:
    """面積がメッシュ全体の min_area_pct% 未満の島を隣の最大の島へ併合する。

    utils.merge_small_islands と同じ規則。違うのは面の持ち方(BMFace の
    リストではなく面番号の配列)と、隣接を numpy で作るところだけ。
    """
    islands = topo.islands
    if len(islands) <= 1:
        return
    areas = [float(topo.area[f].sum()) for f in islands]
    total = sum(areas)
    if total <= 0.0:
        return
    threshold = total * (min_area_pct / 100.0)

    neighbors = topo.island_adjacency(boundary_only=False)
    parent = list(range(len(islands)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    # 小さい島から順に、隣接する最大の島へ併合(決定論的)
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

    # ルート島の面を先頭に保ったまま組み立てる(代表面=色シードの安定性)
    merged = {}
    for i in range(len(islands)):
        if find(i) == i:
            merged[i] = [islands[i]]
    for i in range(len(islands)):
        r = find(i)
        if r != i:
            merged[r].append(islands[i])
    topo.set_islands([np.concatenate(merged[k]) for k in sorted(merged)])


# 葉を房にまとめる(手描き背景モード)。
#
# 葉カードは1枚ずつ別の島で、隣の葉と必ず違う色になるため、葉1枚ごとに
# 輪郭が出て遠くでは黒い塊になる。人が木を描くときは葉を1枚ずつ描かず、
# 房(かたまり)の輪郭を描く。小さい島を 3D 位置で k 房に分け、房を1つの
# 島として塗る。房の中には線が出ず、房と房の境と木の輪郭だけが残る。
#
# 実測(dev/note_assets/eval_tree_clumps.py、1080p):
#   カエデ(葉カード 46万島)  房4〜8 で「描いた木」になり、遠くも形が読める
#   ヤシ(小葉 3.2万島)       房1 が一番よい。房8 は葉を横に切る
#   針葉樹(5千島)            近くは整う。遠くはまだ黒い(枝の線と穴)
# 島の数だけで判定すると機関車のリベット(2万島)まで房になった(実測、
# 町のデモ)。葉カードの特徴を2つ足す(dev/note_assets/eval_foliage_signature.py):
#
#                  小さい島  面積比  面数中央  端の辺の割合
#   カエデ(葉)      46410    1.00      4         0.56
#   針葉樹(葉)       5437    1.00      1         1.00
#   ヘアカード        564    0.96      2         0.33
#   機関車(リベット) 20343    0.59     34         0.01
#   ランチア          210    0.19     20         0.10
#
# 葉カードは面数が少なく、辺のほとんどがメッシュの端(相手の面が無い)。
# リベットやボルトは閉じた立体で端が無い。ヘアカードは葉と同じ形なので
# 房になる(背景のキャラの髪が房になるのは許容)
FOLIAGE_MIN_ISLANDS = 200
FOLIAGE_SMALL_PCT = 1.0
FOLIAGE_MIN_AREA_FRAC = 0.5
FOLIAGE_MAX_FACES_MED = 4.0
FOLIAGE_MIN_OPEN_FRAC = 0.3


def _kmeans(pts: np.ndarray, k: int, seed: int, iters: int = 25):
    rng = np.random.default_rng(seed)
    k = max(1, min(k, len(pts)))
    ctr = [pts[rng.integers(len(pts))]]
    for _ in range(1, k):
        d = np.min(((pts[:, None, :] - np.asarray(ctr)[None, :, :]) ** 2).sum(-1),
                   axis=1).astype(np.float64)
        if d.sum() <= 0.0:
            break
        p = d / d.sum()
        ctr.append(pts[rng.choice(len(pts), p=p / p.sum())])
    ctr = np.asarray(ctr, dtype=np.float64)
    lab = np.zeros(len(pts), dtype=np.int64)
    for _ in range(iters):
        d = ((pts[:, None, :] - ctr[None, :, :]) ** 2).sum(-1)
        lab = d.argmin(axis=1)
        for j in range(len(ctr)):
            m = lab == j
            if m.any():
                ctr[j] = pts[m].mean(axis=0)
    return lab, len(ctr)


def foliage_signature(topo: MeshTopology, small, areas) -> dict:
    """小さい島が葉カードらしいかの特徴。

    面数(葉カードは 1〜2 面)と、島の辺のうちメッシュの端(相手の面が無い)
    の割合(葉カードはほぼ全部が端。ネジやリベットは閉じた立体で端が無い)。
    """
    islands = topo.islands
    total = float(areas.sum())
    io = topo._island_of_face
    n = len(islands)
    cnt = np.asarray([len(islands[i]) for i in small], dtype=np.float64)
    # 辺ごとに: 片面(端) / 両面が同じ島(内側) / 両面が別の島(境)。
    # 片面の辺は face_a/face_b が -1 なので、辺->面の CSR から取る
    two = topo.two_face
    one = np.nonzero(topo._inc_count == 1)[0]
    f_one = topo._inc_faces[topo._inc_first[one]]
    open_cnt = np.bincount(io[f_one], minlength=n).astype(np.float64)
    ib = io[topo.face_b[two]]
    ia2 = io[topo.face_a[two]]
    same = ia2 == ib
    inner = np.bincount(ia2[same], minlength=n).astype(np.float64)
    border = (np.bincount(ia2[~same], minlength=n)
              + np.bincount(ib[~same], minlength=n)).astype(np.float64)
    tot = open_cnt + inner + border
    open_frac = open_cnt[small] / np.maximum(tot[small], 1.0)
    return {"area_frac": float(areas[small].sum()) / total if total > 0 else 0.0,
            "faces_med": float(np.median(cnt)), "faces_p90": float(np.percentile(cnt, 90)),
            "open_med": float(np.median(open_frac)),
            "open_frac": float(open_cnt[small].sum() / max(tot[small].sum(), 1.0))}


def clump_small_islands(topo: MeshTopology, k: int, seed: int,
                        small_pct: float = FOLIAGE_SMALL_PCT,
                        min_islands: int = FOLIAGE_MIN_ISLANDS) -> int:
    """面積が small_pct% 未満の島を 3D 位置で k 房に分けて併合する。

    大きい島(幹・枝・建物)はそのまま。小さい島が min_islands 未満なら
    何もしない。戻り値は作った房の数(0 = 何もしなかった)。
    k=0 でも何もしない(= 従来と1ビットも変わらない)。
    """
    islands = topo.islands
    if k <= 0 or len(islands) < min_islands:
        return 0
    areas = np.asarray([float(topo.area[f].sum()) for f in islands])
    total = float(areas.sum())
    if total <= 0.0:
        return 0
    small = np.nonzero(areas < total * (small_pct / 100.0))[0]
    if len(small) < min_islands:
        return 0
    sig = foliage_signature(topo, small, areas)
    leafy = (sig["area_frac"] >= FOLIAGE_MIN_AREA_FRAC
             and sig["faces_med"] <= FOLIAGE_MAX_FACES_MED
             and sig["open_frac"] >= FOLIAGE_MIN_OPEN_FRAC)
    print(f"[FreePencil] {'葉' if leafy else '葉ではない'}: 小島{len(small)} "
          f"面積比{sig['area_frac']:.2f} 面数中央{sig['faces_med']:.0f} "
          f"端{sig['open_frac']:.2f}")
    if not leafy:
        return 0
    # 島の重心(面積で重み付け)。ローカル座標でよい(房分けは相対位置)
    pts = np.empty((len(small), 3), dtype=np.float64)
    for n, i in enumerate(small):
        f = islands[i]
        w = topo.area[f].astype(np.float64)
        ws = float(w.sum())
        pts[n] = (topo.center[f].astype(np.float64) * w[:, None]).sum(0) / ws \
            if ws > 0 else topo.center[f].mean(0)
    lab, kk = _kmeans(pts, k, seed)
    merged = []
    small_set = set(int(i) for i in small)
    for i in range(len(islands)):
        if i not in small_set:
            merged.append(islands[i])
    for j in range(kk):
        members = [islands[int(small[n])] for n in np.nonzero(lab == j)[0]]
        if members:
            # 代表面(色のシード)は面番号の一番小さい島の先頭に揃える
            members.sort(key=lambda a: int(a[0]))
            merged.append(np.concatenate(members))
    topo.set_islands(merged)
    return kk


# 遠い区画をまとめる(手描き背景、v2.8.3)。
#
# 遠くのビルの窓や帯は、どの仕上がりでも線が詰まって黒い縞の塊になった
# (精密と同じ。手描き背景の「奥ほど線を減らす」はしきい値を上げる仕組みで、
# 窓の色の段差はそれより強いので減らなかった。2 -> 4 にしても変わらず)。
# 人が遠景を描くときは窓を1つずつ描かず、輪郭と大きな帯だけを描く。
# 区画ごとに STEP0 のカメラから見た画面上の面積(出力の px^2)を出し、
# 小さすぎる区画を、残す区画の一番近い面へまとめる(色が同じになり線が消える)。
#
# 実測(dev/note_assets/far_lod_proto.py、大通り 1920x1080):
#   150px はほとんど効かない。500px で一番奥の高層が輪郭と数本の帯になり、
#   手前のビルは変わらない(島 44916 -> 5808)。
# 粗さは STEP0 のカメラで決まるので、カメラが動くなら動きの範囲で一番近い
# 位置を使う(呼ぶ側 vertex_color.far_lod_cameras)。
FAR_LOD_INSTANCES = 3     # 同じメッシュを使う物は、カメラに近い順にこの数だけ見る


def face_screen_area(topo: MeshTopology, mesh, matrices, cam_positions, fpx: float):
    """面ごとの、画面上の面積の最大値(出力の px^2)。

    面積(ワールド) x (焦点距離px / 距離)^2 x |cos(視線と法線)| を、
    渡された物(行列)とカメラ位置の全部で取り、一番大きく写る値を返す。
    """
    nf = topo.n_faces
    out = np.zeros(nf, dtype=np.float64)
    if nf == 0 or not matrices or len(cam_positions) == 0:
        return out
    nrm0 = np.empty(nf * 3, dtype=np.float32)
    mesh.polygons.foreach_get("normal", nrm0)
    nrm0 = nrm0.reshape(nf, 3).astype(np.float64)
    c0 = topo.center.astype(np.float64)
    a0 = topo.area.astype(np.float64)
    cams = np.asarray(cam_positions, dtype=np.float64).reshape(-1, 3)
    for M in matrices:
        M = np.asarray(M, dtype=np.float64)
        L = M[:3, :3]
        try:
            nrm = nrm0 @ np.linalg.inv(L)          # 法線は逆転置で運ぶ
        except np.linalg.LinAlgError:
            continue
        nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
        cw = c0 @ L.T + M[:3, 3]
        area = a0 * abs(np.linalg.det(L)) ** (2.0 / 3.0)
        for cp in cams:
            v = cw - cp
            d = np.maximum(np.linalg.norm(v, axis=1), 1e-3)
            cosv = np.abs((v / d[:, None] * nrm).sum(1))
            np.maximum(out, area * (fpx / d) ** 2 * np.maximum(cosv, 0.02), out=out)
    return out


def merge_far_islands(topo: MeshTopology, face_px, min_px: float, matrix=None) -> int:
    """画面上の面積が min_px 未満の区画を、残す区画の一番近い面へまとめる。

    残す区画が1つも無い(物全体が遠い)ときは、一番広い区画へ全部まとめる
    (物の輪郭だけが残る)。戻り値はまとめた区画の数。
    """
    islands = topo.islands
    n = len(islands)
    if n <= 1 or min_px <= 0.0:
        return 0
    face_px = np.asarray(face_px, dtype=np.float64)
    px = np.array([face_px[f].sum() for f in islands])
    keep = px >= min_px
    if keep.all():
        return 0
    if not keep.any():
        area = np.array([float(topo.area[f].sum()) for f in islands])
        big = int(np.argmax(area))
        topo.set_islands([np.concatenate([islands[big]] + [islands[i] for i in range(n) if i != big])])
        return n - 1
    from mathutils.kdtree import KDTree
    c = topo.center.astype(np.float64)
    if matrix is not None:
        M = np.asarray(matrix, dtype=np.float64)
        c = c @ M[:3, :3].T + M[:3, 3]
    keep_idx = np.flatnonzero(keep)
    kf = np.concatenate([islands[i] for i in keep_idx])
    owner = np.concatenate([np.full(len(islands[i]), i, dtype=np.int64) for i in keep_idx])
    tree = KDTree(len(kf))
    for k, f in enumerate(kf.tolist()):
        tree.insert(c[f].tolist(), k)
    tree.balance()
    target = {}
    for i in np.flatnonzero(~keep):
        ctr = c[islands[i]].mean(0)
        _, k, _ = tree.find(ctr.tolist())
        target.setdefault(int(owner[k]), []).append(i)
    merged = []
    for i in range(n):
        if keep[i]:
            # 代表面(先頭)を保つ: 残す区画の面を先頭に
            merged.append(np.concatenate([islands[i]] + [islands[j] for j in target.get(i, [])]))
    topo.set_islands(merged)
    return int((~keep).sum())
