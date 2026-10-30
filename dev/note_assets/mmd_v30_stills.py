"""4 体のダンスを v3.0 のセル(影の形・カメラからの光・アニメの影色・2 影・光るリム)で静止画にする。

  blender -b --factory-startup --python mmd_v30_stills.py -- <dir> <出力フォルダ> [--frames 360,450,540]
          [--close 450] [--res 3840] [--only group,close]

<dir>/Four_dance_fp.blend(FreePencil を当てた後)を開き、セルのつまみを v3.0 の既定に戻してから
2 影(すき間)と光るリムを入れる。キャラの線の強さは STEP0 の今の既定 0.25 にする。
影の形は撮るコマのポーズで作り直す(ダンスでポーズが大きく変わるため)。
出力:
  group_<f>.png        並んだ 4 体(v2.9 の <dir>/Four_cel/<f>.png と同じカメラ)
  close<k>_<f>.png     顔のアップ(mmd_closeups.py と同じカメラ。v2.9 は <dir>/Four_close<k>_cel/<f>.png、300〜449)
  --look hybrid        順光に逆光をリムとして足す(ぐるり・薄い水色)
  group.blend / close<k>.blend   撮った設定の .blend
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "batch"))
import fp_batch                                   # noqa: E402
fp_batch.install_addon()
import bpy                                        # noqa: E402
from mathutils import Vector                      # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:]
D, OUT = Path(ARGV[0]).resolve(), Path(ARGV[1]).resolve()
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d   # noqa: E731
FRAMES = [int(x) for x in arg("--frames", "360,450,540").split(",")]
CLOSE = int(arg("--close", "400"))
RES = int(arg("--res", "3840"))
ONLY = set(arg("--only", "group,close").split(","))
# hybrid: 順光(既定の左・影の量 0.3)のまま、逆光をリムとして足す(ぐるり・薄い水色)
LOOK = arg("--look", "default")
OUT.mkdir(parents=True, exist_ok=True)

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

# セルのつまみを v3.0 の既定へ(この .blend は v2.9 で影 0.2・落ち影なしにしてあった)
for name in list(type(sc).bl_rna.properties.keys()):
    if name.startswith(("fp_cel_", "fp_light_")):
        sc.property_unset(name)
for o in sc.objects:
    if o.type == "LIGHT" and o.data.type == "SUN":
        o.data.use_shadow = True
sc.fp_lw_strength = float(arg("--lw", "0.25"))
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
    sc.fp_cel_rim_side, sc.fp_cel_rim_color = "ALL", (0.75, 1.0, 0.95)


def aim():
    bpy.context.view_layer.update()
    cel_light.aim_key(sc, create=True)
    cel_shade.update_sun(sc)
    bpy.context.view_layer.update()


def prepare(frame):
    sc.frame_set(frame)
    aim()
    bpy.ops.freepencil2.link_button()
    bpy.ops.freepencil.measure_line_weight()
    bpy.ops.freepencil.shade_shape()               # このコマのポーズで作り直す(セルの木も作り直す)
    aim()


def shot(name):
    sc.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    print("@@ shot", name, sc.camera.name, sc.frame_current, flush=True)


group_cam = sc.camera
if "group" in ONLY:
    for f in FRAMES:
        prepare(f)
        shot(f"group_{f}")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "group.blend"), copy=True)
# ---------------------------------------------------------------- 顔のアップ(mmd_closeups.py と同じカメラ)
F0, F1 = 300, 449                                 # mmd_closeups.py の既定(v2.9 の連番と同じ)
arms = sorted([o for o in sc.objects if o.type == "ARMATURE"], key=lambda o: o.matrix_world.translation.x)


def head_track(a):
    pb = a.pose.bones
    hd = next(pb[n] for n in ("頭", "head") if n in pb)
    nk = next(pb[n] for n in ("首", "neck") if n in pb)
    hs, ns = [], []
    for f in range(F0 - 10, F1 + 11):
        sc.frame_set(f)
        hs.append(a.matrix_world @ hd.head)
        ns.append(a.matrix_world @ nk.head)
    return hs, ns


def smooth(seq, k):
    out = []
    for i in range(len(seq)):
        lo, hi = max(0, i - k), min(len(seq), i + k + 1)
        s = Vector((0, 0, 0))
        for v in seq[lo:hi]:
            s += v
        out.append(s / (hi - lo))
    return out


if "close" in ONLY:
    for k, a in enumerate(arms):
        hs, ns = head_track(a)
        hs, ns = smooth(hs, 6), smooth(ns, 6)
        hlen = sum(((h - n).length for h, n in zip(hs, ns)), 0.0) / len(hs)
        cd = bpy.data.cameras.new(f"Close{k}")
        cd.lens = 85
        cd.sensor_fit = "VERTICAL"
        cam = bpy.data.objects.new(f"Close{k}", cd)
        sc.collection.objects.link(cam)
        sc.camera = cam
        dist = hlen * 6.0 / (2 * math.tan(cd.angle_y / 2))
        i = CLOSE - (F0 - 10)
        aim_pt = hs[i] + (hs[i] - ns[i]) * 0.2 - Vector((0, 0, hlen * 0.8))
        d = Vector((0.15, -1.0, 0.12)).normalized()
        cam.location = aim_pt + d * dist
        cam.rotation_euler = (aim_pt - cam.location).to_track_quat("-Z", "Y").to_euler()
        prepare(CLOSE)
        shot(f"close{k}_{CLOSE}")
        bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"close{k}.blend"), copy=True)
print("@@ done", flush=True)
