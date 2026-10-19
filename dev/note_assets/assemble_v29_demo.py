"""FreePencil2 v2.9 のデモ(曲 Shinjuku Horizon、2:01.8、123 BPM)を組む。

  python assemble_v29_demo.py <r4k_dir> <song.mp3> <out.mp4> [--width 3840] [--from 0] [--to 121.8]

カットは全部小節(1 小節 = 60/123*4 秒)にそろえる。撮れていないコマは、その見せ方で撮れている
いちばん近いコマで代える(撮影の途中でも流れを確かめられるように)。

  0– 2 小節  前奏: タイトル(C62 のセルの 1 コマ目に、黒から明ける)
  2–14       風景: C62 × 鉄橋 × 下町(セル)。最後に元の 3D から境目が横切ってセルへ
 14–24       キャラ: anime-girl 回り込み 3D → STEP0 だけ → 手直しの後 → セル
 24–40       メカ: 戦車 / C58 / スポーツカー / 産業用ロボット(各 4 小節、3D → 線画 → セル)
 40–48       間奏: AI の手直しの前後(殻 / 目のフチ / 継ぎ目 / 線画の目)
 48–60       ダンス: MMD 4 体 3D → セル → 線画 → 顔のアップ → セル
 60–終わり   クレジット
"""
import bisect
import json
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

R, SONG, OUT = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve()
ARGV = sys.argv[4:]
W = int(ARGV[ARGV.index("--width") + 1]) if "--width" in ARGV else 3840
T_FROM = float(ARGV[ARGV.index("--from") + 1]) if "--from" in ARGV else 0.0
T_TO = float(ARGV[ARGV.index("--to") + 1]) if "--to" in ARGV else 121.78
H = W * 9 // 16
K = W / 3840
FPS = 30
BAR = 60 / 123 * 4
REPO = Path(__file__).resolve().parents[2]
FB = ImageFont.truetype("C:/Windows/Fonts/meiryob.ttc", int(92 * K))
FS = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", int(58 * K))
FT = ImageFont.truetype("C:/Windows/Fonts/meiryob.ttc", int(150 * K))
FC = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", int(40 * K))
BG = {"model": (13, 13, 15), "3d": (13, 13, 15)}


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


_IDX, _CACHE = {}, {}


def frame(seq, n, bg="white"):
    """連番のコマ n(無ければいちばん近い撮れたコマ)を W x H で。seq は r4k からのフォルダ。"""
    d = R / seq
    if seq not in _IDX:
        fs = sorted(d.glob("*.png")) if d.exists() else []
        _IDX[seq] = ([int("".join(c for c in p.stem if c.isdigit())) for p in fs], fs)
    nums, fs = _IDX[seq]
    if not fs:
        return Image.new("RGB", (W, H), (60, 60, 60))
    i = bisect.bisect_left(nums, n)
    i = min(range(max(0, i - 1), min(len(nums), i + 1)), key=lambda k: abs(nums[k] - n))
    key = (seq, nums[i])
    if key not in _CACHE:
        im = Image.open(fs[i]).convert("RGBA")
        g = Image.new("RGBA", im.size, bg if isinstance(bg, tuple) else (255, 255, 255))
        g.alpha_composite(im)
        im = g.convert("RGB")
        if im.size != (W, H):
            im = im.resize((W, H), Image.LANCZOS)
        if len(_CACHE) > 16:
            _CACHE.clear()
        _CACHE[key] = im
    return _CACHE[key]


def still(path, fit="contain", bg=(255, 255, 255), crop=None):
    """静止画を W x H に。crop=(x0, y0, x1, y1) は 0..1 で、変わる所に寄る。"""
    key = ("still", str(path), fit, crop)
    if key not in _CACHE:
        im = Image.open(path).convert("RGB")
        if crop:
            im = im.crop(tuple(int(v * (im.width if i % 2 == 0 else im.height)) for i, v in enumerate(crop)))
        s = (min if fit == "contain" else max)(W / im.width, H / im.height)
        im2 = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
        out = Image.new("RGB", (W, H), bg)
        out.paste(im2, ((W - im2.width) // 2, (H - im2.height) // 2))
        _CACHE[key] = out
    return _CACHE[key]


def wipe(a, b, t):
    """左から右へ a → b。境目に白い線。"""
    t = ease(t)
    if t <= 0:
        return a.copy()
    if t >= 1:
        return b.copy()
    A, Bm = np.asarray(a), np.asarray(b)
    e = int(t * W)
    out = A.copy()
    out[:, :e] = Bm[:, :e]
    out[:, max(0, e - int(4 * K)):e + int(4 * K)] = 255
    return Image.fromarray(out)


def caption(img, title, sub="", alpha=1.0, pos="bottom"):
    if not title or alpha <= 0:
        return img
    img = img.copy()
    d = ImageDraw.Draw(img, "RGBA")
    tw = d.textlength(title, font=FB)
    sw = d.textlength(sub, font=FS) if sub else 0
    bw = max(tw, sw) + 110 * K
    bh = (92 + (58 + 26 if sub else 0) + 66) * K
    x0 = 80 * K
    y0 = H - bh - 70 * K if pos == "bottom" else 70 * K
    d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=int(16 * K), fill=(16, 16, 20, int(185 * alpha)))
    d.text((x0 + 55 * K, y0 + 26 * K), title, font=FB, fill=(255, 255, 255, int(255 * alpha)))
    if sub:
        d.text((x0 + 55 * K, y0 + (26 + 92 + 24) * K), sub, font=FS, fill=(255, 205, 140, int(255 * alpha)))
    return img


def fade(img, a, color=(0, 0, 0)):
    if a >= 1:
        return img
    return Image.blend(Image.new("RGB", img.size, color), img, max(0.0, a))


def cap_alpha(t, t0, t1, ramp=0.25):
    return min(1.0, (t - t0) / ramp, (t1 - t) / ramp)


def by_frames(n, plan, seq_of):
    """plan: [(切り替わるコマ, 見せ方), ...]。境目の前後 wipe コマで a → b のワイプ。"""
    for (n0, m0, w), (n1, m1, _w) in zip(plan, plan[1:]):
        if n < n1:
            break
    else:
        return frame(*seq_of(plan[-1][1], n))
    # 次の見せ方へのワイプ(n1 の w コマ前から)
    if n1 - w <= n < n1 and w > 0:
        return wipe(frame(*seq_of(m0, n)), frame(*seq_of(m1, n)), (n - (n1 - w)) / w)
    return frame(*seq_of(m0, n))


# ---------------------------------------------------------------- 場面
def sec_intro(t):
    img = frame("c62/cel", 1)
    img = fade(img, ease(t / (2 * BAR) * 1.6))
    a = cap_alpha(t, 0.5, 2 * BAR + 9, 0.5)
    d = ImageDraw.Draw(img, "RGBA")
    title = "FreePencil2 v2.9"
    tw = d.textlength(title, font=FT)
    d.text(((W - tw) / 2, H * 0.36), title, font=FT, fill=(255, 255, 255, int(255 * a)),
           stroke_width=int(6 * K), stroke_fill=(20, 20, 24, int(255 * a)))
    sub = "3D から、線画とセルへ"
    sw = d.textlength(sub, font=FB)
    d.text(((W - sw) / 2, H * 0.36 + 190 * K), sub, font=FB, fill=(255, 255, 255, int(255 * a)),
           stroke_width=int(4 * K), stroke_fill=(20, 20, 24, int(255 * a)))
    return img


def sec_c62(t):
    n = 1 + int(t * FPS)
    if n < 470:
        img = frame("c62/cel", n)
        return caption(img, "風景：C62 × 鉄橋 × 下町", "STEP0（手描き背景）→ プレビューを「セル」に", cap_alpha(t, 0.4, 7.5))
    if n < 545:
        return caption(frame("c62/3d", n, BG["3d"]), "元の 3D", "", cap_alpha(t, 470 / FPS, 545 / FPS))
    if n < 585:
        return wipe(frame("c62/3d", n, BG["3d"]), frame("c62/cel", n), (n - 545) / 40)
    return caption(frame("c62/cel", n), "FreePencil2 のセル", "", cap_alpha(t, 585 / FPS, 702 / FPS))


def sec_girl(t):
    n = 1 + int(t * FPS)
    plan = [(1, "model", 0), (118, "step0", 18), (235, "fixed", 18), (352, "cel", 18), (99999, "cel", 0)]
    seq = lambda m, k: (f"girl/{m}", k, BG.get(m, "white"))   # noqa: E731
    img = by_frames(n, plan, seq)
    caps = [(1, 117, "キャラ：anime-girl", "元の 3D"), (118, 234, "STEP0（キャラ）を押しただけ", "髪が二重の線 ／ 目のまわりに眼球の丸い線"),
            (235, 351, "手直し：殻を切る・目のフチ・ボタン", "AI の窓口の shells / merge / texture_lines"),
            (352, 585, "セル（影と色）", "日は正面から")]
    for a_, b_, ti, su in caps:
        if a_ <= n <= b_:
            img = caption(img, ti, su, cap_alpha(n / FPS, a_ / FPS, b_ / FPS))
    return img


MECH = [("tank", "メカ：戦車"), ("jnr-c58-steam-lo", "メカ：C58 蒸気機関車"),
        ("lamborghini-revu", "メカ：スポーツカー"), ("robot-kuka-quant", "メカ：産業用ロボット")]


def sec_mech(t):
    k = min(3, int(t / (4 * BAR)))
    tt = t - k * 4 * BAR
    n = 1 + int(tt * FPS)
    m, name = MECH[k]
    plan = [(1, "model", 0), (76, "line", 18), (141, "cel", 22), (99999, "cel", 0)]
    seq = lambda mode, j: (f"mech/{m}/{mode}", j, BG.get(mode, "white"))   # noqa: E731
    img = by_frames(n, plan, seq)
    sub = {1: "元の 3D", 76: "線画（STEP0 精密）", 141: "セル"}
    s = "元の 3D" if n < 76 else ("線画（STEP0 精密）" if n < 141 else "セル")
    return caption(img, name, s, cap_alpha(tt, 0.15, 4 * BAR - 0.1, 0.2))


BREAK = [  # (前, 後, 題, 説明, 寄る四角)
    ("dev/batch/out/girl_demo/k4v3/fp_ai/s1_step0.png", "dev/batch/out/girl_demo/k4v3/fp_ai/s2_noshell.png",
     "殻を切る（shells）", "モデルのトゥーン用の殻で、線が二重になっていた", (0.22, 0.08, 0.70, 0.56)),
    ("dev/batch/out/girl_demo/k4v3/fp_ai/s2_noshell.png", "dev/batch/out/girl_demo/k4v3/fp_ai/s3_eyes.png",
     "目のフチを消す（merge）", "アニメの目は線で描かない", (0.26, 0.23, 0.62, 0.59)),
    ("dev/batch/out/mmd/face/fp_ai/Alicia_fix_4cel_u10_t15.png", "dev/batch/out/mmd/face/fp_ai/seam_weld_cel.png",
     "継ぎ目の線を消す（weld）", "部品を突き合わせたモデルの、見えない継ぎ目", (0.10, 0.25, 0.70, 0.85)),
    ("dev/batch/out/mmd/face/fp_ai/seam_weld.png", "dev/batch/out/mmd/face/fp_ai/Alicia_eye25.png",
     "線画の目（texture_lines）", "目の絵の暗い所だけを線に", (0.28, 0.30, 0.72, 0.74)),
]


def sec_break(t):
    k = min(3, int(t / (2 * BAR)))
    tt = t - k * 2 * BAR
    a, b, ti, su, box = BREAK[k]
    A, Bm = still(REPO / a, "cover", crop=box), still(REPO / b, "cover", crop=box)
    # 前 → 後 を境目でゆっくり(1 小節かけて)。最初の 0.4 小節は前のまま
    img = wipe(A, Bm, (tt - 0.4 * BAR) / (1.0 * BAR))
    img = caption(img, "AI の窓口：" + ti, su, cap_alpha(tt, 0.1, 2 * BAR - 0.05, 0.2), pos="top")
    return img


NAMES = ["ニコニ立体ちゃん", "ミライアカリ", "初音ミク（Tda式 改変）", "サーバル"]


def faces(n, a):
    out = Image.new("RGB", (W, H), (255, 255, 255))
    cw, ch = W // 2, H // 2
    for i in range(4):
        tile = frame(f"dance/Four_close{i}_cel", n).resize((cw, ch), Image.LANCZOS)
        out.paste(tile, ((i % 2) * cw, (i // 2) * ch))
        d = ImageDraw.Draw(out, "RGBA")
        tx, ty = (i % 2) * cw + 30 * K, (i // 2) * ch + 24 * K
        tw = d.textlength(NAMES[i], font=FS)
        d.rounded_rectangle([tx - 16 * K, ty - 8 * K, tx + tw + 16 * K, ty + 64 * K], radius=int(12 * K),
                            fill=(18, 18, 22, int(180 * a)))
        d.text((tx, ty), NAMES[i], font=FS, fill=(255, 255, 255, int(255 * a)))
    d = ImageDraw.Draw(out)
    d.line([W // 2, 0, W // 2, H], fill=(255, 255, 255), width=int(6 * K))
    d.line([0, H // 2, W, H // 2], fill=(255, 255, 255), width=int(6 * K))
    return out


def sec_dance(t):
    n = 300 + int(t * FPS)
    if n < 827:
        plan = [(300, "Four_model", 0), (476, "Four_cel", 50), (720, "Four_line", 25), (827, "Four_line", 0)]
        seq = lambda m, k: (f"dance/{m}", k, BG["model"] if m == "Four_model" else "white")   # noqa: E731
        img = by_frames(n, plan, seq)
        if n < 476:
            img = caption(img, "ダンス：MMD 4 体", "同じ手順で 4 体をアニメの絵に", cap_alpha(t, 0.3, 176 / FPS))
        elif n < 720:
            img = caption(img, "セル", "", cap_alpha(n / FPS, 476 / FPS, 700 / FPS))
        else:
            img = caption(img, "線画", "", cap_alpha(n / FPS, 720 / FPS, 827 / FPS))
        return img
    if n < 944:
        return faces(n, min(1.0, (n - 827) / 15))
    return frame("dance/Four_cel", n)


def sec_credits(t):
    base = frame("dance/Four_cel", 1001)
    a = min(1.0, t / 0.8)
    img = Image.blend(base, Image.new("RGB", (W, H), (255, 255, 255)), 0.82 * a)
    d = ImageDraw.Draw(img)
    lines = [("FreePencil2 v2.9", FB), ("Blender 4.2 / 4.3 / 4.5 / 5.2", FS), ("", FC),
             ("ニコニ立体ちゃん ©dwango, inc.（モーション：2分ループステップ8）", FC),
             ("ミライアカリ (c)Mirai Akari Project", FC), ("Tda式初音ミク 改変：Hiro_K", FC),
             ("サーバル（MMD モデル）", FC), ("3D モデル：BlenderKit", FC), ("音楽：Shinjuku Horizon", FC)]
    y = H * 0.22
    for txt, fnt in lines:
        tw = d.textlength(txt, font=fnt)
        d.text(((W - tw) / 2, y), txt, font=fnt, fill=(30, 30, 34))
        y += fnt.size + 24 * K
    return fade(img, 1 - max(0.0, (t - 3.6) / 1.1))


SECTIONS = [(0, 2, sec_intro), (2, 14, sec_c62), (14, 24, sec_girl), (24, 40, sec_mech),
            (40, 48, sec_break), (48, 60, sec_dance), (60, 99, sec_credits)]


def render_at(t):
    for b0, b1, fn in SECTIONS:
        if t < b1 * BAR:
            return fn(t - b0 * BAR)
    return sec_credits(t - 60 * BAR)


FF = imageio_ffmpeg.get_ffmpeg_exe()
OUT.parent.mkdir(parents=True, exist_ok=True)
n0, n1 = int(T_FROM * FPS), int(T_TO * FPS)
proc = subprocess.Popen([FF, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                         "-r", str(FPS), "-i", "-", "-ss", f"{T_FROM:.3f}", "-t", f"{(n1 - n0) / FPS:.3f}",
                         "-i", str(SONG), "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "slow",
                         "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-shortest",
                         "-movflags", "+faststart", str(OUT)], stdin=subprocess.PIPE)
stills = OUT.parent / (OUT.stem + "_stills")
stills.mkdir(exist_ok=True)
marks = {int(b * BAR * FPS) + int(BAR * FPS) // 2 for b in range(0, 62, 2)}
for n in range(n0, n1):
    img = render_at(n / FPS)
    proc.stdin.write(img.tobytes())
    if n in marks:
        img.resize((960, 540)).save(stills / f"{n:05d}.png")
proc.stdin.close()
proc.wait()
print(OUT, f"{(n1 - n0) / FPS:.1f}s {W}x{H}", json.dumps({"bars": 62}))
