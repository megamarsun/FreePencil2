"""bg_layout.py の配置で背景を作り直す(face_fix.py の後。cable_clear.py の代わり)。

  blender -b <previz.blend> --python bg_build.py -- <layout.json> <出力.blend>

build_city.py の背景(WallPipe・Riser・Cable_・ArchPipe・Machines・Overhead_Beams)を消して、谷の壁・一周するパイプ・
壁の柱と受け金物・機械の箱・門形の梁・橋の吊り桁・梁から梁へのケーブルを City_Root の下に作る。
足場・手すり・橋の吊りケーブルと橋の下のケーブル・灯り・最後の機械は そのまま。
道を横切るパイプ(CrossPipe)は両端を壁まで延ばして作り直し(bg_layout.py)、最後の機械には底からの台、出だしの赤い灯りには
壁からの腕を付ける(宙に浮いていた)。
"""
import json
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

A = sys.argv[sys.argv.index("--") + 1:]
LY = json.load(open(A[0], encoding="utf-8"))
OUT = A[1]

sc = bpy.context.scene
root = bpy.data.objects["City_Root"]
OLD = ("WallPipe", "Riser", "Cable_", "ArchPipe", "Machines", "Overhead_Beams", "CrossPipe")
gone = [o for o in root.children if o.name.startswith(OLD)]
for o in gone:
    bpy.data.objects.remove(o)
print("@@ removed", len(gone), flush=True)


def mat(name, orig):
    """look.py と同じ持ち上げ(背景 0.86)を済ませた色で。元の色は fp_orig_color に残す。"""
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        m["fp_orig_color"] = list(orig)
        m.diffuse_color = (*[1 - (1 - v) * 0.86 for v in orig], 1)
        m.roughness = 0.6
    return m


MAT = {k: bpy.data.materials["city_" + k] for k in ("cable", "machine", "pipe_warm")}
for i in range(6):
    MAT[f"pipe_{i}"] = bpy.data.materials[f"city_pipe_{i}"]
MAT["wall"] = mat("city_wall", (0.07, 0.09, 0.14))
coll = {c.name: c for c in bpy.data.collections}


def group(name):
    nm = f"City_{name}"
    if nm not in coll:
        c = bpy.data.collections.new(nm)
        coll["City"].children.link(c)
        coll[nm] = c
    return coll[nm]


def link(o, g):
    group(g).objects.link(o)
    o.parent = root
    o.matrix_parent_inverse = Matrix()


def add_curve(name, pts, r, m, g, cyclic=False):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = r
    cu.bevel_resolution = 2 if r < 0.05 else 4
    cu.use_fill_caps = True
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for p_, q in zip(sp.points, pts):
        p_.co = (q[0], q[1], q[2], 1)
    sp.use_cyclic_u = cyclic
    cu.materials.append(m)
    o = bpy.data.objects.new(name, cu)
    link(o, g)
    return o


for t in LY["tubes"]:
    add_curve(t["name"], t["pts"], t["r"], MAT[t["mat"]], t["group"], t["cyclic"])

# 角材: 材質と組ごとに 1 つのメッシュへ
bms = {}
for b in LY["boxes"]:
    key = (b["group"], b["mat"])
    bm = bms.setdefault(key, bmesh.new())
    a, c = Vector(b["a"]), Vector(b["b"])
    d = c - a
    ax = d.normalized()
    if b["side"] is not None:
        sd = Vector((*b["side"], 0)) if len(b["side"]) == 2 else Vector(b["side"])
        sd = (sd - ax * sd.dot(ax)).normalized()
    else:
        sd = ax.cross(Vector((0, 0, 1))).normalized()
    up = ax.cross(sd).normalized()
    if up.z < 0 or (abs(up.z) < 1e-6 and abs(ax.z) > 0.99):
        up = -up
    w, h = b["w"], b["h"]
    if abs(ax.z) > 0.99:              # 縦の角材: 長さは z、断面は side と その直角
        corners = [a + sd * (w / 2 * i) + up * (h / 2 * j) for i in (-1, 1) for j in (-1, 1)]
    else:                             # 横・斜め: 下の面が a-b の線(高さ h は上へ)
        corners = [a + sd * (w / 2 * i) + up * (h * (j + 1) / 2) for i in (-1, 1) for j in (-1, 1)]
    v0 = [bm.verts.new(p) for p in corners]
    v1 = [bm.verts.new(p + d) for p in corners]
    for q in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 2, 6, 4), (1, 5, 7, 3), (0, 4, 5, 1), (2, 3, 7, 6)):
        vs = [(v0 + v1)[i] for i in q]
        bm.faces.new(vs)
for (g, m), bm in bms.items():
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(f"BG_{g}_{m}")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MAT[m])
    link(bpy.data.objects.new(f"BG_{g}_{m}", me), g)

# 谷の壁(輪を底から上へ立てる。内側を向く面)
W = LY["wall"]
z0, z1 = LY["z"]
bm = bmesh.new()
lo = [bm.verts.new((x, y, z0)) for x, y in W]
hi = [bm.verts.new((x, y, z1)) for x, y in W]
for i in range(len(W)):
    j = (i + 1) % len(W)
    bm.faces.new([lo[i], lo[j], hi[j], hi[i]])
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
me = bpy.data.meshes.new("Valley_Wall")
bm.to_mesh(me)
bm.free()
me.materials.append(MAT["wall"])
link(bpy.data.objects.new("Valley_Wall", me), "wall")

# 出だしの赤い灯りを壁の手前へ(球の頂点と EEVEE 用の灯り)
old, new = (Vector(v) for v in LY["lamp_a"])
lm = bpy.data.objects["Red_Lamps"].data
for v in lm.vertices:
    if (v.co - old).length < 0.8:
        v.co += new - old
bpy.data.objects["RedLight_A"].location += new - old

bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("@@ wrote", OUT, len(LY["tubes"]), "tubes", len(LY["boxes"]), "boxes", flush=True)
