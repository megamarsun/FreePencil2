"""MMD 4 体のダンスで v3.0 のセル(影の形・アニメの影色・リム)を見せるデモを組む。

  python assemble_v30_dance.py <d4k4 の dir> <v3.0 の連番の dir> <out.mp4> [--width 3840]
          [--sub 2 --model <元の 3D の 2 分割の連番の dir>]

<d4k4>/Four_model(元の 3D)・Four_cel(v2.9 のセル)と、mmd_v30_render.py の <v3.0>/group・close0〜3 を使う。
流れ(1 回のダンスを止めずに見せ方を変える):
  元の 3D → 境目が横切って v2.9 のセル → 境目が横切って v3.0 → v3.0
  → 4 体の顔のアップ(v3.0、2x2) → クレジット
--sub 2: 60 コマ/秒。v3.0 と元の 3D は 1 コマを 2 つに割って撮った連番(<f>_<0|1>.png)を使う。
         v2.9 のセル(30 コマ)は同じ絵を 2 回出す
"""
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

D, V3, OUT = (Path(a).resolve() for a in sys.argv[1:4])
ARGV = sys.argv[4:]
W = int(ARGV[ARGV.index("--width") + 1]) if "--width" in ARGV else 3840
H = W * 9 // 16
K = W / 3840
SUB = int(ARGV[ARGV.index("--sub") + 1]) if "--sub" in ARGV else 1
FPS = 30 * SUB
F0 = 300
FB = ImageFont.truetype("C:/Windows/Fonts/meiryob.ttc", int(76 * K))
FS = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", int(46 * K))
FC = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", int(38 * K))
NAMES = ["ニコニ立体ちゃん", "ミライアカリ", "初音ミク（Tda式 改変）", "サーバル"]
SRC = {"model": D / "Four_model", "v29": D / "Four_cel", "v30": V3 / "group"}
SPLIT = set()                                         # 1 コマを SUB に割って撮った連番
if SUB > 1:
    SPLIT = {"v30", "close"}
    if "--model" in ARGV:
        SRC["model"] = Path(ARGV[ARGV.index("--model") + 1]).resolve()
        SPLIT.add("model")


def src(mode, h, d=None):
    """h = F0 からの 1/SUB コマの番号。"""
    d = d or SRC[mode]
    f, j = F0 + h // SUB, h % SUB
    return d / (f"{f:04d}_{j}.png" if mode in SPLIT else f"{f:04d}.png")
_cache = {}


def frame(mode, f, size=(W, H)):
    key = (mode, f, size)
    if key in _cache:
        return _cache[key]
    im = Image.open(src(mode, f)).convert("RGBA")
    bg = Image.new("RGBA", im.size, (13, 13, 15, 255) if mode == "model" else (255, 255, 255, 255))
    bg.alpha_composite(im)
    im = bg.convert("RGB")
    if im.size != size:
        im = im.resize(size, Image.LANCZOS)
    if len(_cache) > 12:
        _cache.clear()
    _cache[key] = im
    return im


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def caption(img, title, sub="", alpha=1.0):
    if alpha <= 0:
        return img
    img = img.copy()                      # frame() の絵は使い回すので、字幕を焼き込まない(クレジットに残った)
    d = ImageDraw.Draw(img, "RGBA")
    tw = d.textlength(title, font=FB)
    sw = d.textlength(sub, font=FS) if sub else 0
    bw = max(tw, sw) + 120 * K
    bh = (76 + (46 + 26 if sub else 0) + 70) * K
    x0, y0 = (W - bw) / 2, H - bh - 60 * K
    d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=int(18 * K), fill=(18, 18, 22, int(190 * alpha)))
    d.text(((W - tw) / 2, y0 + 30 * K), title, font=FB, fill=(255, 255, 255, int(255 * alpha)))
    if sub:
        d.text(((W - sw) / 2, y0 + (30 + 76 + 22) * K), sub, font=FS, fill=(255, 205, 140, int(255 * alpha)))
    return img


def wipe(a, b, f, t):
    """左から右へ a → b。境目に白い線。"""
    A, B = np.asarray(frame(a, f)), np.asarray(frame(b, f))
    e = int(ease(t) * W)
    out = A.copy()
    out[:, :e] = B[:, :e]
    if 0 < e < W:
        out[:, max(0, e - int(4 * K)):e + int(4 * K)] = 255
    return Image.fromarray(out)


def faces(f, t_in):
    """4 体の顔のアップ(v3.0)を 2x2 に。キャラごとに頭を追うカメラ(mmd_v30_render.py --cam close<k>)。"""
    out = Image.new("RGB", (W, H), (255, 255, 255))
    cw, ch = W // 2, H // 2
    for i in range(4):
        tile = Image.open(src("close", f, V3 / f"close{i}")).convert("RGB")
        if tile.size != (cw, ch):
            tile = tile.resize((cw, ch), Image.LANCZOS)
        out.paste(tile, ((i % 2) * cw, (i // 2) * ch))
        d = ImageDraw.Draw(out, "RGBA")
        tx, ty = (i % 2) * cw + 30 * K, (i // 2) * ch + 24 * K
        tw = d.textlength(NAMES[i], font=FS)
        a = min(1, t_in * 4)
        d.rounded_rectangle([tx - 16 * K, ty - 8 * K, tx + tw + 16 * K, ty + 64 * K], radius=int(12 * K),
                            fill=(18, 18, 22, int(180 * a)))
        d.text((tx, ty), NAMES[i], font=FS, fill=(255, 255, 255, int(255 * a)))
    d = ImageDraw.Draw(out)
    d.line([W // 2, 0, W // 2, H], fill=(255, 255, 255), width=int(6 * K))
    d.line([0, H // 2, W, H // 2], fill=(255, 255, 255), width=int(6 * K))
    return out


# ---------------------------------------------------------------- 台本: (コマ数, f(i) -> 絵)
SEQ = []


def seg(n, fn):
    SEQ.append((n, fn))


T1 = ("MMD 4 体 × FreePencil2 v3.0", "セルの影を、アニメの影に")
V29 = ("v2.9 のセル", "日は正面から。影はほとんど付かない")
V30 = ("v3.0 のセル", "影の形をすっきり・アニメの影色")
V30B = ("v3.0 のセル", "順光の影に、逆光をリムとして足す")
N = SUB                                               # 30 コマ/秒の 1 コマが何コマか
seg(90 * N, lambda i: caption(frame("model", i), *T1, alpha=min(1, i / (15 * N))))
seg(30 * N, lambda i: caption(wipe("model", "v29", 90 * N + i, i / (30 * N - 1)), *V29))
seg(30 * N, lambda i: caption(frame("v29", 120 * N + i), *V29))
seg(45 * N, lambda i: caption(wipe("v29", "v30", 150 * N + i, i / (45 * N - 1)), *V30))
seg(55 * N, lambda i: caption(frame("v30", 195 * N + i), *V30))
seg(50 * N, lambda i: caption(frame("v30", 250 * N + i), *V30B))
# 顔の場面は、4 体とも正面を向いているところだけ(373〜404 は回って横顔・後ろ髪になる)。
# つなぎ目はぱっと飛ばさず、XF コマで重ねて移る
FACE_A = list(range(0, 73 * N))
FACE_B = list(range(105 * N, 150 * N))
XF = 8 * N


def face_seq(i):
    n = len(FACE_A) + len(FACE_B) - XF
    if i < len(FACE_A) - XF:
        return faces(FACE_A[i], i / n)
    if i < len(FACE_A):
        k = i - (len(FACE_A) - XF)
        a, b = faces(FACE_A[i], 1.0), faces(FACE_B[k], 1.0)
        return Image.blend(a, b, ease((k + 1) / (XF + 1)))
    return faces(FACE_B[i - len(FACE_A) + XF], 1.0)


seg(len(FACE_A) + len(FACE_B) - XF, face_seq)


def credits(i):
    img = frame("v30", 300 * SUB - 1).copy()
    ov = Image.new("RGBA", img.size, (255, 255, 255, 215))
    img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
    d = ImageDraw.Draw(img)
    lines = [("FreePencil2 v3.0（開発中）", FB), ("Blender 4.2 / 4.3 / 4.5 / 5.2", FS), ("", FC),
             ("ニコニ立体ちゃん ©dwango, inc.（モーション：2分ループステップ8）", FC),
             ("ミライアカリ (c)Mirai Akari Project", FC),
             ("Tda式初音ミク 改変：Hiro_K", FC), ("サーバル（MMD モデル）", FC)]
    y = H * 0.28
    for t, fnt in lines:
        tw = d.textlength(t, font=fnt)
        d.text(((W - tw) / 2, y), t, font=fnt, fill=(30, 30, 34))
        y += (fnt.size + 26 * K)
    return img


seg(90 * SUB, lambda i: credits(i // SUB))

FF = imageio_ffmpeg.get_ffmpeg_exe()
OUT.parent.mkdir(parents=True, exist_ok=True)
proc = subprocess.Popen([FF, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "17",
                         "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUT)], stdin=subprocess.PIPE)
stills = OUT.parent / (OUT.stem + "_stills")
stills.mkdir(exist_ok=True)
n = 0
for k, (cnt, fn) in enumerate(SEQ):
    for i in range(cnt):
        img = fn(i)
        if img.size != (W, H):
            img = img.resize((W, H))
        proc.stdin.write(img.tobytes())
        if i == cnt // 2:
            img.resize((960, 540)).save(stills / f"{k:02d}.png")
        n += 1
proc.stdin.close()
proc.wait()
print(OUT, f"{n / FPS:.1f}s {W}x{H}")
