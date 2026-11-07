"""プリビズの .blend に STEP0(全自動)をそのまま押して、要所のコマを EEVEE + FreePencil で撮る(効果が出ているかの確かめ)。

  blender -b --factory-startup --python fp_stills.py -- <previz.blend> <出力フォルダ> [--frames 1500,2880,3900,4643]
      [--res 1280] [--modes WHITE,CEL] [--style ...] [--save <出力.blend>] [--curves-to-mesh] [--sun 3] [--world 0.3] [--props fp_light_amount=0.55]
      [--gray NONE]

プリビズはワークベンチなので EEVEE に切り替えてから押す(STEP0 は描画方式を変えない)。--curves-to-mesh は背景のパイプ・
ケーブル(カーブ)をメッシュに変えてから押す(STEP0 はメッシュだけを塗り分ける)。
場面に日が無い(赤い点の灯り 2 つと暗い空だけ)ので、--sun でセルと同じ向き(カメラ基準、cel_light.key_direction)の日を
置いて各コマで向ける(アドオンが日を回すのはセルのときだけ)。--world は空の明るさ。--gray に挙げた種類は白黒にした絵も残す
(テクスチャもモノクロにした陰影)。
look.py が持ち上げた背景の色は元(fp_orig_color)に戻してから押す(ワークベンチ用の明るさで、材質の色ではない)。
手直しはしない(STEP0 を押しただけの絵を見る)。カメラは各コマのマーカーのカメラ。
"""
import sys
import time
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:]
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d   # noqa: E731
SRC, OUT = Path(ARGV[0]).resolve(), Path(ARGV[1]).resolve()
FRAMES = [int(x) for x in arg("--frames", "1500,2880,3900,4643").split(",")]
RES = int(arg("--res", "1280"))
MODES = arg("--modes", "WHITE,CEL").split(",")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "batch"))
import bpy        # noqa: E402
import fp_batch   # noqa: E402

fp_batch.install_addon()
ai = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.ai"))
cel_light = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.cel_light"))
SUN = float(arg("--sun", "0"))
GRAY = [g for g in (arg("--gray") or "").split(",") if g]
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(SRC))
sc = bpy.context.scene
for m in bpy.data.materials:
    if "fp_orig_color" in m:
        m.diffuse_color = (*m["fp_orig_color"], 1)
sc.render.engine = "BLENDER_EEVEE_NEXT"
# build_city.py の材質はノード無し(ワークベンチ用の色だけ)。FreePencil は材質のノードに AOV(塗り分け・陰影)を書くので、
# ノードが無いと何も書けず、セルで空と同じ扱い(空の水色一色)になった。同じ色の Principled を付ける
nodeless = [m for m in bpy.data.materials if not m.use_nodes and m.users]
for m in nodeless:
    m.use_nodes = True
    bs = next(n for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    bs.inputs["Base Color"].default_value = (*m.diffuse_color[:3], 1)
    bs.inputs["Roughness"].default_value = m.roughness
    if "lamp" in m.name:
        bs.inputs["Emission Color"].default_value = (*m.diffuse_color[:3], 1)
        bs.inputs["Emission Strength"].default_value = 3.0
print("@@ nodes added", len(nodeless), flush=True)
if "--curves-to-mesh" in ARGV:
    cur = [o for o in sc.objects if o.type == "CURVE" and not o.hide_render]
    with bpy.context.temp_override(selected_editable_objects=cur, selected_objects=cur, active_object=cur[0]):
        bpy.ops.object.convert(target="MESH")
    print("@@ curves -> mesh", len(cur), flush=True)
if arg("--world"):
    bg = next(n for n in sc.world.node_tree.nodes if n.bl_idname == "ShaderNodeBackground")
    bg.inputs[0].default_value = (*[float(arg("--world"))] * 3, 1)
sun = None
if SUN:
    sun = bpy.data.objects.new("Demo_Sun", bpy.data.lights.new("Demo_Sun", "SUN"))
    sun.data.energy = SUN
    sc.collection.objects.link(sun)
    # 谷は壁(高さ 32 m)と頭上の梁に囲まれていて、斜め上からの日がさえぎられ谷の中が全部影になった。
    # 壁・梁・ケーブル・壁のパイプは影を落とさない(足場・手すり・キャラの影は残す)
    noshadow = [o for o in sc.objects if o.name.startswith(("Valley_", "BG_", "Wall", "Bundle", "Cable", "Gantry",
                                                            "Arch", "Riser", "Cross", "Bridge", "Core", "Abyss"))]
    for o in noshadow:
        o.visible_shadow = False
    print("@@ no shadow", len(noshadow), flush=True)
mks = sorted([m for m in sc.timeline_markers if m.camera], key=lambda m: m.frame)


def cam_at(f):
    return [m for m in mks if m.frame <= f][-1].camera


sc.frame_set(FRAMES[0])
sc.camera = cam_at(FRAMES[0])
sc.render.resolution_x, sc.render.resolution_y = RES, RES * 9 // 16
sc.render.resolution_percentage = 100
for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
    if hasattr(sc, p_):
        setattr(sc, p_, False)
vis = [o.name for o in sc.objects if o.type == "MESH" and not o.hide_render and o.visible_get() and len(o.data.polygons)]
t0 = time.time()
r = ai.auto(arg("--style"), vis)
print("@@ STEP0", round(time.time() - t0, 1), "s style", sc.fp_auto_style, "engine", sc.render.engine,
      "warnings", r.get("warnings", []), flush=True)
for kv in filter(None, (arg("--props") or "").split(",")):     # STEP0 の後に変える値(例 fp_light_amount=0.55)
    k_, v_ = kv.split("=")
    setattr(sc, k_, type(getattr(sc, k_))(v_) if isinstance(getattr(sc, k_), str) else type(getattr(sc, k_))(float(v_)))
if arg("--save"):
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(arg("--save")).resolve()))
for f in FRAMES:
    sc.frame_set(f)
    sc.camera = cam_at(f)
    if sun:
        sun.rotation_euler = cel_light.key_direction(sc).to_track_quat("Z", "Y").to_euler()
    for mode in MODES:
        sc.fp_preview_mode = mode
        sc.render.filepath = str(OUT / f"{f}_{mode}.png")
        t = time.time()
        bpy.ops.render.render(write_still=True)
        if mode in GRAY:
            img = bpy.data.images.load(sc.render.filepath)
            px = list(img.pixels)
            for i in range(0, len(px), 4):
                y = 0.2126 * px[i] + 0.7152 * px[i + 1] + 0.0722 * px[i + 2]
                px[i] = px[i + 1] = px[i + 2] = y
            img.pixels = px
            img.filepath_raw = str(OUT / f"{f}_{mode}_gray.png")
            img.save()
        print("@@ shot", f, mode, round(time.time() - t, 1), "s", flush=True)
