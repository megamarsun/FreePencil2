"""検証の報告を HTML にする。画像は 1 枚ずつ大きく、クリックで原寸。

  python make_findings_report.py spec.json

spec.json:
  {"out": "out/report_xxx", "title": "...", "intro": "...(HTML 可)",
   "sections": [
     {"title": "...", "text": "...(HTML 可)",
      "rows": [ {"caption": "...", "images": [
          {"src": "out/a/1_WHITE.png", "label": "前", "crop": [x0, y0, x1, y1]}   # crop は割合(省略可)
      ]} ]}
   ]}

画像は out/img/ に切り出して書き、HTML は相対パスで指す(フォルダごと渡せる)。
1 行の画像は横に並べ、狭い画面では縦に積む。
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
OUT = (HERE / spec["out"]).resolve()
IMG = OUT / "img"
IMG.mkdir(parents=True, exist_ok=True)


def place(src: str, crop, key: str) -> str:
    im = Image.open(HERE / src)
    if im.mode == "RGBA":                     # 透過は白地に
        bg = Image.new("RGBA", im.size, "white")
        im = Image.alpha_composite(bg, im)
    im = im.convert("RGB")
    if crop:
        w, h = im.size
        im = im.crop((int(crop[0] * w), int(crop[1] * h), int(crop[2] * w), int(crop[3] * h)))
    name = f"{key}.png"
    im.save(IMG / name)
    return f"img/{name}"


CSS = """
:root { --bg:#f6f7f9; --fg:#1d2330; --mut:#5b6474; --card:#fff; --line:#dde1e8; --acc:#2f5fb3; }
@media (prefers-color-scheme: dark) { :root { --bg:#14171c; --fg:#e6e9ef; --mut:#9aa3b2; --card:#1d2128; --line:#2c323c; --acc:#7aa2e8; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:16px/1.7 "Meiryo","Yu Gothic UI",sans-serif; }
main { max-width: 1700px; margin: 0 auto; padding: 24px 16px 80px; }
h1 { font-size: 26px; margin: 0 0 8px; }
h2 { font-size: 21px; margin: 48px 0 6px; padding-top: 16px; border-top: 1px solid var(--line); }
.intro, .text { color: var(--mut); max-width: 75ch; }
.text b, .intro b { color: var(--fg); }
nav { margin: 16px 0 8px; display: flex; flex-wrap: wrap; gap: 6px 14px; }
nav a { color: var(--acc); text-decoration: none; }
.row { margin: 18px 0 30px; }
.cap { font-weight: bold; margin: 0 0 6px; }
.imgs { display: grid; gap: 10px; grid-template-columns: repeat(var(--n), minmax(0, 1fr)); }
figure { margin: 0; background: var(--card); border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }
figure a { display: block; }
figure img { display: block; width: 100%; height: auto; }
figcaption { padding: 4px 10px; font-size: 14px; color: var(--mut); }
@media (max-width: 900px) { .imgs { grid-template-columns: 1fr; } }
"""

parts = [f"<h1>{html.escape(spec['title'])}</h1>", f"<p class='intro'>{spec.get('intro', '')}</p>"]
nav = []
body = []
for si, sec in enumerate(spec["sections"], 1):
    anchor = f"s{si}"
    nav.append(f"<a href='#{anchor}'>{html.escape(sec['title'])}</a>")
    body.append(f"<h2 id='{anchor}'>{html.escape(sec['title'])}</h2>")
    if sec.get("text"):
        body.append(f"<p class='text'>{sec['text']}</p>")
    for ri, row in enumerate(sec.get("rows", []), 1):
        figs = []
        for ii, im in enumerate(row["images"], 1):
            rel = place(im["src"], im.get("crop"), f"s{si}_r{ri}_{ii}")
            figs.append(f"<figure><a href='{rel}' target='_blank'><img src='{rel}' loading='lazy' "
                        f"alt='{html.escape(im.get('label', ''))}'></a>"
                        f"<figcaption>{html.escape(im.get('label', ''))}</figcaption></figure>")
        cap = f"<p class='cap'>{html.escape(row['caption'])}</p>" if row.get("caption") else ""
        body.append(f"<div class='row'>{cap}<div class='imgs' style='--n:{len(figs)}'>{''.join(figs)}</div></div>")
page = (f"<!doctype html><html lang='ja'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{html.escape(spec['title'])}</title><style>{CSS}</style></head><body><main>"
        + "".join(parts) + "<nav>" + "".join(nav) + "</nav>" + "".join(body) + "</main></body></html>")
(OUT / "report.html").write_text(page, encoding="utf-8")
print(OUT / "report.html")
