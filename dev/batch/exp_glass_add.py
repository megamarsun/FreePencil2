"""試し: 透明の BSDF を Add Shader で足したガラスも重ね物(BLEND)にして作例調査を回す(本体は書き換えない)。

  blender -b --factory-startup --python exp_glass_add.py -- <audit_v30_survey.py の引数>

mercedes-benze-s の窓: Principled(透過 1) + Transparent(0.02) を Add Shader で足していて、HASHED のまま
残り、窓一面がざらざらの点になった。auto_setup._transparent_mix は Mix Shader しか見ていない。
"""
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fp_batch  # noqa: E402

fp_batch.install_addon()
au = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.auto_setup"))
orig = au._transparent_mix


def patched(m):
    if orig(m):
        return True
    if not m.use_nodes or m.node_tree is None:
        return False
    for n in m.node_tree.nodes:
        if n.type == "ADD_SHADER" and any(lk.from_node.type == "BSDF_TRANSPARENT"
                                          for s in n.inputs for lk in s.links):
            print(f"[exp] add-transparent -> overlay: {m.name}")
            return True
    return False


au._transparent_mix = patched
sys.argv = [sys.argv[0], "--"] + sys.argv[sys.argv.index("--") + 1:]
runpy.run_path(str(HERE / "audit_v30_survey.py"), run_name="__main__")
