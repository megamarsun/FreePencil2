"""試し: 画面で小さすぎる区画を精密でもまとめる(vertex_color.PRECISE_TINY_PX)。

  TINY_PX=40 blender -b --factory-startup --python exp_tiny_px.py -- <audit_v30_survey.py の引数>

AI のメカ(walker_robot)の黒い点と塊は、画面で数 px の破片の縁だった。角の切れ目をつないで
まとめる案では、mech_tank や spaceship の角の線まで消えた。
"""
import os
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fp_batch  # noqa: E402

fp_batch.install_addon()
vc = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.vertex_color"))
vc.PRECISE_TINY_PX = float(os.environ.get("TINY_PX", "40"))
print("[exp] PRECISE_TINY_PX", vc.PRECISE_TINY_PX)
sys.argv = [sys.argv[0], "--"] + sys.argv[sys.argv.index("--") + 1:]
runpy.run_path(str(HERE / "audit_v30_survey.py"), run_name="__main__")
