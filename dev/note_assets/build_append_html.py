"""第1記事(既存・有料)へ足す部分を、note に貼れる HTML にする。

note の編集画面は Markdown を受け付けないので、ブラウザで描いた文を
コピーして貼る。触る場所ごとに枠を分け、それぞれにコピーボタンを付ける。

    python dev/note_assets/build_append_html.py --version 2.9.2

出力は note/append_v<版>.html。
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_article_html import COPY_JS, CSS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ARGV = sys.argv[1:]
VER = ARGV[ARGV.index("--version") + 1] if "--version" in ARGV else "2.9.2"
DATE = ARGV[ARGV.index("--date") + 1] if "--date" in ARGV else "2026年10月17日"
DATE_SLASH = ARGV[ARGV.index("--date-slash") + 1] if "--date-slash" in ARGV else "2026/10/17"
OUT = ROOT / "note" / f"append_v{VER}.html"
ZIP = ROOT / "dist" / f"freepencil2-{VER}.zip"
PDF = ROOT / "dist" / f"FreePencil2_マニュアル_v{VER}.pdf"
ARTICLE = "https://note.com/megamarsun/n/nddacd81c6eae"

EXTRA_CSS = """
.step { margin: 40px 0; }
.step h2 { border-top: 0; padding-top: 0; margin: 0 0 8px; font-size: 20px; }
.where { font-size: 14px; color: #555; line-height: 1.8; margin: 0 0 10px; }
.old { font-size: 14px; color: #777; background: #f6f6f6; border-radius: 6px;
       padding: 8px 12px; margin: 0 0 10px; }
.old s { color: #999; }
.paste { border: 2px solid #1f6feb; border-radius: 8px; padding: 4px 16px;
         background: #fff; }
.paste-head { display: flex; justify-content: space-between; align-items: center;
              margin: 10px 0 0; }
.paste-head .lbl { font-size: 12px; font-weight: 700; color: #1f6feb; }
.paste-head button { font: inherit; font-size: 13px; font-weight: 700; cursor: pointer;
  padding: 6px 12px; border-radius: 6px; border: 1px solid #1f6feb;
  background: #1f6feb; color: #fff; }
.paste-head button:focus-visible { outline: 3px solid #9cc3ff; outline-offset: 2px; }
table.files { border-collapse: collapse; width: 100%; font-size: 14px; margin: 8px 0; }
table.files td, table.files th { border: 1px solid #e3e3e3; padding: 6px 10px; text-align: left; }
table.files th { background: #fafafa; }
code { font-family: ui-monospace, Consolas, monospace; font-size: 13px; }
"""


def pdf_pages() -> int:
    try:
        import fitz
        return len(fitz.open(PDF))
    except Exception:           # noqa: BLE001  ページ数が取れなくても HTML は作る
        return 0


def block(bid: str, title: str, where: str, old: str | None, paste: str) -> str:
    old_html = (f'<div class="old">いまの文：<s>{html.escape(old)}</s></div>' if old else "")
    return (f'<section class="step"><h2>{html.escape(title)}</h2>'
            f'<p class="where">{where}</p>{old_html}'
            f'<div class="paste-head"><span class="lbl">▼ これを貼る</span>'
            f"<button onclick=\"fpCopy('{bid}', this)\">{html.escape(title)} をコピー</button></div>"
            f'<div class="paste" id="{bid}">{paste}</div></section>')


def main() -> None:
    pages = pdf_pages()
    pages_txt = f"全{pages}ページ" if pages else "全ページ"
    zip_size = f"{ZIP.stat().st_size:,} バイト" if ZIP.exists() else "（未ビルド）"
    blocks = [
        block("b0", "0. 記事のタイトル",
              "タイトルの後ろの追記を置き換えます（前半はそのまま）。",
              "ボタン1つで、3Dモデルが線画になる｜Blenderアドオン FreePencil2"
              "　追記：2026/09/28　FreePencil2 v2.8公開しました！",
              "<p>ボタン1つで、3Dモデルが線画になる｜Blenderアドオン FreePencil2"
              f"　追記：{DATE_SLASH}　FreePencil2 v{VER[:3]}公開しました！</p>"),
        block("b1", "1. 冒頭の追記行",
              "無料部分の一番上。いまの追記行（v2.8）を、下の文に置き換えます。",
              "追記：2026/09/28　FreePencil2 v2.8公開しました！",
              f"<p><strong>追記：{DATE_SLASH}　FreePencil2 v{VER[:3]}公開しました！</strong>"
              "　線画の下に、アニメのようなセルの影と色を自動で付けられるようになりました"
              "（プレビューの種類「セル」）</p>"),
        block("b2", "2. 更新履歴に1行",
              "無料部分「アプリ本体について」の更新履歴の、一番上に足します。",
              None,
              f"<p>{DATE}　FreePencil2 v{VER} 更新</p>"),
        block("b3", "3. 有料部分「更新について」に足すブロック",
              "いまの「FreePencil2 v2.8.2 更新」のブロックの<b>上</b>に入れ、"
              f"その下に <code>{html.escape(ZIP.name)}</code> と "
              f"<code>{html.escape(PDF.name)}</code> を添付します。",
              None,
              f"<p><strong>{DATE}　FreePencil2 v{VER} 更新</strong></p>"
              f"<p>　{html.escape(ZIP.name)}　（アドオン本体）<br>"
              f"　{html.escape(PDF.name)}　（マニュアル全部入り・{pages_txt}）</p>"
              "<p><strong>新しくできること</strong></p>"
              "<ul>"
              "<li><strong>セル（影と色）</strong> … STEP3 のプレビューで「セル」を選ぶと、線画の下に"
              "2 階調の影と、材質の色を薄めた色、空の色が付きます。材質がどんな作りでも影が出て、"
              "日を回すと影もついて行きます</li>"
              "<li><strong>物ごとの線の太さ</strong> … STEP0 で物を選び「線の太さ(倍)」を変えると、"
              "その物の線だけ太く・薄く・消せます</li>"
              "<li><strong>セルを別々の画像で書き出す</strong> … STEP5 のファイル出力に「セルの色」"
              "「セルの影」。線・色・影を別のソフトで重ねられます。カメラ一括では仕上がりの絵"
              "（final.png）も残ります</li>"
              "<li><strong>FreePencil を外す</strong> … STEP0 の一番下のボタン。足した色・ノード・設定を"
              "消して、押す前の状態に戻します（コメントでいただいたご要望です）</li>"
              "<li><strong>手描き背景：遠い区画をまとめる</strong> … 遠くのビルの窓が黒い縞の塊に"
              "なりません</li>"
              "</ul>"
              "<p><strong>直したこと</strong></p>"
              "<ul>"
              "<li>テクスチャで塗り分けた絵を AOV グループの line_texture につなぐ技法が、v2.8 で"
              "効かなくなっていました</li>"
              "<li>STEP0 の後に STEP4 でマスク・ラインを塗っても線が変わりませんでした（手描き背景では"
              "どうやっても消えませんでした）</li>"
              "<li>Half Fill（半分塗る）を作り直しました。境目に沿って頂点を一列選んで押すと、ぼかしの境目が"
              "くっきり 1 本の線になります。編集モードでも頂点ペイントでも押せます"
              "（押せないときは条件がパネルに出ます）</li>"
              "<li>キャラ・手描き背景で、マテリアル・モノクロのプレビューにすると色が消えて"
              "陰影が線になっていました</li>"
              "<li>手描き背景：カメラが動くと遠景がちらつく、線が薄い、を直しました</li>"
              "<li>STEP1 → STEP3 を手で押したとき、目や口のまわりが黒く潰れた太い線になっていました。"
              "手で押しても STEP0 と同じ線になるよう、既定をそろえました</li>"
              "<li>「FreePencil を外す」を Ctrl+Z で取り消すと、ビューポートに線が出ませんでした</li>"
              "</ul>"
              "<p>くわしくは、マニュアルの「セル（影と色）」「物ごとの線の太さ」「テクスチャで"
              "塗り分ける」の節をご覧ください。</p>"),
    ]
    files = (
        '<section class="step"><h2>添付するファイル</h2>'
        '<table class="files"><tr><th>ファイル</th><th>場所</th><th>大きさ</th></tr>'
        f"<tr><td>{html.escape(ZIP.name)}</td><td><code>dist/</code></td><td>{zip_size}</td></tr>"
        f"<tr><td>{html.escape(PDF.name)}</td><td><code>dist/</code></td><td>{pages_txt}</td></tr>"
        "</table>"
        '<p class="where">v2.8.2 の ZIP と PDF は、今までどおり下に残してかまいません'
        "（過去版は note にだけ置く方針）。</p></section>")
    howto = (
        '<div class="howto"><b>使い方</b> — 対象の記事は '
        f'<a href="{ARTICLE}">ボタン1つで、3Dモデルが線画になる｜Blenderアドオン FreePencil2</a>'
        " です。触るのは下の4か所だけで（新しい記事は更新しません）、本文の他の部分は変えません。"
        "青い枠の中を、枠ごとのボタンでコピーして note の編集画面に貼ってください"
        "（太字・箇条書きが残ります）。</div>")
    bar = ('<div class="copybar"><span class="msg" id="fp-msg" role="status" aria-live="polite">'
           "枠ごとのボタンでコピーします</span></div>")
    title = f"第1記事への追記 — FreePencil2 v{VER}"
    OUT.write_text(
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}（note 貼り付け用）</title>"
        f"<style>{CSS}{EXTRA_CSS}</style>{COPY_JS}</head><body><main>"
        f"{bar}<h1>{html.escape(title)}</h1>{howto}{''.join(blocks)}{files}"
        "</main></body></html>", encoding="utf-8")
    print(f"{OUT}  {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
