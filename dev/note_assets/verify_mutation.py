"""STEP0 がモデルに何を書き換えるかを実測する。

「モデルを改変しません」と書いてよいかを、推測ではなく前後比較で判定する。
v2.5.0 の記事執筆時、この確認をせずに「マテリアルにも触れない」と書いて
誤りだった (BLEND マテリアルは HASHED へ変換される)。

  blender -b --factory-startup --python verify_mutation.py -- --blend <asset.blend>
  blender -b --factory-startup --python verify_mutation.py -- --synthetic

--synthetic は BLEND / 本物のガラス / 不透明 の3マテリアルを持つ立方体を
その場で作って確認する (アセット不要)。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
sys.path.insert(0, str(HERE))

import fp_batch          # noqa: E402
import render_samples    # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SYNTHETIC = "--synthetic" in ARGV
BLEND = ARGV[ARGV.index("--blend") + 1] if "--blend" in ARGV else None


def snapshot() -> dict:
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    return {
        "n_objects": len(objs),
        "names": sorted(o.name for o in objs),
        "verts": sum(len(o.data.vertices) for o in objs),
        "polys": sum(len(o.data.polygons) for o in objs),
        "edges": sum(len(o.data.edges) for o in objs),
        "sharp_edges": sum(sum(1 for e in o.data.edges if e.use_edge_sharp)
                           for o in objs),
        "smooth_faces": sum(sum(1 for p in o.data.polygons if p.use_smooth)
                            for o in objs),
        "seams": sum(sum(1 for e in o.data.edges if e.use_seam) for o in objs),
        "color_attrs": sorted({a.name for o in objs
                               for a in o.data.color_attributes}),
        "materials": sorted({m.name for o in objs for m in o.data.materials if m}),
        "blend_methods": sorted(
            {f"{m.name}={getattr(m, 'blend_method', 'n/a')}"
             for o in objs for m in o.data.materials if m}),
        "modifiers": sorted({f"{o.name}:{m.type}"
                             for o in objs for m in o.modifiers}),
    }


def make_mat(name: str, blend: str, alpha: float, transmission: float):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    if hasattr(m, "blend_method"):
        m.blend_method = blend
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = alpha
        for key in ("Transmission Weight", "Transmission"):
            if key in bsdf.inputs:
                bsdf.inputs[key].default_value = transmission
                break
    return m


bpy.ops.wm.read_homefile(use_empty=True)
fp_batch.install_addon()

if SYNTHETIC:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.active_object
    for m in (make_mat("Opaque_Mat", "OPAQUE", 1.0, 0.0),
              make_mat("Blend_Toon", "BLEND", 1.0, 0.0),
              make_mat("Blend_Glass", "BLEND", 0.2, 1.0)):
        cube.data.materials.append(m)
    cube.select_set(True)
    bpy.context.view_layer.objects.active = cube
    label = "synthetic-cube"
else:
    if not BLEND:
        raise SystemExit("--blend か --synthetic のどちらかを指定してください")
    render_samples.stage_model(Path(BLEND))
    fp_batch.select_meshes()
    label = Path(BLEND).name

before = snapshot()
bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
after = snapshot()

diff = {}
for k in before:
    if before[k] == after[k]:
        continue
    if isinstance(before[k], list):
        b, a = set(before[k]), set(after[k])
        diff[k] = {"added": sorted(a - b)[:8], "removed": sorted(b - a)[:8]}
    else:
        diff[k] = {"before": before[k], "after": after[k]}

print("[verify_mutation] " + json.dumps({
    "target": label,
    "unchanged": [k for k in before if k not in diff],
    "changed": diff,
}, ensure_ascii=False))
