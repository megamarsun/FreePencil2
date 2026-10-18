"""ダンスの場面の、各コマのキャラの頭の位置(カメラ画面の割合、左上 0,0)を JSON に書く(顔のアップ用)。

  blender -b --python mmd_heads.py -- <dance_clean.blend> <out.json>
"""
import json
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view

ARGV = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.open_mainfile(filepath=ARGV[0])
sc = bpy.context.scene
arms = sorted([o for o in sc.objects if o.type == "ARMATURE"], key=lambda o: o.matrix_world.translation.x)
out = {}
for f in range(sc.frame_start, sc.frame_end + 1):
    sc.frame_set(f)
    row = []
    for a in arms:
        pb = a.pose.bones
        hd = next(pb[n] for n in ("頭", "head") if n in pb)
        nk = next(pb[n] for n in ("首", "neck") if n in pb)
        p = world_to_camera_view(sc, sc.camera, a.matrix_world @ hd.head)
        q = world_to_camera_view(sc, sc.camera, a.matrix_world @ nk.head)
        row.append([p.x, 1 - p.y, abs((1 - p.y) - (1 - q.y))])
    out[f] = row
json.dump(out, open(ARGV[1], "w"))
print("@@@ heads", len(out), [a.name for a in arms])
