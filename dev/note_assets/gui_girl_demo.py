"""手作業デモの録画: 窓のある Blender で anime-girl を STEP0 → 手直し → セル まで進め、画面を撮り続ける。

  blender --enable-event-simulate --window-maximized <girl_clean.blend> --python gui_girl_demo.py -- <out_dir>

手直しは AI の窓口(freepencil2.ai)で行う。直す所は、人が四角で囲むように画面に描いてから直す。
画面の下に字幕を出す。撮った絵(frames/*.png)と時刻(frames.json)を残し、動画は別のスクリプトで組む。
"""
import json
import sys
import time
from pathlib import Path

import blf
import bpy
import gpu
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

OUT = Path(sys.argv[sys.argv.index("--") + 1:][0]).resolve()
FR = OUT / "frames"
FR.mkdir(parents=True, exist_ok=True)
for p in FR.glob("*.png"):
    p.unlink()
LOG = []
S = {"beat": 0, "t_beat": None, "caption": "", "sub": "", "rect": None, "rect_p": 0.0,
     "rect_t0": None, "shot": 0, "t0": time.time(), "busy": None, "done": False}


def fp():
    return next(m for n, m in sys.modules.items() if n.endswith("freepencil2.ai"))


def win():
    return bpy.context.window_manager.windows[0]


def v3d():
    areas = list(win().screen.areas)
    a = next((a for a in areas if a.type == "VIEW_3D"), None)
    if a is None:
        # モデルのファイルが保存していた画面に 3D ビューが無いことがある。いちばん大きい区画を使う
        a = max(areas, key=lambda a: a.width * a.height)
        a.type = "VIEW_3D"
    return a


def ov():
    a = v3d()
    return dict(window=win(), area=a, region=next(r for r in a.regions if r.type == "WINDOW"),
                screen=win().screen)


# ---------------------------------------------------------------- 画面に描く(字幕と四角)
def _frame_corners_2d():
    """カメラの枠の 4 隅の画面座標(右上・右下・左下・左上)。"""
    sc = bpy.context.scene
    cam = sc.camera
    a = v3d()
    region = next(r for r in a.regions if r.type == "WINDOW")
    rv3d = a.spaces[0].region_3d
    fr = cam.data.view_frame(scene=sc)
    return [view3d_utils.location_3d_to_region_2d(region, rv3d, cam.matrix_world @ v) for v in fr]


def _rect_to_px(rect):
    c = _frame_corners_2d()
    if any(p is None for p in c):
        return None
    tr, br, bl, tl = c

    def at(x, y):              # x: 左→右, y: 上→下(0〜1)
        top = tl.lerp(tr, x)
        bot = bl.lerp(br, x)
        return top.lerp(bot, y)
    x0, y0, x1, y1 = rect
    return [at(x0, y0), at(x1, y0), at(x1, y1), at(x0, y1)]


SH = gpu.shader.from_builtin("UNIFORM_COLOR")


def draw_cb():
    region = bpy.context.region
    # 四角(人が囲むように、左上から右下へ伸びる)
    if S["rect"] is not None:
        p = min(1.0, S["rect_p"])
        x0, y0, x1, y1 = S["rect"]
        r = (x0, y0, x0 + (x1 - x0) * p, y0 + (y1 - y0) * p)
        pts = _rect_to_px(r)
        if pts:
            gpu.state.blend_set("ALPHA")
            gpu.state.line_width_set(3.0)
            fill = batch_for_shader(SH, "TRI_FAN", {"pos": [tuple(q) for q in pts]})
            SH.bind()
            SH.uniform_float("color", (1.0, 0.45, 0.1, 0.12))
            fill.draw(SH)
            loop = batch_for_shader(SH, "LINE_LOOP", {"pos": [tuple(q) for q in pts]})
            SH.uniform_float("color", (1.0, 0.45, 0.1, 0.95))
            loop.draw(SH)
            gpu.state.line_width_set(1.0)
            gpu.state.blend_set("NONE")
    # 字幕
    if S["caption"]:
        w = region.width
        fid = 0
        blf.size(fid, 46)
        tw, th = blf.dimensions(fid, S["caption"])
        sub = S["sub"]
        blf.size(fid, 30)
        sw, sh_ = blf.dimensions(fid, sub) if sub else (0, 0)
        box_w = max(tw, sw) + 72
        box_h = th + (sh_ + 22 if sub else 0) + 50
        x = (w - box_w) / 2
        y = 36
        gpu.state.blend_set("ALPHA")
        bg = batch_for_shader(SH, "TRI_FAN", {"pos": [(x, y), (x + box_w, y), (x + box_w, y + box_h),
                                                     (x, y + box_h)]})
        SH.bind()
        SH.uniform_float("color", (0.08, 0.08, 0.1, 0.78))
        bg.draw(SH)
        gpu.state.blend_set("NONE")
        blf.size(fid, 46)
        blf.color(fid, 1, 1, 1, 1)
        blf.position(fid, (w - tw) / 2, y + box_h - th - 22, 0)
        blf.draw(fid, S["caption"])
        if sub:
            blf.size(fid, 30)
            blf.color(fid, 1.0, 0.8, 0.55, 1)
            blf.position(fid, (w - sw) / 2, y + 22, 0)
            blf.draw(fid, sub)


# ---------------------------------------------------------------- 撮る
def shot():
    p = FR / f"{S['shot']:05d}.png"
    with bpy.context.temp_override(window=win()):
        bpy.ops.screen.screenshot(filepath=str(p))
    LOG.append({"i": S["shot"], "t": round(time.time() - S["t0"], 3), "beat": S["beat"],
                "caption": S["caption"]})
    S["shot"] += 1


# ---------------------------------------------------------------- 手順
def full_area():
    # 使う人の Blender の設定を変えない(終了時の自動保存を止める)
    bpy.context.preferences.use_preferences_save = False
    with bpy.context.temp_override(**ov()):
        try:
            bpy.ops.screen.screen_full_area(use_hide_panels=False)
        except Exception:                     # noqa: BLE001
            pass


def setup():
    sc = bpy.context.scene
    a = v3d()
    sp = a.spaces[0]
    sp.show_region_ui = False         # サイドバーはタブを選べない(読み取り専用)ので隠し、STEP0 はポップアップで見せる
    sp.show_region_toolbar = False
    sp.show_region_header = True
    for r in a.regions:
        if r.type == "UI":
            try:
                r.active_panel_category = "FreePencil"
            except Exception as e:            # noqa: BLE001
                print("@@@ panel category:", e, flush=True)
    sp.overlay.show_overlays = False
    sp.show_gizmo = False
    sp.shading.type = "RENDERED"
    sc.eevee.taa_samples = 8
    sc.fp_enable_compositor_view = True
    with bpy.context.temp_override(**ov()):
        bpy.ops.view3d.view_camera()
        bpy.ops.view3d.view_center_camera()
    a.spaces[0].region_3d.view_camera_zoom = a.spaces[0].region_3d.view_camera_zoom * 0.96
    for o in sc.objects:
        o.select_set(False)
    bpy.types.SpaceView3D.draw_handler_add(draw_cb, (), "WINDOW", "POST_PIXEL")


def cap(text, sub=""):
    S["caption"], S["sub"] = text, sub


def marquee(rect):
    S["rect"] = rect
    S["rect_p"] = 0.0
    S["rect_t0"] = time.time()


def show_panel():
    """STEP0 のパネルを出す(使う人がサイドバーの STEP0 を見るのと同じ)。"""
    w = win()
    w.event_simulate(type="MOUSEMOVE", value="NOTHING", x=int(w.width * 0.80), y=int(w.height * 0.70))
    with bpy.context.temp_override(**ov()):
        bpy.ops.wm.call_panel(name="FREEPENCIL_PT_STEP0", keep_open=True)


def close_popups():
    """出ているポップアップ(パネル・完了のメッセージ)を ESC で閉じ、マウスを外へ逃がす。"""
    w = win()
    try:
        w.event_simulate(type="ESC", value="PRESS")
        w.event_simulate(type="ESC", value="RELEASE")
        w.event_simulate(type="MOUSEMOVE", value="NOTHING", x=w.width - 5, y=w.height - 5)
    except Exception as e:                    # noqa: BLE001
        print("@@@ event_simulate:", e, flush=True)


def zoom2():
    """2倍レンダ中はビューポートの絵が半分の大きさで出るので、カメラの拡大を 2 倍にする。"""
    import math
    rv = v3d().spaces[0].region_3d
    z = rv.view_camera_zoom
    rv.view_camera_zoom = 50 * (math.sqrt(2) * (math.sqrt(2) + z / 50) - math.sqrt(2))


def step0():
    # ここで ESC を送らない(動き始めた STEP0 の進捗処理に届いて中断させた)
    sc = bpy.context.scene
    sc.fp_auto_style = "WEIGHTED"
    ms = [o for o in sc.objects if o.type == "MESH" and len(o.data.polygons) and not o.hide_render]
    for o in ms:
        o.select_set(True)
    bpy.context.view_layer.objects.active = ms[0]
    with bpy.context.temp_override(**ov()):
        bpy.ops.freepencil.auto_setup("INVOKE_DEFAULT")       # 進捗バー付きで回る
    t0 = time.time()
    S["busy"] = lambda: fp()._applied(bpy.context.scene) or time.time() - t0 > 120


def after_step0():
    close_popups()
    for o in bpy.context.scene.objects:
        o.select_set(False)
    a = v3d()
    a.spaces[0].shading.type = "RENDERED"
    sc = bpy.context.scene
    if getattr(sc, "fp_supersample", False):
        # 2倍レンダ中はビューポートの絵が半分の大きさで出る(既知の制限)。録画では切って等倍で見せる
        sc.fp_supersample = False
        with bpy.context.temp_override(**ov()):
            bpy.ops.freepencil2.link_button()
        close_popups()


MOUTH = (0.39, 0.47, 0.49, 0.58)
BUTTONS = (0.40, 0.62, 0.50, 0.84)
HAIR = (0.40, 0.14, 0.64, 0.58)

BEATS = [
    # (秒, 始めにすること, 字幕, 下の字幕)
    (0.6, full_area, None, None),
    (2.5, setup, "anime-girl（元の 3D）", "FreePencil2 v2.9 で、手作業で線画を仕上げる"),
    (2.0, show_panel, "STEP0（キャラ）を押す", "塗り分け → AOV → 線画のコンポジタ を全自動で"),
    (0.4, close_popups, None, None),
    (0.5, step0, None, None),
    (3.5, after_step0, "STEP0 だけ", "口が無い ／ ボタンが黒い棒 ／ 髪は輪郭だけ"),
    (1.4, lambda: marquee(MOUTH), "口：顔の絵（テクスチャ）の線を、口のまわりだけ使う",
     "目は形の線のまま（絵の瞳は細かすぎて黒く潰れる）"),
    (3.0, lambda: fp().texture_lines({"objects": ["Face"], "rect": MOUTH}, strength=0.7), None, None),
    (1.4, lambda: marquee(BUTTONS), "ボタン：服の絵の線を、ボタンのまわりだけ", "淡い陰は線にしない（強さ 0.3）"),
    (3.0, lambda: fp().texture_lines({"objects": ["Clothes"], "rect": BUTTONS}, strength=0.3), None, None),
    (1.4, lambda: marquee(HAIR), "髪：髪の絵の筋を、弱めに足す", "前髪の筋とポニーテール"),
    (3.5, lambda: fp().texture_lines({"objects": ["Hair"]}, strength=0.25), None, None),
    (0.3, lambda: S.update(rect=None), "仕上がり（線画）", ""),
    (3.0, lambda: fp().preview("WHITE"), None, None),
    (4.0, lambda: fp().cel(), "セル（影と色）", "STEP3 のプレビューで「セル」"),
    (1.0, None, None, None),
]


def tick():
    try:
        if S["rect"] is not None and S["rect_t0"] is not None:
            S["rect_p"] = (time.time() - S["rect_t0"]) / 0.8
        if S["busy"] is not None:
            if not S["busy"]():
                shot()
                return 0.25
            S["busy"] = None
            S["t_beat"] = time.time()
        if S["t_beat"] is None or time.time() - S["t_beat"] >= BEATS[S["beat"]][0]:
            if S["t_beat"] is not None:
                S["beat"] += 1
            if S["beat"] >= len(BEATS):
                (OUT / "frames.json").write_text(json.dumps(LOG, ensure_ascii=False), encoding="utf-8")
                print("@@@ done", S["shot"], flush=True)
                bpy.ops.wm.quit_blender()
                return None
            sec, fn, c, sub = BEATS[S["beat"]]
            if c is not None:
                cap(c, sub or "")
            if fn is not None:
                fn()
            S["t_beat"] = time.time()
            print("@@@ beat", S["beat"], c, flush=True)
        if S["beat"] >= 1:                 # 準備の前のコマは録らない
            shot()
        return 0.2
    except Exception:                           # noqa: BLE001
        import traceback
        print("@@@ EXCEPTION", traceback.format_exc(), flush=True)
        (OUT / "frames.json").write_text(json.dumps(LOG, ensure_ascii=False), encoding="utf-8")
        bpy.ops.wm.quit_blender()
        return None


bpy.app.timers.register(tick, first_interval=4.0)
