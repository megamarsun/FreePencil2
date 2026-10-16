"""audit_buttons.py の結果を、場面ごとに 1 行の画像にして並べる(目で見る用)。

  python audit_buttons_sheet.py out/audit_buttons/4.5.2 [--group s_WEIGHTED]

1 行 = 左に文字(押したボタン・期待・戻り値・メッセージ・変わった中身・時間)、
右に 押す前 | 押した後 | 期待の絵(あれば) | 違う所(赤) | 頂点カラーの前 | 後。
違う所は、期待の絵があればそれと、無ければ押す前と比べる。
数値(違う画素の割合)は並べる順と目印にだけ使う。判定は絵を見て行う。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

D = Path(sys.argv[1]).resolve()
ARGV = sys.argv[2:]
GROUP = ARGV[ARGV.index("--group") + 1] if "--group" in ARGV else None
W, H = 256, 192
TXT = 470
F = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 12)
FB = ImageFont.truetype("C:/Windows/Fonts/meiryob.ttc", 14)


def load(p):
    im = Image.open(p).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return bg.convert("RGB")


def fit(im):
    return im.resize((W, H), Image.LANCZOS)


def diff_img(a, b):
    """b を薄い灰色にして、a と違う所を赤で塗る。"""
    a = np.asarray(fit(a), dtype=np.float32)
    b = np.asarray(fit(b), dtype=np.float32)
    d = np.abs(a - b).max(axis=2)
    base = b.mean(axis=2, keepdims=True) * 0.35 + 255 * 0.65
    out = np.repeat(base, 3, axis=2)
    m = d > 12
    out[m] = [230, 20, 20]
    weak = (d > 3) & ~m
    out[weak] = [250, 160, 160]
    return Image.fromarray(out.astype(np.uint8)), float(m.mean() * 100)


def wrap(text, width_px, font):
    lines, cur = [], ""
    for ch in str(text):
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        if font.getlength(cur + ch) > width_px:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def short(v):
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    return s if len(s) < 70 else s[:67] + "…"


recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(D.glob("*/rec.json"))]
order = {}
for i, p in enumerate(json.loads((D / "cases.json").read_text(encoding="utf-8"))
                      if (D / "cases.json").exists() else []):
    order[p["name"]] = i
recs.sort(key=lambda r: order.get(r["name"], 999))
if GROUP:
    recs = [r for r in recs if r["name"].startswith(GROUP + "__")]

rows = []
summary = []
for r in recs:
    d = D / r["name"]
    cols = []
    labels = []
    pct = None
    if "before" in r and (d / r["before"]).exists():
        b = load(d / r["before"])
        cols.append(fit(b))
        labels.append("押す前")
        if "after" in r and (d / r["after"]).exists():
            a = load(d / r["after"])
            cols.append(fit(a))
            labels.append("押した後")
            if r.get("ref") and (D / r["ref"]).exists():
                ref = load(D / r["ref"])
                cols.append(fit(ref))
                labels.append("期待")
                di, pct = diff_img(a, ref)
                labels.append(f"違う所(期待と) {pct:.2f}%")
            else:
                di, pct = diff_img(a, b)
                labels.append(f"違う所(前と) {pct:.2f}%")
            cols.append(di)
    if r.get("before_vc") and (d / r["before_vc"]).exists():
        cols.append(fit(load(d / r["before_vc"])))
        labels.append(f"頂点カラー前 {r.get('vc')}")
    if r.get("after_vc") and (d / r["after_vc"]).exists():
        cols.append(fit(load(d / r["after_vc"])))
        labels.append("頂点カラー後")
    for f in r.get("files", [])[:3]:
        if f.endswith(".png") and "final" in f:
            cols.append(fit(load(d / f)))
            labels.append(f.replace("\\", "/")[-30:])

    text = []
    text.append(("b", r["name"]))
    text.append(("n", r.get("note", "")))
    text.append(("n", f"戻り値: {short(r.get('result'))}   {r.get('sec', '?')} 秒"))
    for m in r.get("msgs", [])[:4]:
        text.append(("m", m))
    if "error" in r:
        text.append(("e", "例外: " + r["error"].strip().splitlines()[-1]))
    ch = r.get("changed", [])
    text.append(("n", f"変わった中身 {len(ch)} 件:"))
    keys = [c for c in ch if not c[0].startswith(("obj/", "fp/fp_cel", "pass/"))] + \
           [c for c in ch if c[0].startswith(("obj/", "fp/fp_cel", "pass/"))]
    for k, a, b in keys[:9]:
        text.append(("s", f"  {k}: {short(a)} → {short(b)}"))
    if len(keys) > 9:
        text.append(("s", f"  …ほか {len(keys) - 9} 件"))
    if r.get("vs_ref_state") is not None:
        vs = r["vs_ref_state"]
        text.append(("n", f"期待の中身との違い {len(vs)} 件" + (":" if vs else "")))
        for k, a, b in vs[:5]:
            text.append(("s", f"  {k}: 期待 {short(a)} / 今 {short(b)}"))
    for k in ("mode_after_paint", "active_after_paint", "sel_after_paint"):
        if k in r:
            text.append(("s", f"  {k}: {r[k]}"))
    if r.get("files"):
        text.append(("s", f"  書き出し {len(r['files'])} 枚: " + ", ".join(Path(f).name for f in r['files'][:6])))

    lines = []
    for kind, t in text:
        fnt = FB if kind == "b" else F
        for ln in wrap(t, TXT - 12, fnt):
            lines.append((kind, ln, fnt))
    th = 8 + sum(18 if k == "b" else 15 for k, _, _ in lines)
    rh = max(H + 22, th + 6)
    row = Image.new("RGB", (TXT + len(cols) * (W + 6) + 6, rh), (255, 255, 255))
    dr = ImageDraw.Draw(row)
    y = 6
    color = {"b": (0, 0, 0), "n": (40, 40, 40), "m": (20, 70, 160), "e": (200, 0, 0), "s": (90, 90, 90)}
    for kind, ln, fnt in lines:
        dr.text((8, y), ln, fill=color[kind], font=fnt)
        y += 18 if kind == "b" else 15
    x = TXT
    for im, lb in zip(cols, labels):
        dr.text((x, 3), lb, fill=(60, 60, 60), font=F)
        row.paste(im, (x, 20))
        dr.rectangle([x - 1, 19, x + W, 20 + H], outline=(200, 200, 200))
        x += W + 6
    dr.line([0, rh - 1, row.width, rh - 1], fill=(170, 170, 170))
    rows.append(row)
    summary.append((r["name"], r.get("result"), pct, len(ch), "error" in r))

if not rows:
    sys.exit("no rows")
Wt = max(r.width for r in rows)
# 縦に長すぎると見られないので、8 行ずつのシートに分ける
tag = GROUP or "all"
outs = []
for i in range(0, len(rows), 8):
    part = rows[i:i + 8]
    sheet = Image.new("RGB", (Wt, sum(r.height for r in part)), (255, 255, 255))
    y = 0
    for r in part:
        sheet.paste(r, (0, y))
        y += r.height
    p = D / f"sheet_{tag}_{i // 8 + 1:02d}.png"
    sheet.save(p)
    outs.append(p)
for s in summary:
    print(f"{s[0]:45s} {str(s[1])[:40]:40s} diff={s[2] if s[2] is None else round(s[2], 2)}"
          f" changed={s[3]}{' ERROR' if s[4] else ''}")
for p in outs:
    print(p)
