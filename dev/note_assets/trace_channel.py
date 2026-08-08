"""PROノードの中で、あるグループ入力がどこへ流れているか辿る。

STEP4 の mask_color / line_color の説明が実装と合っているかを、
推測ではなく配線から確かめるための調査用。

  blender -b --factory-startup --python trace_channel.py -- --socket mask_color
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))

import fp_batch  # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
WANT = ARGV[ARGV.index("--socket") + 1] if "--socket" in ARGV else None
DEPTH = int(ARGV[ARGV.index("--depth") + 1]) if "--depth" in ARGV else 12

bpy.ops.wm.read_homefile(use_empty=True)
fp_batch.install_addon()
bpy.ops.mesh.primitive_cube_add()
bpy.context.active_object.select_set(True)
bpy.context.scene.fp_node_type = "pro"
bpy.context.scene.fp_enable_compositor_view = False
bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")

ng = next(g for g in bpy.data.node_groups if g.name.endswith("_pro"))


def describe(node) -> str:
    bits = [node.type]
    for attr in ("operation", "blend_type", "filter_type", "use_alpha"):
        v = getattr(node, attr, None)
        if v not in (None, ""):
            bits.append(f"{attr}={v}")
    if node.type == "VALTORGB" and hasattr(node, "color_ramp"):
        els = [(round(e.position, 3),
                tuple(round(c, 3) for c in e.color[:3]))
               for e in node.color_ramp.elements]
        bits.append(f"ramp={els}")
    if node.label:
        bits.append(f"label={node.label!r}")
    return " ".join(bits)


def walk(socket, depth=0, seen=None):
    """出力ソケットから下流を辿る。Reroute は透過して数えない。"""
    seen = seen if seen is not None else set()
    out = []
    for lk in socket.links:
        n = lk.to_node
        key = (n.name, lk.to_socket.name)
        if key in seen or depth > DEPTH:
            continue
        seen.add(key)
        if n.type == "REROUTE":
            out += walk(n.outputs[0], depth, seen)
            continue
        out.append({
            "depth": depth,
            "node": n.name,
            "into": lk.to_socket.name,
            "what": describe(n),
        })
        for o in n.outputs:
            out += walk(o, depth + 1, seen)
    return out


gin = next(n for n in ng.nodes if n.type == "GROUP_INPUT")
names = [s.name for s in gin.outputs]
targets = [WANT] if WANT else names

result = {}
for name in targets:
    sock = next((s for s in gin.outputs if s.name == name), None)
    if sock is None:
        result[name] = "no such socket"
        continue
    result[name] = walk(sock)

print("[trace] " + json.dumps({"sockets": names, "trace": result},
                              ensure_ascii=False))
