"""FreePencil2 v3.0 デモリール: 迷路の街の全編(fp_v30)と、いろんな作例の回転(turntable_v30)を音楽に合わせてつなぐ。

  python dev/note_assets/v30_reel/assemble_reel.py --music <mp3> --city <film_v30 のコマ> --tt <回転のフォルダ> --out reel.mp4
      [--still 1200,2600]   # その時刻(コマ)の完成の絵を PNG で書き出して終わる(確かめ用)

曲は 160 BPM、1 小節 = 1.5 秒 = 45 コマ(30fps)。区切り 12 / 48 / 78 / 84 / 120 / 123 / 153 秒はどれも小節の頭。
切り替えはすべて小節の頭(ずらさない)。区間ごとに素材を割り当てる表 EDL を作り、1 コマずつ PIL で合成して ffmpeg に流す。
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 2560, 1440, 30
BAR = 45
FF = r"C:/Users/machi/AppData/Roaming/Python/Python313/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe"
FONT_B = r"C:/Windows/Fonts/YuGothB.ttc"
FONT_M = r"C:/Windows/Fonts/YuGothM.ttc"

# 街の全編のカット頭(fp_v30 の撮影と同じ)
CUTS = [1, 297, 568, 808, 995, 1178, 1725, 2055, 2318, 2752, 3016, 3446, 3729, 4059, 4437, 5179, 5401]
SHOTS = list(zip(CUTS[:-1], CUTS[1:]))

# 回転の順(サビ 1 / サビ 2 / 山場)。キャラ・乗り物・メカ・小物がばらけるように
TT_A = ["dwarf", "taxi", "red_mecha", "food_truck", "jnr-c62-1-steam-", "monster", "airplane", "mushroom_house",
        "terna", "spaceship"]
TT_B = ["turtle", "robot-kuka-quant", "treehouse", "old_man_bust", "80-s-cartoon-wag", "dragon", "coffee_machine",
        "kaino-school-mil", "girl", "dutch_ship_mediu", "chest", "spider_robot"]
TT_C = ["oni_mask", "rover", "toy_gun", "tank", "walker_mech", "sushi", "medic", "donut", "duck", "lotus"]


def city(shot, length, off=None):
    a, b = SHOTS[shot]
    s = a + max(0, (b - a - length) // 2) if off is None else a + off
    return ("city", s, length)


def tt(name, length, start=1):
    return ("tt", name, start, length)


def build_edl():
    """[(長さ(コマ), 素材, 字幕)]。字幕は (主, 副) か None。"""
    e = []
    # 0-12 秒(8 小節): 導入。街の最初のカットをそのまま、タイトル
    # 最初の 2 小節は黒にタイトル、3 秒(小節の頭)で街へ。最初のカットは 296 コマしか無い(続けると小節の途中で切り替わった)
    e.append((2 * BAR, ("black",), "TITLE"))
    e.append((6 * BAR, city(0, 6 * BAR, 26), "TITLE"))
    # 12-48 秒(24 小節): 街を 2 小節ずつ 12 カット。v3.0 の機能を字幕で
    caps = {0: ("キャラは v3.0 のセル", "カメラからの日 ・ アニメの影色"), 2: ("キャラと背景で光を分ける", "背景はいつもの陰影のまま"),
            4: ("影の形をコマごとに作り直す", "歩いても影がちらつかない"), 6: ("顔はいつも日なた", "リムは影の側だけ控えめに"),
            8: ("すき間の 2 影", "AO で奥まった所を一段暗く")}
    for i, s in enumerate([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]):
        e.append((2 * BAR, city(s, 2 * BAR), caps.get(i)))
    # 48-78 秒(20 小節): サビ 1。回転を 2 小節ずつ 10 体
    for i, n in enumerate(TT_A):
        e.append((2 * BAR, tt(n, 2 * BAR, 136 + 15 * (i % 3 - 1)), ("どんなモデルも STEP0 一発", "") if i == 0 else None))
    # 78-84 秒(4 小節): 息継ぎ。顔の正面
    e.append((4 * BAR, city(2, 4 * BAR), None))
    # 84-120 秒(24 小節): サビ 2。回転を 2 小節ずつ 12 体
    for i, n in enumerate(TT_B):
        e.append((2 * BAR, tt(n, 2 * BAR, 136 + 15 * (i % 3 - 1)), ("AI が作った 3D も、手作りの 3D も", "") if i == 0 else None))
    # 120-123 秒(2 小節): 落ち。タイトルだけ
    e.append((2 * BAR, ("card",), "CARD"))
    # 123-153 秒(20 小節): 山場。1 小節ずつ 街 / 回転 を交互に
    cs = [13, 14, 3, 5, 7, 9, 11, 12, 6, 10]
    for i in range(10):
        e.append((BAR, city(cs[i], BAR, 8), None))   # Aメロと同じコマにならないようカットの頭から
        e.append((BAR, tt(TT_C[i], BAR, 160), None))   # 1 周の頭の前後(正面)
    # 153-177.4 秒: 終わり。街の最後のカット → クレジット
    e.append((4 * BAR, city(15, 4 * BAR, 0), None))
    # 回転を 16 体並べて 6 小節
    e.append((6 * BAR, ("grid", TT_A[:6] + TT_B[:6] + TT_C[:4]), None))
    rest = 5322 - sum(x[0] for x in e)
    e.append((rest, ("end",), "END"))
    return e


class Src:
    def __init__(self, city_dir: Path, tt_dir: Path):
        self.city_dir, self.tt_dir = city_dir, tt_dir
        self.font = {k: ImageFont.truetype(FONT_B if b else FONT_M, k) for k, b in
                     ((120, 1), (64, 1), (44, 0), (36, 0), (200, 1), (30, 0))}

    def frame(self, src, i):
        if src[0] == "city":
            p = self.city_dir / f"f_{src[1] + i:04d}.png"
        elif src[0] == "tt":
            n = len(list((self.tt_dir / src[1]).glob("f_*.png")))
            p = self.tt_dir / src[1] / f"f_{(src[2] - 1 + i) % n + 1:04d}.png"
        elif src[0] == "black":
            return Image.new("RGB", (W, H), (0, 0, 0))
        elif src[0] == "grid":
            im = Image.new("RGB", (W, H), (205, 226, 245))
            for k, nm in enumerate(src[1]):
                q = self.tt_dir / nm / f"f_{(136 + 11 * k + i) % 180 + 1:04d}.png"
                im.paste(Image.open(q).convert("RGB").resize((W // 4, H // 4), Image.LANCZOS),
                         ((k % 4) * W // 4, (k // 4) * H // 4))
            return im
        else:
            return Image.new("RGB", (W, H), (246, 244, 238))
        im = Image.open(p).convert("RGB")
        return im if im.size == (W, H) else im.resize((W, H), Image.LANCZOS)


def text_c(d, y, s, f, fill, W_=W):
    w = d.textlength(s, font=f)
    d.text(((W_ - w) / 2, y), s, font=f, fill=fill)


def overlay(src_obj, im, cap, i, n, gi):
    """字幕・タイトル。i は区間の中のコマ、n は区間の長さ、gi は全体のコマ。"""
    if cap is None:
        return im
    F = src_obj.font
    if cap == "TITLE":
        a = min(1, max(0, (gi - 20) / 40)) * min(1, max(0, (345 - gi) / 30))   # 2 区間にまたがるので全体のコマで
        if a <= 0:
            return im
        lay = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        d.rectangle((0, H // 2 - 170, W, H // 2 + 150), fill=(20, 24, 32, int(150 * a)))
        text_c(d, H // 2 - 140, "FreePencil2  v3.0", F[200], (255, 255, 255, int(255 * a)))
        text_c(d, H // 2 + 80, "Blender のための線画・セル塗りアドオン", F[44], (230, 236, 245, int(255 * a)))
        return Image.alpha_composite(im.convert("RGBA"), lay).convert("RGB")
    if cap == "CARD":
        d = ImageDraw.Draw(im)
        text_c(d, H // 2 - 130, "FreePencil2  v3.0", F[200], (30, 34, 44))
        return im
    if cap == "END":
        d = ImageDraw.Draw(im)
        a = min(1, i / 20) * min(1, max(0, (n - i) / 60))
        c = lambda v: tuple(int(246 + (x - 246) * a) for x in v)   # noqa: E731
        text_c(d, 330, "FreePencil2  v3.0", F[200], c((30, 34, 44)))
        lines = ["キャラクター: デルタもん (BlendAI)",
                 "AI 生成モデル: Scenario 3D Collection (CC BY 4.0) — Scenario",
                 "モデル: BlenderKit",
                 "Music: Beyond the Meridian",
                 "動き: MotionBricks"]
        for k, s in enumerate(lines):
            text_c(d, 680 + k * 70, s, F[44], c((70, 76, 88)))
        return im
    # 機能の字幕: 左下に帯。区間の頭 10 コマで出し、最後の 10 コマで消す
    a = min(1, i / 8) * min(1, max(0, (n - i) / 8))
    lay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    main, sub = cap
    wm = d.textlength(main, font=F[64])
    ws = d.textlength(sub, font=F[36]) if sub else 0
    bw = max(wm, ws) + 100
    y0 = H - 300
    d.rectangle((0, y0, bw, y0 + (190 if sub else 120)), fill=(15, 18, 26, int(170 * a)))
    d.text((60, y0 + 22), main, font=F[64], fill=(255, 255, 255, int(255 * a)))
    if sub:
        d.text((60, y0 + 118), sub, font=F[36], fill=(215, 225, 240, int(255 * a)))
    return Image.alpha_composite(im.convert("RGBA"), lay).convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--music", required=True)
    ap.add_argument("--city", required=True)
    ap.add_argument("--tt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--still")
    a = ap.parse_args()
    s = Src(Path(a.city), Path(a.tt))
    edl = build_edl()
    seq = []          # 全体のコマ -> (区間, 区間の中のコマ)
    for k, (n, _, _) in enumerate(edl):
        seq += [(k, i) for i in range(n)]
    print("frames", len(seq), "segments", len(edl))
    if a.still:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        for g in [int(x) for x in a.still.split(",")]:
            k, i = seq[g]
            n, src, cap = edl[k]
            overlay(s, s.frame(src, i), cap, i, n, g).save(out / f"reel_{g:04d}.jpg", quality=90)
        return
    p = subprocess.Popen([FF, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-i", a.music, "-map", "0:v", "-map", "1:a",
                          "-vf", "scale=in_range=pc:out_range=tv,format=yuv420p", "-c:v", "libx264", "-crf", "18",
                          "-c:a", "aac", "-b:a", "256k", "-shortest", a.out], stdin=subprocess.PIPE)
    for g, (k, i) in enumerate(seq):
        n, src, cap = edl[k]
        p.stdin.write(overlay(s, s.frame(src, i), cap, i, n, g).tobytes())
        if g % 300 == 0:
            print("frame", g, flush=True)
    p.stdin.close()
    p.wait()
    print("done", a.out)


if __name__ == "__main__":
    main()
