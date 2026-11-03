"""プリビズの通しを連番 JPEG に撮る(ワークベンチ = ビューポートのソリッド表示と同じ絵)。ショット名とコマ番号を焼き込む。

  blender -b <city.blend> --python playblast.py -- <出力フォルダ> [--start 1] [--end 5400] [--res 960]

カメラはマーカーで切り替わる。何本かに分けて同時に回し、つなぐのは ffmpeg(imageio_ffmpeg の物)で。
"""
import sys
from pathlib import Path

import bpy

ARGV = sys.argv[sys.argv.index("--") + 1:]
OUT = Path(ARGV[0])
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d   # noqa: E731
RES = int(arg("--res", "960"))
OUT.mkdir(parents=True, exist_ok=True)
sc = bpy.context.scene
r = sc.render
sc.frame_start = int(arg("--start", "1"))
sc.frame_end = int(arg("--end", "5400"))
r.resolution_x, r.resolution_y = RES, RES * 9 // 16
r.resolution_percentage = 100
r.image_settings.file_format = "JPEG"
r.image_settings.quality = 92
r.filepath = str(OUT / "f_")
r.use_file_extension = True
r.use_overwrite = False          # 止まったら続きから
r.use_stamp = True
for k in ("date", "time", "render_time", "filename", "scene", "memory", "hostname", "lens",
          "frame_range", "camera", "sequencer_strip", "note"):
    setattr(r, "use_stamp_" + k, False)
r.use_stamp_frame = True
r.use_stamp_marker = True
r.stamp_font_size = 16
r.stamp_background = (0, 0, 0, 0.55)
bpy.ops.render.render(animation=True)
print("@@ playblast", sc.frame_start, sc.frame_end, OUT, flush=True)
