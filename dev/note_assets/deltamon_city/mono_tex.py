"""モノクロ陰影(MONO_LIGHT)に、材質の色・テクスチャの明るさも掛ける(テクスチャのモノクロ化)。

アドオンの MONO_LIGHT は光(Diffuse Direct)だけを白黒にして線の下に敷くので、テクスチャで描いた目や口が出ず、
顔がのっぺらぼうになった。敷く陰影に、材質の色のパス(Diffuse Color)を白黒にしたものを掛ける。
掛けるのはキャラ(アーマチュアで動く物)だけ。背景の材質はワークベンチ用の暗い単色で、掛けると承認した背景の明るさが
暗く沈んだ(背景にテクスチャは無いので、掛けても陰影が暗くなるだけ)。キャラはクリプトマット(物)で分ける(EEVEE には物のインデックスのパスが無い)。
fp_preview_mode を MONO_LIGHT にした後で呼ぶ(切り替えるとアドオンが敷く絵を作り直す)。
"""
import bpy

LABEL = "demo_mono_tex"
UNDER = "FP_Underlay"


def apply(scene, floor=0.0):
    vl = scene.view_layers[0]
    vl.use_pass_diffuse_color = True
    vl.use_pass_cryptomatte_object = True
    chars = [o for o in scene.objects if o.type == "MESH" and any(m.type == "ARMATURE" for m in o.modifiers)]
    print("@@ mono_tex chars", [o.name for o in chars], flush=True)
    tree = scene.node_tree if hasattr(scene, "node_tree") and scene.node_tree else scene.compositing_node_group
    for n in [n for n in tree.nodes if n.label == LABEL]:
        tree.nodes.remove(n)
    lift = next((n for n in tree.nodes if n.label == UNDER and n.type == "MAP_RANGE"), None)
    rl = next(n for n in tree.nodes if n.type == "R_LAYERS")
    col = next((s for s in rl.outputs if s.name in ("Diffuse Color", "DiffCol") and s.enabled), None)
    if lift is None or col is None:
        raise RuntimeError(f"mono_tex: lift={lift} col={col}")
    dst = [lk.to_socket for lk in lift.outputs[0].links]

    def add(t):
        n = tree.nodes.new(t)
        n.label = LABEL
        n.hide = True
        n.location = (lift.location.x, lift.location.y - 120 * (len([m for m in tree.nodes if m.label == LABEL])))
        return n
    bw = add("CompositorNodeRGBToBW")
    tree.links.new(col, bw.inputs[0])
    # キャラの外は 1: alb = bw * mask + (1 - mask)
    cm = add("CompositorNodeCryptomatteV2")
    cm.source = "RENDER"
    cm.scene = scene
    cm.layer_name = f"{vl.name}.CryptoObject"
    cm.matte_id = ",".join(o.name for o in chars)
    addn = add("CompositorNodeMixRGB")
    tree.links.new(cm.outputs["Matte"], addn.inputs[0])
    addn.inputs[1].default_value = (1, 1, 1, 1)
    tree.links.new(bw.outputs[0], addn.inputs[2])
    # 黒い材質でも真っ黒につぶさない(floor)
    rng = add("CompositorNodeMapRange")
    rng.inputs["To Min"].default_value = floor
    tree.links.new(addn.outputs[0], rng.inputs[0])
    mul = add("CompositorNodeMath")
    mul.operation = "MULTIPLY"
    tree.links.new(lift.outputs[0], mul.inputs[0])
    tree.links.new(rng.outputs[0], mul.inputs[1])
    for s in dst:
        tree.links.new(mul.outputs[0], s)
    print("@@ mono_tex on", len(dst), "links", flush=True)
