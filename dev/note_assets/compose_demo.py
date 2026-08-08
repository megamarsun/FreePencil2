"""STEP4 手動チャンネルのサンプルを1枚の比較図にまとめる。

右半分だけを塗ってあるので、左(未塗装)と右(塗装)の差がそのまま効果。
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONT = r"C:\Windows\Fonts\meiryob.ttc"
FONT_R = r"C:\Windows\Fonts\meiryo.ttc"


def crop_content(im: Image.Image, pad: float = -0.10) -> Image.Image:
    """中身に合わせて切る。pad が負なら内側に食い込ませて拡大表示する。"""
    box = im.split()[3].getbbox() if im.mode == "RGBA" else None
    if box is None:
        return im.convert("RGB")
    m = int(max(box[2] - box[0], box[3] - box[1]) * pad)
    box = (max(0, box[0] - m), max(0, box[1] - m),
           min(im.width, box[2] + m), min(im.height, box[3] + m))
    im = im.crop(box)
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    return Image.alpha_composite(bg, im).convert("RGB")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "out" / "demo"))
    args = ap.parse_args()
    src = Path(args.out)

    rows = [
        ("mask_color（マスク）", "暗く塗ると線が消える。白では何も起きない",
         [("suzanne_base.png", "未塗装"),
          ("suzanne_mask_0.2.png", "0.2 で塗る"),
          ("suzanne_mask_0.5.png", "0.5 で塗る"),
          ("suzanne_mask_1.0.png", "白(1.0)で塗る")]),
        ("line_color（ライン）", "線の濃さが変わる。明るいほど薄く、白で見えなくなる",
         [("suzanne_base.png", "未塗装"),
          ("suzanne_line_0.3.png", "0.3 で塗る"),
          ("suzanne_line_0.6.png", "0.6 で塗る"),
          ("suzanne_line_1.0.png", "白(1.0)で塗る")]),
    ]

    cell = 420
    cap_h, head_h, gap = 46, 74, 16
    cols = 4
    width = cols * cell + (cols + 1) * gap
    height = len(rows) * (head_h + cell + cap_h + gap) + gap

    out = Image.new("RGB", (width, height), (255, 255, 255))
    d = ImageDraw.Draw(out)
    f_head = ImageFont.truetype(FONT, 30)
    f_sub = ImageFont.truetype(FONT_R, 21)
    f_cap = ImageFont.truetype(FONT_R, 22)

    y = gap
    for title, subtitle, items in rows:
        d.text((gap, y), title, font=f_head, fill=(20, 20, 20))
        d.text((gap, y + 36), subtitle, font=f_sub, fill=(90, 90, 90))
        y += head_h
        for i, (name, cap) in enumerate(items):
            p = src / name
            x = gap + i * (cell + gap)
            if p.exists():
                im = crop_content(Image.open(p).convert("RGBA"))
                im = im.resize((cell, cell), Image.LANCZOS)
                out.paste(im, (x, y))
            d.rectangle([x, y, x + cell, y + cell], outline=(215, 215, 215))
            tw = d.textbbox((0, 0), cap, font=f_cap)[2]
            d.text((x + (cell - tw) // 2, y + cell + 12), cap,
                   font=f_cap, fill=(40, 40, 40))
            # 塗った側(右半分)を示す
            if i > 0:
                d.line([(x + cell // 2, y + 4), (x + cell // 2, y + cell - 4)],
                       fill=(230, 120, 120), width=2)
        y += cell + cap_h + gap

    note = "赤い線から右半分だけを塗っています。左半分は未塗装なので比較用。"
    d.text((gap, height - 30), note, font=f_sub, fill=(150, 90, 90))

    dst = src / "step4_channels.png"
    out.save(dst, optimize=True)
    print(f"{dst}  {out.size}  {dst.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
