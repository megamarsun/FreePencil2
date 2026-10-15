"""audit_texture.py の絵を並べる。  python audit_texture_sheet.py <dir>"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
D = Path(sys.argv[1])
FONT = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 15)
W, H = 320, 180
cols = ["0_step0", "1_plugged", "2_step3", "3_step23", "4_cel", "5_step0_again"]
s = Image.new("RGB", (130 + W * len(cols), 22 + H * 4), "white")
d = ImageDraw.Draw(s)
for c, n in enumerate(cols):
    d.text((130 + c * W + 4, 2), n, fill="black", font=FONT)
for r, st in enumerate(("PRECISE", "WEIGHTED", "BACKGROUND", "ref")):
    d.text((4, 22 + r * H + 4), st, fill="black", font=FONT)
    for c, n in enumerate(cols):
        p = D / (f"{st}_{n}.png" if st != "ref" else ("ref_texture.png" if c == 0 else "_none.png"))
        if not p.exists():
            continue
        im = Image.open(p).convert("RGBA").resize((W - 2, H - 2), Image.LANCZOS)
        bg = Image.new("RGBA", im.size, (200, 200, 200, 255))
        bg.alpha_composite(im)
        s.paste(bg.convert("RGB"), (130 + c * W, 22 + r * H))
s.save(D / "sheet.png")
print("sheet", D / "sheet.png")
