"""強弱(line_weight.build_weight)の途中の絵を書き出す。どの段で絵が崩れるかを目で見るため。

  blender -b --factory-startup --python dump_lw_taps.py -- <fp 済みの .blend> <out_dir> [--mode WHITE]

fp_tap の付いたノードと、レンダーレイヤーの AO・Alpha を File Output に全部つないで 1 回レンダする。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fp_batch                                   # noqa: E402
fp_batch.install_addon()
import bpy                                        # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = Path(ARGV[0]).resolve(), Path(ARGV[1]).resolve()
MODE = ARGV[ARGV.index("--mode") + 1] if "--mode" in ARGV else "WHITE"
OUT.mkdir(parents=True, exist_ok=True)
compat = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.compat"))

bpy.ops.wm.open_mainfile(filepath=str(SRC))
sc = bpy.context.scene
sc.fp_preview_mode = MODE
tree = compat.get_compositor_tree(sc)
srcs = {n["fp_tap"]: n.outputs[0] for n in tree.nodes if n.get("fp_tap")}
rl = next(n for n in tree.nodes if n.type == "R_LAYERS")
for k in ("AO", "Alpha", "Image"):
    if rl.outputs.get(k) is not None and rl.outputs[k].enabled:
        srcs["rl_" + k] = rl.outputs[k]
fo = tree.nodes.new("CompositorNodeOutputFile")
fo.label = "FreePencil_tapdump"
if hasattr(fo, "base_path"):
    fo.base_path = str(OUT) + "/"
else:                                            # 5.x
    fo.directory = str(OUT) + "/"
fo.format.file_format = "PNG"
fo.format.color_mode = "RGB"
if hasattr(fo, "file_slots"):
    fo.file_slots.clear()
    for name, sock in srcs.items():
        fo.file_slots.new(name)
        tree.links.new(sock, fo.inputs[name])
else:
    for name, sock in srcs.items():
        it = fo.file_output_items.new("RGBA", name)
        tree.links.new(sock, fo.inputs[it.name])
sc.render.filepath = str(OUT / "final.png")
bpy.ops.render.render(write_still=True)
print("@@@ taps", sorted(srcs), "res", sc.render.resolution_x, sc.render.resolution_percentage)
