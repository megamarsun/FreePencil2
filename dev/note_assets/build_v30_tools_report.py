"""v3.0 に組み込んだデモの道具(VRM の下ごしらえ・目手口・アップ・光を分ける)の報告 HTML。

画像は 1 枚ずつ大きく、クリックで原寸。 python dev/note_assets/build_v30_tools_report.py [audit_dir]
"""
import shutil
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent / "v30_tools_report"
INTEG = Path(r"E:\10_cowork\00_code\motionbricks_tools\out\integ")
AUDIT = Path(sys.argv[1]) if len(sys.argv) > 1 else None

SECTIONS = [
    ("VRM の下ごしらえ(STEP0 が自動で)",
     "MToon の出力を止めて Principled で描く・金属 0・MToon の輪郭の殻を切る。「FreePencil を外す」で元に戻る。",
     [("a_vrmprep.png", "下ごしらえだけ入れた STEP0。肌・髪・服の色がそのまま出る")]),
    ("目・手・口の塗り分け(VRM のとき STEP0 が自動で)",
     "左から: 下ごしらえだけ / アドオンだけで STEP0(今回)/ デモで手で直したもの。今回とデモがそろった。",
     [("cmp_mouth_c.png", "口: 口の中を塗り分けて 0.02 開ける(ai.mouth_line)。目は顔と 1 色で縁の黒い丸が消える"),
      ("cmp_hands_c.png", "手: 前腕から指先までを手ごとに 1 色。指の節ごとの線が消える"),
      ("c_vrmfix.png", "全身(アドオンだけで STEP0 → セル)")]),
    ("アップの確認レンダ(ai.render(focus=…))",
     "今のカメラの側から 85mm の仮のカメラを置いて撮り、カメラを戻す。face / hands。",
     [("d_face.png", "focus='face'"),
      ("e_left_hand.png", "focus='hands' の左手"),
      ("e_right_hand.png", "focus='hands' の右手")]),
    ("キャラと背景の光を分ける(セル > 「カメラから」の下の切り替え)",
     "カメラからの日はキャラだけ、背景は動かない日(向きはパネルで回せる)。上段: 切 / 下段: 入。"
     "キャラの陰は上下で同じ、壁と床はワールドに固定の日で決まる。",
     [("split2/cmp_split.png", "95 コマと 135 コマ(カメラが約 60 度曲がる)"),
      ("split3/strip.png", "91〜139 コマを 8 コマおき"),
      ("split/cmp_split.png", "212 / 213 コマ")]),
    ("見え方の監査(install_all --test --audit)",
     "基準(10/25)との差は、コミット済みの HEAD の時点ですでにあった(10/25 以降のコミットの分)。"
     "HEAD と今回は 4.5.2 で全場面まったく同じ、5.2 は点々のノイズだけで線の見え方は同じ。"
     "ただし facades_precise_far_zoom の窓の線が 10/25 以降で消えている(今回とは別の、前からの退行)。",
     [("audit_head_vs_now.png", "左から 基準 | HEAD | 今回 | HEAD と今回の違う所(赤)")]),
]


def put(src: Path, name: str) -> str:
    dst = ROOT / "img" / name
    dst.parent.mkdir(parents=True, exist_ok=True)
    full = dst.with_suffix(".png")
    shutil.copy2(src, full)
    im = Image.open(src).convert("RGB")
    im.thumbnail((1800, 1800))
    view = dst.with_name(dst.stem + "_v.jpg")
    im.save(view, quality=90)
    return f"img/{view.name}", f"img/{full.name}"


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    parts = []
    for title, lead, imgs in SECTIONS:
        figs = []
        for rel, cap in imgs:
            v, f = put(INTEG / rel, rel.replace("/", "_"))
            figs.append(f'<figure><a href="{f}"><img src="{v}" alt=""></a><figcaption>{cap}</figcaption></figure>')
        parts.append(f"<section><h2>{title}</h2><p>{lead}</p>{''.join(figs)}</section>")
    if AUDIT is not None and AUDIT.exists():
        figs = []
        for p in sorted(AUDIT.glob("*.png")):
            v, f = put(p, "audit_" + p.name)
            figs.append(f'<figure><a href="{f}"><img src="{v}" alt=""></a><figcaption>{p.name}</figcaption></figure>')
        parts.append("<section><h2>見え方の監査(基準 | 今回 | 違う所)</h2>"
                     "<p>install_all --test --audit のシート。</p>" + "".join(figs) + "</section>")
    html = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>v3.0 デモの道具の組み込み</title>
<style>
:root{{--bg:#f6f5f2;--fg:#22211f;--mut:#6b675f;--card:#fff;--line:#dedad2}}
@media (prefers-color-scheme:dark){{:root{{--bg:#1b1a18;--fg:#ecebe7;--mut:#a29d93;--card:#262522;--line:#3a3833}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.7 "Yu Gothic UI","Hiragino Sans",sans-serif}}
main{{max-width:1900px;margin:0 auto;padding:24px 16px 80px}}
h1{{font-size:26px;margin:0 0 4px}} h2{{font-size:20px;margin:48px 0 4px;border-bottom:1px solid var(--line);padding-bottom:6px}}
p{{color:var(--mut);margin:4px 0 16px;max-width:70ch}}
figure{{margin:0 0 28px;background:var(--card);border:1px solid var(--line);border-radius:6px;padding:8px}}
img{{width:100%;height:auto;display:block}} figcaption{{font-size:14px;color:var(--mut);padding:6px 4px 0}}
</style></head><body><main><h1>v3.0 デモの道具の組み込み</h1>
<p>デルタもんの迷路のデモで使った道具を 4 つアドオンに入れた。画像はクリックで原寸。</p>
{''.join(parts)}</main></body></html>"""
    (ROOT / "index.html").write_text(html, encoding="utf-8")
    print(ROOT / "index.html")


if __name__ == "__main__":
    main()
