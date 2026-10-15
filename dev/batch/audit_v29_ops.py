"""v2.9 の操作の順番を通して、毎回撮る(押し直し・保存して開き直し・外す・やり直し)。

  blender -b --factory-startup --python audit_v29_ops.py -- [--out out/audit_v29_ops/<版>] [--style WEIGHTED]

順番:
  01 STEP0 の後(白)
  02 セルにする
  03 サルを 2、地面を 0
  04 STEP3 を押し直す(セルと太さが残るか)
  05 セルの「影の線」と空なし
  06 マテリアル
  07 保存して開き直す(マテリアルのまま)
  08 開き直した後に STEP3
  09 書き出しを全部入れて STEP3(合成 + 各レイヤー)
  10 STEP0 を押し直す(太さはオブジェクトに残る)
  11 外す(STEP0 の前と同じか)
  12 外した後にもう一度 STEP0
"""
from __future__ import annotations

import math
import shutil
import sys
import traceback
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d   # noqa: E731
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bpy                        # noqa: E402
import fp_batch                   # noqa: E402

STYLE = arg("--style", "WEIGHTED")
OUT = Path(arg("--out", str(HERE / "out" / "audit_v29_ops" / f"{bpy.app.version_string}_{STYLE}"))).resolve()
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True, exist_ok=True)
fp_batch.install_addon()
import audit_v29_scene as S       # noqa: E402

sc, objs = S.scene_setup(False, 480)
sc.render.filepath = str(OUT / "00_before.png")
bpy.ops.render.render(write_still=True)


def shot(name):
    sc = bpy.context.scene
    sc.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    print("@@@", name, sc.fp_preview_mode, sc.render.resolution_percentage, flush=True)


def ob(name):
    return bpy.data.objects[name]


try:
    sc.fp_auto_style = STYLE
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    shot("01_step0")
    sc.fp_preview_mode = "CEL"
    shot("02_cel")
    ob("Monkey").fp_line_scale = 2.0
    ob("Ground").fp_line_scale = 0.0
    shot("03_scale")
    bpy.ops.freepencil2.link_button()
    shot("04_step3")
    sc.fp_cel_shadow_line = True
    sc.fp_cel_sky = False
    shot("05_shadowline_nosky")
    sc.fp_preview_mode = "NONE"
    shot("06_material")
    blend = OUT / "ops.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    sc = bpy.context.scene
    shot("07_reopen")
    bpy.ops.freepencil2.link_button()
    shot("08_reopen_step3")
    sc.fp_preview_mode = "CEL"
    sc.fp_file_output = True
    for k in [p for p in dir(sc) if p.startswith("fp_fo_")]:
        setattr(sc, k, True)
    sc.fp_file_output_path = str(OUT / "fo") + "/"
    bpy.ops.freepencil2.link_button()
    shot("09_fileout")
    bpy.ops.object.select_all(action="DESELECT")
    for n in ("Monkey", "Box", "Ground"):
        ob(n).select_set(True)
    bpy.context.view_layer.objects.active = ob("Monkey")
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    shot("10_step0_again")
    print("@@@ scale kept", ob("Monkey").fp_line_scale, ob("Ground").fp_line_scale, flush=True)
    bpy.ops.freepencil.remove()
    shot("11_removed")
    mats = {m.name: [n.label for n in m.node_tree.nodes if n.label.startswith("FreePencil")]
            for m in bpy.data.materials if m.use_nodes}
    print("@@@ leftover material nodes", {k: v for k, v in mats.items() if v}, flush=True)
    print("@@@ leftover aovs", [a.name for a in bpy.context.view_layer.aovs], flush=True)
    bpy.ops.object.select_all(action="DESELECT")
    for n in ("Monkey", "Box", "Ground"):
        ob(n).select_set(True)
    bpy.context.view_layer.objects.active = ob("Monkey")
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    shot("12_step0_after_remove")
except Exception:                                                # noqa: BLE001
    print("@@@ ERROR", traceback.format_exc(), flush=True)
print("@@@ files", sorted(p.name for p in (OUT / "fo").glob("*.png")) if (OUT / "fo").exists() else [], flush=True)
