"""FreePencil batch evaluation driver (stdlib only, runs on any Python 3).

    python run_batch.py --limit 100 [--preset default] [--seed 42]
                        [--timeout 900] [--retry-failed] [--blender <exe>]

Parameter sweep (models x presets matrix):

    python run_batch.py --models "003_audi,069_woman" \
                        --presets "s15,default,s45,s60" --out out/sweep

Per model x preset, spawns a headless Blender running fp_batch.py with a
timeout. Already-processed combinations (metrics JSON with ok:true) are
skipped, so an interrupted batch can simply be re-run. Crashes/timeouts
are recorded as failure metrics so they show up in the report. Finally
builds <out>/report.html via make_report.py (matrix view when several
presets are present).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

BATCH_DIR = Path(__file__).resolve().parent
FP_BATCH = BATCH_DIR / "fp_batch.py"

sys.path.insert(0, str(BATCH_DIR))
import make_report  # noqa: E402
import scan_models  # noqa: E402

DEFAULT_BLENDER = r"C:\blender\blender-4.5.2-windows-x64\blender.exe"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--root", default=scan_models.DEFAULT_ROOT)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--preset", default="default")
    p.add_argument("--presets", default=None,
                   help="comma-separated preset names; overrides --preset (sweep)")
    p.add_argument("--models", default=None,
                   help="comma-separated substrings; keep only matching model names")
    p.add_argument("--material", choices=["white", "keep"], default="white")
    p.add_argument("--supersample", type=int, default=2)
    p.add_argument("--turntable", type=int, default=0)
    p.add_argument("--fps", type=int, default=12)
    p.add_argument("--res", type=int, default=1024)
    p.add_argument("--out", default=str(BATCH_DIR / "out"))
    p.add_argument("--timeout", type=int, default=900,
                   help="per-model timeout in seconds")
    p.add_argument("--retry-failed", action="store_true",
                   help="re-run models whose previous run failed")
    p.add_argument("--blender", default=DEFAULT_BLENDER)
    return p.parse_args()


def metrics_path(out_dir: Path, name: str, seed: int, preset: str, material: str) -> Path:
    return out_dir / "metrics" / f"{name}_seed{seed}_{preset}_{material}.json"


def previous_result(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_failure(path: Path, model: dict, preset: str,
                  args: argparse.Namespace, error: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "name": model["name"],
        "blend": model["path"],
        "seed": args.seed,
        "preset": preset,
        "material": args.material,
        "ok": False,
        "error": error,
    }, indent=2, ensure_ascii=False), encoding="utf-8")


def run_one(out_dir: Path, model: dict, preset: str, args: argparse.Namespace) -> bool:
    cmd = [
        args.blender, "-b", "--factory-startup", "-P", str(FP_BATCH), "--",
        "--blend", model["path"], "--name", model["name"],
        "--seed", str(args.seed), "--preset", preset,
        "--material", args.material,
        "--supersample", str(args.supersample),
        "--turntable", str(args.turntable), "--fps", str(args.fps),
        "--res", str(args.res), "--out", str(out_dir),
    ]
    mpath = metrics_path(out_dir, model["name"], args.seed, preset, args.material)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=args.timeout)
    except subprocess.TimeoutExpired:
        write_failure(mpath, model, preset, args, f"timeout after {args.timeout}s")
        return False
    rec = previous_result(mpath)
    if rec is None:
        # blender crashed before fp_batch could write metrics
        tail = "\n".join(((proc.stdout or "") + "\n" + (proc.stderr or ""))
                         .strip().splitlines()[-20:])
        write_failure(mpath, model, preset, args,
                      f"blender exited {proc.returncode} without metrics\n{tail}")
        return False
    return bool(rec.get("ok"))


def main() -> None:
    args = parse_args()
    if not Path(args.blender).exists():
        print(f"ERROR: blender not found: {args.blender}")
        sys.exit(1)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    models = scan_models.scan(args.root, args.limit, out_dir=out_dir)
    if args.models:
        subs = [s.strip() for s in args.models.split(",") if s.strip()]
        models = [m for m in models if any(s in m["name"] for s in subs)]
    if not models:
        print("ERROR: no models found")
        sys.exit(1)

    presets = ([s.strip() for s in args.presets.split(",") if s.strip()]
               if args.presets else [args.preset])
    jobs = [(m, p) for m in models for p in presets]
    print(f"[batch] {len(models)} models x {len(presets)} presets = {len(jobs)} runs")

    t0 = time.time()
    n_ok = n_fail = n_skip = 0
    for i, (model, preset) in enumerate(jobs, 1):
        mpath = metrics_path(out_dir, model["name"], args.seed, preset, args.material)
        prev = previous_result(mpath)
        if prev is not None and (prev.get("ok") or not args.retry_failed):
            n_skip += 1
            print(f"[{i}/{len(jobs)}] SKIP {model['name']} [{preset}] "
                  f"({'ok' if prev.get('ok') else 'failed before'})", flush=True)
            continue
        t1 = time.time()
        ok = run_one(out_dir, model, preset, args)
        if ok:
            n_ok += 1
        else:
            n_fail += 1
        print(f"[{i}/{len(jobs)}] {'OK  ' if ok else 'FAIL'} {model['name']} [{preset}] "
              f"({round(time.time() - t1, 1)}s)", flush=True)

    make_report.main(out_dir)
    print(f"[batch] done in {round(time.time() - t0, 1)}s: "
          f"{n_ok} ok / {n_fail} fail / {n_skip} skipped")
    print(f"[batch] report: {out_dir / 'report.html'}")


if __name__ == "__main__":
    main()
