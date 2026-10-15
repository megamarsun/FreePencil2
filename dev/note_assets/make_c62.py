"""C62 x 鉄橋 x 下町: 宣伝デモの場面(線画で魅せる、最後に 3D -> 線画のワイプ)。

  blender -b --factory-startup --python make_c62.py -- --wire [--res 1600] [--cam x,y,z,pitch,yaw] [--name wire]
      構図の確認(Workbench、STEP0 なし)
  blender -b --factory-startup --python make_c62.py -- --pre [--out out/c62]
      STEP0 前の .blend(c62_pre.blend)を保存

配置(ワールド):
  - 川は x 方向に流れる。水面 z=-4、川幅 60m(y=-30..30)。両岸は護岸(コンクリートの壁)と川沿いの道
  - 線路は y 方向。x=0 で川をまたぐ 3 連の下路トラス(1 連 30m)。レール面 z=4.6。陸は土手
  - C62 は鉄橋の上(機関車はメカとして塗る)。町は両岸に川を向いて並び、奥に高層
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = Path(__file__).resolve().parent
OUT = Path(arg("--out", str(HERE / "out" / "c62"))).resolve()
RES = int(arg("--res", "1600"))
SEED = int(arg("--seed", "7"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "batch"))

import bpy                      # noqa: E402
from mathutils import Matrix, Vector   # noqa: E402

import fp_batch                 # noqa: E402
import town_kit as kit          # noqa: E402
import town_kit_more as more    # noqa: E402
from town_kit import MB         # noqa: E402

WATER = -4.0
BANK = 30.0                 # 護岸の位置(|y|)
RAIL = 4.6                  # レール面の高さ
SPAN = 30.0                 # トラス 1 連の長さ
NSPAN = 3
TRUSS_X = 2.9               # 主構の位置(|x|)
TRUSS_H = 7.0
C62_BLEND = Path.home() / "blenderkit_data/models/jnr-c62-1-steam-_9ea0806c-28b1-4445-8e48-1df75c70ff41/jnr-c62-1-steam-locomotive_2K_a71b6d19-529f-4eca-91c4-aa16899e311c.blend"
TRAIN_Y = float(arg("--train-y", "0"))


def say(m):
    print(f"@@@ {m}", flush=True)


# ---------------------------------------------------------------- 鉄橋

def truss_bridge():
    mb = MB("bridge")
    L = SPAN * NSPAN
    y0 = -L / 2
    deck = RAIL - 0.9                                 # 縦桁の上
    for s in range(NSPAN):
        ya, yb = y0 + s * SPAN, y0 + (s + 1) * SPAN
        n = 6                                         # 格間
        p = (yb - ya) / n
        for sx in (-1, 1):
            x = sx * TRUSS_X
            zb, zt = deck - 0.6, deck - 0.6 + TRUSS_H
            mb.box_ab((x, ya, zb), (x, yb, zb), 0.55, 0.8)                     # 下弦
            mb.box_ab((x, ya + p, zt), (x, yb - p, zt), 0.55, 0.7)             # 上弦
            mb.box_ab((x, ya, zb), (x, ya + p, zt), 0.5, 0.6)                  # 端斜材
            mb.box_ab((x, yb, zb), (x, yb - p, zt), 0.5, 0.6)
            for i in range(1, n):                                              # 垂直材
                yy = ya + i * p
                mb.box_ab((x, yy, zb), (x, yy, zt), 0.35, 0.4)
            for i in range(1, n - 1):                                          # 斜材(ワーレン)
                a, b = ya + i * p, ya + (i + 1) * p
                if i < n / 2:
                    mb.box_ab((x, a, zt), (x, b, zb), 0.3, 0.35)
                else:
                    mb.box_ab((x, a, zb), (x, b, zt), 0.3, 0.35)
            for i in range(n + 1):                                             # 格点の添え板
                yy = ya + i * p
                mb.box(x - sx * 0.3, yy, zb, 0.06, 1.4, 1.2)
        for i in range(1, n):                                                  # 上横構(横つなぎと X)
            yy = ya + i * p
            zt = deck - 0.6 + TRUSS_H
            mb.box_ab((-TRUSS_X, yy, zt), (TRUSS_X, yy, zt), 0.3, 0.45)
            if i < n - 1:
                mb.box_ab((-TRUSS_X, yy, zt), (TRUSS_X, yy + p, zt), 0.15, 0.15)
                mb.box_ab((TRUSS_X, yy, zt), (-TRUSS_X, yy + p, zt), 0.15, 0.15)
        for yy in (ya + p, yb - p):                                            # 橋門構
            zt = deck - 0.6 + TRUSS_H
            mb.box_ab((-TRUSS_X, yy, zt - 1.4), (TRUSS_X, yy, zt - 1.4), 0.3, 0.9)
            for sx in (-1, 1):
                mb.box_ab((sx * TRUSS_X, yy, zt - 2.6), (sx * TRUSS_X * 0.4, yy, zt - 1.4), 0.2, 0.2)
        for i in range(n + 1):                                                 # 横桁
            yy = ya + i * p
            mb.box_ab((-TRUSS_X, yy, deck - 0.6), (TRUSS_X, yy, deck - 0.6), 0.4, 0.8)
        for sx in (-1, 1):                                                     # 縦桁
            mb.box_ab((sx * 0.75, ya, deck - 0.3), (sx * 0.75, yb, deck - 0.3), 0.3, 0.6)
    # 枕木・レール・歩み板・手すり(橋の上は全長通し)
    yy = y0 - 2
    while yy < -y0 + 2:
        mb.box(0, yy, deck + 0.1, 2.4, 0.2, 0.2)
        yy += 0.62
    for sx in (-1, 1):
        mb.box(sx * 0.534, 0, RAIL - 0.1, 0.07, L + 4, 0.16)                  # レール(狭軌)
        mb.box(sx * 1.9, 0, deck + 0.02, 0.9, L + 4, 0.06)                    # 歩み板
    # 橋脚(水面から)と橋台
    for s in range(1, NSPAN):
        yy = y0 + s * SPAN
        mb.box(0, yy, (WATER - 2 + deck - 0.8) / 2, 8.5, 3.0, deck - 0.8 - WATER + 2)
        mb.box(0, yy, deck - 0.6, 9.5, 3.6, 0.6)                              # 沓座
        for sx in (-1, 1):                                                     # 水切り(先端)
            mb.prism(sx * 4.25, sx * 5.8, yy - 1.5, yy + 1.5, WATER - 2, deck - 1.4) if False else \
                mb.box(sx * 4.9, yy, (WATER - 2 + deck - 1.4) / 2, 1.3, 2.1, deck - 1.4 - WATER + 2)
    for sy in (-1, 1):
        yy = sy * (L / 2 + 2.0)
        mb.box(0, yy, (WATER - 2 + deck) / 2, 10.0, 4.0, deck - WATER + 2)
    return mb.build()


def embankment():
    """陸の土手(線路の盛土)と、その上の枕木・レール・バラスト。"""
    mb = MB("embankment")
    L = SPAN * NSPAN
    for sy in (-1, 1):
        ya, yb = sy * (L / 2 + 4.0), sy * 260.0
        lo, hi = min(ya, yb), max(ya, yb)
        mb.box(0, (lo + hi) / 2, RAIL / 2 - 0.6, 6.0, hi - lo, RAIL - 1.2)          # 天端
        for sx in (-1, 1):                                                       # のり面(段)
            for k in range(4):
                w = 1.5
                mb.box(sx * (3.0 + w * (k + 0.5)), (lo + hi) / 2, (RAIL - 1.2) * (1 - (k + 1) / 5) / 2,
                       w, hi - lo, (RAIL - 1.2) * (1 - (k + 1) / 5))
        mb.box(0, (lo + hi) / 2, RAIL - 0.75, 3.4, hi - lo, 0.3)                 # バラスト
        yy = lo
        while yy < hi:
            mb.box(0, yy, RAIL - 0.5, 2.2, 0.2, 0.18)
            yy += 0.62
        for sx in (-1, 1):
            mb.box(sx * 0.534, (lo + hi) / 2, RAIL - 0.1, 0.07, hi - lo, 0.16)
        y = lo + 10                                                               # 架線柱の代わりの信号柱・距離標
        while y < hi:
            mb.box(3.4, y, RAIL + 1.5, 0.15, 0.15, 3.0)
            mb.box(3.4, y, RAIL + 3.1, 0.6, 0.12, 0.4)
            y += 40.0
    return mb.build()


# ---------------------------------------------------------------- 川と護岸

def river():
    mb = MB("banks")
    for sy in (-1, 1):
        y = sy * BANK
        for x0, x1 in ((-260.0, -6.5), (6.5, 260.0)):
            xm, L = (x0 + x1) / 2, x1 - x0
            mb.box(xm, y + sy * 0.6, (WATER - 1) / 2, L, 1.2, -WATER + 1)        # 護岸の壁
            mb.box(xm, y + sy * 0.1, 0.15, L, 0.4, 0.3)                          # 天端
            mb.box(xm, y - sy * 0.8, WATER + 0.6, L, 1.6, 1.2)                    # 根固め
            k = int(L / 12)
            for i in range(k + 1):                                               # 目地
                mb.box(x0 + i * L / k, y - sy * 0.02, (WATER) / 2, 0.08, 0.06, -WATER)
            # 川沿いの柵(手すり)
            mb.box(xm, y + sy * 0.8, 1.1, L, 0.06, 0.06)
            mb.box(xm, y + sy * 0.8, 0.6, L, 0.04, 0.04)
            for i in range(int(L / 2.5) + 1):
                mb.box(x0 + i * L / int(L / 2.5), y + sy * 0.8, 0.55, 0.06, 0.06, 1.1)
        # 川へ降りる階段(数か所)
        for xc in (-120.0, -55.0, 48.0, 110.0):
            for i in range(10):
                mb.box(xc, y - sy * (0.3 + i * 0.35), -i * 0.4, 3.0, 0.35, 0.4)
    # 川沿いの道(両岸)
    for sy in (-1, 1):
        mb.box(0, sy * (BANK + 5.0), 0.02, 520, 8.0, 0.04)
        mb.box(0, sy * (BANK + 9.2), 0.08, 520, 0.4, 0.16)                       # 縁石
    return mb.build()


def water_and_ground():
    bpy.ops.mesh.primitive_plane_add(size=1)
    w = bpy.context.object
    w.scale = (700, 2 * BANK + 2, 1)
    w.location = (0, 0, WATER)
    w.name = "FP_water"
    bpy.ops.mesh.primitive_plane_add(size=1)
    g = bpy.context.object
    g.scale = (2000, 2000, 1)
    g.location = (0, 0, -0.02)
    g.name = "FP_ground"
    # 川の部分の地面を抜く: 地面を両岸の 2 枚に分ける
    g.scale = (2000, 1000, 1)
    g.location = (0, BANK + 500, -0.02)
    g2 = g.copy()
    g2.data = g.data.copy()
    bpy.context.scene.collection.objects.link(g2)
    g2.location = (0, -(BANK + 500), -0.02)
    return [w, g, g2]


def poles_and_wires():
    """川沿いの道の電柱と電線(電柱 25m おき、腕木は道に直角、電線は 2 段 x 3 本)。"""
    mb = MB("poles")
    for sy in (-1, 1):
        y = sy * (BANK + 9.6)
        xs = [x for x in range(-250, 251, 25) if abs(x) > 12]
        for x in xs:
            mb.cyl(x, y, 5.5, 0.16, 11.0, 10, r2=0.11)
            for zz in (10.2, 9.4):
                mb.box(x, y, zz, 0.12, 2.4, 0.12)                              # 腕木
                for dy in (-1.0, 0.0, 1.0):
                    mb.cyl(x, y + dy, zz + 0.12, 0.05, 0.14, 8)                 # 碍子
            mb.box(x + 0.4, y - sy * 0.4, 7.6, 0.6, 0.6, 0.9)                   # 変圧器
        for a, b in zip(xs, xs[1:]):
            if b - a > 30:
                continue
            for zz in (10.35, 9.55):
                for dy in (-1.0, 0.0, 1.0):
                    n = 6
                    pts = [(a + (b - a) * i / n, zz - 0.45 * math.sin(math.pi * i / n)) for i in range(n + 1)]
                    for (x0, z0), (x1, z1) in zip(pts, pts[1:]):
                        mb.cyl_ab((x0, y + dy, z0), (x1, y + dy, z1), 0.02, 4)
    return mb.build()


# ---------------------------------------------------------------- 町

def town(rng):
    made = []
    idx = 0
    for sy in (-1, 1):
        face = "-y" if sy > 0 else "+y"
        x = -250.0
        while x < 250.0:
            if abs(x) < 16:                              # 線路の土手をよける
                x = 16.0
                continue
            w = rng.uniform(8, 16)
            d = rng.uniform(9, 14)
            y = sy * (BANK + 11.0 + d / 2)
            kind = rng.random()
            if kind < 0.45:
                made.append(kit.shophouse(x + w / 2, y, w, d, rng.randint(2, 3), face, rng, idx))
            elif kind < 0.8:
                made.append(kit.apartment(x + w / 2, y, w, d, rng.randint(3, 5), face, rng, idx))
            else:
                made.append(kit.house(x + w / 2, y, w, d, face, rng, idx))
            idx += 1
            x += w + rng.uniform(0.6, 2.5)
        # 2 列目: 高めの集合住宅とビル(屋根の連なりが重なって見える)
        x = -250.0
        while x < 250.0:
            if abs(x) < 16:
                x = 16.0
                continue
            w = rng.uniform(12, 22)
            d = rng.uniform(12, 18)
            y = sy * (BANK + 11.0 + 16.0 + rng.uniform(2, 10) + d / 2)
            made.append(more.tower(x + w / 2, y, w, d, rng.randint(6, 14), face, rng, idx))
            idx += 1
            x += w + rng.uniform(3, 9)
        # 3 列目(遠景の高層)
        x = -300.0
        while x < 300.0:
            w = rng.uniform(16, 28)
            d = rng.uniform(16, 24)
            y = sy * (BANK + 70.0 + rng.uniform(0, 40) + d / 2)
            made.append(more.tower(x + w / 2, y, w, d, rng.randint(14, 30), face, rng, idx))
            idx += 1
            x += w + rng.uniform(8, 20)
    return [o for o in made if o is not None]


# ---------------------------------------------------------------- 機関車

def load_c62():
    meshes, others = fp_batch.append_objects(C62_BLEND)
    o = meshes[0]
    for x in others:
        bpy.data.objects.remove(x, do_unlink=True)
    o.parent = None
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    # 長手が y。レールの上(車輪の下 = 最下点)をレール面に置く
    o.location += Vector((-(lo.x + hi.x) / 2, TRAIN_Y - (lo.y + hi.y) / 2, RAIL - lo.z))
    o.name = "C62"
    o["fp_mecha"] = True
    say(f"C62 {len(o.data.polygons):,} 面 寸法 {tuple(round(v, 2) for v in (hi - lo))}")
    return o


# ---------------------------------------------------------------- 撮影の準備

def stage():
    sc = bpy.context.scene
    cd = bpy.data.cameras.new("C")
    cd.lens = float(arg("--lens", "24"))
    cd.clip_start = 0.1
    cd.clip_end = 3000
    cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    x, y, z, pitch, yaw = (float(v) for v in arg("--cam", "-18,-34,1.0,88,-55").split(","))
    cam.location = (x, y, z)
    cam.rotation_euler = (math.radians(pitch), 0.0, math.radians(yaw))
    w = bpy.data.worlds.new("W")
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.78, 0.8, 0.84, 1)
        bg.inputs[1].default_value = 0.8
    sc.world = w
    lt = bpy.data.lights.new("K", type="SUN")
    lt.energy = 3.0
    lt.angle = math.radians(2.0)
    lo = bpy.data.objects.new("K", lt)
    sc.collection.objects.link(lo)
    lo.rotation_euler = (math.radians(50), 0, math.radians(-35))


# 色(画面に出る色、sRGB)。建物は棟ごとに薄い色の組から選ぶ。セル(影と色)で材質の色として出る
PALETTE = [(0.95, 0.88, 0.70), (0.72, 0.82, 0.90), (0.90, 0.68, 0.58), (0.74, 0.86, 0.72),
           (0.93, 0.92, 0.86), (0.84, 0.76, 0.90), (0.98, 0.80, 0.58), (0.68, 0.74, 0.80),
           (0.92, 0.80, 0.80), (0.80, 0.88, 0.84)]
NAMED = {"bridge": (0.86, 0.26, 0.18), "FP_water": (0.55, 0.75, 0.88),
         "banks": (0.80, 0.79, 0.76), "embankment": (0.80, 0.79, 0.76), "poles": (0.55, 0.55, 0.55)}


def _lin(c):
    return tuple(((v + 0.055) / 1.055) ** 2.4 if v > 0.04045 else v / 12.92 for v in c)


def grey(objs, color=(0.8, 0.8, 0.8)):
    """共有の材質 1 つ。色はオブジェクトの色(Object Info)から取る(棟ごとに変えられる)。"""
    m = bpy.data.materials.new("c62_grey")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes.get("Principled BSDF")
    if b:
        b.inputs["Roughness"].default_value = 0.9
        info = nt.nodes.new("ShaderNodeObjectInfo")
        nt.links.new(info.outputs["Color"], b.inputs["Base Color"])
    rng = random.Random(5)
    for o in objs:
        if o.type == "MESH":
            o.data.materials.clear()
            o.data.materials.append(m)
            if o.name in NAMED:
                c = NAMED[o.name]
            elif o.name.startswith("FP_ground"):
                c = (0.86, 0.85, 0.82)
            else:
                c = rng.choice(PALETTE)
            o.color = (*_lin(c), 1.0)


def build():
    bpy.ops.wm.read_homefile(use_empty=True)
    rng = random.Random(SEED)
    parts = [truss_bridge(), embankment(), river(), poles_and_wires()]
    blds = town(rng)
    flat = water_and_ground()
    grey(parts + blds + flat)
    loco = load_c62()                    # 機関車は元の材質のまま(3D のワイプで色が出る)
    stage()
    faces = sum(len(o.data.polygons) for o in bpy.data.objects if o.type == "MESH")
    say(f"建物 {len(blds)} 棟 / 面 {faces:,}")
    return bpy.context.scene, parts + blds + flat + [loco], loco


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sc, objs, loco = build()
    sc.render.resolution_x = RES
    sc.render.resolution_y = RES * 9 // 16
    sc.render.image_settings.file_format = "PNG"
    if "--wire" in ARGV:
        sc.render.engine = "BLENDER_WORKBENCH"
        sh = sc.display.shading
        sh.light = "STUDIO"
        sh.color_type = "SINGLE"
        sh.single_color = (0.85, 0.85, 0.85)
        sh.show_cavity = True
        sh.cavity_type = "BOTH"
        sh.show_object_outline = True
        sc.render.film_transparent = False
        sc.render.filepath = str(OUT / f"{arg('--name', 'wire')}.png")
        bpy.ops.render.render(write_still=True)
        say("wire done")
        return
    fp_batch.install_addon()
    for p_ in ("fp_use_random_seed", "fp_enable_compositor_view", "fp_auto_detect_aov"):
        setattr(sc, p_, False)
    sc.fp_color_seed = 42
    sc.render.engine = fp_batch.eevee_engine()
    sc.eevee.taa_render_samples = int(arg("--samples", "16"))
    loco.fp_paint_as = "MECHA"
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = loco
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "c62_pre.blend"))
    say("saved pre")


main()
