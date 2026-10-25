"""調べもの: 作例調査と同じ置き方で STEP0 だけを cProfile にかけ、時間の内訳を書く。

  blender -b --factory-startup --python prof_step0.py -- --set holdout --only tank --out <abs dir>

<out>/<name>/prof.txt に、累積時間の上位と自分の時間の上位を書く。
"""
import cProfile
import io
import pstats
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fp_batch  # noqa: E402

fp_batch.install_addon()
ai = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.ai"))
_auto = ai.auto
OUTS = []


def auto_prof(*a, **k):
    pr = cProfile.Profile()
    pr.enable()
    try:
        return _auto(*a, **k)
    finally:
        pr.disable()
        s = io.StringIO()
        st = pstats.Stats(pr, stream=s)
        st.sort_stats("cumulative").print_stats(60)
        st.sort_stats("tottime").print_stats(40)
        OUTS.append(s.getvalue())


ai.auto = auto_prof
fp_batch.install_addon = lambda: None          # 調査スクリプトに入れ直させない(置き換えが消える)
args = sys.argv[sys.argv.index("--"):]
out = Path(args[args.index("--out") + 1])
sys.argv = [str(HERE / "audit_v30_survey.py")] + args
try:
    runpy.run_path(str(HERE / "audit_v30_survey.py"), run_name="__main__")
finally:
    out.mkdir(parents=True, exist_ok=True)
    (out / "prof.txt").write_text("\n\n".join(OUTS), encoding="utf-8")
