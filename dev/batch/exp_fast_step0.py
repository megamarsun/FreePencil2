"""試作: STEP0 を速くする(絵は変えない)。置き換えて作例調査を回す。

  blender -b --factory-startup --python exp_fast_step0.py -- <audit_v30_survey.py の引数>

戦車(42 万面)の STEP0 101.8 秒の内訳(prof_step0.py):
  稜線の起伏 ridge_residual 66.5 秒   うち np.add.at が 49.6 秒
  パレット作り build_palette   18.6 秒   同じ引数で何度も作り直している(84 回の呼び出しで 396 回)
置き換え:
  np.add.at -> np.bincount(重み付き)。足す順番だけが変わる(倍精度の丸めの差)
  build_palette -> 引数ごとに覚えておく。同じ引数なら同じ結果を返す関数なので、絵は 1 ビットも変わらない
"""
import functools
import runpy
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fp_batch  # noqa: E402

fp_batch.install_addon()
mi = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.mesh_islands"))
ut = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.utils"))


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
    dst = np.concatenate([a, b])            # 足し込む先
    src = np.concatenate([b, a])            # 足すもと
    m = vn.copy()
    for _ in range(iters):
        g = m[src]
        acc = np.empty_like(m)
        for k in range(3):
            acc[:, k] = m[:, k] + np.bincount(dst, weights=g[:, k], minlength=nv)
        m = acc / den
    ln = np.linalg.norm(m, axis=1)
    align = np.clip((ln - mi.RIDGE_ALIGN_LO) / (mi.RIDGE_ALIGN_HI - mi.RIDGE_ALIGN_LO), 0.0, 1.0)
    ln[ln < 1e-12] = 1.0
    m /= ln[:, None]
    d = np.clip((vn - m) * 0.5, -1.0, 1.0) * align[:, None]
    lv = np.empty(nl, dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", lv)
    return d[lv], iters


_build = ut.build_palette


@functools.lru_cache(maxsize=512)
def _build_cached(k, seed_int, luma_lo, luma_hi):
    cols, pmin, lmin = _build(k, seed_int, luma_lo=luma_lo, luma_hi=luma_hi)
    return tuple(cols), pmin, lmin


def build_palette(k, seed_int, luma_lo=0.25, luma_hi=0.75):
    cols, pmin, lmin = _build_cached(k, seed_int, luma_lo, luma_hi)
    return list(cols), pmin, lmin


mi.ridge_residual = ridge_residual
ut.build_palette = build_palette
fp_batch.install_addon = lambda: None          # 調査スクリプトに入れ直させない(置き換えが消える)
sys.argv = [str(HERE / "audit_v30_survey.py")] + sys.argv[sys.argv.index("--"):]
runpy.run_path(str(HERE / "audit_v30_survey.py"), run_name="__main__")
