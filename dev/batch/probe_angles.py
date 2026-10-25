"""調べもの: 保存済みの作例の物ごとに、二面角の分布(自動しきい値が見る値)を書く。

  blender -b --factory-startup --python probe_angles.py -- a.blend b.blend ...
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bpy                        # noqa: E402
import numpy as np                # noqa: E402
import fp_batch                   # noqa: E402

fp_batch.install_addon()
mi = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.mesh_islands"))
for src in sys.argv[sys.argv.index("--") + 1:]:
    bpy.ops.wm.open_mainfile(filepath=src)
    seen = set()
    for o in bpy.context.scene.objects:
        if o.type != "MESH" or o.data in seen or not len(o.data.polygons):
            continue
        seen.add(o.data)
        t = mi.MeshTopology(o.data)
        a = np.asarray(t.angle_samples_deg(), dtype=np.float64)
        if not len(a):
            continue
        p = {q: float(np.percentile(a, q)) for q in (50, 90, 95, 99, 99.9)}
        print("@@@", Path(src).stem, o.name, len(o.data.polygons),
              " ".join(f"p{q}={v:.1f}" for q, v in p.items()), f"max={a.max():.1f}",
              f"p99/p50={p[99] / max(p[50], 1e-6):.2f}", "subsurf" if any(m.type == 'SUBSURF' for m in o.modifiers) else "")
