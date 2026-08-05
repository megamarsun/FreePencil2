"""ビューポート(リアルタイム)コンポジタの対応状況を調べる。

FreePencil のプレビューは View3DShading.use_compositor に依存する
(sample_node.py)。バージョンごとに何が使えるかを実測するための調査用。

  blender -b --factory-startup --python probe_realtime_compositor.py
"""
from __future__ import annotations

import json

import bpy

out: dict = {"blender": bpy.app.version_string, "version": list(bpy.app.version)}

shading = bpy.types.View3DShading.bl_rna.properties

# ビューポートコンポジタのスイッチ
if "use_compositor" in shading:
    prop = shading["use_compositor"]
    out["use_compositor"] = {
        "exists": True,
        "type": prop.type,
        "items": [i.identifier for i in getattr(prop, "enum_items", [])],
        "default": getattr(prop, "default", None) if prop.type != "ENUM"
        else prop.default,
    }
else:
    out["use_compositor"] = {"exists": False}

# シーン側のコンポジタ実行デバイス(4.x で追加。GPU=リアルタイム相当)
render = bpy.types.RenderSettings.bl_rna.properties
for key in ("compositor_device", "compositor_precision",
            "compositor_denoise_preview_quality"):
    if key in render:
        prop = render[key]
        out[key] = {
            "exists": True,
            "items": [i.identifier for i in getattr(prop, "enum_items", [])],
        }
    else:
        out[key] = {"exists": False}

# FreePencil の PRO グループが使うノードが、この版に存在するか
NODES = [
    "CompositorNodeRLayers", "CompositorNodeComposite", "NodeGroupOutput",
    "CompositorNodeValToRGB", "ShaderNodeValToRGB",
    "CompositorNodeMixRGB", "ShaderNodeMixRGB",
    "CompositorNodeMath", "ShaderNodeMath",
    "CompositorNodeFilter", "CompositorNodeAntiAliasing",
    "CompositorNodeSetAlpha", "CompositorNodeScale",
    "CompositorNodeOutputFile", "CompositorNodeSwitch",
    "CompositorNodeBlur", "CompositorNodeInvert", "CompositorNodeAlphaOver",
]
out["nodes"] = {n: hasattr(bpy.types, n) for n in NODES}

# ノードツリーのインターフェースAPI(3.x と 4.x で別物)
out["nodetree_interface"] = hasattr(bpy.types.ShaderNodeTree.bl_rna.properties,
                                    "get") and \
    "interface" in bpy.types.ShaderNodeTree.bl_rna.properties
out["aov_output_has_aov_name"] = "aov_name" in \
    bpy.types.ShaderNodeOutputAOV.bl_rna.properties

print("[probe] " + json.dumps(out, ensure_ascii=False))
