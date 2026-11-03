"""フォルダの PNG を並べて 1 枚にする。  python sheet.py <フォルダ> <out.png> [列 8] [幅 320]"""
import glob
import sys

from PIL import Image

fs = sorted(glob.glob(sys.argv[1] + "/*.png"))
cols = int(sys.argv[3]) if len(sys.argv) > 3 else 8
W = int(sys.argv[4]) if len(sys.argv) > 4 else 320
im0 = Image.open(fs[0])
H = W * im0.height // im0.width
rows = (len(fs) + cols - 1) // cols
sh = Image.new("RGB", (W * cols, H * rows))
for i, f in enumerate(fs):
    sh.paste(Image.open(f).convert("RGB").resize((W, H)), ((i % cols) * W, (i // cols) * H))
sh.save(sys.argv[2])
print("@@ sheet", len(fs), sys.argv[2])
