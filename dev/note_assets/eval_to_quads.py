"""「四角面化(This to Quads)」が線画にどれだけ効いているかを測る。

このオプションはメッシュを恒久的に書き換える(実測: 1000万面のメッシュが
904万面に減った)うえ、編集モードに入るため 1000万面で 31秒 / 13.8GB を
消費する。線画の品質に見合う効果があるのかを、同じモデルの ON/OFF で
比べて確かめる。

  blender -b --factory-startup --python eval_to_quads.py -- --limit 6
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
import fp_batch      # noqa: E402
import scan_models   # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


OUT = Path(arg("--out", str(HERE / "out" / "toquads"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
LIMIT = int(arg("--limit", "6"))
RES = int(arg("--res", "800"))


def run(model: dict, to_quads: bool) -> dict:
    bpy.ops.wm.read_homefile(use_empty=True)
    # append_objects の戻りは (meshes, others)。順序を取り違えると
    # アーマチュアをメッシュとして扱って落ちる
    meshes, others = fp_batch.append_objects(Path(model["path"]))
    if not meshes:
        return {}
    fp_batch.normalize(meshes + others, meshes)
    scene = bpy.context.scene
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 42
    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False
    scene.fp_to_quads = to_quads

    before = sum(len(o.data.polygons) for o in meshes)
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]

    import time
    t = time.time()
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    secs = time.time() - t
    after = sum(len(o.data.polygons) for o in meshes)

    fp_batch.setup_camera_and_light()
    scene.render.engine = fp_batch.eevee_engine()
    scene.eevee.taa_render_samples = 16
    scene.render.resolution_x = scene.render.resolution_y = RES
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    png = OUT / f"{model['name'][:24]}_{'q' if to_quads else 'n'}.png"
    fp_batch.render_still(scene, png, 2)
    m = fp_batch.lineart_metrics(png)
    return {"faces_before": before, "faces_after": after,
            "seconds": round(secs, 2), **m}


def main() -> None:
    fp_batch.install_addon()
    models = scan_models.scan(scan_models.DEFAULT_ROOT)[:LIMIT]
    rows = []
    for m in models:
        try:
            off = run(m, False)
            on = run(m, True)
        except Exception as e:                   # noqa: BLE001
            print(f"[quads] {m['name'][:30]} FAILED {e}", flush=True)
            continue
        if not off or not on:
            continue
        row = {"name": m["name"][:30], "off": off, "on": on}
        rows.append(row)
        d_ink = (on["ink_ratio"] - off["ink_ratio"]) / max(off["ink_ratio"],
                                                           1e-9) * 100
        print(f"[quads] {row['name']:<32} "
              f"面 {off['faces_before']:>8,} -> {on['faces_after']:>8,}"
              f" ({(on['faces_after'] / max(off['faces_before'], 1) - 1) * 100:+.1f}%)"
              f"  ink {off['ink_ratio']:.5f} -> {on['ink_ratio']:.5f}"
              f" ({d_ink:+.1f}%)"
              f"  時間 {off['seconds']:.1f}s -> {on['seconds']:.1f}s",
              flush=True)
    (OUT / "result.json").write_text(json.dumps(rows, indent=1,
                                                ensure_ascii=False),
                                     encoding="utf-8")
    print(f"[quads] {len(rows)} モデル -> {OUT / 'result.json'}", flush=True)


if __name__ == "__main__":
    main()
