"""試し: 面の切れ目を縫う処理(mesh_islands.SPLIT_STITCH_DEG)を切って作例調査を回す(本体は書き換えない)。

  blender -b --factory-startup --python exp_no_stitch.py -- <audit_v30_survey.py の引数>

縫う処理を入れる前の絵と並べて、人が作ったモデル(MMD・車・機関車)が変わっていないかを見る。
"""
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fp_batch  # noqa: E402

fp_batch.install_addon()
mi = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.mesh_islands"))
mi._split_seams = lambda *a, **k: None
sys.argv = [sys.argv[0], "--"] + sys.argv[sys.argv.index("--") + 1:]
runpy.run_path(str(HERE / "audit_v30_survey.py"), run_name="__main__")
