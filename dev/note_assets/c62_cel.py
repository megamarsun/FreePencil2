"""試作: 線画の下にセル調の陰影(2 階調)と薄い色を敷く(アドオンには入れず、コンポジタに足す)。

  blender -b --factory-startup --python c62_cel.py -- [--bg out/c62/c62_bg.blend] [--out out/c62/cel]
      [--res 1920] [--cams name=x,y,z,pitch,yaw;...] [--pale 0.45] [--thr 0.35] [--save out/c62/c62_cel.blend]

色:
  - 建物は薄い色の組(クリーム、薄い灰青、薄いれんが、薄緑...)から棟ごとに選ぶ。材質は FreePencil の
    AOV ノードが入った共有の灰色のままにして、色はオブジェクトの色(Object Info)から取る
  - 鉄橋は朱、川は水色、地面は明るい灰、空は薄い水色
  - 機関車は元の材質の色(黒)をそのまま薄める
陰影:
  - 材質に関係なく「白い拡散面に当たった光(影込み)」を AOV(fp_shade)に出し、ぼかしてしきい値で 2 階調
  - 影の所に薄い青紫を掛ける
合成: 線画(白地に黒線) x (薄めた色 x 影)。物の外は空の色
"""
import math
import random
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
HERE = Path(__file__).resolve().parent
BG = Path(arg("--bg", str(HERE / "out" / "c62" / "c62_bg.blend"))).resolve()
OUT = Path(arg("--out", str(HERE / "out" / "c62" / "cel"))).resolve()
RES = int(arg("--res", "1920"))
CAMS = [c.split("=") for c in arg("--cams", "a=6,16,6.5,88,160").split(";")]
PALE = float(arg("--pale", "0.12"))          # 白へ寄せる割合(大きいほど薄い)
THR = float(arg("--thr", "0.35"))
SHADOW = tuple(float(v) for v in arg("--shadow", "0.70,0.72,0.86").split(","))
SKY = tuple(float(v) for v in arg("--sky", "0.80,0.88,0.96").split(","))
sys.path.insert(0, str(HERE.parent / "batch"))
import bpy, fp_batch          # noqa: E402
import importlib              # noqa: E402

fp_batch.install_addon()
compat = importlib.import_module(fp_batch.ADDON_NAME + ".compat")
line_weight = importlib.import_module(fp_batch.ADDON_NAME + ".line_weight")
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(BG))
sc = bpy.context.scene
vl = bpy.context.view_layer
rng = random.Random(5)

# ---------------------------------------------------------------- 色(線形)
# 薄い色(画面に出る色そのもの、sRGB)。棟ごとに選ぶ
PALETTE = [(0.95, 0.88, 0.70), (0.72, 0.82, 0.90), (0.90, 0.68, 0.58), (0.74, 0.86, 0.72),
           (0.93, 0.92, 0.86), (0.84, 0.76, 0.90), (0.98, 0.80, 0.58), (0.68, 0.74, 0.80),
           (0.92, 0.80, 0.80), (0.80, 0.88, 0.84)]


def lin(c):
    return tuple(((v + 0.055) / 1.055) ** 2.4 if v > 0.04045 else v / 12.92 for v in c)


for o in sc.objects:
    if o.type != "MESH":
        continue
    n = o.name
    if n.startswith("b") and n[1:].isdigit() or n.startswith(("shop", "apt", "house", "tower", "konbini")):
        c = rng.choice(PALETTE)
    elif n == "bridge":
        c = (0.86, 0.26, 0.18)                     # 朱
    elif n == "FP_water":
        c = (0.55, 0.75, 0.88)
    elif n.startswith("FP_ground"):
        c = (0.86, 0.85, 0.82)
    elif n in ("banks", "embankment"):
        c = (0.80, 0.79, 0.76)
    elif n == "poles":
        c = (0.55, 0.55, 0.55)
    else:
        c = rng.choice(PALETTE)
    o.color = (*lin(c), 1.0)

# 空: カメラから見える背景だけ白にする(照らす光は元の灰色のまま。影の出方を変えない)
wt = sc.world.node_tree
bg0 = wt.nodes.get("Background")
out = next(nd for nd in wt.nodes if nd.type == "OUTPUT_WORLD")
bgw = wt.nodes.new("ShaderNodeBackground")
bgw.inputs[0].default_value = (1, 1, 1, 1)
bgw.inputs[1].default_value = 1.0
lp = wt.nodes.new("ShaderNodeLightPath")
mx = wt.nodes.new("ShaderNodeMixShader")
wt.links.new(lp.outputs["Is Camera Ray"], mx.inputs[0])
wt.links.new(bg0.outputs[0], mx.inputs[1])
wt.links.new(bgw.outputs[0], mx.inputs[2])
wt.links.new(mx.outputs[0], out.inputs["Surface"])

grey = bpy.data.materials.get("c62_grey")
nt = grey.node_tree
bsdf = nt.nodes.get("Principled BSDF")
info = nt.nodes.new("ShaderNodeObjectInfo")
nt.links.new(info.outputs["Color"], bsdf.inputs["Base Color"])

# ---------------------------------------------------------------- 影の AOV(全材質)
SHADE = "fp_shade"
if SHADE not in [a.name for a in vl.aovs]:
    a = vl.aovs.add()
    a.name = SHADE
    a.type = "VALUE"
for m in bpy.data.materials:
    if not m.use_nodes or m.name.startswith("FreePencil"):
        continue
    t = m.node_tree
    if any(nd.type == "OUTPUT_AOV" and getattr(nd, "aov_name", "") == SHADE for nd in t.nodes):
        continue
    dif = t.nodes.new("ShaderNodeBsdfDiffuse")
    dif.inputs["Color"].default_value = (1, 1, 1, 1)
    s2r = t.nodes.new("ShaderNodeShaderToRGB")
    aov = t.nodes.new("ShaderNodeOutputAOV")
    aov.aov_name = SHADE
    t.links.new(dif.outputs[0], s2r.inputs[0])
    t.links.new(s2r.outputs["Color"], aov.inputs["Value"])
vl.use_pass_diffuse_color = True

# ---------------------------------------------------------------- コンポジタ
tree = compat.get_compositor_tree(sc)
rl = next(n for n in tree.nodes if n.type == "R_LAYERS")
comp = next(n for n in tree.nodes if n.type in compat.OUTPUT_NODE_TYPES)
target = comp.inputs[0]
src = target.links[0].from_socket
if src.node.type == "SCALE":                      # 縮小の前に掛ける(等倍の解像度で合成)
    target = src.node.inputs[0]
    src = target.links[0].from_socket
ss = 2.0 if sc.render.resolution_percentage == 200 else 1.0


def node(t, x, y):
    n = tree.nodes.new(t)
    n.location = (x, y)
    n.label = "FP_CelProto"
    return n


def math_(op, a=None, b=None, x=0, y=0, clamp=False):
    n = node("CompositorNodeMath", x, y)
    n.operation = op
    n.use_clamp = clamp
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            tree.links.new(v, n.inputs[i])
    return n.outputs[0]


def mix(fac, c1, c2, blend="MIX", x=0, y=0):
    n = node("CompositorNodeMixRGB", x, y)
    n.blend_type = blend
    for i, v in ((0, fac), (1, c1), (2, c2)):
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        elif isinstance(v, tuple):
            n.inputs[i].default_value = (*v, 1)
        else:
            tree.links.new(v, n.inputs[i])
    return n.outputs[0]


shade = compat.render_layer_socket(rl, (SHADE,))
dcol = compat.render_layer_socket(rl, ("DiffCol", "Diffuse Color"))
# 物のある所: 背景を透過にしてレンダーのアルファで取る(深度での判定は空まで物と見なした)
sc.render.film_transparent = True
sil = rl.outputs["Alpha"]
# 光の強さで割る(日なたが 1 前後)。太陽の強さ / pi
sun = next(o for o in sc.objects if o.type == "LIGHT")
norm = math_("DIVIDE", shade, sun.data.energy / math.pi + 0.8 * 0.6, 400, -1200)
blur = node("CompositorNodeBlur", 560, -1200)
compat.set_node_value(blur, "filter_type", "GAUSS")
for k in ("size_x", "size_y"):
    try:
        setattr(blur, k, int(3 * ss))
    except Exception:
        pass
if "Size" in blur.inputs:
    dv = blur.inputs["Size"].default_value
    blur.inputs["Size"].default_value = (3 * ss, 3 * ss) if hasattr(dv, "__len__") else 3 * ss
tree.links.new(norm, blur.inputs[0])
lit = math_("GREATER_THAN", blur.outputs[0], THR, 720, -1200)
# 薄めた色: 色 -> 白へ PALE だけ寄せる
pale = mix(PALE, dcol, (1.0, 1.0, 1.0), x=720, y=-1000)
cel = mix(lit, SHADOW, (1.0, 1.0, 1.0), x=880, y=-1100)      # 日なた 1、影は青紫
colored = mix(1.0, pale, cel, "MULTIPLY", 1040, -1000)
body = mix(sil, SKY, colored, x=1200, y=-1000)                # 物の外は空の色
# 線画は背景が透過(アルファ 0)なので、白の上に重ねてから掛ける
over = node("CompositorNodeAlphaOver", 1200, -800)
over.inputs[1].default_value = (1, 1, 1, 1)
tree.links.new(src, over.inputs[2])
final = mix(1.0, body, over.outputs[0], "MULTIPLY", 1360, -900)            # 線画(白地に黒線)を掛ける
if "--debug-shade" in ARGV:                                      # 影の明るさ(正規化後)をそのまま出す
    final = norm
opaque = node("CompositorNodeSetAlpha", 1520, -900)               # 出力は不透明(空も色で塗る)
compat.set_node_value(opaque, "mode", "REPLACE_ALPHA")
tree.links.new(final, opaque.inputs["Image"])
opaque.inputs["Alpha"].default_value = 1.0
final = opaque.outputs[0]
tree.links.new(final, target)
sc.fp_preview_mode = "WHITE"
sc.render.resolution_x = RES
sc.render.resolution_y = RES * 9 // 16
if arg("--save"):
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(arg("--save")).resolve()))
cam = sc.camera
for name, spec in CAMS:
    x, y, z, p, yaw = (float(v) for v in spec.split(","))
    cam.location = (x, y, z)
    cam.rotation_euler = (math.radians(p), 0, math.radians(yaw))
    sc.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    print("@@@ rendered", name, flush=True)
