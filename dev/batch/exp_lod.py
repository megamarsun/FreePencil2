"""試し: 同じ場所に重ねて置いてある LOD(_LOD1, _LOD2 ...)を、いちばん細かい LOD0 だけ残して隠してから STEP0。

  blender -b --factory-startup --python exp_lod.py -- <audit_v30_survey.py の引数>

dirty_football: LOD0〜3 の 4 つが全部見えていて、重なった面が交互に顔を出し、ボール一面に
ぎざぎざの線が出た。
"""
import re
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bpy  # noqa: E402
import fp_batch  # noqa: E402

fp_batch.install_addon()
ai = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.ai"))
orig = ai.auto
LOD = re.compile(r"[_.\-]LOD(\d+)", re.I)


def patched(ctx, names, *a, **k):
    keep = []
    for n in names:
        mt = LOD.search(n)
        if mt and int(mt.group(1)) > 0:
            bpy.data.objects[n].hide_render = True
            bpy.data.objects[n].hide_viewport = True
            print(f"[exp] hide LOD: {n}")
        else:
            keep.append(n)
    return orig(ctx, keep, *a, **k)


ai.auto = patched
sys.argv = [sys.argv[0], "--"] + sys.argv[sys.argv.index("--") + 1:]
runpy.run_path(str(HERE / "audit_v30_survey.py"), run_name="__main__")
