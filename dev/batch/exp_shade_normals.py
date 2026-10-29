"""実験: 法線をならす(大きな形にする)と、セルの影の形はどう変わるか(v3.0 の陰影の調査)。

  blender -b --factory-startup --python exp_shade_normals.py -- <作例の .blend> <出力フォルダ> [--iters 0,15,60] [--no-normalmap]

作例の .blend は audit_v30_survey.py が保存した物(STEP0 済み、プレビューはセル)。
メッシュごとに、同じ位置の頂点をまとめてから、隣の頂点の法線と平均する(ラプラシアンの
ならし)を iters 回くり返し、カスタム法線として入れてセルで撮る。0 はそのまま(比べる元)。
アドオンには手を入れない。出力: <出力>/cel_nNN.png
"""
import sys
from pathlib import Path

import bpy
import numpy as np

ARGV = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = Path(ARGV[0]), Path(ARGV[1])
ITERS = [int(v) for v in (ARGV[ARGV.index("--iters") + 1] if "--iters" in ARGV else "0,15,60").split(",")]
NO_NMAP = "--no-normalmap" in ARGV          # ノーマルマップを BSDF から外す(シワの絵が影を決めていないか見る)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fp_batch  # noqa: E402

fp_batch.install_addon()
bpy.ops.wm.open_mainfile(filepath=str(SRC))
sc = bpy.context.scene
OUT.mkdir(parents=True, exist_ok=True)
if NO_NMAP:
    for m in bpy.data.materials:
        if m.use_nodes:
            for n in m.node_tree.nodes:
                if n.type in ("NORMAL_MAP", "BUMP"):
                    for lk in list(n.outputs[0].links):
                        m.node_tree.links.remove(lk)

meshes = {o.data for o in sc.objects if o.type == "MESH" and not o.hide_render and len(o.data.polygons)}
base = {}
for me in meshes:
    n = len(me.vertices)
    co = np.empty(n * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    nr = np.empty(n * 3, np.float32)
    me.vertices.foreach_get("normal", nr)
    # 同じ位置の頂点(UV の切れ目で分かれた物)を 1 つにまとめる。まとめないと切れ目で法線がずれた
    key = np.round(co / max(np.ptp(co, axis=0).max(), 1e-6) * 1e5).astype(np.int64)
    _, weld = np.unique(key, axis=0, return_inverse=True)
    weld = weld.ravel()
    e = np.empty(len(me.edges) * 2, np.int64)
    me.edges.foreach_get("vertices", e)
    e = weld[e.reshape(-1, 2)]
    e = e[e[:, 0] != e[:, 1]]
    base[me] = (weld, e, nr.reshape(-1, 3))


def smooth(me, iters):
    weld, e, nr = base[me]
    m = weld.max() + 1
    acc = np.zeros((m, 3))
    np.add.at(acc, weld, nr)
    v = acc / np.maximum(np.linalg.norm(acc, axis=1, keepdims=True), 1e-9)
    for _ in range(iters):
        s = v.copy()
        np.add.at(s, e[:, 0], v[e[:, 1]])
        np.add.at(s, e[:, 1], v[e[:, 0]])
        v = s / np.maximum(np.linalg.norm(s, axis=1, keepdims=True), 1e-9)
    return v[weld]


sc.fp_preview_mode = "CEL"
for it in ITERS:
    for me in meshes:
        if it == 0:                       # そのまま(先頭で撮る)
            continue
        me.normals_split_custom_set_from_vertices(smooth(me, it).tolist())
        me.update()
    sc.render.filepath = str(OUT / f"cel_n{it:02d}.png")
    bpy.ops.render.render(write_still=True)
    print("@@ shot", it, flush=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"smoothed_n{ITERS[-1]:02d}.blend"))
print("@@ done", flush=True)
