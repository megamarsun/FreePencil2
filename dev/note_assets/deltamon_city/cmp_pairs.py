"""前後の比較: 2 つのフォルダの同じコマを上下に並べる。  python cmp_pairs.py <前> <後> <out.png> コマ,コマ,... [切り出し x0,y0,x1,y1]"""
import sys

from PIL import Image, ImageDraw

a, b, out = sys.argv[1:4]
fs = sys.argv[4].split(",")
box = tuple(int(v) for v in sys.argv[5].split(",")) if len(sys.argv) > 5 else (80, 80, 560, 560)
w, h = box[2] - box[0], box[3] - box[1]
cols = 4
rows = (len(fs) + cols - 1) // cols
sh = Image.new("RGB", (w * cols, h * rows * 2), "black")
d = ImageDraw.Draw(sh)
for i, f in enumerate(fs):
    for j, src in enumerate((a, b)):
        x, y = (i % cols) * w, ((i // cols) * 2 + j) * h
        sh.paste(Image.open(f"{src}/{f}.png").convert("RGB").crop(box), (x, y))
        d.rectangle((x + 4, y + 4, x + 120, y + 26), fill=(0, 0, 0))
        d.text((x + 8, y + 8), f"{'before' if j == 0 else 'after'} {f}", fill=(255, 255, 255))
sh.save(out)
