"""試作 A案: 角度が全体に一様な滑らかな物(卵)は、分割線を人工的に作らない。作例調査を回す。

  blender -b --factory-startup --python exp_uniform.py -- <audit_v30_survey.py の引数>

choose_auto_threshold の最後の枝(一様に滑らか → p50 x 0.95 で人工分割)に落ちる物のうち、
p99 / p50 が UNIFORM_RATIO 未満(角度がどこでもほぼ同じ)なら 60 度にする(分割しない)。
実測: 卵 1.8、バスケットボール 5.8(溝)、靴 11.8、包丁 12.2
"""
import os
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fp_batch  # noqa: E402

fp_batch.install_addon()
ut = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.utils"))
UNIFORM_RATIO = float(os.environ.get("UNIFORM_RATIO", "3.0"))
_choose = ut.choose_auto_threshold


def choose(angles_deg, has_armature=False, many_parts=False, has_subsurf=False, split_floor=None):
    got = _choose(angles_deg, has_armature, many_parts, has_subsurf, split_floor)
    if not angles_deg or has_armature or many_parts or has_subsurf:
        return got
    s = sorted(angles_deg)
    n = len(s)

    def pct(p):
        return s[min(n - 1, int(n * p / 100))]
    if pct(90) > 100.0 or pct(95) > 75.0 or pct(99) > 45.0:
        return got
    if pct(99) < UNIFORM_RATIO * max(pct(50), 1e-6):
        print(f"[exp] 一様に滑らか(p99/p50 {pct(99) / max(pct(50), 1e-6):.2f}): 分割しない")
        return 60.0, None
    return got


ut.choose_auto_threshold = choose
fp_batch.install_addon = lambda: None          # 調査スクリプトに入れ直させない(置き換えが消える)
sys.argv = [str(HERE / "audit_v30_survey.py")] + sys.argv[sys.argv.index("--"):]
runpy.run_path(str(HERE / "audit_v30_survey.py"), run_name="__main__")
