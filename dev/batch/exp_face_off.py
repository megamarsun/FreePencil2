"""前後比べ用: 顔のボーンを頭の色に寄せる(vertex_color.head_family)のを止めて作例調査を回す。

  blender -b --factory-startup --python exp_face_off.py -- <audit_v30_survey.py の引数>
"""
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fp_batch  # noqa: E402

fp_batch.install_addon()
vc = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.vertex_color"))
vc.head_family = lambda *a: (set(), None)
fp_batch.install_addon = lambda: None          # 調査スクリプトに入れ直させない(置き換えが消える)
sys.argv = [str(HERE / "audit_v30_survey.py")] + sys.argv[sys.argv.index("--"):]
runpy.run_path(str(HERE / "audit_v30_survey.py"), run_name="__main__")
