"""AI の窓口(ai.py)で手直しを試す。STEP0 済みの .blend を写して開き、手を順に当てて前後を撮る。

  blender -b --factory-startup --python manual_fix.py -- <STEP0 済み.blend> <出力フォルダ(絶対)> '<手の JSON>'

手の JSON: [["fade_lines", {"where": {"rect": [0.4, 0.1, 0.6, 0.3]}, "amount": 0.3}], ...]
空の [] なら撮るだけ(目盛り付きの絵で rect を読むため)。
出力: <出力>/fp_ai/before_{WHITE,CEL}.png(+ _grid)、after_{WHITE,CEL}.png、<名前>.blend
"""
import json
import shutil
import sys
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fp_batch  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
src, out, steps = Path(argv[0]), Path(argv[1]), json.loads(argv[2])
out.mkdir(parents=True, exist_ok=True)
dst = out / src.name
shutil.copy2(src, dst)
fp_batch.install_addon()
bpy.ops.wm.open_mainfile(filepath=str(dst))
fp = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.ai"))


def shoot(tag):
    for mode in ("WHITE", "CEL"):
        fp.preview(mode)
        r = fp.render(f"{tag}_{mode}", scale=1.0, grid=(mode == "WHITE"))
        print("@@ shot", r.get("image"))


shoot("before")
if steps:
    for name, kw in steps:
        r = getattr(fp, name)(**kw)
        print("@@ step", name, json.dumps(kw, ensure_ascii=False),
              "->", json.dumps({k: r.get(k) for k in ("done", "warnings")}, ensure_ascii=False))
    shoot("after")
    bpy.ops.wm.save_mainfile()
print("@@ done")
