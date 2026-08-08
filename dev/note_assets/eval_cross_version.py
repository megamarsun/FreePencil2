"""5.2 で作ったファイルを 4.5 で開いたときの挙動を確かめる。

  段階1 (5.2): シーンを作って STEP0 -> レンダ -> 保存
  段階2 (4.5): 開いてレンダ(そのまま) -> STEP3 押し直し -> レンダ

  blender -b --factory-startup --python cross_version.py -- \
      --stage make|check --blend <path> --out <dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
import numpy as np

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


STAGE = arg("--stage", "make")
BLEND = Path(arg("--blend")).resolve()
OUT = Path(arg("--out")).resolve()
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(Path(r"E:\10_cowork\00_code\22_FreePencil\dev\batch")))
import fp_batch  # noqa: E402


def ink_of(png: Path) -> float:
    img = bpy.data.images.load(str(png.resolve()))
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    bpy.data.images.remove(img)
    a = px[:, :, 3]
    g = px[:, :, :3].mean(axis=2) * a + (1.0 - a)
    return float((g < 0.5).mean())


def render(tag: str) -> float:
    scene = bpy.context.scene
    scene.render.engine = fp_batch.eevee_engine()
    scene.eevee.taa_render_samples = 8
    scene.render.resolution_x = scene.render.resolution_y = 400
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    png = OUT / f"{tag}.png"
    fp_batch.render_still(scene, png, 1)
    return ink_of(png)


fp_batch.install_addon()
ver = ".".join(map(str, bpy.app.version[:2]))

if STAGE == "make":
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.mesh.primitive_monkey_add()
    o = bpy.context.object
    m = o.modifiers.new("s", "SUBSURF")
    m.levels = 2
    bpy.ops.object.modifier_apply(modifier=m.name)
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    scene = bpy.context.scene
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 42
    scene.fp_enable_compositor_view = False
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    fp_batch.setup_camera_and_light()
    ink = render(f"made_on_{ver}")
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))
    print(json.dumps({"stage": "make", "blender": ver, "ink": ink}))
else:
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    groups = {g.name: {"nodes": len(g.nodes),
                       "built_for": g.get("fp_built_for"),
                       "version": g.get("fp_nodegroup_version")}
              for g in bpy.data.node_groups if "FreePencil" in g.name}
    as_is = render(f"opened_on_{ver}")
    # STEP3 を押し直したら直るか
    bpy.context.scene.fp_enable_compositor_view = False
    bpy.ops.freepencil2.link_button()
    after = render(f"after_step3_on_{ver}")
    print(json.dumps({"stage": "check", "blender": ver,
                      "ink_as_is": as_is, "ink_after_step3": after,
                      "groups": groups}, ensure_ascii=False))
