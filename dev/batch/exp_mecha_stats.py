"""調査: メカ(骨付きロボット)と人を見分ける手がかりを測る。

  blender -b --factory-startup --python exp_mecha_stats.py -- <出力 .txt> <.blend> [<.blend> ...]

.blend がシーンならそのメッシュを、BlenderKit の素材ならメッシュを足してから測る。
1 行 1 ファイル: 骨付きの割合、角(30 度より折れた辺と開いた縁)の長さの割合を 30/45/60 度で、
部品(つながった塊)の数、材質名に skin/hair/face などがあるか。
"""
import math
import sys
from pathlib import Path

import bmesh
import bpy

ARGV = sys.argv[sys.argv.index("--") + 1:]
OUT = Path(ARGV[0])
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fp_batch  # noqa: E402

HUMAN_WORDS = ("skin", "hair", "face", "eye", "body", "肌", "髪", "顔", "目", "体")


def has_rig(o):
    return any(m.type == 'ARMATURE' for m in o.modifiers) or (
        o.parent is not None and o.parent.type == 'ARMATURE')


def stats(meshes):
    lims = [math.radians(d) for d in (30, 45, 60)]
    sharp = [0.0, 0.0, 0.0]
    tot = 0.0
    parts = 0
    faces = 0
    rig_faces = 0
    words = set()
    for o in meshes:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bm.transform(o.matrix_world)
        n = len(bm.faces)
        faces += n
        if has_rig(o):
            rig_faces += n
        for e in bm.edges:
            ln = e.calc_length()
            tot += ln
            open_ = len(e.link_faces) != 2
            ang = 0.0 if open_ else e.calc_face_angle(0.0)
            for i, lim in enumerate(lims):
                if open_ or ang > lim:
                    sharp[i] += ln
        seen = set()
        for v in bm.verts:
            if v.index in seen:
                continue
            parts += 1
            stack = [v]
            seen.add(v.index)
            while stack:
                a = stack.pop()
                for e in a.link_edges:
                    b = e.other_vert(a)
                    if b.index not in seen:
                        seen.add(b.index)
                        stack.append(b)
        bm.free()
        for s in o.material_slots:
            if s.material:
                nm = s.material.name.lower()
                words.update(w for w in HUMAN_WORDS if w in nm)
    f = [round(s / tot, 3) if tot else 0 for s in sharp]
    return {"rig": round(rig_faces / faces, 2) if faces else 0, "sharp30": f[0], "sharp45": f[1], "sharp60": f[2],
            "parts": parts, "faces": faces, "words": ",".join(sorted(words))}


fp_batch.install_addon()
lines = []
for p in ARGV[1:]:
    path = Path(p)
    bpy.ops.wm.read_homefile(use_empty=True)
    try:
        bpy.ops.wm.open_mainfile(filepath=str(path))
    except RuntimeError as e:
        lines.append(f"{path.parent.name}\tERROR {e}")
        continue
    meshes = [o for o in bpy.context.scene.objects
              if o.type == 'MESH' and not o.hide_render and len(o.data.polygons)]
    if not meshes:          # 素材ファイルでシーンに何も無い
        meshes = [o for o in bpy.data.objects if o.type == 'MESH' and len(o.data.polygons)]
    s = stats(meshes)
    name = path.parent.name.split("_")[0] if "blenderkit" in str(path) else path.parent.name + "/" + path.stem
    line = f"{name}\t" + "\t".join(f"{k}={v}" for k, v in s.items())
    print("@@", line, flush=True)
    lines.append(line)
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("@@ done", flush=True)
