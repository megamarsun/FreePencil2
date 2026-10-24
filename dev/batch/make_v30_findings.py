"""v3.0 の作例で見つけた欠点を、拡大した絵に見出しを付けて 1 枚ずつ並べる。

  python make_v30_findings.py [out/v30_survey]

切り出しは割合(x0, y0, x1, y1)。列: 0 元の 3D / 1 白 / 2 材質 + 線 / 3 セル。
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent / "out" / "v30_survey")
FILES = {0: "0_3d.png", 1: "1_WHITE.png", 2: "2_NONE.png", 3: "3_CEL.png"}
LABEL = {0: "元の 3D", 1: "白(線だけ)", 2: "材質 + 線", 3: "セル"}
F_T = ImageFont.truetype(r"C:\Windows\Fonts\meiryob.ttc", 30)
F_S = ImageFont.truetype(r"C:\Windows\Fonts\meiryo.ttc", 20)
TILE_H = 420

FINDINGS = [  # (見出し, 説明, [(モデル, 切り出し, [列])])
    ("1. 滑らかな形の内側に線が出ない", "ネコのあご・前足、カップの内側の縁、受け皿のくぼみ。輪郭しか出ない",
     [("cat_figurine", (0.25, 0.05, 0.85, 0.95), [0, 1]), ("tea_set_01", (0.45, 0.2, 0.75, 0.75), [0, 1])]),
    ("2. 強弱の太い線が輪郭から離れて、二重に見える", "仕上がり「強弱」の人物。影の側の太い線と細い輪郭の間に白いすき間",
     [("woman_01", (0.42, 0.08, 0.60, 0.45), [0, 1]), ("zombie_riot_poli", (0.38, 0.25, 0.66, 0.75), [0, 1])]),
    ("3. 黒く潰れる", "木の葉は真っ黒な影絵、建物の窓ガラスは黒いザラザラ",
     [("tree_autumn", (0.38, 0.05, 0.62, 0.6), [0, 1]), ("japan-apartment", (0.36, 0.05, 0.62, 0.45), [0, 1])]),
    ("4. 人の顔の線が出ない / 髪の線が二重になる", "左: 目・鼻が出ず、髪と顔の境目も無い。右: 殻(Solidify)が無いのにツインテールの線が二重",
     [("woman_01", (0.44, 0.07, 0.56, 0.27), [0, 1]), ("loli_anime_girl", (0.50, 0.08, 0.60, 0.42), [0, 1])]),
    ("5. MMD: 前髪の影がザラザラの黒い点になる", "半透明の影の材質がそのまま線に出る(AI が手で直していた所)",
     [("Alicia", (0.43, 0.15, 0.56, 0.32), [0, 1]), ("Miku", (0.42, 0.12, 0.54, 0.30), [0, 1])]),
    ("6. MMD: パーツのつなぎ目に線が出る", "ミクの太もも・手首。形はつながっているのに線になる",
     [("Miku", (0.36, 0.72, 0.62, 1.0), [0, 2])]),
    ("7. セル: 顔の影がまだらになる", "頬・鼻に形の崩れた明るい所と影。アニメの顔にならない",
     [("loli_anime_girl", (0.44, 0.08, 0.56, 0.30), [0, 3]), ("Akari", (0.42, 0.10, 0.56, 0.32), [0, 3])]),
    ("8. セル: 鮮やかな色がくすむ", "オレンジがサーモン色・茶色に寄る",
     [("robot-kuka-quant", (0.25, 0.0, 0.95, 1.0), [0, 3]), ("lamborghini-revu", (0.1, 0.05, 0.95, 0.9), [0, 3])]),
    ("9. セル: 細かい凹凸の影がザラザラになる", "銃のグリップ、家の屋根",
     [("pistol", (0.4, 0.3, 0.95, 1.0), [0, 3]), ("modern-house", (0.25, 0.1, 0.75, 0.6), [0, 3])]),
]


def tile(name, box, col):
    im = Image.open(SRC / name / FILES[col]).convert("RGBA")
    bg = Image.new("RGBA", im.size, "white")
    im = Image.alpha_composite(bg, im).convert("RGB")
    w, h = im.size
    t = im.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)))
    t = t.resize((int(TILE_H * t.width / t.height), TILE_H), Image.LANCZOS)
    dr = ImageDraw.Draw(t)
    dr.rectangle((0, 0, dr.textlength(LABEL[col], font=F_S) + 12, 30), fill="#ffffffcc")
    dr.text((6, 3), LABEL[col], fill="#333", font=F_S)
    return t


for i, (title, note, groups) in enumerate(FINDINGS, 1):
    tiles = []
    for name, box, cols in groups:
        tiles += [tile(name, box, c) for c in cols] + [None]
    tiles = tiles[:-1]
    W = sum(t.width + 8 if t else 24 for t in tiles) + 32
    im = Image.new("RGB", (max(W, 1200), TILE_H + 110), "white")
    dr = ImageDraw.Draw(im)
    dr.text((16, 10), title, fill="#111", font=F_T)
    dr.text((16, 54), note, fill="#555", font=F_S)
    x = 16
    for t in tiles:
        if t is None:
            x += 24
            continue
        im.paste(t, (x, 94))
        x += t.width + 8
    out = SRC / f"finding_{i:02d}.png"
    im.save(out)
    print(out)
