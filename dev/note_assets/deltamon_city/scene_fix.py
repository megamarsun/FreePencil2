"""FreePencil で撮ると崩れた所を場面の側で直す(cam_fix.py の後)。

  blender -b <previz.blend> --python scene_fix.py -- <layout.json> <出力.blend> [--grate-keep 3]

- 段の立ち上がりの面が 2 枚重なっていた(build_city.py が区間の前の面と段差の面を両方作る)。重なった所がちらついて、
  線画で段の縁に黒い ざらつきが出た。同じ平面にあって、ほかの面の中にすっぽり入る面を消す。
- 網目の床(Walkway_Grates)の桟は 0.1 m おきで、離れると線がつぶれて黒い帯になった。道を横切る桟を --grate-keep 本に 1 本残す。
- 谷の上が開いていて、見上げると空(線の無い灰色)がのぞいた。壁の上の縁(layout の z の上)に天井を張る。
"""
import json
import sys
from collections import defaultdict

import bmesh
import bpy
from mathutils import Vector

A = sys.argv[sys.argv.index("--") + 1:]
LY = json.load(open(A[0], encoding="utf-8"))
OUT = A[1]
arg = lambda n, d: A[A.index(n) + 1] if n in A else d   # noqa: E731
KEEP = int(arg("--grate-keep", "3"))

# 1. 重なった面
me = bpy.data.objects["Walkway"].data
bm = bmesh.new()
bm.from_mesh(me)
bm.faces.ensure_lookup_table()
planes = defaultdict(list)
for f in bm.faces:
    n = f.normal.normalized()
    if n.length < 0.5:
        continue
    k = (round(abs(n.x), 2), round(abs(n.y), 2), round(abs(n.z), 2), round(abs(n.dot(f.verts[0].co)), 2))
    planes[k].append(f)


def inside(a, b):
    """面 a の頂点がみな面 b の中(b の平面上の凸な 4 角形)にあるか。"""
    nb = b.normal
    vs = [v.co for v in b.verts]
    for p in (v.co for v in a.verts):
        for i in range(len(vs)):
            e = vs[(i + 1) % len(vs)] - vs[i]
            if e.cross(p - vs[i]).dot(nb) < -1e-4:
                return False
    return True


dead = set()
for fs in planes.values():
    if len(fs) < 2:
        continue
    for a in fs:
        for b in fs:
            if a is b or b in dead or a in dead or a.calc_area() > b.calc_area() + 1e-9:
                continue
            if abs(a.normal.dot(b.verts[0].co - a.verts[0].co)) < 1e-3 and inside(a, b):
                dead.add(a)
                break
bmesh.ops.delete(bm, geom=list(dead), context="FACES_ONLY")
bm.to_mesh(me)
bm.free()
print("@@ overlapping faces removed", len(dead), flush=True)

# 2. 網目の桟を間引く(ばらばらの箱。道を横切る桟は 0.03 m 幅・道の幅の長さ)
me = bpy.data.objects["Walkway_Grates"].data
bm = bmesh.new()
bm.from_mesh(me)
parts, seen = [], set()
for v in bm.verts:
    if v in seen:
        continue
    st, comp = [v], []
    seen.add(v)
    while st:
        x = st.pop()
        comp.append(x)
        for e in x.link_edges:
            y = e.other_vert(x)
            if y not in seen:
                seen.add(y)
                st.append(y)
    parts.append(comp)
bars = []
for comp in parts:
    pts = [v.co for v in comp]
    c = sum(pts, Vector()) / len(pts)
    L = max((a - b).length for a in pts for b in pts)
    thin = min((pts[i] - pts[j]).length for i in range(len(pts)) for j in range(i + 1, len(pts)))
    if len(comp) == 8 and L > 1.5 and thin < 0.035:
        bars.append((c, comp))
# 隣り合う桟(0.1 m おき)でつないで 1 枚の網目ごとに分け、網目の向きに並べて KEEP 本に 1 本残す(両端は残す)
groups, used = [], set()
for i in range(len(bars)):
    if i in used:
        continue
    st, g = [i], []
    used.add(i)
    while st:
        k = st.pop()
        g.append(bars[k])
        for j in range(len(bars)):
            if j not in used and (bars[j][0] - bars[k][0]).length < 0.16:
                used.add(j)
                st.append(j)
    groups.append(g)
drop = []
for g in groups:
    a = max(g, key=lambda t: (t[0] - g[0][0]).length)[0]
    g.sort(key=lambda t: (t[0] - a).length)
    for i, (c, comp) in enumerate(g):
        if i % KEEP and i != len(g) - 1:
            drop += comp
bmesh.ops.delete(bm, geom=drop, context="VERTS")
bm.to_mesh(me)
bm.free()
print("@@ grate bars", len(bars), "rows", len(groups), "removed verts", len(drop), flush=True)

# 3. 天井
root = bpy.data.objects["City_Root"]
W = LY["wall"]
z1 = LY["z"][1]
bm = bmesh.new()
vs = [bm.verts.new((x, y, z1)) for x, y in W]
es = [bm.edges.new((vs[i], vs[(i + 1) % len(vs)])) for i in range(len(vs))]
bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=es)
for f in bm.faces:
    if f.normal.z > 0:
        f.normal_flip()
me = bpy.data.meshes.new("Valley_Ceiling")
bm.to_mesh(me)
bm.free()
me.materials.append(bpy.data.materials["city_wall"])
o = bpy.data.objects.new("Valley_Ceiling", me)
wall = bpy.data.objects["Valley_Wall"]
for c in wall.users_collection:
    c.objects.link(o)
o.parent = root
o.matrix_parent_inverse = wall.matrix_parent_inverse.copy()
print("@@ ceiling faces", len(me.polygons), flush=True)

bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("@@ wrote", OUT, flush=True)
