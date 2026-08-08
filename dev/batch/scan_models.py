"""Scan the BlenderKit cache for .blend assets.

Importable (used by run_batch.py) and runnable with any Python 3
(stdlib only, bpy not required):
    python scan_models.py -- --limit 100

Writes dev/batch/out/models.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# scan only model assets (the cache also holds materials/ hdrs/ without meshes)
# 評価用アセットは BlenderKit のローカルキャッシュを使う。置き場所は環境に
# よって違うので FP_MODEL_ROOT で上書きできる。既定はホーム直下の標準の場所
# (公開リポジトリに個人のパスを残さないため)
DEFAULT_ROOT = os.environ.get(
    "FP_MODEL_ROOT", str(Path.home() / "blenderkit_data" / "models"))
BATCH_DIR = Path(__file__).resolve().parent
OUT_DIR = BATCH_DIR / "out"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    if argv is None:
        argv = sys.argv
        argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=DEFAULT_ROOT)
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--min-mb", type=float, default=0.05)
    p.add_argument("--max-mb", type=float, default=150.0)
    return p.parse_args(argv)


def find_blends(root: Path, min_b: float, max_b: float) -> list[Path]:
    found: dict[str, Path] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        # BlenderKit cache keeps resolution variants; prefer the base file
        for fn in filenames:
            if not fn.lower().endswith(".blend"):
                continue
            path = Path(dirpath) / fn
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if not (min_b <= size <= max_b):
                continue
            # Deduplicate resolution variants (foo_2k.blend / foo.blend) by stem prefix
            key = fn.split("_resolution_")[0].lower()
            prev = found.get(key)
            if prev is None or path.stat().st_size < prev.stat().st_size:
                found[key] = path
    return sorted(found.values())


def scan(root: str = DEFAULT_ROOT, limit: int = 100,
         min_mb: float = 0.05, max_mb: float = 150.0,
         out_dir: Path | None = None) -> list[dict]:
    """Scan the cache and write models.json; returns the model list."""
    out = Path(out_dir) if out_dir else OUT_DIR
    root_path = Path(root)
    if not root_path.exists():
        raise FileNotFoundError(f"cache root not found: {root_path}")

    blends = find_blends(root_path, min_mb * 1e6, max_mb * 1e6)[:limit]
    out.mkdir(parents=True, exist_ok=True)

    models = [
        {
            "name": f"{i:03d}_{b.stem[:40]}",
            "path": str(b),
            "size_mb": round(b.stat().st_size / 1e6, 2),
        }
        for i, b in enumerate(blends)
    ]
    (out / "models.json").write_text(
        json.dumps(models, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[scan] {len(models)} models -> {out / 'models.json'}")
    return models


def main() -> None:
    args = parse_args()
    scan(args.root, args.limit, args.min_mb, args.max_mb)


if __name__ == "__main__":
    main()
