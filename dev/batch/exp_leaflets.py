"""試作: 葉の材質の小さいパーツ(ヤシの小葉など、形のある葉)を材質ごとに 1 つの島にまとめて作例調査を回す。

  blender -b --factory-startup --python exp_leaflets.py -- <audit_v30_survey.py の引数>

葉の材質(名前が leaf_clump.LEAF_RE に合う)の島が LEAFLET_MIN 個以上あり、どれも面積が
全体の LEAFLET_PCT% 未満なら、それらを 1 つの島にする(同じ色になり、葉 1 枚ごとの線が消える)。
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
lc = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.leaf_clump"))
LEAFLET_MIN = int(os.environ.get("LEAFLET_MIN", "20"))
LEAFLET_PCT = float(os.environ.get("LEAFLET_PCT", "5"))

_init = mi.MeshTopology.__init__


MATS = {}                                       # MeshTopology は __slots__ なので外に持つ


def _init_keep(self, mesh, *a, **k):
    _init(self, mesh, *a, **k)
    MATS[id(self)] = [m.name if m else "" for m in mesh.materials]


mi.MeshTopology.__init__ = _init_keep
_merge = mi.merge_small_islands


def merge_and_leaflets(topo, pct):
    _merge(topo, pct)
    names = MATS.get(id(topo), [])
    leafy = {i for i, n in enumerate(names) if lc.LEAF_RE.search(n)}
    if not leafy:
        return
    isl = topo.islands
    area = np.asarray([float(topo.area[f].sum()) for f in isl])
    total = max(float(area.sum()), 1e-12)
    groups, keep = {}, []
    for i, f in enumerate(isl):
        m = int(np.bincount(topo.material[f]).argmax())
        if m in leafy and area[i] / total < LEAFLET_PCT / 100.0:
            groups.setdefault(m, []).append(f)
        else:
            keep.append(f)
    out = list(keep)
    for m, fs in groups.items():
        if len(fs) >= LEAFLET_MIN:
            fs.sort(key=lambda a: int(a[0]))
            out.append(np.concatenate(fs))
            print(f"[exp] 小葉 {len(fs)} 島 -> 1 島 ({names[m]})")
        else:
            out += fs
    if len(out) != len(isl):
        topo.set_islands(out)


mi.merge_small_islands = merge_and_leaflets
fp_batch.install_addon = lambda: None          # 調査スクリプトに入れ直させない(置き換えが消える)
sys.argv = [str(HERE / "audit_v30_survey.py")] + sys.argv[sys.argv.index("--"):]
runpy.run_path(str(HERE / "audit_v30_survey.py"), run_name="__main__")
