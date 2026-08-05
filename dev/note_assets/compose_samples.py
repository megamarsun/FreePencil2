"""レンダー結果を掲載用に整える (Pillow が要る、Blender は不要)。

透過PNGの中身に合わせてトリミングし、白背景に載せて幅1600pxで書き出す。
塗り分け→線画の対比図も作る。

  python compose_samples.py --out out --pair mecha
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONT_PATH = r"C:\Windows\Fonts\meiryob.ttc"
MAX_W = 1600


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATH, size)


def trimmed(path: Path, margin_pct: float = 0.04) -> Image.Image:
    """アルファの実体範囲で切り出し、白背景に合成して返す。"""
    im = Image.open(path).convert("RGBA")
    box = im.split()[3].getbbox() or (0, 0, im.width, im.height)
    m = int(max(box[2] - box[0], box[3] - box[1]) * margin_pct)
    box = (max(0, box[0] - m), max(0, box[1] - m),
           min(im.width, box[2] + m), min(im.height, box[3] + m))
    im = im.crop(box)
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    return Image.alpha_composite(bg, im).convert("RGB")


def fit_width(im: Image.Image, width: int) -> Image.Image:
    if im.width == width:
        return im
    return im.resize((width, round(im.height * width / im.width)),
                     Image.LANCZOS)


def pad_to(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    canvas = Image.new("RGB", size, (255, 255, 255))
    canvas.paste(im, ((size[0] - im.width) // 2, (size[1] - im.height) // 2))
    return canvas


def labelled_pair(left: Image.Image, right: Image.Image,
                  left_text: str, right_text: str,
                  cell: int = 780, gap: int = 40) -> Image.Image:
    """2枚を横並びにし、下にキャプション、間に矢印を描く。"""
    lab_h = 86
    left = pad_to(fit_width(left, cell), (cell, cell))
    right = pad_to(fit_width(right, cell), (cell, cell))
    out = Image.new("RGB", (cell * 2 + gap, cell + lab_h), (255, 255, 255))
    out.paste(left, (0, 0))
    out.paste(right, (cell + gap, 0))

    d = ImageDraw.Draw(out)
    f = font(34)
    for text, x0 in ((left_text, 0), (right_text, cell + gap)):
        tw = d.textbbox((0, 0), text, font=f)[2]
        d.text((x0 + (cell - tw) // 2, cell + 26), text, font=f,
               fill=(40, 40, 40))

    cy, cx = cell // 2, cell + gap // 2
    d.line([(cx - 46, cy), (cx + 30, cy)], fill=(120, 120, 120), width=9)
    d.polygon([(cx + 46, cy), (cx + 20, cy - 20), (cx + 20, cy + 20)],
              fill=(120, 120, 120))
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(HERE / "out"))
    p.add_argument("--pair", default="mecha",
                   help="対比図に使うモデル名 (<name>_line/_paint が要る)")
    args = p.parse_args()
    out = Path(args.out)
    dst = out / "final"
    dst.mkdir(parents=True, exist_ok=True)

    made = []
    for src in sorted(out.glob("*_line.png")) + sorted(out.glob("*_paint.png")):
        name = src.stem                       # mecha_line / mecha_paint
        im = fit_width(trimmed(src), MAX_W)
        target = dst / f"{name}.png"
        im.save(target, optimize=True)
        made.append((target.name, im.size))

    lp, pp = out / f"{args.pair}_paint.png", out / f"{args.pair}_line.png"
    if lp.exists() and pp.exists():
        pair = labelled_pair(trimmed(lp), trimmed(pp),
                             "自動で塗り分けた状態", "そこから出てくる線画")
        pair.save(dst / "paint_to_line.png", optimize=True)
        made.append(("paint_to_line.png", pair.size))

    for name, size in made:
        kb = (dst / name).stat().st_size // 1024
        print(f"{name:28s} {size[0]}x{size[1]}  {kb} KB")


if __name__ == "__main__":
    main()
