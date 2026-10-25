"""作例調査の 1 体の一部を、元の 3D / 白 / セル で並べて拡大する(解像度が違っても割合で切る)。
  python zoom_frac.py out/v30_third/<name> out.png x0,y0,x1,y1 [files]   x,y は 0..1
"""
import sys
from PIL import Image
d, out, box = sys.argv[1], sys.argv[2], [float(v) for v in sys.argv[3].split(",")]
files = sys.argv[4].split(",") if len(sys.argv) > 4 else ["0_3d.png", "1_WHITE.png", "3_CEL.png"]
crops = []
for f in files:
    im = Image.open(f"{d}/{f}").convert("RGB")
    W, H = im.size
    c = im.crop((int(box[0] * W), int(box[1] * H), int(box[2] * W), int(box[3] * H)))
    crops.append(c)
h = max(c.size[1] for c in crops)
crops = [c.resize((int(c.size[0] * h / c.size[1]), h)) for c in crops]
o = Image.new("RGB", (sum(c.size[0] for c in crops) + 8 * (len(crops) - 1), h), "white")
x = 0
for c in crops:
    o.paste(c, (x, 0)); x += c.size[0] + 8
o.save(out)
print(out, o.size)
