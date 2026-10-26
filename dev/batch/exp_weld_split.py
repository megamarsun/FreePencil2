"""試し: 面の切れ目(同じ位置に頂点が 2 つある縁)を STEP0 の前につないで作例調査を回す(本体は書き換えない)。

  blender -b --factory-startup --python exp_weld_split.py -- <audit_v30_survey.py の引数>

AI が作った 3D(Scenario 3D Collection)の .glb は、絵の UV の切れ目で面が離れたまま書き出されていて、
アヒルが 78 個の部品に分かれ、その縁が全部ぎざぎざの線になった。縁の頂点だけ、同じ位置の物をつなぐ。
UV は面の角ごとに持つので、つないでも絵は変わらない。
環境変数 SMOOTH_DEG=30 で、向こう側の面との角度が 30 度未満の切れ目だけをつなぐ。
"""
import math
import os
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bmesh  # noqa: E402
import bpy  # noqa: E402
import fp_batch  # noqa: E402

fp_batch.install_addon()
SMOOTH_ONLY = os.environ.get("SMOOTH_DEG") is not None    # SMOOTH_DEG=30 なら滑らかな所の切れ目だけ
SMOOTH_DEG = float(os.environ.get("SMOOTH_DEG", "0"))
ai = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.ai"))
orig = ai.auto


def patched(ctx, names, *a, **k):
    for me in {bpy.data.objects[n].data for n in names if bpy.data.objects[n].type == "MESH"}:
        bm = bmesh.new()
        bm.from_mesh(me)
        dim = max(max(v.co[i] for v in bm.verts) - min(v.co[i] for v in bm.verts) for i in range(3))
        n0 = len(bm.verts)
        if SMOOTH_ONLY:
            # 縁を位置で突き合わせ、向こう側の面との角度が SMOOTH_DEG 未満の切れ目だけつなぐ
            # (角の所の切れ目は、メカのパネルの線として残す)
            q = lambda co: tuple(round(c / (dim * 1e-5)) for c in co)
            key = {}
            for e in bm.edges:
                if e.is_boundary:
                    key.setdefault(frozenset((q(e.verts[0].co), q(e.verts[1].co))), []).append(e)
            edge = set()
            for es in key.values():
                if len(es) == 2:
                    n1, n2 = es[0].link_faces[0].normal, es[1].link_faces[0].normal
                    if n1.length and n2.length and math.degrees(n1.angle(n2)) < SMOOTH_DEG:
                        edge.update(v for e in es for v in e.verts)
            edge = list(edge)
        else:
            edge = [v for v in bm.verts if any(e.is_boundary for e in v.link_edges)]
        bmesh.ops.remove_doubles(bm, verts=edge, dist=dim * 1e-5)
        print(f"[exp] weld split seams: {me.name} {n0} -> {len(bm.verts)} verts")
        bm.to_mesh(me)
        bm.free()
    return orig(ctx, names, *a, **k)


ai.auto = patched
sys.argv = [sys.argv[0], "--"] + sys.argv[sys.argv.index("--") + 1:]
runpy.run_path(str(HERE / "audit_v30_survey.py"), run_name="__main__")
