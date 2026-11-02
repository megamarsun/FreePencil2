"""プリビズの .blend から、ショットのカメラで要所のコマを撮る(ワークベンチ = ビューポートのソリッド表示と同じ絵)。

  blender -b <city.blend> --python snap_shots.py -- <出力フォルダ> [--frames 150,420,...] [--res 1280] [--every 0]

--frames を省くと各ショットの頭・真ん中・終わり。--every N はその間隔で全部(通しの確認用)。
"""
import sys
from pathlib import Path

import bpy

ARGV = sys.argv[sys.argv.index("--") + 1:]
OUT = Path(ARGV[0])
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d   # noqa: E731
RES = int(arg("--res", "1280"))
EVERY = int(arg("--every", "0"))
OUT.mkdir(parents=True, exist_ok=True)
sc = bpy.context.scene
mks = sorted([m for m in sc.timeline_markers if m.camera], key=lambda m: m.frame)
ends = [m.frame for m in mks[1:]] + [sc.frame_end + 1]
if arg("--frames"):
    frames = [int(x) for x in arg("--frames").split(",")]
elif EVERY:
    frames = list(range(sc.frame_start, sc.frame_end + 1, EVERY))
else:
    frames = []
    for m, e in zip(mks, ends):
        frames += [m.frame + 5, (m.frame + e) // 2, e - 6]
sc.render.resolution_x, sc.render.resolution_y = RES, RES * 9 // 16
sc.render.resolution_percentage = 100
sc.render.image_settings.file_format = "PNG"
for f in frames:
    m = max((m for m in mks if m.frame <= f), key=lambda m: m.frame)
    sc.camera = m.camera
    sc.frame_set(f)
    sc.render.filepath = str(OUT / f"{m.name}_{f:04d}.png")
    bpy.ops.render.render(write_still=True)
    print("@@ snap", sc.render.filepath, flush=True)
