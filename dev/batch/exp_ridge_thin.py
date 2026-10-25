"""試し: 稜線の起伏(mesh_islands.ridge_residual)を、細い所で弱めて作例調査を回す(中核は書き換えない)。

  blender -b --factory-startup --python exp_ridge_thin.py -- <audit_v30_survey.py の引数>

起伏は「法線 - 距離 R で均した法線」。R は物の大きさの 8% なので、木を 1 つのメッシュにした
物では枝の太さより R がずっと大きく、枝の周りで法線が打ち消し合って均した向きが 0 近くになる。
正規化するとでたらめな向きになり、法線そのものが色に乗って枝の中が線で真っ黒に潰れた
(european-maple。チャンネルを止めるとメカだけで黒くなる)。

均した法線の正規化前の長さ L は「周りの向きがそろっている度合い」。平らな面や大きな凸面で
1 近く、細い筒で 0 近く。起伏に clip((L - LO) / (HI - LO), 0, 1) を掛ける。
RIDGE_LO / RIDGE_HI(環境変数)で境を変えられる。
"""
import os
import runpy
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fp_batch  # noqa: E402

fp_batch.install_addon()
mi = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.mesh_islands"))
LO = float(os.environ.get("RIDGE_LO", "0.3"))
HI = float(os.environ.get("RIDGE_HI", "0.7"))


def ridge_residual(mesh, radius_frac: float):
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
    iters = min(iters, mi.MAX_RIDGE_ITERS)
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
    w = np.clip((ln - LO) / max(HI - LO, 1e-6), 0.0, 1.0)
    ln[ln < 1e-12] = 1.0
    m /= ln[:, None]
    d = np.clip((vn - m) * 0.5, -1.0, 1.0) * w[:, None]
    print(f"[exp] ridge thin-weight: L p5={np.percentile(ln, 5):.2f} p50={np.percentile(ln, 50):.2f} "
          f"弱めた頂点 {float((w < 1).mean()) * 100:.1f}%")
    lv = np.empty(nl, dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", lv)
    return d[lv], iters


mi.ridge_residual = ridge_residual
fp_batch.install_addon = lambda: None          # 調査スクリプトに入れ直させない(置き換えが消える)
sys.argv = [str(HERE / "audit_v30_survey.py")] + sys.argv[sys.argv.index("--"):]
runpy.run_path(str(HERE / "audit_v30_survey.py"), run_name="__main__")
