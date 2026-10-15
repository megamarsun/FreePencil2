"""峡谷のカメラ移動を、境界線が右から左へスライドして「つぶれる → 軽減」に切り替わる動画にする。

  python assemble_canyon_wipe.py --dir out/canyon2/move [--out out/canyon2/canyon_wipe.mp4]
        [--fps 24] [--hold-in 1.0] [--slide 4.0] [--hold-out 2.5] [--label-off "..."] [--label-on "..."]

--dir には r0/(つぶれ軽減 OFF)と r1/(ON)の連番 PNG(f0001.png ...)。
左が OFF、右が ON。最初は全面が OFF で、境界線が右端から左端へ動いて全面 ON になる。
出力は元の大きさの H.264 と、1080p の 2 本。フレームはパイプで ffmpeg へ渡す(一時ファイルなし)。
"""
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ARGV = sys.argv[1:]
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
HERE = Path(__file__).resolve().parent
D = Path(arg("--dir", str(HERE / "out" / "canyon2" / "move")))
OUT = Path(arg("--out", str(D.parent / "canyon_wipe.mp4")))
FPS = int(arg("--fps", "24"))
HOLD_IN = float(arg("--hold-in", "1.0"))
SLIDE = float(arg("--slide", "4.0"))
HOLD_OUT = float(arg("--hold-out", "2.5"))
LB_OFF = arg("--label-off", "つぶれ軽減 OFF")
LB_ON = arg("--label-on", "つぶれ軽減 ON(既定)")
POS = [tuple(float(v) for v in k.split(":")) for k in arg("--pos", "").split(",") if k]   # 境界線の位置(秒:画面幅の割合)
# 左右の連番を別々の場所から取る(片方だけ撮り直したとき)。無ければ --dir の r0/ と r1/
R0 = Path(arg("--r0", str(D / "r0")))
R1 = Path(arg("--r1", str(D / "r1")))
SPLIT_ONLY = "--labels-split-only" in ARGV      # 左右のラベルは画面が分かれている間だけ出す
CAP_FROM = float(arg("--caption-from", "0"))   # 字幕を出し始める秒
CAPTION = arg("--caption", "同じシーン・同じ設定。違いは「つぶれ軽減」だけ")
FONT = "C:/Windows/Fonts/meiryob.ttc"


def white(p):
    im = Image.open(p).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return bg.convert("RGB")


def smoother(t):
    t = min(1.0, max(0.0, t))
    return t * t * t * (t * (t * 6 - 15) + 10)


names = sorted(p.name for p in R1.glob("f*.png"))
n_total = len(names)
a0 = white(R1 / names[0])
W, H = a0.size
fs = max(24, H // 34)
font = ImageFont.truetype(FONT, fs)
ff = imageio_ffmpeg.get_ffmpeg_exe()
common = ["-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-framerate", str(FPS), "-i", "-"]
p_full = subprocess.Popen([ff, *common, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "14",
                           "-preset", "slow", str(OUT)], stdin=subprocess.PIPE,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
out_hd = OUT.with_name(OUT.stem + "_1080p.mp4")
p_hd = subprocess.Popen([ff, *common, "-vf", "scale=1920:1080:flags=lanczos", "-c:v", "libx264",
                         "-pix_fmt", "yuv420p", "-crf", "16", "-preset", "slow", str(out_hd)],
                        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def pill(d, xy, text, anchor):
    x, y = xy
    tw = d.textlength(text, font=font)
    pad = fs // 2
    w, h = tw + 2 * pad, fs + pad
    x0 = x if anchor == "l" else (x - w if anchor == "r" else x - w / 2)
    d.rounded_rectangle((x0, y, x0 + w, y + h), radius=h // 2, fill=(20, 20, 20), outline=(255, 255, 255), width=max(2, fs // 14))
    d.text((x0 + pad, y + pad // 3), text, fill=(255, 255, 255), font=font)


m = int(H * 0.03)
for k in range(n_total):
    t_sec = k / FPS
    if POS:                                       # 境界線の位置をキーで指定(秒:画面幅の割合)
        if t_sec <= POS[0][0]:
            fx = POS[0][1]
        elif t_sec >= POS[-1][0]:
            fx = POS[-1][1]
        else:
            j = max(i for i in range(len(POS) - 1) if POS[i][0] <= t_sec)
            u = smoother((t_sec - POS[j][0]) / (POS[j + 1][0] - POS[j][0]))
            fx = POS[j][1] + (POS[j + 1][1] - POS[j][1]) * u
        x = int(round(W * fx))
    else:
        prog = smoother((t_sec - HOLD_IN) / SLIDE)
        x = int(round(W * (1.0 - prog)))          # 境界線の位置(右端 -> 左端)
    on = white(R1 / names[k])
    if x <= 0:                                    # 全面が右(ON)。左の連番はこの間は無くてよい
        frame = on.copy()
    else:
        frame = white(R0 / names[k])
        if x < W:
            frame.paste(on.crop((x, 0, W, H)), (x, 0))
    d = ImageDraw.Draw(frame)
    if 0 < x < W:
        # 縦線だらけの絵に溶けないよう、太い 3 層(黒 / 白 / 橙)にする
        bk = max(8, H // 80)               # 黒い帯の半幅(明るい面で見える)
        wh = max(6, H // 110)              # 白い帯の半幅(暗い面で見える)
        og = max(3, H // 220)              # 橙の芯の半幅(白黒の絵の中で目を引く)
        d.rectangle((x - bk, 0, x + bk, H), fill=(20, 20, 20))
        d.rectangle((x - wh, 0, x + wh, H), fill=(255, 255, 255))
        d.rectangle((x - og, 0, x + og, H), fill=(255, 106, 0))
        r = H // 20
        cy = H // 2
        d.ellipse((x - r - 6, cy - r - 6, x + r + 6, cy + r + 6), fill=(20, 20, 20))
        d.ellipse((x - r, cy - r, x + r, cy + r), fill=(255, 106, 0), outline=(255, 255, 255), width=max(4, H // 360))
        s = r * 0.42
        d.polygon([(x - r * 0.25, cy), (x - r * 0.25 - s, cy - s * 0.8), (x - r * 0.25 - s, cy + s * 0.8)], fill=(255, 255, 255))
        d.polygon([(x + r * 0.25, cy), (x + r * 0.25 + s, cy - s * 0.8), (x + r * 0.25 + s, cy + s * 0.8)], fill=(255, 255, 255))
    split = 0 < x < W
    if x > W * 0.18 and (split or not SPLIT_ONLY):
        pill(d, (m, m), LB_OFF, "l")
    if W - x > W * 0.18 and (split or not SPLIT_ONLY):
        pill(d, (W - m, m), LB_ON, "r")
    if CAPTION and t_sec >= CAP_FROM:
        pill(d, (W // 2, H - m - int(fs * 1.6)), CAPTION, "c")
    raw = np.asarray(frame, dtype=np.uint8).tobytes()
    p_full.stdin.write(raw)
    p_hd.stdin.write(raw)
for p in (p_full, p_hd):
    p.stdin.close()
    p.wait()
print("video:", OUT, n_total, "frames", f"{W}x{H}")
print("1080p:", out_hd)
