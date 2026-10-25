"""試し: リグ付きの小物(箱のふた)をキャラと見なさず、塗りをメカ(角度で分ける)にして STEP0(本体は書き換えない)。

  blender -b --factory-startup --python exp_prop_rig.py -- <audit_v30_survey.py の引数>

rigged-box-model: リグがあるのでキャラの「ざっくり塗り」になり、箱の 90 度の角に線が出なかった。
"""
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bpy  # noqa: E402
import fp_batch  # noqa: E402

fp_batch.install_addon()
ai = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.ai"))
orig = ai.auto


def patched(ctx, names, *a, **k):
    for n in names:
        o = bpy.data.objects[n]
        if any(md.type == "ARMATURE" for md in o.modifiers):
            o.fp_paint_as = "MECHA"     # リグ(ポーズ)は残して、塗りだけメカにする
            print(f"[exp] paint_as MECHA: {n}")
    return orig(ctx, names, *a, **k)


ai.auto = patched
sys.argv = [sys.argv[0], "--"] + sys.argv[sys.argv.index("--") + 1:]
runpy.run_path(str(HERE / "audit_v30_survey.py"), run_name="__main__")
