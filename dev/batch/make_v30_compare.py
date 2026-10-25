"""作例調査の前後を 1 体 1 行(白 前 | 白 後 | セル 前 | セル 後)に並べる。変わった量の多い順。

  python make_v30_compare.py [out/v30_survey] [out/v30_after] [--per 6] [--w 480]

<後>/compare_01.png ... を書く。変わった量は並べ順に使うだけ。良し悪しは絵を見て決める。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont

ARGV = sys.argv[1:]
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d   # noqa: E731
pos = [a for i, a in enumerate(ARGV) if not a.startswith("--") and (i == 0 or not ARGV[i - 1].startswith("--"))]
HERE = Path(__file__).resolve().parent
BEFORE = Path(pos[0]) if len(pos) > 0 else HERE / "out" / "v30_survey"
AFTER = Path(pos[1]) if len(pos) > 1 else HERE / "out" / "v30_after"
PER, W = int(arg("--per", "6")), int(arg("--w", "480"))
COLS = [("1_WHITE.png", "白 前", BEFORE), ("1_WHITE.png", "白 後", AFTER),
        ("3_CEL.png", "セル 前", BEFORE), ("3_CEL.png", "セル 後", AFTER)]
FONT = ImageFont.truetype(r"C:\Windows\Fonts\meiryo.ttc", 20)


def load(p: Path) -> Image.Image:
    im = Image.open(p).convert("RGBA")
    bg = Image.new("RGBA", im.size, "white")
    return Image.alpha_composite(bg, im).convert("RGB")


def change(name: str) -> float:
    d = 0.0
    for f in ("1_WHITE.png", "3_CEL.png"):
        a, b = load(BEFORE / name / f), load(AFTER / name / f)
        if a.size != b.size:
            return 1.0
        d += float((np.asarray(ImageChops.difference(a, b).convert("L")) > 24).mean())
    return d


def row(name: str, d: float) -> Image.Image:
    h = W * 9 // 16
    im = Image.new("RGB", (W * len(COLS), h + 30), "white")
    dr = ImageDraw.Draw(im)
    for i, (f, label, src) in enumerate(COLS):
        im.paste(load(src / name / f).resize((W, h), Image.LANCZOS), (W * i, 30))
        dr.text((W * i + 6, 4), f"{name}  {label}" if i == 0 else label, fill=(200, 0, 0), font=FONT)
    dr.text((W * len(COLS) - 170, 4), f"変化 {d * 100:.1f}%", fill=(90, 90, 90), font=FONT)
    return im


names = [p.name for p in sorted(AFTER.iterdir())
         if p.is_dir() and all((p / f).exists() for f, _, _ in COLS) and (BEFORE / p.name / "1_WHITE.png").exists()]
ranked = sorted(((change(n), n) for n in names), reverse=True)
for k in range(0, len(ranked), PER):
    rows = [row(n, d) for d, n in ranked[k:k + PER]]
    sheet = Image.new("RGB", (rows[0].width, sum(r.height for r in rows)), "white")
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height
    out = AFTER / f"compare_{k // PER + 1:02d}.png"
    sheet.save(out)
    print(out)
print("missing:", sorted({p.name for p in BEFORE.iterdir() if p.is_dir()} - set(names)))
