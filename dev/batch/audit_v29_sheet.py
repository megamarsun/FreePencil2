"""audit_v29.py の絵を、仕上がりごとに 1 枚のシートへ並べる(透過は市松)。

  python audit_v29_sheet.py <dir>
行 = プレビュー x 太さ、列 = 背景 x 細線化。
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

D = Path(sys.argv[1])
FONT = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 16)
W, H = 360, 203
COLS = [("opaque", "ss"), ("opaque", "x1"), ("clear", "ss"), ("clear", "x1")]
ROWS = [(m, s) for m in ("NONE", "WHITE", "MONO_LIGHT", "CEL") for s in ("all1", "mixed")]


def checker(size):
    ch = Image.new("RGBA", size, (225, 225, 225, 255))
    d = ImageDraw.Draw(ch)
    for y in range(0, size[1], 12):
        for x in range(0, size[0], 12):
            if (x // 12 + y // 12) % 2:
                d.rectangle((x, y, x + 11, y + 11), fill=(175, 175, 175, 255))
    return ch


for style in ("PRECISE", "WEIGHTED", "BACKGROUND"):
    s = Image.new("RGB", (120 + W * len(COLS), 24 + H * len(ROWS)), "white")
    d = ImageDraw.Draw(s)
    for c, (bg, ss) in enumerate(COLS):
        d.text((120 + c * W + 6, 3), f"{bg} / {ss}", fill="black", font=FONT)
    for r, (mode, scale) in enumerate(ROWS):
        d.text((4, 24 + r * H + 6), f"{mode}\n{scale}", fill="black", font=FONT)
        for c, (bg, ss) in enumerate(COLS):
            p = D / f"{style}_{mode}_{scale}_{bg}_{ss}.png"
            if not p.exists():
                d.rectangle((120 + c * W, 24 + r * H, 120 + (c + 1) * W - 2, 24 + (r + 1) * H - 2), fill=(255, 0, 0))
                continue
            im = Image.open(p).convert("RGBA").resize((W - 2, H - 2), Image.LANCZOS)
            ch = checker(im.size)
            ch.alpha_composite(im)
            s.paste(ch.convert("RGB"), (120 + c * W, 24 + r * H))
    s.save(D / f"sheet_{style}.png")
    print("sheet", D / f"sheet_{style}.png")
