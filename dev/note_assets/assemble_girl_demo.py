"""手作業デモの録画(gui_girl_demo.py の frames と frames.json)を、時刻どおりの 30fps の mp4 にする。

  python assemble_girl_demo.py <rec_dir> <out.mp4> [--width 1920] [--hold 1.5]

撮った時刻に合わせてコマを並べる(撮影の間隔はまちまちなので、各時刻で最後に撮れた絵を使う)。
画面は 16:9 に中央で切り、指定の幅に縮める。最後の絵を hold 秒止める。
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

REC = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
ARGV = sys.argv[3:]
W = int(ARGV[ARGV.index("--width") + 1]) if "--width" in ARGV else 1920
HOLD = float(ARGV[ARGV.index("--hold") + 1]) if "--hold" in ARGV else 1.5
FPS = 30
H = W * 9 // 16

import imageio_ffmpeg                              # noqa: E402
FF = imageio_ffmpeg.get_ffmpeg_exe()

log = json.loads((REC / "frames.json").read_text(encoding="utf-8"))
log.sort(key=lambda f: f["t"])
t0, t1 = log[0]["t"], log[-1]["t"] + HOLD
n = int((t1 - t0) * FPS)
tmp = Path(tempfile.mkdtemp(prefix="girl_demo_"))
cache = {}
j = 0
for k in range(n):
    t = t0 + k / FPS
    while j + 1 < len(log) and log[j + 1]["t"] <= t:
        j += 1
    i = log[j]["i"]
    if i not in cache:
        im = Image.open(REC / "frames" / f"{i:05d}.png").convert("RGB")
        w, h = im.size
        cw = min(w, int(h * 16 / 9))
        ch = min(h, int(cw * 9 / 16))
        x = (w - cw) // 2
        y = (h - ch) // 2
        im = im.crop((x, y, x + cw, y + ch)).resize((W, H), Image.LANCZOS)
        p = tmp / f"src_{i:05d}.png"
        im.save(p)
        cache = {i: p}                             # 直前の 1 枚だけ持つ
    (tmp / f"{k:05d}.png").write_bytes(cache[i].read_bytes())
OUT.parent.mkdir(parents=True, exist_ok=True)
subprocess.run([FF, "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(tmp / "%05d.png"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart",
                str(OUT)], check=True)
print(OUT, f"{n / FPS:.1f}s", f"{W}x{H}")
