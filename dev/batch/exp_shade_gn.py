"""実験: 影用の法線をモディファイアの最後(ジオメトリノード)でならすと、セルの影はどう変わるか。

  blender -b --factory-startup --python exp_shade_gn.py -- <作例の .blend> <出力フォルダ> [--iters 0,20,80] [--no-normalmap] [--sharp 35]

exp_shade_normals.py はメッシュにカスタム法線を書いたが、細分化のモディファイアがそれを捨て
(woman_01 の服と体)、影が変わらなかった。こちらはスタックの最後に
「法線 → Blur Attribute(iters 回) → Set Mesh Normal(Free)」の GN モディファイアを足すので、
シェイプキー・アーマチュア・細分化の後の形に効く。0 はモディファイアなし(比べる元)。
--sharp DEG: その角度より折れた辺で先に切ってからならす(建物の壁の面ごとの明暗を残す)。
アドオンには手を入れない。出力: <出力>/cel_gNN.png と smoothed_gNN.blend
"""
import sys
from pathlib import Path

import bpy

ARGV = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = Path(ARGV[0]), Path(ARGV[1])
ITERS = [int(v) for v in (ARGV[ARGV.index("--iters") + 1] if "--iters" in ARGV else "0,20,80").split(",")]
NO_NMAP = "--no-normalmap" in ARGV
SHARP = float(ARGV[ARGV.index("--sharp") + 1]) if "--sharp" in ARGV else None
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fp_batch  # noqa: E402

fp_batch.install_addon()
bpy.ops.wm.open_mainfile(filepath=str(SRC))
sc = bpy.context.scene
OUT.mkdir(parents=True, exist_ok=True)
if NO_NMAP:
    for m in bpy.data.materials:
        if m.use_nodes:
            for n in m.node_tree.nodes:
                if n.type in ("NORMAL_MAP", "BUMP"):
                    for lk in list(n.outputs[0].links):
                        m.node_tree.links.remove(lk)


def shade_group():
    ng = bpy.data.node_groups.new("FP_ShadeNormal_exp", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    it = ng.interface.new_socket("Iterations", in_out="INPUT", socket_type="NodeSocketInt")
    it.default_value = 20
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N = ng.nodes
    gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    nrm = N.new("GeometryNodeInputNormal")
    blur = N.new("GeometryNodeBlurAttribute")
    blur.data_type = "FLOAT_VECTOR"
    vn = N.new("ShaderNodeVectorMath")
    vn.operation = "NORMALIZE"
    setn = N.new("GeometryNodeSetMeshNormal")
    setn.mode = "FREE"
    setn.domain = "POINT"
    L = ng.links
    L.new(nrm.outputs[0], blur.inputs["Value"])
    L.new(gi.outputs["Iterations"], blur.inputs["Iterations"])
    L.new(blur.outputs[0], vn.inputs[0])
    geo = gi.outputs["Geometry"]
    if SHARP is not None:                   # 角で切ると、ならしが角を越えない
        ang = N.new("GeometryNodeInputMeshEdgeAngle")
        gt = N.new("FunctionNodeCompare")
        gt.data_type = "FLOAT"
        gt.operation = "GREATER_THAN"
        gt.inputs["B"].default_value = __import__("math").radians(SHARP)
        split = N.new("GeometryNodeSplitEdges")
        L.new(ang.outputs["Unsigned Angle"], gt.inputs["A"])
        L.new(gi.outputs["Geometry"], split.inputs["Mesh"])
        L.new(gt.outputs[0], split.inputs["Selection"])
        geo = split.outputs[0]
    L.new(geo, setn.inputs["Mesh"])
    custom = next(s for s in setn.inputs if s.enabled and s.type == "VECTOR")
    L.new(vn.outputs["Vector"], custom)
    L.new(setn.outputs[0], go.inputs["Geometry"])
    return ng


ng = shade_group()
objs = [o for o in sc.objects if o.type == "MESH" and not o.hide_render and len(o.data.polygons)]
mods = []
for o in objs:
    md = o.modifiers.new("FP_ShadeNormal_exp", "NODES")
    md.node_group = ng
    md.show_viewport = md.show_render = False
    mods.append(md)
key = next(s.identifier for s in ng.interface.items_tree if getattr(s, "name", "") == "Iterations")

sc.fp_preview_mode = "CEL"
for it in ITERS:
    for md in mods:
        md.show_viewport = md.show_render = it > 0
        md[key] = it
    for o in objs:
        o.update_tag()
    sc.render.filepath = str(OUT / f"cel_g{it:02d}.png")
    bpy.ops.render.render(write_still=True)
    print("@@ shot", it, flush=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"smoothed_g{ITERS[-1]:02d}.blend"))
print("@@ done", flush=True)
