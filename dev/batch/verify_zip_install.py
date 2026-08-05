"""配布ZIPを実際にインストールして、動く状態になるかを確かめる。

構造テストはリポジトリを直接importして走るため、
「ZIPに必要なファイルが入っているか」は検証していない。
v2.5.0 では ZIP に画像が混入して 1.9MB に膨らんだり、
バージョン表記がずれたまま出荷したりした。ここで実物を通す。

  blender -b --factory-startup --python verify_zip_install.py -- --zip <path>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ZIP = Path(ARGV[ARGV.index("--zip") + 1]).resolve()
MODULE = "bl_ext.user_default.freepencil2"

rec: dict = {"blender": bpy.app.version_string, "zip": ZIP.name,
             "zip_bytes": ZIP.stat().st_size, "ok": False}
try:
    # 既に入っていれば消してから入れ直す(前回の残骸で通ってしまうのを防ぐ)
    try:
        bpy.ops.extensions.package_uninstall(repo_index=0, pkg_id="freepencil2")
    except Exception:
        pass

    bpy.ops.extensions.package_install_files(
        filepath=str(ZIP), repo="user_default", enable_on_install=True)
    rec["installed"] = True

    mod = sys.modules.get(MODULE)
    assert mod is not None, sorted(k for k in sys.modules if "freepencil" in k)
    rec["module_file"] = getattr(mod, "__file__", None)

    # 拡張機能として入ると bl_info はモジュールから参照できなくなる(実測)。
    # 版番号は import 時に控えた ADDON_VERSION と、入った manifest を見る。
    rec["addon_version"] = list(mod.ADDON_VERSION)
    installed = Path(mod.__file__).parent / "blender_manifest.toml"
    text = installed.read_text(encoding="utf-8")
    import re
    mver = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M).group(1)
    mmin = re.search(r'^blender_version_min\s*=\s*"([^"]+)"', text, re.M).group(1)
    rec["manifest_version"] = mver
    rec["manifest_blender_min"] = mmin
    assert tuple(int(x) for x in mver.split(".")) == tuple(mod.ADDON_VERSION), \
        (mver, mod.ADDON_VERSION)
    assert bpy.app.version >= tuple(int(x) for x in mmin.split(".")), \
        f"この Blender は最低バージョン {mmin} を満たさない"

    # パネルが登録され、見出しの版番号が一致すること
    label = bpy.types.FREEPENCIL_PT_LINE.bl_label
    rec["panel_label"] = label
    assert label.endswith(mver), (label, mver)

    # 主要オペレータが呼べる状態か
    ops = ["freepencil.auto_setup", "freepencil.auto_vertex_color",
           "freepencil4.link_button", "freepencil2.link_button"]
    missing = []
    for path in ops:
        head, tail = path.split(".")
        if not hasattr(getattr(bpy.ops, head), tail):
            missing.append(path)
    rec["missing_operators"] = missing
    assert not missing, missing

    # 実際に1回通す(立方体で STEP0)
    bpy.ops.mesh.primitive_cube_add()
    bpy.context.active_object.select_set(True)
    res = bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    rec["auto_setup"] = list(res)
    assert "FINISHED" in res, res
    rec["node_groups"] = [g.name for g in bpy.data.node_groups]
    assert any(n.startswith("FreePencil") for n in rec["node_groups"]), \
        rec["node_groups"]

    rec["ok"] = True
except Exception as exc:                                    # noqa: BLE001
    import traceback
    rec["error"] = traceback.format_exc().splitlines()[-1]
    rec["trace_tail"] = traceback.format_exc()[-400:]

print("[verify_zip] " + json.dumps(rec, ensure_ascii=False))
if not rec["ok"]:
    sys.exit(1)
