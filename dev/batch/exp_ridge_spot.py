"""試し: 稜線の起伏のうち、画面で小さな「かたまり」だけを消す(点を消して線は残す)。

  SPOT_T=0.06 SPOT_PX=12 blender -b --factory-startup --python exp_ridge_spot.py -- <audit_v30_survey.py の引数>

起伏を先に均す案(exp_ridge_band.py)は、ドラゴンの点は消えたが、蜘蛛ロボの甲羅の角や馬の首の
飾りの線まで消えた。均すと小さい物だけでなく鋭い物も弱まるため。
ここでは起伏の強い頂点(|d| > SPOT_T)をつながりで「かたまり」に分け、外接箱の対角が STEP0 の
カメラで SPOT_PX(横 1920 基準)未満のかたまりだけ起伏を 0 にする。長い線は長いので残る。
"""
import os
import runpy
import sys
from pathlib import Path

import bpy
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fp_batch  # noqa: E402

fp_batch.install_addon()
mi = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.mesh_islands"))
vc = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.vertex_color"))
T = float(os.environ.get("SPOT_T", "0.06"))
PX = float(os.environ.get("SPOT_PX", "12"))
SMALL = float(os.environ.get("SPOT_SMALL", "0.003"))
print("[exp] SPOT_T", T, "SPOT_PX", PX)


def smooth(m, src, dst, den, nv, iters):
    for _ in range(iters):
        g = m[src]
        acc = np.empty_like(m)
        for k in range(m.shape[1]):
            acc[:, k] = m[:, k] + np.bincount(dst, weights=g[:, k], minlength=nv)
        m = acc / den
    return m


def components(nv, a, b):
    lab = np.arange(nv)
    while True:
        lo = np.minimum(lab[a], lab[b])
        new = lab.copy()
        np.minimum.at(new, a, lo)
        np.minimum.at(new, b, lo)
        new = new[new]
        new = new[new]
        if np.array_equal(new, lab):
            return lab
        lab = new


def spot(mesh, radius_frac, rep=None):
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
    # --- 細かい起伏のかたまりのうち、画面で小さい物だけ均した法線に置き換える ---
    it_s = min(int(round((size * SMALL / max(mean_edge, 1e-9)) ** 2)), mi.MAX_RIDGE_ITERS)
    scene = bpy.context.scene
    obj = next((o for o in scene.objects if o.type == 'MESH' and o.data == mesh), None)
    cams = vc.far_lod_cameras(scene)
    use = vn
    if it_s > 0 and obj is not None and cams is not None:
        ns = smooth(vn.copy(), src, dst, den, nv, it_s)
        l2 = np.linalg.norm(ns, axis=1); l2[l2 < 1e-12] = 1.0
        ns /= l2[:, None]
        M = np.asarray(obj.matrix_world, dtype=np.float64)
        cw = co @ M[:3, :3].T + M[:3, 3]
        hf = np.linalg.norm(vn - ns, axis=1)
        strong = hf > T
        e_ok = strong[a] & strong[b]
        lab = components(nv, a[e_ok], b[e_ok])
        idx = np.flatnonzero(strong)
        if len(idx):
            u, inv = np.unique(lab[idx], return_inverse=True)
            lo = np.full((len(u), 3), np.inf); hi = np.full((len(u), 3), -np.inf)
            np.minimum.at(lo, inv, cw[idx]); np.maximum.at(hi, inv, cw[idx])
            ctr = (lo + hi) * 0.5
            cp = np.asarray(cams[0], dtype=np.float64).reshape(-1, 3)
            dist = np.min(np.linalg.norm(ctr[:, None, :] - cp[None], axis=2), axis=1)
            ext = np.linalg.norm(hi - lo, axis=1) * float(cams[1]) / np.maximum(dist, 1e-3)
            drop_c = ext < PX
            drop = np.zeros(nv, bool)
            drop[idx[drop_c[inv]]] = True
            w = smooth(drop.astype(np.float64)[:, None], src, dst, den, nv, 2)
            w[drop] = 1.0
            use = vn * (1.0 - w) + ns * w
            print(f"[exp] spot '{obj.name}': small {it_s} strong {len(idx)} / {nv}, clumps {len(u)}, "
                  f"dropped {int(drop_c.sum())} ({int(drop.sum())} verts)")
    d = np.clip((use - m) * 0.5, -1.0, 1.0) * align[:, None]
    lv = np.empty(nl, np.int32); mesh.loops.foreach_get("vertex_index", lv)
    if rep is not None:
        lv = rep[lv]
    return d[lv], iters


mi.ridge_residual = spot
sys.argv = [sys.argv[0], "--"] + sys.argv[sys.argv.index("--") + 1:]
runpy.run_path(str(HERE / "audit_v30_survey.py"), run_name="__main__")
