"""STEP1 の塗り結果をハッシュ化して、実装を変えても出力が変わらないことを見る。

島検出を bmesh から numpy へ移すような内部改修では、「テストが通る」だけ
では不十分で、塗った色そのものが1ビットも動いていないことを確かめたい。

  blender -b --factory-startup --python hash_paint.py -- --out <json> \
      [--models a,b,c] [--limit N] [--blend <path> --rank N]

出力: {モデル名: {メッシュ名: {チャンネル: sha1}}}
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import bpy
import numpy as np

BATCH = Path(__file__).resolve().parent
sys.path.insert(0, str(BATCH))
import fp_batch      # noqa: E402
import scan_models   # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None):
    return ARGV[ARGV.index(name) + 1] if name in ARGV else default


OUT = Path(arg("--out", str(BATCH / "out" / "paint_hash.json"))).resolve()
LIMIT = int(arg("--limit", "6"))
ONLY = arg("--models")
BLEND = arg("--blend")
RANK = int(arg("--rank", "-1"))

CHANNELS = ("mecha_color", "bone_color", "mask_color", "line_color")


def hash_mesh(me) -> dict:
    out = {}
    for ch in CHANNELS:
        attr = me.color_attributes.get(ch)
        if attr is None or len(attr.data) == 0:
            continue
        buf = np.empty(len(attr.data) * 4, dtype=np.float32)
        attr.data.foreach_get("color", buf)
        # float32 の生バイトをそのまま。丸めない
        out[ch] = hashlib.sha1(buf.tobytes()).hexdigest()[:16]
    return out


def paint_selected() -> None:
    bpy.ops.freepencil.auto_vertex_color("EXEC_DEFAULT")


def run_one(name: str, blend: Path) -> dict:
    bpy.ops.wm.read_homefile(use_empty=True)
    # append_objects の戻りは (meshes, others)。normalize は
    # (全オブジェクト, メッシュ) を取るので、渡す順を間違えると
    # アーマチュアや空を基準に正規化してしまう
    meshes, others = fp_batch.append_objects(Path(blend))
    if not meshes:
        return {}
    fp_batch.normalize(meshes + others, meshes)
    scene = bpy.context.scene
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 42
    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False

    meshes = [o for o in scene.objects if o.type == "MESH"]
    if not meshes:
        return {}
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    paint_selected()
    return {me.name: h for me in bpy.data.meshes if (h := hash_mesh(me))}


fp_batch.install_addon()
result = {}

if BLEND:
    # 単一 .blend の中の、面数上位のメッシュだけを対象にする
    bpy.ops.wm.open_mainfile(filepath=str(Path(BLEND).resolve()))
    scene = bpy.context.scene
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 42
    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False
    rep = {}
    for o in scene.objects:
        if o.type != "MESH":
            continue
        cur = rep.get(o.data.name)
        if cur is None or o.name < cur.name:
            rep[o.data.name] = o
    ranked = sorted(rep.values(), key=lambda o: -len(o.data.polygons))
    picks = [ranked[RANK]] if RANK >= 0 else ranked[:LIMIT]
    for o in picks:
        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        paint_selected()
        result.setdefault(Path(BLEND).stem, {})[o.data.name] = hash_mesh(o.data)
        print(f"[hash] {o.data.name} {len(o.data.polygons):,}面", flush=True)
else:
    models = scan_models.scan(scan_models.DEFAULT_ROOT)
    if ONLY:
        want = set(ONLY.split(","))
        models = [m for m in models if m["name"] in want]
    else:
        models = models[:LIMIT]
    for m in models:
        try:
            result[m["name"]] = run_one(m["name"], m["path"])
            print(f"[hash] {m['name']}", flush=True)
        except Exception as e:                   # noqa: BLE001
            result[m["name"]] = {"ERROR": str(e)[:200]}
            print(f"[hash] {m['name']} FAILED {e}", flush=True)

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=1, sort_keys=True), encoding="utf-8")
print(f"[hash] -> {OUT}  {len(result)} 件", flush=True)
