"""audit_v30_survey.py の絵を、1 体 1 行(元の 3D | 白 | 材質 | セル)に並べたシートにする。

  python make_v30_sheet.py [out/v30_survey] [--per 5] [--w 640]

out/v30_survey/sheet_01.png ... と、1 体ずつの <名前>/row.png(拡大して見る用)を書く。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ARGV = sys.argv[1:]
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d   # noqa: E731
pos = [a for i, a in enumerate(ARGV) if not a.startswith("--") and (i == 0 or not ARGV[i - 1].startswith("--"))]
SRC = Path(pos[0] if pos else Path(__file__).resolve().parent / "out" / "v30_survey")
PER, W = int(arg("--per", "5")), int(arg("--w", "640"))
COLS = [("0_3d.png", "元の 3D"), ("1_WHITE.png", "白(線だけ)"), ("2_NONE.png", "材質 + 線"), ("3_CEL.png", "セル")]
FONT = ImageFont.truetype(r"C:\Windows\Fonts\meiryo.ttc", 22)
FONT_S = ImageFont.truetype(r"C:\Windows\Fonts\meiryo.ttc", 16)


def row(d: Path) -> Image.Image:
    rec = json.loads((d / "rec.json").read_text(encoding="utf-8"))
    h = W * 9 // 16
    im = Image.new("RGB", (W * len(COLS), h + 34), "white")
    dr = ImageDraw.Draw(im)
    for i, (f, label) in enumerate(COLS):
        p = d / f
        if p.exists():
            t = Image.open(p).convert("RGBA")
            bg = Image.new("RGBA", t.size, "white")
            im.paste(Image.alpha_composite(bg, t).convert("RGB").resize((W, h), Image.LANCZOS), (i * W, 34))
        dr.text((i * W + 8, 6), label, fill="#555", font=FONT_S)
    info = f"{rec['name']}  {rec.get('style', '')}  面 {rec.get('faces', '?')}  STEP0 {rec.get('t_step0', '?')} 秒"
    if "error" in rec:
        info += "  エラー"
    dr.text((W * 2 - 60, 4), info, fill="#111", font=FONT_S, anchor="ra")
    return im


dirs = sorted(p for p in SRC.iterdir() if (p / "rec.json").exists())
rows = []
for d in dirs:
    r = row(d)
    r.save(d / "row.png")
    rows.append((d.name, r))
for k in range(0, len(rows), PER):
    chunk = rows[k:k + PER]
    sheet = Image.new("RGB", (chunk[0][1].width, sum(r.height + 6 for _, r in chunk)), "#ddd")
    y = 0
    for _, r in chunk:
        sheet.paste(r, (0, y))
        y += r.height + 6
    out = SRC / f"sheet_{k // PER + 1:02d}.png"
    sheet.save(out)
    print(out, [n for n, _ in chunk])
