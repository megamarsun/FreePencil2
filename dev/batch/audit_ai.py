"""AI の窓口(ai.py)の道具を全部押して、時間・undo で戻るか・外すで元に戻るかを測る(v2.9.x の点検)。

  blender -b --factory-startup --python audit_ai.py -- <clean.blend> <out_dir>

道具ごとに: STEP0 の後の状態を写す → 道具を押す(時間) → 撮る → undo() → 写しと比べる → 撮る。
最後に 全部押した後に remove() して、STEP0 の前の状態と比べる。絵は並べて目で見る(数値は仕分け)。
"""
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fp_batch                                   # noqa: E402
fp_batch.install_addon()
import bpy                                        # noqa: E402
import numpy as np                                # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = Path(ARGV[0]).resolve(), Path(ARGV[1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
fp = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.ai"))


def state():
    s = {}
    for o in bpy.context.scene.objects:
        if o.type != "MESH" or o.hide_render:
            continue
        for a in o.data.color_attributes:
            if a.domain != "CORNER":
                continue
            buf = np.empty(len(a.data) * 4, dtype=np.float32)
            a.data.foreach_get("color", buf)
            s[f"vc/{o.name}/{a.name}"] = hashlib.md5(np.round(buf, 3).tobytes()).hexdigest()[:10]
    for m in bpy.data.materials:
        if m.node_tree and not m.name.startswith("_fp_undo_"):
            s[f"mat/{m.name}"] = (len(m.node_tree.nodes), len(m.node_tree.links),
                                  getattr(m, "blend_method", None))
    s["images"] = sorted(im.name for im in bpy.data.images if im.name not in ("Render Result", "Viewer Node"))
    return s


def diff(a, b):
    return [k for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]


bpy.ops.wm.open_mainfile(filepath=str(SRC))
sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = 960, 540
clean = state()
mesh = next(o for o in sc.objects if o.type == "MESH" and not o.hide_render and len(o.data.polygons))
t0 = time.time()
fp.auto("WEIGHTED")
rec = {"mesh": mesh.name, "faces": len(mesh.data.polygons), "auto_sec": round(time.time() - t0, 2)}
fp.preview("WHITE")
fp.render("base", scale=1.0, grid=False)
base = state()
mats = [m.name for m in bpy.data.materials if m.node_tree][:6]
TOOLS = [
    ("erase_lines", lambda: fp.erase_lines({"objects": [mesh.name], "rect": (0.4, 0.2, 0.6, 0.5)})),
    ("fade_lines", lambda: fp.fade_lines({"objects": [mesh.name], "rect": (0.4, 0.2, 0.6, 0.5)}, 0.3)),
    ("add_lines", lambda: fp.add_lines({"objects": [mesh.name], "rect": (0.4, 0.5, 0.6, 0.7)})),
    ("crisp", lambda: fp.crisp({"objects": [mesh.name], "rect": (0.4, 0.2, 0.6, 0.5)})),
    ("merge_mat", lambda: fp.merge({"objects": [mesh.name], "material": mats[:2]})),
    ("merge_rect", lambda: fp.merge({"objects": [mesh.name], "rect": (0.42, 0.25, 0.58, 0.45)})),
    ("weld", lambda: fp.weld()),
    ("soft_overlays", lambda: fp.soft_overlays(mats[:3])),
    ("clip_alpha", lambda: fp.clip_alpha()),
    ("texture_lines", lambda: fp.texture_lines({"objects": [mesh.name], "material": mats[:3]}, strength=0.5)),
    ("texture_area", lambda: fp.texture_lines({"objects": [mesh.name], "rect": (0.4, 0.3, 0.6, 0.5)},
                                              strength=1.0, dark_only=0.3, blur=2)),
]
rec["tools"] = []
for name, fn in TOOLS:
    r = {"tool": name}
    try:
        t0 = time.time()
        out = fn()
        r["sec"] = round(time.time() - t0, 2)
        r["done"] = out.get("done")
        r["warnings"] = out.get("warnings")
        after = state()
        r["changed"] = len(diff(base, after))
        fp.render(f"{name}_a", scale=1.0, grid=False)
        u = fp.undo()
        back = state()
        r["undo_left"] = diff(base, back)
        r["undo_msg"] = u.get("done") or u.get("warnings")
        fp.render(f"{name}_u", scale=1.0, grid=False)
    except Exception:                              # noqa: BLE001
        import traceback
        r["error"] = traceback.format_exc()[-800:]
    rec["tools"].append(r)
    print("@@@", json.dumps(r, ensure_ascii=False)[:600], flush=True)
# 全部押してから外す
for name, fn in TOOLS:
    try:
        fn()
    except Exception:                              # noqa: BLE001
        pass
fp.remove()
after_rm = state()
rec["remove_left"] = diff(clean, after_rm)
rec["images_left"] = sorted(set(after_rm["images"]) - set(clean["images"]))
rec["mats_left"] = [k for k in after_rm if k.startswith("mat/") and k not in clean]
fp.render("removed", scale=1.0, grid=False)
(OUT / "audit_ai.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
print("@@@ remove_left", rec["remove_left"][:20], rec["images_left"], rec["mats_left"][:5], flush=True)
print("@@@ done", flush=True)
