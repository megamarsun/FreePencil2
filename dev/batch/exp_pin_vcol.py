"""試し: 材質の「名前が空の頂点カラー」ノードを、STEP0 の前に元の色レイヤー名で固定して作例調査を回す(本体は書き換えない)。

  blender -b --factory-startup --python exp_pin_vcol.py -- <audit_v30_survey.py の引数>

頂点に色を持つスキャンの .glb(Scenario の old_man_bust, two_people)は、材質の Color Attribute ノードの
名前が空で「レンダー用に選ばれた色」を読む。FreePencil が mecha_color を足してレンダー用に切り替えると、
材質の色が塗り分けのまだらに化けた。空の名前を、その時点のレンダー用レイヤー名(Color)で埋める。
"""
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bpy  # noqa: E402
import fp_batch  # noqa: E402

fp_batch.install_addon()
ai = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.ai"))
orig = ai.auto


def patched(ctx, names, *a, **k):
    for n in names:
        o = bpy.data.objects[n]
        if o.type != "MESH" or not o.data.color_attributes:
            continue
        ca = o.data.color_attributes
        cur = ca[ca.render_color_index].name if 0 <= ca.render_color_index < len(ca) else ca[0].name
        for s in o.material_slots:
            m = s.material
            if not (m and m.node_tree):
                continue
            for nd in m.node_tree.nodes:
                if nd.bl_idname == "ShaderNodeVertexColor" and nd.layer_name == "":
                    nd.layer_name = cur
                    print(f"[exp] pin vcol: {m.name} -> {cur}")
    return orig(ctx, names, *a, **k)


ai.auto = patched
sys.argv = [sys.argv[0], "--"] + sys.argv[sys.argv.index("--") + 1:]
runpy.run_path(str(HERE / "audit_v30_survey.py"), run_name="__main__")
