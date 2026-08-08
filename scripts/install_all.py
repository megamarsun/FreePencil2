"""配布ZIPをビルドして、インストール済みの全 Blender へ入れ直す。

アドオンを直すたびに必ず走らせる。実機に反映しないまま「直った」と
言わないための手順。

  python scripts\\install_all.py            # ビルド -> 全バージョンへ導入 -> 検証
  python scripts\\install_all.py --no-build # 既存の dist を使う
  python scripts\\install_all.py --test     # 導入後にスモークテストも回す

注意:
- `--factory-startup` は使わない。使うと有効化がプリファレンスに残らず、
  次に GUI で開いたときアドオンが無効のままになる
- Blender が portable 構成(インストール先に portable/ がある)なら
  %APPDATA% ではなくそちらが読まれる。package_install_files は
  Blender 自身が判断するので、ここでは気にしなくてよい
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DIST = REPO / "dist"
BLENDER_ROOT = Path(r"C:\blender")
# 対応する下限。これ未満は入れても動かない
# (4.1 以下は ShaderNodeOutputAOV.aov_name が無く STEP2 が通らない)
MIN_VERSION = (4, 2)

INSTALL_SNIPPET = '''
import bpy, sys, json
MODULE = "bl_ext.user_default.freepencil2"
rec = {"blender": bpy.app.version_string, "ok": False}
try:
    try:
        bpy.ops.preferences.addon_disable(module=MODULE)
    except Exception:
        pass
    bpy.ops.extensions.package_install_files(
        filepath=r"%(zip)s", repo="user_default", enable_on_install=True)
    # 入れ替え前のモジュールが sys.modules に残っていると、
    # 古いバージョンを読んで「入ったのに前の番号が出る」ことになる。
    # ファイルは新しいのに表示だけ古い、という紛らわしい状態だったので
    # 明示的に読み直してから確認する
    mod = sys.modules.get(MODULE)
    if mod is not None:
        import importlib
        try:
            mod = importlib.reload(mod)
        except Exception:
            pass
    rec["version"] = list(mod.ADDON_VERSION)
    # 実ファイルの記述とも突き合わせる(reload が効かない場合の保険)
    import ast, pathlib
    src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Assign) and getattr(
                node.targets[0], "id", "") == "bl_info":
            info = ast.literal_eval(node.value)
            rec["file_version"] = list(info["version"])
            break
    rec["panel"] = bpy.types.FREEPENCIL_PT_LINE.bl_label
    rec["path"] = mod.__file__
    bpy.ops.wm.save_userpref()
    rec["ok"] = True
except Exception:
    import traceback
    rec["error"] = traceback.format_exc().splitlines()[-1]
print("[install] " + json.dumps(rec, ensure_ascii=False))
'''


VERIFY_SNIPPET = '''
import bpy, sys, json
MODULE = "bl_ext.user_default.freepencil2"
rec = {"blender": bpy.app.version_string, "ok": False}
try:
    mod = sys.modules.get(MODULE)
    if mod is None:
        rec["error"] = "アドオンが有効になっていない"
    else:
        rec["version"] = list(mod.ADDON_VERSION)
        rec["panel"] = bpy.types.FREEPENCIL_PT_LINE.bl_label
        rec["path"] = mod.__file__
        rec["ok"] = True
except Exception:
    import traceback
    rec["error"] = traceback.format_exc().splitlines()[-1]
print("[install] " + json.dumps(rec, ensure_ascii=False))
'''


def version_of(exe: Path) -> tuple:
    m = re.match(r"blender-(\d+)\.(\d+)", exe.parent.name)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def find_blenders() -> list[Path]:
    """対応バージョンの Blender だけ返す。古いものは黙って飛ばさず報告する。"""
    found, skipped = [], []
    for d in sorted(BLENDER_ROOT.glob("blender-*-windows-x64")):
        exe = d / "blender.exe"
        if not exe.exists():
            continue
        if version_of(exe) < MIN_VERSION:
            skipped.append(label(exe))
        else:
            found.append(exe)
    if skipped:
        print(f"[skip] 対応外のため除外: {', '.join(skipped)} "
              f"(最低 {MIN_VERSION[0]}.{MIN_VERSION[1]})")
    return found


def label(exe: Path) -> str:
    return exe.parent.name.replace("blender-", "").replace("-windows-x64", "")


def build(exe: Path) -> Path:
    for old in DIST.glob("*.zip"):
        old.unlink()
    subprocess.run([str(exe), "--command", "extension", "build",
                    "--source-dir", str(REPO), "--output-dir", str(DIST)],
                   check=True, capture_output=True)
    zips = list(DIST.glob("*.zip"))
    if len(zips) != 1:
        raise SystemExit(f"expected one zip in dist, got {zips}")
    return zips[0]


def check_zip(zip_path: Path) -> None:
    """配布物に入ってはいけないものが混じっていないか見る。"""
    import zipfile

    names = zipfile.ZipFile(zip_path).namelist()
    stray = [n for n in names
             if n.rsplit(".", 1)[-1].lower() in ("png", "jpg", "jpeg",
                                                 "mp4", "blend", "blend1")]
    if stray:
        raise SystemExit(f"配布ZIPに不要なファイルが混入: {stray[:6]}")
    required = {"__init__.py", "blender_manifest.toml", "fp_core.py",
                "node_layout.py"}
    missing = required - set(Path(n).name for n in names)
    if missing:
        raise SystemExit(f"配布ZIPに必須ファイルが無い: {sorted(missing)}")
    size = zip_path.stat().st_size
    if size > 5 * 1024 * 1024:
        raise SystemExit(f"配布ZIPが大きすぎる ({size} bytes)")
    print(f"[zip] {zip_path.name}  {len(names)} files  {size} bytes  OK")


def run_snippet(exe: Path, code: str) -> dict:
    tmp = DIST / "_install_tmp.py"
    tmp.write_text(code, encoding="utf-8")
    try:
        # Blender の出力に UTF-8 が混じるので cp932 で読ませない
        out = subprocess.run([str(exe), "-b", "--python", str(tmp)],
                             capture_output=True, text=True, timeout=900,
                             encoding="utf-8", errors="replace")
        m = re.search(r"\[install\] (\{.*\})", out.stdout)
        if not m:
            return {"ok": False, "error": (out.stdout + out.stderr)[-300:]}
        return json.loads(m.group(1))
    finally:
        tmp.unlink(missing_ok=True)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--no-build", action="store_true")
    p.add_argument("--test", action="store_true")
    args = p.parse_args()

    blenders = find_blenders()
    if not blenders:
        raise SystemExit(f"Blender が見つからない: {BLENDER_ROOT}")
    print(f"[found] {len(blenders)} Blender: "
          + ", ".join(label(b) for b in blenders))

    if args.no_build:
        zips = list(DIST.glob("*.zip"))
        if not zips:
            raise SystemExit("dist に zip が無い。--no-build を外して")
        zip_path = zips[0]
    else:
        zip_path = build(blenders[-1])
    check_zip(zip_path)

    failed = []
    for exe in blenders:
        ver = label(exe)
        rec = run_snippet(exe, INSTALL_SNIPPET % {"zip": str(zip_path)})
        if not rec.get("ok"):
            print(f"[install] {ver:<8} NG  {rec.get('error', '')}")
            failed.append(ver)
            continue
        # 導入したプロセスでは、パネルのクラスが古いモジュールで登録された
        # ままなので版が古く見える(実際 2.6.1 を入れて 2.6.0 と表示した)。
        # 立ち上げ直して、実際に読み込まれるものを確かめる
        chk = run_snippet(exe, VERIFY_SNIPPET)
        fv = rec.get("file_version")
        mv = chk.get("version")
        bad = (not chk.get("ok")) or (fv and mv and fv != mv)
        note = ""
        if fv and mv and fv != mv:
            note = f"  ★再起動後の版が違う file={fv} loaded={mv}"
        print(f"[install] {ver:<8} {'NG ' if bad else 'OK '} "
              f"{chk.get('panel', '')} {chk.get('error', '')}{note}")
        if bad:
            failed.append(ver)

    if args.test:
        tests = REPO / "dev" / "batch" / "tests_smoke.py"
        for exe in blenders:
            ver = label(exe)
            out = subprocess.run(
                [str(exe), "-b", "--factory-startup", "--python", str(tests)],
                capture_output=True, text=True, timeout=1800,
                encoding="utf-8", errors="replace")
            line = next((ln for ln in out.stdout.splitlines()
                         if "passed" in ln), "no result")
            print(f"[tests]   {ver:<8} {line.strip()}")
            if "/" in line and line.split("/")[0].split()[-1] != \
                    line.split("/")[1].split()[0]:
                failed.append(f"{ver} tests")

    if failed:
        raise SystemExit(f"失敗: {failed}")
    print("[done] 全バージョンへ導入・有効化・保存まで完了")


if __name__ == "__main__":
    main()
