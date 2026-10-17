"""手作業デモの 4K 版を組む: F12 で 4K に撮った各段階(girl_4k_states.py)に、字幕・直す所を囲む四角・
操作画面の小窓(gui_girl_ui.py)を重ねて、30fps の mp4 にする。

  python assemble_girl_4k.py <states_dir> <ui_dir> <out.mp4> [--width 3840]
"""
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ST, UI, OUT = (Path(a).resolve() for a in sys.argv[1:4])
ARGV = sys.argv[4:]
W = int(ARGV[ARGV.index("--width") + 1]) if "--width" in ARGV else 3840
H = W * 9 // 16
K = W / 3840
FPS = 30
FB = ImageFont.truetype("C:/Windows/Fonts/meiryob.ttc", int(76 * K))
FS = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", int(48 * K))
FT = ImageFont.truetype("C:/Windows/Fonts/meiryob.ttc", int(40 * K))


def load(name):
    im = Image.open(ST / f"{name}.png").convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    if name in ("s0_model", "s6_material_lines"):
        bg = Image.new("RGBA", im.size, (0, 0, 0, 255))
    bg.alpha_composite(im)
    return bg.convert("RGB").resize((W, H), Image.LANCZOS)


IM = {n: load(n) for n in ("s0_model", "s1_step0", "s2_mouth", "s3_buttons", "s4_hair", "s5_cel")}
panel = Image.open(UI / "panel.png").convert("RGB").crop((1105, 315, 1335, 800))
prog_src = sorted(UI.glob("progress_*.png"))
prog = Image.open(prog_src[-1]).convert("RGB") if prog_src else None

MOUTH = (0.39, 0.47, 0.49, 0.58)
BUTTONS = (0.40, 0.62, 0.50, 0.84)
HAIR = (0.40, 0.14, 0.64, 0.58)
ORANGE = (255, 120, 30)


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def caption(img, title, sub="", alpha=1.0):
    if not title or alpha <= 0:
        return img
    d = ImageDraw.Draw(img, "RGBA")
    tw = d.textlength(title, font=FB)
    sw = d.textlength(sub, font=FS) if sub else 0
    bw = max(tw, sw) + 120 * K
    bh = (76 + (48 + 26 if sub else 0) + 70) * K
    x0 = (W - bw) / 2
    y0 = H - bh - 70 * K
    a = int(200 * alpha)
    d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=int(18 * K), fill=(18, 18, 22, a))
    d.text(((W - tw) / 2, y0 + 30 * K), title, font=FB, fill=(255, 255, 255, int(255 * alpha)))
    if sub:
        d.text(((W - sw) / 2, y0 + (30 + 76 + 22) * K), sub, font=FS, fill=(255, 205, 140, int(255 * alpha)))
    return img


def marquee(img, rect, p, alpha=1.0):
    """人が左上から右下へ囲むように伸びる四角。"""
    if rect is None or alpha <= 0:
        return img
    p = ease(p)
    x0, y0, x1, y1 = rect
    r = [x0 * W, y0 * H, (x0 + (x1 - x0) * p) * W, (y0 + (y1 - y0) * p) * H]
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    d.rectangle(r, fill=(*ORANGE, int(30 * alpha)), outline=(*ORANGE, int(240 * alpha)), width=max(2, int(6 * K)))
    if 0 < p < 1:      # 筆先(マウス)
        cx, cy = r[2], r[3]
        rr = 14 * K
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(*ORANGE, int(255 * alpha)))
    out = img.convert("RGBA")
    out.alpha_composite(ov)
    return out.convert("RGB")


def inset(img, ui, box_w, label, alpha=1.0, pos="right"):
    """操作画面の小窓(右上)。"""
    if ui is None or alpha <= 0:
        return img
    s = box_w / ui.width
    u = ui.resize((int(ui.width * s), int(ui.height * s)), Image.LANCZOS)
    pad = int(36 * K)
    x = W - u.width - pad * 2 if pos == "right" else pad
    y = pad * 2
    frame = Image.new("RGBA", (u.width + 2 * int(8 * K), u.height + 2 * int(8 * K) + int(60 * K)), (30, 30, 34, 235))
    d = ImageDraw.Draw(frame)
    d.text((int(16 * K), int(10 * K)), label, font=FT, fill=(255, 205, 140, 255))
    frame.paste(u, (int(8 * K), int(60 * K) + int(8 * K)))
    sh = Image.new("RGBA", (frame.width + 40, frame.height + 40), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle([20, 20, frame.width + 20, frame.height + 20], fill=(0, 0, 0, 120))
    sh = sh.filter(ImageFilter.GaussianBlur(14))
    out = img.convert("RGBA")
    if alpha < 1:
        frame.putalpha(frame.getchannel("A").point(lambda v: int(v * alpha)))
        sh.putalpha(sh.getchannel("A").point(lambda v: int(v * alpha)))
    out.alpha_composite(sh, (x - 14, y - 6))
    out.alpha_composite(frame, (x, y))
    return out.convert("RGB")


def blend(a, b, t):
    return Image.blend(IM[a], IM[b], ease(t)) if t > 0 else IM[a].copy()


def wipe(a, b, t, soft=0.03):
    """左から右へ a → b。境目に細い白い線。"""
    t = ease(t)
    A, B = np.asarray(IM[a], np.float32), np.asarray(IM[b], np.float32)
    x = np.linspace(0, 1, W)[None, :, None]
    m = np.clip((t * (1 + soft) - x) / soft, 0, 1)
    out = A * (1 - m) + B * m
    edge = int(t * (1 + soft) * W - soft * W / 2)
    if 0 < edge < W:
        out[:, max(0, edge - int(3 * K)):edge + int(3 * K)] = 255
    return Image.fromarray(out.astype(np.uint8))


# ---------------------------------------------------------------- 台本 (秒, 描く関数)
SCRIPT = []


def seg(sec, fn):
    SCRIPT.append((sec, fn))


C0 = ("anime-girl（元の 3D）", "FreePencil2 v2.9 で、線画を手作業で仕上げる")
seg(3.0, lambda t: caption(IM["s0_model"].copy(), *C0, alpha=min(1, t * 3)))
seg(3.0, lambda t: caption(inset(IM["s0_model"].copy(), panel, 560 * K, "STEP0：仕上がり＝キャラ", min(1, t * 4)),
                           "STEP0（キャラ）を押す", "塗り分け → AOV → 線画のコンポジタ を全自動で"))
seg(2.2, lambda t: caption(inset(IM["s0_model"].copy(), prog, 1100 * K, "STEP1/3 塗り分け中", 1.0),
                           "STEP0（キャラ）を押す", "塗り分け → AOV → 線画のコンポジタ を全自動で"))
seg(1.2, lambda t: blend("s0_model", "s1_step0", t))
C1 = ("STEP0 だけ", "口が無い ／ ボタンが黒い棒 ／ 髪は輪郭だけ")
seg(3.2, lambda t: caption(IM["s1_step0"].copy(), *C1, alpha=min(1, t * 3)))
for a, b, rect, title, sub in (
        ("s1_step0", "s2_mouth", MOUTH, "口：顔の絵（テクスチャ）の線を、口のまわりだけ",
         "目は形の線のまま（絵の瞳は細かすぎて黒く潰れる）"),
        ("s2_mouth", "s3_buttons", BUTTONS, "ボタン：服の絵の線を、ボタンのまわりだけ", "淡い陰は線にしない（強さ 0.3）"),
        ("s3_buttons", "s4_hair", HAIR, "髪：髪の絵の筋を、弱めに足す", "前髪の筋とポニーテール（強さ 0.25）")):
    seg(1.0, lambda t, a=a, rect=rect, title=title, sub=sub: caption(marquee(IM[a].copy(), rect, t), title, sub))
    seg(0.6, lambda t, a=a, rect=rect, title=title, sub=sub: caption(marquee(IM[a].copy(), rect, 1), title, sub))
    seg(1.0, lambda t, a=a, b=b, rect=rect, title=title, sub=sub:
        caption(marquee(blend(a, b, t), rect, 1, 1 - t * 0.5), title, sub))
    seg(1.8, lambda t, b=b, rect=rect, title=title, sub=sub:
        caption(marquee(IM[b].copy(), rect, 1, max(0, 0.5 - t)), title, sub))
seg(3.0, lambda t: caption(IM["s4_hair"].copy(), "仕上がり（線画）", "STEP0 ＋ 手直し 3 つ"))
seg(1.2, lambda t: blend("s4_hair", "s5_cel", t))
seg(3.5, lambda t: caption(IM["s5_cel"].copy(), "セル（影と色）", "STEP3 のプレビューで「セル」"))
def split(edge, labels=0.0):
    """左が元の 3D、右が仕上がり。edge は境目の位置(0〜1)。"""
    e = int(edge * W)
    out = IM["s5_cel"].copy()
    if e > 0:
        out.paste(IM["s0_model"].crop((0, 0, e, H)), (0, 0))
        d = ImageDraw.Draw(out)
        d.rectangle([e - int(3 * K), 0, e + int(3 * K), H], fill=(255, 255, 255))
    if labels > 0:
        d = ImageDraw.Draw(out, "RGBA")
        for txt, cx in (("元の 3D", e / 2), ("FreePencil", e + (W - e) / 2)):
            tw = d.textlength(txt, font=FB)
            d.rounded_rectangle([cx - tw / 2 - 30 * K, 60 * K, cx + tw / 2 + 30 * K, 170 * K], radius=int(16 * K),
                                fill=(18, 18, 22, int(190 * labels)))
            d.text((cx - tw / 2, 72 * K), txt, font=FB, fill=(255, 255, 255, int(255 * labels)))
    return out


seg(1.0, lambda t: split(0.5 * ease(t)))
seg(2.2, lambda t: split(0.5, min(1, t * 4)))
seg(0.8, lambda t: split(0.5 * (1 - ease(t))))
seg(2.5, lambda t: caption(IM["s5_cel"].copy(), "FreePencil2 v2.9", "Blender 4.2 / 4.3 / 4.5 / 5.2"))

# ---------------------------------------------------------------- 書き出す
OUT.parent.mkdir(parents=True, exist_ok=True)
FF = imageio_ffmpeg.get_ffmpeg_exe()
proc = subprocess.Popen([FF, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow",
                         "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUT)],
                        stdin=subprocess.PIPE)
n = 0
stills = OUT.parent / (OUT.stem + "_stills")
stills.mkdir(exist_ok=True)
for k, (sec, fn) in enumerate(SCRIPT):
    frames = max(1, int(round(sec * FPS)))
    for f in range(frames):
        img = fn(f / max(1, frames - 1))
        proc.stdin.write(img.tobytes())
        if f == frames - 1:
            img.resize((960, 540)).save(stills / f"{k:02d}.png")
        n += 1
proc.stdin.close()
proc.wait()
print(OUT, f"{n / FPS:.1f}s {W}x{H}")
