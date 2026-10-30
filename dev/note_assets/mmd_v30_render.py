"""4 体のダンスを v3.0 のセルで連番にする(動画用)。設定は mmd_v30_stills.py と同じ。

  blender -b --factory-startup --python mmd_v30_render.py -- <dir> <出力フォルダ> --cam group|close0..3
          [--frames 450-599] [--res 3840] [--look default|hybrid] [--resume]
          [--sub 2] [--cam-smooth 6] [--lw 0.25]

<dir>/Four_dance_fp.blend を開き、セルのつまみを v3.0 の既定に戻して 2 影(すき間)と光るリムを入れる。
キャラの線の強さは 0.25(STEP0 の既定)。影の形はコマごとにそのポーズで作り直す(作り直さないと、腕を回したとき
影が元のポーズの向きのまま残る)。
--cam group: 並んだ 4 体(場面のカメラ。v2.9 の <dir>/Four_cel と同じ)
--cam close<k>: 顔のアップ(mmd_closeups.py と同じ、頭を追うカメラ。v2.9 の <dir>/Four_close<k>_cel と同じ)
--sub 2: 1 コマを 2 つに割って撮る(60 コマ/秒。骨はキーの間を、物理は焼いた値の間を補う)。
        名前は <コマ>_<0..sub-1>.png
--cam-smooth: 顔のアップのカメラが頭を追うときのならし(前後のコマ数)。6 ではステップで上下する頭が
        コマごとに画面の中を跳ねた
出力: <出力フォルダ>/<cam>/<コマ>.png と <cam>.blend
"""
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "batch"))
import fp_batch                                   # noqa: E402
fp_batch.install_addon()
import bpy                                        # noqa: E402
from mathutils import Vector                      # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:]
D, OUT = Path(ARGV[0]).resolve(), Path(ARGV[1]).resolve()
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d   # noqa: E731
CAM = arg("--cam", "group")
F_A, F_B = (int(x) for x in arg("--frames", "450-599").split("-"))
RES = int(arg("--res", "3840"))
LOOK = arg("--look", "hybrid")
SUB = int(arg("--sub", "1"))
CAM_SMOOTH = int(arg("--cam-smooth", "6"))
LW = float(arg("--lw", "0.25"))
DST = OUT / CAM
DST.mkdir(parents=True, exist_ok=True)

CLEAN = "--clean" in ARGV
if CLEAN:
    # FreePencil を当てる前の場面に STEP0(キャラ)だけを押す(v2.9 のデモの手直しは使わない)
    bpy.ops.wm.open_mainfile(filepath=str(D / "Four_dance_clean.blend"))
    sc = bpy.context.scene
    bpy.ops.object.select_all(action="DESELECT")
    meshes = [o for o in sc.objects if o.type == "MESH" and not o.hide_render and o.visible_get()]
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    sc.fp_auto_style = "WEIGHTED"
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
else:
    bpy.ops.wm.open_mainfile(filepath=str(D / "Four_dance_fp.blend"))
    sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = RES, RES * 9 // 16
mods = {n.rsplit(".", 1)[-1]: m for n, m in sys.modules.items() if n.startswith("freepencil2.")}
cel_light, cel_shade = mods["cel_light"], mods["cel_shade"]

for name in list(type(sc).bl_rna.properties.keys()):
    if name.startswith(("fp_cel_", "fp_light_")):
        sc.property_unset(name)
for o in sc.objects:
    if o.type == "LIGHT" and o.data.type == "SUN":
        o.data.use_shadow = True
sc.fp_lw_strength = LW
if "--highlights" in ARGV:
    # 目の光を残す(アドオンの auto_setup.keep_highlights。STEP0 も同じものを呼ぶ)。この .blend は
    # v2.9 のデモで目の光を重ね物(BLEND)にしてあり、セルで消えていた
    targets = [o for o in sc.objects if o.type == "MESH" and not o.hide_render]
    names = mods["auto_setup"].keep_highlights(sc, bpy.context.view_layer, targets)
    print("@@ highlights", names, flush=True)
sc.fp_preview_mode = "NONE"
sc.fp_preview_mode = "CEL"
# --no-shadow2: すき間の 2 影を入れない(重なった髪の束の AO が髪にまだらの濃い影を出した、ミク)
sc.fp_cel_shadow2 = "NONE" if "--no-shadow2" in ARGV else "AO"
sc.fp_cel_rim = True
if LOOK == "hybrid":
    # 順光(左・影の量 0.3)のまま、逆光をリムとして足す(ぐるり・薄い水色)
    sc.fp_cel_rim_side, sc.fp_cel_rim_color = "ALL", (0.75, 1.0, 0.95)


def aim():
    bpy.context.view_layer.update()
    cel_light.aim_key(sc, create=True)
    cel_shade.update_sun(sc)
    bpy.context.view_layer.update()


def smooth(seq, k):
    out = []
    for i in range(len(seq)):
        lo, hi = max(0, i - k), min(len(seq), i + k + 1)
        s = Vector((0, 0, 0))
        for v in seq[lo:hi]:
            s += v
        out.append(s / (hi - lo))
    return out


def close_camera(k):
    """mmd_closeups.py と同じ: 頭を追う 85mm、正面寄り。コマ 300〜449 でならす。"""
    F0, F1 = 300, 449
    arms = sorted([o for o in sc.objects if o.type == "ARMATURE"], key=lambda o: o.matrix_world.translation.x)
    a = arms[k]
    pb = a.pose.bones
    hd = next(pb[n] for n in ("頭", "head") if n in pb)
    nk = next(pb[n] for n in ("首", "neck") if n in pb)
    hs, ns = [], []
    for f in range(F0 - 10, F1 + 11):
        sc.frame_set(f)
        hs.append(a.matrix_world @ hd.head)
        ns.append(a.matrix_world @ nk.head)
    hs, ns = smooth(hs, CAM_SMOOTH), smooth(ns, CAM_SMOOTH)
    hlen = sum(((h - n).length for h, n in zip(hs, ns)), 0.0) / len(hs)
    cd = bpy.data.cameras.new(f"Close{k}")
    cd.lens = 85
    cd.sensor_fit = "VERTICAL"
    cam = bpy.data.objects.new(f"Close{k}", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    dist = hlen * 6.0 / (2 * math.tan(cd.angle_y / 2))
    d = Vector((0.15, -1.0, 0.12)).normalized()
    for i, f in enumerate(range(F0 - 10, F1 + 11)):
        p = hs[i] + (hs[i] - ns[i]) * 0.2 - Vector((0, 0, hlen * 0.8))
        cam.location = p + d * dist
        cam.rotation_euler = (p - cam.location).to_track_quat("-Z", "Y").to_euler()
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)


if CAM.startswith("close"):
    close_camera(int(CAM[5:]))
sc.frame_set((F_A + F_B) // 2)
aim()
bpy.ops.freepencil2.link_button()
bpy.ops.freepencil.measure_line_weight()          # カメラごとに 1 回(mmd_closeups.py と同じ)
saved = False
for f in range(F_A, F_B + 1):
    for j in range(SUB):
        path = DST / (f"{f:04d}.png" if SUB == 1 else f"{f:04d}_{j}.png")
        if path.exists() and "--resume" in ARGV:
            continue
        t0 = time.time()
        sc.frame_set(f, subframe=j / SUB)
        aim()
        bpy.ops.freepencil.shade_shape()               # このコマのポーズで影の形を作り直す
        aim()
        t1 = time.time()
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        print(f"@@ {CAM} {f}.{j} bake {t1 - t0:.1f}s render {time.time() - t1:.1f}s", flush=True)
        if not saved:
            bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{CAM}.blend"), copy=True)
            saved = True
print("@@ done", CAM, flush=True)
