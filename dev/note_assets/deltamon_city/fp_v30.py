"""v3.0 のセルを全部使って撮る: STEP0 → セル + キャラと背景で光を分ける + カメラからの日 + 影の形(コマごとに作り直す)
+ アニメの影色 + 顔はいつも日なた + リム(ぐるり)+ 2 影(すき間)。

  blender -b --factory-startup --python fp_v30.py -- <previz.blend> <出力フォルダ> [--frames 690,1890] [--start 1 --end 5400]
      [--res 1280] [--bg-sun 3] [--world 0.3] [--save <出力.blend>] [--no-rim] [--no-ao] [--set fp_light_amount=0.4,...]

背景は場面の光の通常の陰影(分ける機能のとおり、簡易化は入れない)。場面には赤い点の灯り 2 つと暗い空しか無いので、
ワールドに固定した日(--bg-sun)と空の明るさ(--world)を足す(カメラに付いて回すと、曲がるたびに壁の明暗が入れ替わる)。
谷の壁(高さ 32 m)・頭上の梁・天井はその日の影を落とさない(谷の中が全部影になった。fp_stills.py と同じ)。
キャラの日(FP_KeySun)はアドオンが作り、カメラ基準で各コマ回す。影の形は「影の形を追ってアニメをレンダー」と同じく
コマごとにそのポーズで作り直す。出力は f_0001.png …、もうあるコマは飛ばす。
"""
import math
import sys
import time
from pathlib import Path

from mathutils import Euler

ARGV = sys.argv[sys.argv.index("--") + 1:]
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d   # noqa: E731
SRC, OUT = Path(ARGV[0]).resolve(), Path(ARGV[1]).resolve()
RES = int(arg("--res", "1280"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "batch"))
import bpy        # noqa: E402
import fp_batch   # noqa: E402

fp_batch.install_addon()
mod = lambda s: next(m for n, m in sys.modules.items() if n.endswith("freepencil2." + s))   # noqa: E731
ai, cel_light, cel_shade, shade_normal, light_split = (mod(s) for s in
                                                       ("ai", "cel_light", "cel_shade", "shade_normal", "light_split"))
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(SRC))
sc = bpy.context.scene
vl = bpy.context.view_layer
mks = sorted([m for m in sc.timeline_markers if m.camera], key=lambda m: m.frame)


def cam_at(f):
    return [m for m in mks if m.frame <= f][-1].camera


if not sc.get("fp_v30_ready"):     # --save で残した .blend なら下ごしらえは済んでいる
    # --- 下ごしらえ(fp_stills.py と同じ)
    for m in bpy.data.materials:
        if "fp_orig_color" in m:
            m.diffuse_color = (*m["fp_orig_color"], 1)
    sc.render.engine = "BLENDER_EEVEE_NEXT"
    for m in [m for m in bpy.data.materials if not m.use_nodes and m.users]:
        m.use_nodes = True
        bs = next(n for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
        bs.inputs["Base Color"].default_value = (*m.diffuse_color[:3], 1)
        bs.inputs["Roughness"].default_value = m.roughness
        if "lamp" in m.name:
            bs.inputs["Emission Color"].default_value = (*m.diffuse_color[:3], 1)
            bs.inputs["Emission Strength"].default_value = 3.0
    bg = next(n for n in sc.world.node_tree.nodes if n.bl_idname == "ShaderNodeBackground")
    bg.inputs[0].default_value = (*[float(arg("--world", "0.3"))] * 3, 1)
    sun = bpy.data.objects.new("Demo_BgSun", bpy.data.lights.new("Demo_BgSun", "SUN"))
    sun.data.energy = float(arg("--bg-sun", "3"))
    sun.rotation_euler = Euler((math.radians(40), 0, math.radians(30)))   # ワールドに固定(斜め上から)
    sc.collection.objects.link(sun)
    for o in sc.objects:
        if o.name.startswith(("Valley_", "BG_", "Wall", "Bundle", "Cable", "Gantry", "Arch", "Riser", "Cross",
                              "Bridge", "Core", "Abyss")):
            o.visible_shadow = False
    sc.render.resolution_x, sc.render.resolution_y = RES, RES * 9 // 16
    sc.render.resolution_percentage = 100
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
        if hasattr(sc, p_):
            setattr(sc, p_, False)
    f0 = int((arg("--frames") or arg("--start", "1")).split(",")[0])
    sc.frame_set(f0)
    sc.camera = cam_at(f0)
    vis = [o.name for o in sc.objects if o.type == "MESH" and not o.hide_render and o.visible_get() and len(o.data.polygons)]
    t0 = time.time()
    r = ai.auto(None, vis)
    print("@@ STEP0", round(time.time() - t0, 1), "s style", sc.fp_auto_style, "warnings", r.get("warnings", []), flush=True)
    # --- v3.0 のセル
    sc.fp_light_mode = "CAMERA"
    sc.fp_light_split = True
    sc.fp_preview_mode = "CEL"
    chars = light_split.char_objects(sc)
    b = shade_normal.bake(sc, vl, chars)
    print("@@ chars", [o.name for o in chars], "shade", b, flush=True)
    sc.fp_cel_rim = "--no-rim" not in ARGV
    # 影の側だけ・幅 6・暗め(ぐるり・幅 10・明るい水色では縁がシールのように白く光って強すぎた。4 案を並べて選んだ)
    sc.fp_cel_rim_side = "AUTO"
    sc.fp_cel_rim_width = 6.0
    sc.fp_cel_rim_color = (0.4, 0.5, 0.48)
    # 街は C(光)で決めた。アドオンの既定が日なたの色になったので、ここで光に固定する
    sc.fp_cel_rim_style = "GLOW"
    sc.fp_cel_shadow2 = "NONE" if "--no-ao" in ARGV else "AO"
    for kv in filter(None, (arg("--set") or "").split(",")):
        k_, v_ = kv.split("=")
        cur = getattr(sc, k_)
        setattr(sc, k_, v_ if isinstance(cur, str) else type(cur)(float(v_)))
    cel_shade.set_cel(sc, True)
    sc["fp_v30_ready"] = True
    print("@@ split", light_split.enabled(sc), "key", cel_shade.key_sun(sc).name, "face", sc.fp_cel_face,
          "shape", sc.fp_cel_shape, "style", sc.fp_cel_shadow_style, flush=True)
    if arg("--save"):
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(arg("--save")).resolve()))
elif arg("--set"):                                  # 保存した .blend の値を変えて撮る(リムの強さを試す等)
    for kv in arg("--set").split(","):
        k_, v_ = kv.split("=")
        cur = getattr(sc, k_)
        if isinstance(cur, str):
            setattr(sc, k_, v_)
        elif hasattr(cur, "__len__"):
            setattr(sc, k_, [float(x) for x in v_.split("/")])
        else:
            setattr(sc, k_, type(cur)(float(v_)))
    cel_shade.set_cel(sc, True)

frames = ([int(x) for x in arg("--frames").split(",")] if arg("--frames")
          else range(int(arg("--start", "1")), int(arg("--end", "5400")) + 1))
for f in frames:
    p = OUT / f"f_{f:04d}.png"
    if p.exists():
        continue
    t = time.time()
    sc.frame_set(f)
    sc.camera = cam_at(f)
    n = shade_normal.follow(sc)
    cel_light.aim_key(sc)
    cel_shade.update_sun(sc)
    sc.render.filepath = str(p)
    bpy.ops.render.render(write_still=True)
    print("@@ shot", f, "shapes", n, round(time.time() - t, 1), "s", flush=True)
print("@@ done", flush=True)
