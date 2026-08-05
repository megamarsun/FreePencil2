"""UIスクリーンショットを掲載用に切り出す (Pillow が要る)。

撮影エリアは 2400x1400 ウィンドウで約 1982x1198 になるが、下半分が空くので
中身のある範囲だけ残す。切り出し高さはショットごとに決め打ち。
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
MAX_W = 1600

# name -> 中身が終わる行 (幅は全幅)
BOTTOM = {
    "10_ui_sidebar_step0.png": 700,
    "11_ui_step3.png": 830,
    "12_ui_preferences.png": 560,
    "13_ui_outliner.png": 190,
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(HERE / "out"))
    args = p.parse_args()
    src = Path(args.out)
    dst = src / "final"
    dst.mkdir(parents=True, exist_ok=True)

    for name, bottom in BOTTOM.items():
        path = src / name
        if not path.exists():
            print(f"{name:28s} 見つからない (スキップ)")
            continue
        im = Image.open(path).convert("RGB")
        im = im.crop((0, 0, im.width, min(bottom, im.height)))
        if im.width > MAX_W:
            im = im.resize((MAX_W, round(im.height * MAX_W / im.width)),
                           Image.LANCZOS)
        im.save(dst / name, optimize=True)
        kb = (dst / name).stat().st_size // 1024
        print(f"{name:28s} {im.width}x{im.height}  {kb} KB")


if __name__ == "__main__":
    main()
