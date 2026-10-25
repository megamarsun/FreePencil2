"""試し: 稜線の起伏を止めて作例調査を回す(本体は書き換えない)。

  blender -b --factory-startup --python exp_no_ridge.py -- <audit_v30_survey.py の引数>

standing-cool-ba(写真から作った人のスキャン): 上着に黒いしみが出た。面がでこぼこのスキャンで、
稜線の起伏が島の中の色を大きく動かしているのかを見る。
"""
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fp_batch  # noqa: E402

fp_batch.install_addon()
mi = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.mesh_islands"))
mi.ridge_residual = lambda *a, **k: None
sys.argv = [sys.argv[0], "--"] + sys.argv[sys.argv.index("--") + 1:]
runpy.run_path(str(HERE / "audit_v30_survey.py"), run_name="__main__")
