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
    ("追加(11/1 夜): アニメでも影の形と日をそのコマに合わせる",
     "影の形(骨の筒・頭の球)は作ったときのポーズのまま頂点カラーに残るので、ふつうのアニメのレンダー(Ctrl+F12)では"
     "腕や脚が動いても影は作ったコマの形のままだった。デモは 1 コマずつ手で作り直して撮っていた。"
     "セルの「影の形」の下に「影の形を追ってアニメをレンダー」を足した。1 コマずつ進め、骨で動く物の影の形を作り直して"
     "(ポーズが同じなら飛ばす)出力先に撮る。デルタもん 9 コマで、手で作り直した絵と全コマ 1 画素も違わない"
     "(1 コマ約 5.7 秒、Esc で止まる)。<br>"
     "調べる途中で、Ctrl+F12 の「カメラから」の日が<b>前のコマのカメラ</b>で回っていたのも見つけた。アニメのレンダーでは"
     "元のカメラがそのコマに進まないため、床の影がコマを追うごとにずれた(296〜304 コマで画面の 11〜20% が違う)。"
     "そのコマの評価済みのカメラを読むように直し、違いは 1 コマあたり 150〜340 画素(0.05% 前後)になった。"
     "残りは、評価の後に日を回すと Blender が少し前の日で影を描くため。<br>"
     "Ctrl+F12 の途中で影の形を作り直す案は、骨で動く体を評価し直すと体が 4 m ずれ、骨に印を付け直すと Blender が落ちたので"
     "やめた。",
     [("shade_render/sheet_304.png", "304 コマ。左上 前の Ctrl+F12(床の影が後ろに出る)| 右上 直した Ctrl+F12(床の影は合う・"
       "脚の影は 260 コマの形)| 左下 新しいボタン | 右下 基準(手で作り直して静止画)。新しいボタンと基準は 0 画素の違い。"
       ".blend: shade_render/shade_render.blend"),
      ("shade_render/sheet_300.png", "300 コマ。並びは同じ"),
      ("shade_render/sheet_296.png", "296 コマ(アニメの最初のコマ)。並びは同じ")]),
    ("追加(11/1 夜): 公開前の撮り直し — 作例 66 体",
     "1 巡目 31 体 + MMD 4 体(10/25 と比べる)と、2 巡目 31 体(10/30 と比べる)を今のコードで撮り直した。"
     "2 巡目は 31 体すべて 10/30 と 1 画素も変わらず、STEP0 は合計 576 → 422 秒(C62 128 → 96 秒、戦車 75 → 54 秒)。"
     "1 巡目の変化は 10/25 以降に入れた意図した変化(キャラの線 0.25、アニメの影色、金属とガラスの色、葉のかたまり)。"
     "椅子の足掛けと機動隊の面が白くなったのは、材質が銀の金属で、金属の地の色を出すようにしたため(3D の絵が黒いのは"
     "写り込む周りが無いだけ)。",
     [("../../../22_FreePencil/dev/batch/out/v30_rc/compare_mmd.png", "MMD 4 体。白 10/25 | 白 今 | セル 10/25 | セル 今"),
      ("../../../22_FreePencil/dev/batch/out/v30_rc/compare_01.png", "1 巡目の変化の大きい順(1 枚目)"),
      ("../../../22_FreePencil/dev/batch/out/v30_rc/zoom_chair_zombie.png", "椅子と機動隊の寄り"),
      ("../../../22_FreePencil/dev/batch/out/v30_holdout_rc/compare_01.png", "2 巡目。一番変わった物でも 0.0%")]),
    ("追加(11/1 夜): 床の影のちらつきを直した",
     "迷路の場面は影を落とす面の光が 14 個あり、EEVEE の影のプール 512MB では 4K で影のページが倍ほど足りなかった"
     "(Shadow buffer full 4014 / 2048)。キャラの床の影が抜け、同じコマを撮るたびに床の影が変わった。"
     "セルを立てるとき、日以外の影を落とす光が 4 個以上なら影のプールを一番大きく(1024MB)する。"
     "「FreePencil を外す」で元に戻る。10/31 の迷路の動画は 512MB で撮ったので、床の影が欠けて揺れている恐れがある。",
     [("shadow/cmp_shadow_fix.png", "上: 前(512MB)を 2 回 / 下: 今回(STEP0 → セルで自動 1024MB)を 2 回。違う所 0 px。"
       ".blend: shadow/after/shadow_after.blend"),
      ("shadow/cmp_pool.png", "プールの大きさだけ変えて同じコマを 2 回ずつ")]),
    ("追加(11/1 夜): 材質の名前で分からない顔も顔に",
     "天宮翼は材質の名前が絵の名前で、顔の物が体・服・髪と同じ材質だった。表情のシェイプキーが 5 個以上あって"
     "頭の骨に付いた物を顔とする(物の fp_face)。顔の名前の材質を持つ物には付けないので、デルタもんは何も変わらない"
     "(セルの絵が前と 0 px の違い)。",
     [("face/cmp_face.png", "顔。顔の大きな影と、白目の影の色が消えた。.blend: face/tsubasa_face.blend"),
      ("face/cmp_main.png", "全身。顔のほかは同じ")]),
    ("追加(11/1 夜): もう一段速く — STEP0 19.0 → 12.3 秒(塗り分けの中核に触るので採用は相談)",
     "weld_seams(行ごとの unique と全部の点での bincount をやめた)・手の判定(1 体 1 回)はコミット済み。"
     "残りは vertex_color.py(中核): 骨の塗りを 48 万角ぶん 1 つずつ Python で書いていたのをまとめて書き、"
     "ぼかしの np.add.at を bincount に。色の種を固定して比べると、52 個の色の層がすべて 1 ビットも変わらない。"
     "白いプレビューは違う所 0 px。セルの違いは床の影だけで、点の光 63 個の影のバッファあふれ(同じ設定で 2 回撮っても変わる所)。",
     [("speed/cmp_vc.png", "前(HEAD)と今回。種は 12345 に固定。.blend: speed/v_new/step0.blend")]),
    ("追加(11/1 夕): 速くした — 影の形の書き直し 18.7 → 5.5 秒、STEP0 22.0 → 17.4 秒",
     "デルタもん(48 万面)の迷路 br_dm5、300 コマ。遅かったのは np.add.at(影の形の書き直しの半分)と、"
     "Python の union-find(1 体で 1 秒以上)、切れ目の色ぼかしで全部の辺を 64 回足していたところ。"
     "bincount と mesh_islands.connected_components(呼ぶだけ、中核は変えていない)に置き換え。"
     "違う所の赤は線の縁の 1 px のぶれ(同じ設定で 2 回撮っても出る程度)。右の床の赤い塊は、"
     "点の光 63 個で影のバッファがあふれて床の影が毎回変わるため(今回の変更と無関係。本番でちらつく恐れ)。",
     [("speed/s0_final/cel_300_crop.png", "コミットしたコードで STEP0 からセルまで(.blend: speed/s0_final/speed_after.blend)"),
      ("speed/cmp_bake3.png", "セル。キャラの影の形の書き直しだけ。前 18.7 秒 / 今回 5.5 秒"),
      ("speed/cmp_step0.png", "STEP0 から全部。上: 白いプレビュー / 下: セル"),
      ("speed/cmp_step0_zoom.png", "いちばん赤が多かった髪とランドセルの所を 3 倍。見分けられない")]),
    ("追加(11/1 午後): 遠景の窓の線は退行ではなかった",
     "窓の線が消えたのは d86a34a(画面で 150px² 未満の区画をまとめる。AI のメカの黒い点のため)から。"
     "STEP0 のカメラ(左)では、奥の壁が黒い格子の塊から輪郭だけになった。望遠(右)は塗りを STEP0 のカメラで"
     "決めたあとで撮り方だけ変えた場面で、手描き背景の基準と同じ見え方。基準を今の絵に更新するかは要相談。",
     [("bisect_facade.png", "コミットごとの facades(精密)。左 24mm、右 300mm で奥の壁")]),
    ("追加: 天宮翼(VRoid、VRM 0.x)で確かめた",
     "見つけて直したもの 3 つ: ① 本物の VRM は MToon の出力がグループのノードで、STEP0 が落ちた"
     "(5.2 向けの直しで入れた不具合。テストもグループのノードに)② 顔のアップが全身の絵を上書きした(名前に _face を付ける)"
     "③ 手ごと 1 色で指の間の線まで消えた → 指の重みが節ごとに切り替わるモデル(デルタもん)だけにした。",
     [("tsubasa/cmp_main.png", "全身。左: 目・手・口の処理なし / 右: あり"),
      ("tsubasa/cmp_face.png", "顔。口の線が出る(Fcl_MTH_A)。顔に大きな影が出るのは、この子の材質名が絵の名前で"
       "顔と服が同じ材質のため(材質名で顔を見分けられない。別の課題)"),
      ("cmp_hands_rule.png", "手。天宮翼は重みがなだらかで節に線が無いので触らない、デルタもんは前と同じ")]),
    ("試してやめた手の直し方",
     "指ごと・甲ごとに面で塗ると、重みで混ぜた色との境に段ができ、拳にぎざぎざの線が出た。",
     [("tsubasa/cmp_hands4.png", "甲と指を別の色に(重みの多い組へ)"),
      ("tsubasa/cmp_hands5.png", "指の節を付け根の色に")]),

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
     "facades_precise_far_zoom の窓の線が消えたのは意図どおり(上の「遠景の窓の線」)で、基準は今の絵に更新済み。",
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
