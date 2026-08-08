"""ターンテーブル動画+フレーム毎採点のHTMLレポート(stdlib only)。

Usage: python make_turntable_report.py <run_dir>
run_dir/metrics/*.json の turntable 付きレコードを集めて
run_dir/turntable.html を生成する。
"""
from __future__ import annotations

import html
import json
import sys
from datetime import datetime
from pathlib import Path


def sparkline(values: list[float], width=360, height=64,
              band=(0.02, 0.30)) -> str:
    """ink_sil のフレーム推移をSVG化(緑帯=目標帯)。"""
    if not values:
        return ""
    vmax = max(max(values), band[1]) * 1.15
    n = len(values)

    def x(i):
        return i / max(n - 1, 1) * (width - 8) + 4

    def y(v):
        return height - 4 - (v / vmax) * (height - 8)

    pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(values))
    band_y1, band_y0 = y(band[1]), y(band[0])
    return f"""<svg width="{width}" height="{height}"
 style="background:#fafafa;border:1px solid #ddd">
 <rect x="0" y="{band_y1:.1f}" width="{width}" height="{band_y0 - band_y1:.1f}"
  fill="#e4f5e4"/>
 <polyline points="{pts}" fill="none" stroke="#06c" stroke-width="1.5"/>
</svg>"""


def main() -> None:
    run = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("out_turn")
    recs = []
    for f in sorted((run / "metrics").glob("*.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        if r.get("ok") and r.get("turntable"):
            recs.append(r)

    cards = []
    for r in recs:
        t = r["turntable"]
        la = r["lineart_metrics"]
        grade = ("S" if t["score_mean"] >= 0.98 and t["score_worst"] >= 0.9 else
                 "A" if t["score_mean"] >= 0.9 else
                 "B" if t["score_mean"] >= 0.7 else "C")
        cards.append(f"""
<div class="card">
 <h2>{html.escape(r['name'][:44])} <span class="grade g{grade}">{grade}</span></h2>
 <video src="{t['video']}" width="512" height="512" loop autoplay muted controls></video>
 <table>
  <tr><th>総合(帯スコア平均)</th><td><b>{t['score_mean']:.3f}</b></td>
      <th>最悪角</th><td>{t['score_worst']:.3f} @ {t['worst_angle_deg']}°</td></tr>
  <tr><th>ink_sil 平均</th><td>{t['ink_mean']:.4f}</td>
      <th>min / max</th><td>{t['ink_min']:.4f} / {t['ink_max']:.4f}</td></tr>
  <tr><th>角度ばらつき</th><td>{(t['ink_max'] - t['ink_min']) / max(t['ink_mean'], 1e-6):.2f}</td>
      <th>フレーム/所要</th><td>{t['frames']}f / {t.get('seconds', '?')}s</td></tr>
 </table>
 <div class="spark">ink_sil 推移(緑帯=目標帯 0.02-0.30):<br>
  {sparkline(t['ink_per_frame'])}</div>
</div>""")

    doc = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<title>FreePencil 360° ターンテーブル評価</title>
<style>
 body {{ font-family: "Segoe UI", "Yu Gothic UI", sans-serif; margin: 24px; color: #222; }}
 .card {{ display: inline-block; vertical-align: top; margin: 0 18px 24px 0;
   border: 1px solid #ddd; border-radius: 8px; padding: 14px 16px; }}
 video {{ background: #fff; border: 1px solid #eee; display: block; }}
 table {{ border-collapse: collapse; margin-top: 8px; }}
 th, td {{ border: 1px solid #eee; padding: 3px 8px; font-size: 12px; text-align: left; }}
 th {{ background: #f7f7f7; }}
 .grade {{ padding: 1px 10px; border-radius: 4px; color: #fff; font-size: 16px; }}
 .gS {{ background: #d4a017; }} .gA {{ background: #2a9d2a; }}
 .gB {{ background: #e08a00; }} .gC {{ background: #c33; }}
 .spark {{ margin-top: 8px; font-size: 12px; color: #555; }}
</style></head><body>
<h1>FreePencil 360° ターンテーブル評価</h1>
<div>生成: {datetime.now().strftime('%Y-%m-%d %H:%M')} /
 評価 = フレーム毎の線密度帯スコア(S: 平均0.98+かつ最悪角0.9+ / A: 0.9+ / B: 0.7+)</div><br>
{''.join(cards)}
</body></html>"""
    (run / "turntable.html").write_text(doc, encoding="utf-8")
    print(f"[turntable] {len(recs)} videos -> {run / 'turntable.html'}")


if __name__ == "__main__":
    main()
