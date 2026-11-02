"""プリビズの報告(report.html)を作る。画像は 1 枚ずつ大きく、クリックで原寸。

  python build_report.py <報告のフォルダ>

フォルダの中: shots/<S01_0150>.png(snap_shots.py)、method/*.png(横から見た図)、notes.json(各画像の説明)
"""
import html
import json
import sys
from pathlib import Path

R = Path(sys.argv[1])
N = json.loads((R / "notes.json").read_text(encoding="utf-8"))


def fig(src, cap):
    return (f'<figure><a href="{src}" target="_blank"><img src="{src}" loading="lazy"></a>'
            f'<figcaption>{cap}</figcaption></figure>')


parts = []
for sec in N["sections"]:
    parts.append(f'<h2>{html.escape(sec["title"])}</h2>')
    if sec.get("text"):
        parts.append(f'<p>{sec["text"]}</p>')
    if sec.get("table"):
        rows = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in sec["table"][1:])
        head = "".join(f"<th>{c}</th>" for c in sec["table"][0])
        parts.append(f"<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>")
    for im in sec.get("images", []):
        parts.append(fig(im[0], im[1]))
    if sec.get("list"):
        parts.append("<ul>" + "".join(f"<li>{x}</li>" for x in sec["list"]) + "</ul>")

page = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(N["title"])}</title>
<style>
body {{ background:#10141c; color:#dfe6f0; font-family:"Yu Gothic UI","Meiryo",sans-serif; margin:0 auto; max-width:1500px; padding:24px 16px 80px; line-height:1.7 }}
h1 {{ font-size:28px; margin:0 0 8px }} h2 {{ font-size:21px; margin:44px 0 12px; border-left:5px solid #e0412f; padding-left:10px }}
p, li {{ font-size:16px }} a {{ color:#8cc8ff }}
figure {{ margin:18px 0 30px }} figure img {{ width:100%; height:auto; display:block; border:1px solid #2c3546; border-radius:4px }}
figcaption {{ font-size:15px; color:#b9c4d4; margin-top:6px }}
table {{ border-collapse:collapse; width:100%; font-size:14px; margin:10px 0 }} td, th {{ border:1px solid #2c3546; padding:6px 8px; vertical-align:top }}
th {{ background:#1a2130 }} code {{ background:#1a2130; padding:1px 5px; border-radius:3px }}
</style></head><body>
<h1>{html.escape(N["title"])}</h1>
<p>{N["lead"]}</p>
{''.join(parts)}
</body></html>"""
(R / "report.html").write_text(page, encoding="utf-8")
print("@@ report", R / "report.html")
