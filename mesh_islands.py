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


class MeshTopology:
    """1つのメッシュから、島の判定に要るものを全部配列で持つ。"""

    __slots__ = ("n_faces", "n_edges", "face_a", "face_b", "two_face",
                 "angle", "sharp", "seam", "material", "area", "center",
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
