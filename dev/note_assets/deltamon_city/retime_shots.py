"""動きを作り直したあと、ショットの区切り(f)と止める位置(anchor)を道のりで新しい動きへ移す。

  python retime_shots.py <旧.npz> <新.npz> <shots.json>

旧の区切りのコマで居た道のり s に、新の動きで初めて着いたコマを新しい区切りにする。最後は新の終わり。
"""
import json
import sys

import numpy as np

S0 = np.load(sys.argv[1])["s"]
S1 = np.load(sys.argv[2])["s"]
P = sys.argv[3]
shots = json.load(open(P, encoding="utf-8"))
n1 = len(S1)


def move(f):
    s = S0[min(f, len(S0)) - 1]
    i = int(np.searchsorted(np.maximum.accumulate(S1), s - 1e-6))
    return min(i + 1, n1)


for k, sh in enumerate(shots):
    a, b = sh["f"]
    a = 1 if k == 0 else shots[k - 1]["f"][1] + 1
    b = n1 if k == len(shots) - 1 else move(b + 1) - 1
    if sh.get("anchor") and sh["anchor"] > 1:
        sh["anchor"] = min(max(move(sh["anchor"]), a), b)
    sh["f"] = [a, b]
    print(sh["id"], sh["f"], sh.get("anchor"))
json.dump(shots, open(P, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
