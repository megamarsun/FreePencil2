"""影の形(shade_normal)の試し撮り: いま / 影の形 / ポーズを変えた後(作り直さない / 作り直す)。

  blender -b --factory-startup --python try_shade_shape.py -- <作例の .blend> <出力フォルダ> [--pose]

出力: before.png / after.png / normal.png(影の向きの AOV をそのまま色に) / after.blend
--pose: 上腕の骨を 50° 下げて posed_keep.png(作り直さない)と posed_rebake.png を足す。
"""
import math
import sys
from pathlib import Path

import bpy

ARGV = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = Path(ARGV[0]), Path(ARGV[1])
POSE = "--pose" in ARGV
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fp_batch  # noqa: E402

fp_batch.install_addon()
bpy.ops.wm.open_mainfile(filepath=str(SRC))
sc = bpy.context.scene
OUT.mkdir(parents=True, exist_ok=True)
sc.fp_preview_mode = "CEL"


def shot(name):
    sc.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    print("@@ shot", name, flush=True)


def shot_normal():
    """影の向きの AOV を、セルの代わりに出力へつないで撮る(目で向きを見る)。"""
    from importlib import import_module
    compat = next(m for k, m in sys.modules.items() if k.endswith(".compat"))
    tree = compat.get_compositor_tree(sc)
    rl = next(n for n in tree.nodes if n.type == "R_LAYERS")
    sock = compat.render_layer_socket(rl, ("fp_shade_n",))
    target = next(n for n in tree.nodes if n.type in compat.OUTPUT_NODE_TYPES)
    inp = target.inputs[0]
    old = inp.links[0].from_socket if inp.is_linked else None
    tree.links.new(sock, inp)
    shot("normal")
    if old is not None:
        tree.links.new(old, inp)


def arm_down():
    """上腕を 50° 下げる。骨の拘束(コントロールの骨に従う)は止める。"""
    import re
    arm = next((o for o in sc.objects if o.type == "ARMATURE"), None)
    if arm is None:
        return False
    pat = re.compile(r"(left|right)arm$|upper_?arm[._]?(l|r)$|^upperarm", re.I)
    ctrl = re.compile(r"arm_fk", re.I)              # コントロールの骨(上腕がこれに従う)があればそちらを回す
    use_ctrl = any(ctrl.search(pb.name) and "fore" not in pb.name.lower() for pb in arm.pose.bones)
    done = []
    for pb in arm.pose.bones:
        nm = pb.name.split(":")[-1]
        hit = (ctrl.search(nm) and "fore" not in nm.lower()) if use_ctrl else (pb.bone.use_deform and pat.search(nm))
        if hit:
            right = "right" in pb.name.lower() or pb.name.lower().endswith(("r", ".r", "_r"))
            pb.rotation_mode = "XYZ"
            pb.rotation_euler.z += math.radians(50) * (1 if right else -1)
            done.append(pb.name)
    print("@@ posed bones", done, flush=True)
    bpy.context.view_layer.update()
    return bool(done)


shot("before")
import time
t0 = time.time()
r = bpy.ops.freepencil.shade_shape()
print("@@ bake seconds", round(time.time() - t0, 1), flush=True)
mod = next(m for k, m in sys.modules.items() if k.endswith(".shade_normal"))
print("@@ bake", r, sum("fp_shade_o" in o.data.color_attributes for o in sc.objects if o.type == "MESH"),
      "of", sum(o.type == "MESH" for o in sc.objects), flush=True)
shot("after")
shot_normal()
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "after.blend"))
if POSE and arm_down():
    shot("posed_keep")
    bpy.ops.freepencil.shade_shape()
    shot("posed_rebake")
    sc.fp_cel_shape = 0.0
    shot("posed_off")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "posed.blend"))
print("@@ done", flush=True)
