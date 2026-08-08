"""Aggregate metrics JSONs into an HTML contact-sheet report (stdlib only).

Usage:  python make_report.py [out_dir]

When the metrics contain multiple presets (parameter sweep), a
model x preset matrix section is rendered above the score table.
"""
from __future__ import annotations

import html
import json
import sys
from datetime import datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out"


def score(rec: dict) -> float:
    """Line-art quality heuristic (higher = better). v1, refine over time.

    - penalize fragmentation (many small components = broken lines/noise)
    - penalize extreme ink ratios (near 0 = missing lines, too high = dirt)
    - penalize color-distance violations (bad separation -> missing boundaries)
    """
    if not rec.get("ok"):
        return -1.0
    la = rec.get("lineart_metrics", {})
    mm = rec.get("mesh_metrics", {})
    ink = la.get("ink_ratio", 0.0)
    comp = la.get("components", 0)
    pairs = max(mm.get("adjacent_color_pairs", 1), 1)
    viol = mm.get("min_distance_violations", 0)

    # v2: シルエット面積で正規化した線密度(フレーム占有率に依存しない)。
    # 目視アンカー6体(車/メカ/人物/橋/本/飛行機)は 0.05〜0.35 に収まり
    # すべて良品質だったため、広い許容帯を持つ「破綻検出ゲート」として設計。
    # 順位の微差より、白紙(線が出ない)・真っ黒(潰れ)・違反まみれを弾く。
    # 2倍スーパーサンプリング(1px線)基準の許容帯
    ink_sil = la.get("ink_silhouette")
    if ink_sil is not None:
        if 0.02 <= ink_sil <= 0.30:
            ink_score = 1.0
        elif ink_sil < 0.02:
            ink_score = max(0.0, (ink_sil - 0.003) / 0.017)
        else:
            ink_score = max(0.0, (0.55 - ink_sil) / 0.25)
        frag_score = max(0.0, 1.0 - comp / 3000.0)
        sep_score = 1.0 - min(1.0, viol / pairs)
        return round(0.50 * ink_score + 0.25 * frag_score + 0.25 * sep_score, 4)

    # 旧メトリクス(ink_silhouette無し)へのフォールバック
    target = 0.02 if rec.get("material") == "white" else 0.06
    ink_score = max(0.0, 1.0 - abs(ink - target) / (2 * target))
    frag_score = max(0.0, 1.0 - comp / 400.0)                # fewer blobs = cleaner
    sep_score = 1.0 - min(1.0, viol / pairs)                 # violation ratio
    return round(0.45 * ink_score + 0.30 * frag_score + 0.25 * sep_score, 4)


def cell_html(r: dict | None) -> str:
    if r is None:
        return "<td>&mdash;</td>"
    la = r.get("lineart_metrics", {})
    mm = r.get("mesh_metrics", {})
    img = (f'<a href="{r["render"]}"><img src="{r["render"]}" loading="lazy"></a>'
           if r.get("render") else "&mdash;")
    if not r.get("ok"):
        first = (r.get("error") or "").strip().splitlines()
        return (f'<td class="fail">{img}<div class="err">'
                f'{html.escape(first[-1] if first else "unknown")}</div></td>')
    return (f'<td>{img}<div class="m">score <b>{r["score"]:.3f}</b><br>'
            f'ink {la.get("ink_ratio", 0):.4f} / comp {la.get("components", "")}<br>'
            f'viol {mm.get("min_distance_violations", "")}/{mm.get("adjacent_color_pairs", "")}'
            f'<br>{r.get("step1_seconds", "")}s + {r.get("render_seconds", "")}s</div></td>')


def matrix_html(recs: list[dict], presets: list[str]) -> str:
    """Model rows x preset columns thumbnail grid."""
    presets_file = Path(__file__).resolve().parent / "presets.json"
    pdefs = json.loads(presets_file.read_text(encoding="utf-8")) if presets_file.exists() else {}

    by_key = {(r["name"], r["preset"]): r for r in recs}
    names = sorted({r["name"] for r in recs})

    header = "".join(
        f"<th>{html.escape(p)}<br><small>{html.escape(json.dumps(pdefs.get(p, {}), ensure_ascii=False))}</small></th>"
        for p in presets)
    rows = []
    for n in names:
        cells = "".join(cell_html(by_key.get((n, p))) for p in presets)
        rows.append(f"<tr><th class='rowh'>{html.escape(n[:36])}</th>{cells}</tr>")
    return (f"<h2>モデル × プリセット マトリクス</h2>"
            f"<div class='wrap'><table class='matrix'>"
            f"<tr><th></th>{header}</tr>{''.join(rows)}</table></div>")


def main(out: Path | str | None = None) -> None:
    out = Path(out) if out else OUT
    recs = []
    for f in sorted((out / "metrics").glob("*.json")):
        try:
            recs.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    for r in recs:
        r["score"] = score(r)
    recs.sort(key=lambda r: r["score"], reverse=True)

    ok = [r for r in recs if r.get("ok")]
    fail = [r for r in recs if not r.get("ok")]
    presets = sorted({r.get("preset", "?") for r in recs})

    matrix = matrix_html(recs, presets) if len(presets) > 1 else ""

    rows = []
    for r in recs:
        la = r.get("lineart_metrics", {})
        mm = r.get("mesh_metrics", {})
        img = (
            f'<a href="{r["render"]}"><img src="{r["render"]}" loading="lazy"></a>'
            if r.get("render") else "&mdash;"
        )
        err = ""
        if not r.get("ok"):
            first = (r.get("error") or "").strip().splitlines()
            err = f'<div class="err">{html.escape(first[-1] if first else "unknown")}</div>'
        if r.get("degenerate"):
            err += '<div class="adapt">&#9888; degenerate asset (faces &le; 8)</div>'
        if r.get("adaptive"):
            ov = {k: v for k, v in r["adaptive"].items() if k != "reason"}
            err += (f'<div class="adapt">&#10227; adaptive '
                    f'({html.escape(r["adaptive"].get("reason", ""))}): '
                    f'{html.escape(json.dumps(ov))}</div>')
        rows.append(f"""
<tr class="{'ok' if r.get('ok') else 'fail'}">
  <td>{img}</td>
  <td><b>{html.escape(r['name'])}</b><br>
      <small>{r.get('faces_total', '?')} faces / {r.get('mesh_objects', '?')} obj /
      seed {r['seed']} / {html.escape(r['preset'])} /
      {html.escape(r.get('material', 'keep'))}</small>{err}</td>
  <td>{r['score']:.3f}</td>
  <td>{la.get('ink_ratio', '')}</td>
  <td>{la.get('components', '')}</td>
  <td>{mm.get('distinct_colors', '')}</td>
  <td>{mm.get('min_distance_violations', '')}/{mm.get('adjacent_color_pairs', '')}</td>
  <td>{r.get('step1_seconds', '')}s</td>
  <td>{r.get('render_seconds', '')}s</td>
</tr>""")

    doc = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<title>FreePencil batch report</title>
<style>
 body {{ font-family: "Segoe UI", "Yu Gothic UI", sans-serif; margin: 24px; color:#222; }}
 table {{ border-collapse: collapse; width: 100%; }}
 th, td {{ border: 1px solid #ddd; padding: 6px 8px; font-size: 13px; vertical-align: top; }}
 th {{ background: #f4f4f4; }}
 img {{ width: 180px; height: 180px; object-fit: contain; background:
        repeating-conic-gradient(#eee 0% 25%, #fff 0% 50%) 50% / 16px 16px; }}
 tr.fail, td.fail {{ background: #fff2f2; }}
 .err {{ color: #b00; font-size: 11px; max-width: 320px; }}
 .adapt {{ color: #06c; font-size: 11px; }}
 .summary {{ margin-bottom: 16px; }}
 .wrap {{ overflow-x: auto; margin-bottom: 24px; }}
 .matrix img {{ width: 150px; height: 150px; }}
 .matrix .m {{ font-size: 11px; color: #444; }}
 .matrix th {{ font-size: 11px; max-width: 170px; }}
 .matrix th small {{ font-weight: normal; color: #777; }}
 .matrix .rowh {{ writing-mode: horizontal-tb; font-size: 12px; }}
</style></head><body>
<h1>FreePencil 一括評価レポート</h1>
<div class="summary">
 生成: {datetime.now().strftime('%Y-%m-%d %H:%M')} /
 成功 <b>{len(ok)}</b> ・ 失敗 <b>{len(fail)}</b> / 全 {len(recs)} ラン
 / プリセット: {html.escape(', '.join(presets))}<br>
 スコア: 線密度(45%) + 線の断片化(30%) + 塗り分け違反率(25%) の加重。降順ソート。
</div>
{matrix}
<h2>スコア順一覧</h2>
<table>
<tr><th>線画</th><th>モデル</th><th>score</th><th>ink</th><th>components</th>
<th>colors</th><th>violations</th><th>STEP1</th><th>render</th></tr>
{''.join(rows)}
</table>

<div id="lb" style="position:fixed;inset:0;background:rgba(0,0,0,.88);display:none;
 flex-direction:column;align-items:center;justify-content:center;z-index:99">
 <img id="lb-img" style="max-width:94vw;max-height:88vh;background:#fff">
 <div id="lb-cap" style="color:#eee;font-size:14px;margin-top:10px"></div>
 <div style="color:#aaa;font-size:12px;margin-top:4px">← →: 前後の画像 / Esc: 閉じる</div>
</div>
<script>
// サムネイルクリックで大画面ライトボックス(←→でスライド送り)
const lbImgs = [...document.querySelectorAll('td img')];
const lb = document.getElementById('lb');
const lbImg = document.getElementById('lb-img');
const lbCap = document.getElementById('lb-cap');
let lbIdx = -1;
function lbShow(i) {{
  lbIdx = (i + lbImgs.length) % lbImgs.length;
  const im = lbImgs[lbIdx];
  lbImg.src = im.src;
  const row = im.closest('tr');
  const name = row ? (row.querySelector('b') || {{}}).textContent || '' : '';
  lbCap.innerHTML = `<b>${{name}}</b> (${{lbIdx + 1}}/${{lbImgs.length}})`;
  lb.style.display = 'flex';
}}
lbImgs.forEach((im, i) => {{
  im.style.cursor = 'zoom-in';
  im.addEventListener('click', e => {{
    e.preventDefault(); e.stopPropagation(); lbShow(i);
  }});
}});
lb.addEventListener('click', e => {{ if (e.target === lb) lb.style.display = 'none'; }});
document.addEventListener('keydown', e => {{
  if (lb.style.display !== 'flex') return;
  if (e.key === 'Escape') lb.style.display = 'none';
  else if (e.key === 'ArrowRight') lbShow(lbIdx + 1);
  else if (e.key === 'ArrowLeft') lbShow(lbIdx - 1);
}});
</script>
</body></html>"""
    (out / "report.html").write_text(doc, encoding="utf-8")
    print(f"[report] {len(ok)} ok / {len(fail)} fail -> {out / 'report.html'}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
