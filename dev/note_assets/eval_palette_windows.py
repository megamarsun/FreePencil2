"""パーツ・トーン分けの明度窓を、方式ごとに机上比較する。

現状 (v2.5.0):
    part_tint = (cls % 3) * 0.17
    window    = [0.25 + tint, min(0.85, 0.75 + tint)]
  -> 幅 0.50 / 0.43 / 0.26。3つ目が上限 0.85 に潰されて線が薄くなる。
     vertex_color.py に「既知の弱点(未解決)」として記録されている。

ここでは Blender のメッシュを触らず、build_palette の出力だけを見て
各方式の以下を出す:
  - パーツ内の隣接輝度差 (= 線の出やすさ)。span = 幅/(k-1)
  - パーツ間の輝度分離 (= 接するパーツ境界に線が出るか)
  - 白背景 1.0 との差 (= シルエット線)
  - RGB 最小ペア距離 (= fp_min_neighbor_color_distance の契約)

  blender -b --factory-startup --python eval_palette_windows.py
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))

import fp_batch  # noqa: E402

fp_batch.install_addon()
from freepencil2 import utils  # noqa: E402

LUMA_LO, LUMA_HI = 0.25, 0.85
SEED = 42
# 実アセットの島数分布に合わせる (メカ155パーツは大半が少数島)
K_VALUES = [1, 2, 3, 4, 5, 6, 8, 12]
N_TINT = 3


def scheme_current(p: int):
    """v2.5.0: 窓を上へずらす。上限クランプで3つ目が潰れる。"""
    tint = p * 0.17
    return LUMA_LO + tint, min(LUMA_HI, 0.75 + tint)


def scheme_equal_width(p: int, delta: float, width: float):
    """幅を全パーツで揃え、位置だけずらす。"""
    lo = LUMA_LO + p * delta
    return lo, lo + width


def scheme_alternating(p: int):
    """低-高-中の順に配置し、上限の余りを使い切る。

    0 -> 下寄せ / 1 -> 上寄せ / 2 -> 中央。窓幅は等しい。
    """
    width = 0.40
    slots = [LUMA_LO,
             LUMA_HI - width,
             LUMA_LO + (LUMA_HI - LUMA_LO - width) / 2.0]
    lo = slots[p % 3]
    return lo, lo + width


SCHEMES = {
    "current": scheme_current,
    "equal_w040_d010": lambda p: scheme_equal_width(p, 0.10, 0.40),
    "equal_w036_d012": lambda p: scheme_equal_width(p, 0.12, 0.36),
    "alternating_w040": scheme_alternating,
}


def evaluate(fn) -> dict:
    windows = [fn(p) for p in range(N_TINT)]
    widths = [round(hi - lo, 3) for lo, hi in windows]

    inner, silhouette, rgbmin = [], [], []
    per_part_levels = {p: {} for p in range(N_TINT)}
    for p, (lo, hi) in enumerate(windows):
        for k in K_VALUES:
            colors, pmin, lmin = utils.build_palette(k, SEED,
                                                     luma_lo=lo, luma_hi=hi)
            lumas = sorted(utils._luma(c) for c in colors)
            per_part_levels[p][k] = lumas
            if k >= 2:
                inner.append(lmin)          # 最小輝度差 = 一番出にくい線
                rgbmin.append(pmin)
            silhouette.append(1.0 - max(lumas))

    # パーツ間分離: 接する2パーツが同じ島数のとき、最も近い輝度どうしの差
    between = []
    for k in K_VALUES:
        for a in range(N_TINT):
            for b in range(a + 1, N_TINT):
                la, lb = per_part_levels[a][k], per_part_levels[b][k]
                between.append(min(abs(x - y) for x in la for y in lb))

    return {
        "widths": widths,
        "inner_luma_min": round(min(inner), 4),
        "inner_luma_median": round(statistics.median(inner), 4),
        "silhouette_min": round(min(silhouette), 4),
        "between_parts_median": round(statistics.median(between), 4),
        "between_parts_min": round(min(between), 4),
        "rgb_min": round(min(rgbmin), 4),
    }


out = {name: evaluate(fn) for name, fn in SCHEMES.items()}
print("[eval] " + json.dumps(out, ensure_ascii=False, indent=2))
