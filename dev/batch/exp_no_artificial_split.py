"""試し: 「一様に滑らかな物に分割線を人工で作る」枝を止めて作例調査を回す(中核は書き換えない)。

  blender -b --factory-startup --python exp_no_artificial_split.py -- <audit_v30_survey.py の引数>

utils.choose_auto_threshold の最後の枝(p50 x 0.95)だけを 60 度に置き換える。
SMOOTH_ONLY=1 なら、面の 8 割以上がスムーズの物だけ置き換える(物は vertex_color の呼び出しから拾う)。
"""
import os
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fp_batch  # noqa: E402

fp_batch.install_addon()
utils = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.utils"))
vc = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.vertex_color"))
orig = utils.choose_auto_threshold
SMOOTH_ONLY = os.environ.get("SMOOTH_ONLY") == "1"
CUR = {"obj": None}


def patched(angles_deg, has_armature=False, many_parts=False, has_subsurf=False, split_floor=None):
    deg, merge = orig(angles_deg, has_armature=has_armature, many_parts=many_parts,
                      has_subsurf=has_subsurf, split_floor=split_floor)
    if deg < 59.0 and not has_armature and not many_parts and not has_subsurf:
        import bpy
        o = bpy.data.objects.get(CUR["obj"] or "")
        smooth = True
        if SMOOTH_ONLY and o is not None and o.type == "MESH" and len(o.data.polygons):
            import numpy as np
            sm = np.empty(len(o.data.polygons), dtype=bool)
            o.data.polygons.foreach_get("use_smooth", sm)
            smooth = sm.mean() >= 0.8
        print(f"[exp] artificial split {deg:.1f} -> {'60' if smooth else 'keep'} "
              f"({o.name if o else '?'})")
        if smooth:
            return 60.0, merge
    return deg, merge


utils.choose_auto_threshold = patched
# 物を拾う: vertex_color が物ごとに呼ぶ関数を包む
for name in dir(vc):
    fn = getattr(vc, name)
    if callable(fn) and getattr(fn, "__module__", "") == vc.__name__ and "obj" in getattr(
            getattr(fn, "__code__", None), "co_varnames", ())[:3]:
        def wrap(f):
            def inner(*a, **k):
                for x in list(a) + list(k.values()):
                    if getattr(x, "type", None) == "MESH" and hasattr(x, "data"):
                        CUR["obj"] = x.name
                        break
                return f(*a, **k)
            return inner
        setattr(vc, name, wrap(fn))
fp_batch.install_addon = lambda: None          # 調査スクリプトに入れ直させない(置き換えが消える)
sys.argv = [str(HERE / "audit_v30_survey.py")] + sys.argv[sys.argv.index("--"):]
runpy.run_path(str(HERE / "audit_v30_survey.py"), run_name="__main__")
