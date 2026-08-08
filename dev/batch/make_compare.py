"""2つのランのレンダを並べて比較するHTMLを生成する(stdlib only)。

Usage:
    python make_compare.py <dirA> <dirB> <out_html> [labelA] [labelB]

- dirA/dirB: metrics/ と renders/ を含むランのディレクトリ
- out_html は dirA/dirB を相対参照できる場所に置くこと(例: out/compare.html)
- サムネイルクリックで大画面ビューア:
    ドラッグ/スライダーで新旧ワイプ比較、←→でモデル送り、Escで閉じる
"""
from __future__ import annotations

import html
import json
import sys
from datetime import datetime
from pathlib import Path


def load_run(d: Path) -> dict:
    recs = {}
    for f in sorted((d / "metrics").glob("*.json")):
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if r.get("ok") and r.get("render"):
            recs[r["name"]] = r
    return recs


def main() -> None:
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    dir_a, dir_b = Path(sys.argv[1]), Path(sys.argv[2])
    out_html = Path(sys.argv[3])
    label_a = sys.argv[4] if len(sys.argv) > 4 else dir_a.name
    label_b = sys.argv[5] if len(sys.argv) > 5 else dir_b.name

    run_a, run_b = load_run(dir_a), load_run(dir_b)
    names = sorted(set(run_a) & set(run_b))
    base = out_html.parent

    def rel(d: Path, r: dict) -> str:
        p = (d / r["render"]).resolve()
        return p.relative_to(base.resolve()).as_posix()

    rows = []
    for i, n in enumerate(names):
        ra, rb = run_a[n], run_b[n]
        la, lb = ra["lineart_metrics"], rb["lineart_metrics"]
        pa, pb = rel(dir_a, ra), rel(dir_b, rb)
        rows.append(f"""
<tr class="row" data-a="{pa}" data-b="{pb}" data-name="{html.escape(n)}">
  <td class="name"><b>{html.escape(n[:48])}</b><br>
    <small>{label_a}: ink {la['ink_silhouette']:.4f} / comp {la['components']}<br>
    {label_b}: ink {lb['ink_silhouette']:.4f} / comp {lb['components']}</small></td>
  <td><img src="{pa}" loading="lazy" data-idx="{i}"></td>
  <td><img src="{pb}" loading="lazy" data-idx="{i}"></td>
</tr>""")

    doc = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<title>FreePencil 比較: {html.escape(label_a)} vs {html.escape(label_b)}</title>
<style>
 body {{ font-family: "Segoe UI", "Yu Gothic UI", sans-serif; margin: 24px; color:#222; }}
 table {{ border-collapse: collapse; }}
 th, td {{ border: 1px solid #ddd; padding: 6px 8px; font-size: 13px; vertical-align: top; }}
 th {{ background: #f4f4f4; }}
 td img {{ width: 240px; height: 240px; object-fit: contain; cursor: zoom-in;
   background: repeating-conic-gradient(#eee 0% 25%, #fff 0% 50%) 50% / 16px 16px; }}
 .name {{ max-width: 260px; }}
 #viewer {{ position: fixed; inset: 0; background: rgba(0,0,0,.88); display: none;
   flex-direction: column; align-items: center; justify-content: center; z-index: 99; }}
 #stage {{ position: relative; touch-action: none; cursor: ew-resize; }}
 #stage img {{ display: block; max-width: 94vw; max-height: 86vh;
   background: #fff; user-select: none; -webkit-user-drag: none; }}
 #imgB {{ position: absolute; inset: 0; }}
 #divider {{ position: absolute; top: 0; bottom: 0; width: 2px; background: #f33;
   pointer-events: none; }}
 #cap {{ color: #eee; font-size: 14px; margin-top: 10px; text-align: center; }}
 #cap b {{ color: #fff; }}
 .tag {{ padding: 1px 8px; border-radius: 3px; font-size: 12px; }}
 .tagA {{ background: #666; color: #fff; }}
 .tagB {{ background: #06c; color: #fff; }}
 #help {{ color: #aaa; font-size: 12px; margin-top: 4px; }}
</style></head><body>
<h1>FreePencil 比較: <span class="tag tagA">{html.escape(label_a)}</span> vs
 <span class="tag tagB">{html.escape(label_b)}</span></h1>
<div>生成: {datetime.now().strftime('%Y-%m-%d %H:%M')} / {len(names)} モデル /
 サムネイルクリックで大画面ワイプ比較(ドラッグで境界移動、←→でモデル送り、Escで閉じる)</div><br>
<table>
<tr><th>モデル</th><th>{html.escape(label_a)}</th><th>{html.escape(label_b)}</th></tr>
{''.join(rows)}
</table>

<div id="viewer">
  <div id="stage">
    <img id="imgA"><img id="imgB"><div id="divider"></div>
  </div>
  <div id="cap"></div>
  <div id="help">ドラッグ: ワイプ境界 / ← →: モデル切替 / Esc: 閉じる
   (左={html.escape(label_a)}, 右={html.escape(label_b)})</div>
</div>
<script>
const rows = [...document.querySelectorAll('tr.row')].map(r => ({{
  a: r.dataset.a, b: r.dataset.b, name: r.dataset.name }}));
const viewer = document.getElementById('viewer');
const stage = document.getElementById('stage');
const imgA = document.getElementById('imgA');
const imgB = document.getElementById('imgB');
const divider = document.getElementById('divider');
const cap = document.getElementById('cap');
let idx = -1, split = 0.5;

function setSplit(v) {{
  split = Math.min(1, Math.max(0, v));
  const px = stage.clientWidth * split;
  imgB.style.clipPath = `inset(0 0 0 ${{px}}px)`;
  divider.style.left = px + 'px';
}}
function show(i) {{
  idx = (i + rows.length) % rows.length;
  imgA.src = rows[idx].a;
  imgB.src = rows[idx].b;
  cap.innerHTML = `<b>${{rows[idx].name}}</b> (${{idx + 1}}/${{rows.length}})`;
  viewer.style.display = 'flex';
  requestAnimationFrame(() => setSplit(split));
}}
document.querySelectorAll('td img').forEach(im => {{
  im.addEventListener('click', () => show(+im.dataset.idx));
}});
let dragging = false;
stage.addEventListener('pointerdown', e => {{
  dragging = true;
  stage.setPointerCapture(e.pointerId);
  setSplit((e.clientX - stage.getBoundingClientRect().left) / stage.clientWidth);
}});
stage.addEventListener('pointermove', e => {{
  if (dragging)
    setSplit((e.clientX - stage.getBoundingClientRect().left) / stage.clientWidth);
}});
stage.addEventListener('pointerup', () => dragging = false);
viewer.addEventListener('click', e => {{
  if (e.target === viewer) viewer.style.display = 'none';
}});
document.addEventListener('keydown', e => {{
  if (viewer.style.display !== 'flex') return;
  if (e.key === 'Escape') viewer.style.display = 'none';
  else if (e.key === 'ArrowRight') show(idx + 1);
  else if (e.key === 'ArrowLeft') show(idx - 1);
}});
window.addEventListener('resize', () => {{
  if (viewer.style.display === 'flex') setSplit(split);
}});
imgA.addEventListener('load', () => setSplit(split));
</script>
</body></html>"""
    out_html.write_text(doc, encoding="utf-8")
    print(f"[compare] {len(names)} models -> {out_html}")


if __name__ == "__main__":
    main()
