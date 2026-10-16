"""C62 デモのカメラワークを撮る。STEP0 の前にカメラの動きをキーにする(遠い区画をまとめるが近づく先を測る)。

  blender -b --factory-startup --python c62_move.py -- --keys "t:x:y:z:pitch:yaw,..." --frames 336
      [--pre out/c62/c62_pre.blend] [--bg out/c62/c62_move_bg.blend(あれば STEP0 を飛ばす)]
      [--out out/c62/move] [--res 1920] [--samples 16] [--only 1,50,...] [--mode cel|3d|white]

  --mode cel   セル(影と色)。アドオンの機能だけ(STEP0 を押して、プレビューをセルにしただけ)
  --mode 3d    元の 3D(コンポジタを切った素のレンダー)。最後のワイプ用
  --mode white 線画だけ
"""
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGV[ARGV.index(n) + 1] if n in ARGV else d
HERE = Path(__file__).resolve().parent
PRE = Path(arg("--pre", str(HERE / "out" / "c62" / "c62_pre.blend"))).resolve()
BG = Path(arg("--bg", str(HERE / "out" / "c62" / "c62_move_bg.blend"))).resolve()
OUT = Path(arg("--out", str(HERE / "out" / "c62" / "move"))).resolve()
RES = int(arg("--res", "1920"))
N = int(arg("--frames", "336"))
ONLY = {int(v) for v in arg("--only", "").split(",") if v}
MODE = arg("--mode", "cel")
SPEED = float(arg("--speed", "2.5"))         # 列車の速さ(m/s)
FPS = 24
# カメラは前半だけ列車について行く(1 = 列車と一緒に動く)。この区間の外は場所に固定
FOLLOW = [tuple(float(v) for v in k.split(":")) for k in arg("--follow", "0:1,0.45:1,0.72:0").split(",")]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))
import bpy, fp_batch          # noqa: E402
import cam_path               # noqa: E402

KEYS = cam_path.parse(arg("--keys"))


def follow_w(t):
    if t <= FOLLOW[0][0]:
        return FOLLOW[0][1]
    for (t0, w0), (t1, w1) in zip(FOLLOW, FOLLOW[1:]):
        if t <= t1:
            u = (t - t0) / max(t1 - t0, 1e-6)
            u = u * u * (3 - 2 * u)
            return w0 + (w1 - w0) * u
    return FOLLOW[-1][1]


def dist(i):
    return SPEED * i / FPS


def cam_pose(i):
    """コマ i のカメラ。列車について行く分だけ +y(列車の進む向き)へずらす。"""
    loc, rot = cam_path.pose(KEYS, i, N)
    w = follow_w(i / max(1, N - 1))
    return (loc[0], loc[1] + w * dist(i), loc[2]), rot


def load_rig(sc):
    import json
    import c62_rig
    root = bpy.data.objects.get("C62_root")
    if root is None or "fp_rig" not in root:
        return None, None
    rig = json.loads(root["fp_rig"])
    ob = bpy.data.objects
    for key in ("axles", "couplings", "mains", "eccs"):
        for r in rig[key]:
            r["obj"] = ob.get(r["obj"])
            if r.get("cross"):
                r["cross"] = ob.get(r["cross"])
    return root, rig


def place_train(root, rig, i):
    import c62_rig
    if root is None:
        return
    d = dist(i)
    root.location.y = rig["y0"] + d            # 親は 180 度回してあるので、ローカルの前(-y)= ワールドの +y
    c62_rig.pose(rig, d)
fp_batch.install_addon()
if BG.exists() and "--restep" not in ARGV:
    bpy.ops.wm.open_mainfile(filepath=str(BG))
    sc = bpy.context.scene
else:
    bpy.ops.wm.open_mainfile(filepath=str(PRE))
    sc = bpy.context.scene
    # カメラの動きをキーにする(列車について行く分も入れる)。STEP0 の遠い区画をまとめるが見る
    cam = sc.camera
    sc.frame_start, sc.frame_end = 1, N
    for i in list(range(0, N, 8)) + [N - 1]:
        loc, rot = cam_pose(i)
        cam.location = loc
        cam.rotation_euler = rot
        cam.keyframe_insert("location", frame=i + 1)
        cam.keyframe_insert("rotation_euler", frame=i + 1)
    sc.frame_set(1)
    sc.fp_auto_style = "BACKGROUND"
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    print("@@@ STEP0 done", flush=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(BG))
sc.render.resolution_x = RES
sc.render.resolution_y = RES * 9 // 16
sc.eevee.taa_render_samples = int(arg("--samples", "16"))
if MODE == "3d":
    sc.render.use_compositing = False
    sc.render.film_transparent = False
    sc.render.resolution_percentage = 200       # セルと同じ大きさ(4K)で出す
    sc.view_settings.view_transform = arg("--view", "Standard")   # AgX は白っぽくかすんだ
else:
    sc.fp_preview_mode = {"cel": "CEL", "white": "WHITE", "mat": "NONE", "mono": "MONO_LIGHT"}[MODE]
for kv in [v for v in arg("--set", "").split(",") if v]:      # 確かめ用(k=v)
    k, v = kv.split("=")
    setattr(sc, k, type(getattr(sc, k))(float(v)))
root, rig = load_rig(sc)
cam = sc.camera
cam.animation_data_clear()            # 塗りは STEP0 で決まった。撮影はスクリプトで置く
d = OUT / MODE
d.mkdir(parents=True, exist_ok=True)
for i in range(N):
    if ONLY and (i + 1) not in ONLY:
        continue
    loc, rot = cam_pose(i)
    place_train(root, rig, i)
    cam.location = loc
    cam.rotation_euler = rot
    sc.render.filepath = str(d / f"f{i + 1:04d}.png")
    bpy.ops.render.render(write_still=True)
print("@@@ done", MODE, flush=True)
