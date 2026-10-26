"""試し: でこぼこの面に散る点(稜線の起伏)を、小さすぎる凹凸だけ落とす。

  RIDGE=off      blender -b --factory-startup --python exp_ridge_band.py -- <audit_v30_survey.py の引数>
  RIDGE=band:0.01 ...   法線を物の大きさの 1% ぶん先に均してから起伏を取る(小さな凹凸を落とす)

Scenario の dragon の肌は 3D でも小さなくぼみがあり、稜線の起伏がそれを全部拾って汚れのような
点になった。起伏は「法線 - 遠くまで均した法線」なので、細かい凹凸ほど必ず残る(高い周波数だけ通す)。
先に近くだけ均した法線から引けば、中くらいの稜線(まぶた・眉)だけが残るはず。
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
MODE = os.environ.get("RIDGE", "off")
print("[exp] RIDGE", MODE)
orig = mi.ridge_residual


def smooth(m, src, dst, den, nv, iters):
    for _ in range(iters):
        g = m[src]
        acc = np.empty_like(m)
        for k in range(3):
            acc[:, k] = m[:, k] + np.bincount(dst, weights=g[:, k], minlength=nv)
        m = acc / den
    return m


def banded(mesh, radius_frac, rep=None):
    small = float(MODE.split(":")[1])
    nv, nl, ne = len(mesh.vertices), len(mesh.loops), len(mesh.edges)
    if nv == 0 or nl == 0 or ne == 0 or radius_frac <= 0.0:
        return None
    co = np.empty(nv * 3, np.float32); mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3).astype(np.float64)
    vn = np.empty(nv * 3, np.float32); mesh.vertices.foreach_get("normal", vn)
    vn = vn.reshape(-1, 3).astype(np.float64)
    ev = np.empty(ne * 2, np.int32); mesh.edges.foreach_get("vertices", ev)
    ev = ev.reshape(-1, 2)
    if rep is not None:
        s = np.empty_like(vn)
        for k in range(3):
            s[:, k] = np.bincount(rep, weights=vn[:, k], minlength=nv)
        ls = np.linalg.norm(s, axis=1); ls[ls < 1e-12] = 1.0
        vn = s / ls[:, None]
        ev = rep[ev]
        ev = ev[ev[:, 0] != ev[:, 1]]
        ev = np.unique(np.sort(ev, axis=1), axis=0)
        if not len(ev):
            return None
    size = float(np.linalg.norm(co.max(0) - co.min(0)))
    el = np.linalg.norm(co[ev[:, 0]] - co[ev[:, 1]], axis=1)
    mean_edge = float(np.mean(el)) if len(el) else size
    iters = min(int(round((size * radius_frac / max(mean_edge, 1e-9)) ** 2)), mi.MAX_RIDGE_ITERS)
    it_s = min(int(round((size * small / max(mean_edge, 1e-9)) ** 2)), mi.MAX_RIDGE_ITERS)
    if iters <= 0:
        return None
    a, b = ev[:, 0].astype(np.int64), ev[:, 1].astype(np.int64)
    deg = np.bincount(np.concatenate([a, b]), minlength=nv).astype(np.float64); deg[deg == 0] = 1.0
    den = (deg + 1.0)[:, None]
    dst, src = np.concatenate([a, b]), np.concatenate([b, a])
    m = smooth(vn.copy(), src, dst, den, nv, iters)
    ln = np.linalg.norm(m, axis=1)
    align = np.clip((ln - mi.RIDGE_ALIGN_LO) / (mi.RIDGE_ALIGN_HI - mi.RIDGE_ALIGN_LO), 0.0, 1.0)
    ln[ln < 1e-12] = 1.0
    m /= ln[:, None]
    ns = smooth(vn.copy(), src, dst, den, nv, it_s)
    l2 = np.linalg.norm(ns, axis=1); l2[l2 < 1e-12] = 1.0
    ns /= l2[:, None]
    print(f"[exp] band iters {iters} small {it_s} (edge {mean_edge / size:.5f} of size)")
    d = np.clip((ns - m) * 0.5, -1.0, 1.0) * align[:, None]
    lv = np.empty(nl, np.int32); mesh.loops.foreach_get("vertex_index", lv)
    if rep is not None:
        lv = rep[lv]
    return d[lv], iters


if MODE == "off":
    mi.ridge_residual = lambda *a, **k: None
elif MODE.startswith("band:"):
    mi.ridge_residual = banded
sys.argv = [sys.argv[0], "--"] + sys.argv[sys.argv.index("--") + 1:]
runpy.run_path(str(HERE / "audit_v30_survey.py"), run_name="__main__")
