"""boy(骨の無い人物)の線の手直しを HTML にする。前と後を、回転の動画と 4 方向で大きく並べる。

  python build_boy_report.py

前: out/tt_models/boy/white/fNNN.png(STEP0 のまま)
後: out/tt_models/boy/boy_fixed/fNNNN.png(奥行きの線 2.0 + 絵の線 強さ 0.5・ぼかし 4、tabletown_fix.py)
試し: arm_depth / arm_inner / arm_inner2 / tex_b4 / c1_d2_t4 / c3_d2_t8(23, 68 は横から)
出力: dev/batch/out/report_boy/report.html
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

HERE = Path(__file__).resolve().parent
D = HERE / "out" / "tt_models" / "boy"
BATCH = HERE.parent / "batch"
FF = imageio_ffmpeg.get_ffmpeg_exe()


def rel(p: Path) -> str:
    return str(Path("..") / p.relative_to(HERE.parent)).replace("\\", "/")


def mp4(pattern: str, out: Path) -> Path:
    subprocess.run([FF, "-y", "-loglevel", "error", "-framerate", "30", "-i", pattern,
                    "-vf", "scale=1280:720:flags=lanczos", "-c:v", "libx264", "-crf", "18",
                    "-pix_fmt", "yuv420p", str(out)], check=True)
    return out


before = mp4(str(D / "white" / "f%03d.png"), D / "turn.mp4")
after = mp4(str(D / "boy_fixed" / "f%04d.png"), D / "turn_fixed.mp4")
A = {0: 1, 90: 23, 180: 46, 270: 68}


def b(a):
    return {"src": rel(D / "white" / f"f{A[a]:03d}.png"), "label": f"前 {a}°"}


def f(a):
    return {"src": rel(D / "boy_fixed" / f"f{A[a]:04d}.png"), "label": f"後 {a}°"}


def t(name, a, label):
    return {"src": rel(D / name / f"f{A[a]:04d}.png"), "label": label}


rows_main = [
    {"caption": "1 周(3 秒)。左が前、右が後", "images": [
        {"video": rel(before), "label": "前: STEP0 のまま"},
        {"video": rel(after), "label": "後: 奥行きの線 2.0 + 絵の線(強さ 0.5、ぼかし 4)"}]},
    {"caption": "横から(右を向いた所)。前は腕が胴に溶けて消えていた", "images": [b(90), f(90)]},
    {"caption": "横から(左を向いた所)", "images": [b(270), f(270)]},
    {"caption": "正面。前は目鼻が薄く、服は輪郭だけだった", "images": [b(0), f(0)]},
    {"caption": "後ろ", "images": [b(180), f(180)]},
    {"caption": "セル(後)", "images": [
        {"src": rel(D / "boy_fixed_render" / "cel" / "f0001.png"), "label": "セル 0°"},
        {"src": rel(D / "boy_fixed_render" / "cel" / "f0023.png"), "label": "セル 90°"}]},
]
rows_trials = [
    {"caption": "腕を出す: 奥行きの線を強く(2.0)と、内側の線(滑らかな形の谷)を比べた", "images": [
        t("arm_depth", 90, "奥行きの線 2.0 — 腕と手の輪郭が細くきれいに出る(採用)"),
        t("arm_inner", 90, "内側の線 1.0 — 腕は出るが、袖口やしわまで灰色の線が増える")]},
    {"caption": "", "images": [
        t("arm_inner2", 90, "内側の線 2.0 — さらに増える"),
        t("arm_depth", 270, "奥行きの線 2.0、反対側 — こちらも腕が出る")]},
    {"caption": "顔と服を出す: 絵の線の強さとぼかしを比べた(どれも奥行きの線 2.0)", "images": [
        t("c1_d2_t4", 0, "強さ 1.0、ぼかし 4 — 鼻のまわりが黒く潰れ、靴も黒い"),
        t("c2_d2_t4s05", 0, "強さ 0.5、ぼかし 4 — 目・眉・鼻・口が出て、潰れない(採用)")]},
    {"caption": "", "images": [
        t("c3_d2_t8", 0, "強さ 1.0、ぼかし 8 — 潰れは少し減るが、まだ黒い"),
        t("tex_b4", 0, "奥行きの線なし、強さ 1.0、ぼかし 4 — 正面は c1 と同じ")]},
]
spec = {"out": "out/report_boy", "title": "骨の無い人物(boy)の線",
        "intro": "AI が作った人物は骨(アーマチュア)が無く、腕と胴が 1 つの形でつながっている。"
                 "骨で塗り分けられないので、横から見ると腕が胴に溶けて消え、顔や服も輪郭だけになった。<br>"
                 "アドオン本体は変えず、今ある 2 つの手を当てた: "
                 "<b>奥行きの線の強さ 2.0</b>(シーンの設定 fp_ch_depth。胴の手前にある腕の縁を奥行きの差で拾う)と、"
                 "<b>絵の線</b>(ai.texture_lines、強さ 0.5・ぼかし 4。顔や服は絵にしか描かれていない)。<br>"
                 "画像はクリックで原寸。.blend は dev/note_assets/out/tt_models/boy/boy_fixed.blend。"
                 "3D model by Scenario(CC BY 4.0)",
        "sections": [{"title": "前と後", "text": "", "rows": rows_main},
                     {"title": "試したもの", "text": "決めるまでに比べた絵。", "rows": rows_trials}]}
p = BATCH / "out" / "report_boy.json"
p.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
subprocess.run([sys.executable, str(BATCH / "make_findings_report.py"), str(p)], check=True, cwd=BATCH)
