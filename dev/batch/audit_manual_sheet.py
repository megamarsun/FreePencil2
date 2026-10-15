"""audit_manual.py の絵を並べる。行 = 仕上がり x プレビュー x 塗った種類、列 = base / 塗っただけ / STEP3 / STEP2+3。

  python audit_manual_sheet.py <dir>
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

D = Path(sys.argv[1])
FONT = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 15)
W, H = 320, 180
COLS = ["base", "paint", "s3", "s23"]
for preview in ("WHITE", "CEL"):
    rows = [(st, k) for st in ("PRECISE", "WEIGHTED", "BACKGROUND") for k in ("mask", "line", "mecha")]
    s = Image.new("RGB", (170 + W * 4, 22 + H * len(rows)), "white")
    d = ImageDraw.Draw(s)
    for c, n in enumerate(["STEP0 の後", "塗っただけ", "STEP3", "STEP2 -> STEP3"]):
        d.text((170 + c * W + 4, 2), n, fill="black", font=FONT)
    for r, (st, k) in enumerate(rows):
        d.text((4, 22 + r * H + 4), f"{st}\n{k}", fill="black", font=FONT)
        for c, col in enumerate(COLS):
            p = D / (f"{st}_{preview}_base.png" if col == "base" else f"{st}_{preview}_{k}_{col}.png")
            if not p.exists():
                continue
            im = Image.open(p).convert("RGBA").resize((W - 2, H - 2), Image.LANCZOS)
            bg = Image.new("RGBA", im.size, (200, 200, 200, 255))
            bg.alpha_composite(im)
            s.paste(bg.convert("RGB"), (170 + c * W, 22 + r * H))
    s.save(D / f"sheet_{preview}.png")
    print("sheet", D / f"sheet_{preview}.png")
