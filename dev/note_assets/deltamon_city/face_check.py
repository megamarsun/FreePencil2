"""顔の寄りを撮る(顔の向き・表情・目線の確かめ)。体の進む向きの前、頭の高さから顔を撮る。

  blender -b <previz.blend> --python face_check.py -- <出力フォルダ> <コマ,コマ,...> [--side 0]

--side は 体の前から横へ回す角度(度)。頭の骨の前後の傾き(下向きが +)も出す。
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

A = sys.argv[sys.argv.index("--") + 1:]
OUT = Path(A[0])
FR = [int(x) for x in A[1].split(",")]
arg = lambda n, d: A[A.index(n) + 1] if n in A else d   # noqa: E731
SIDE = math.radians(float(arg("--side", "0")))
OUT.mkdir(parents=True, exist_ok=True)
sc = bpy.context.scene
arm = bpy.data.objects["Armature"]
r = sc.render
r.resolution_x, r.resolution_y = 640, 640
r.image_settings.file_format = "PNG"
r.use_stamp = True
for k in ("date", "time", "render_time", "filename", "scene", "memory", "hostname", "lens", "frame_range", "camera",
          "marker", "sequencer_strip", "note"):
    setattr(r, "use_stamp_" + k, False)
r.use_stamp_frame = True
cam = bpy.data.objects.new("face_cam", bpy.data.cameras.new("face_cam"))
sc.collection.objects.link(cam)
cam.data.lens = 85
for m in sc.timeline_markers:
    m.camera = cam
sc.camera = cam
for f in FR:
    sc.frame_set(f)
    mw = arm.matrix_world
    P = arm.pose.bones
    head = mw @ P["head.x"].head
    top = mw @ P["head.x"].tail
    hips = mw @ P["root.x"].head
    # 体の前: 左右の股関節を結ぶ線と上向きの外積
    lr = (mw @ P["thigh_stretch.l"].head) - (mw @ P["thigh_stretch.r"].head)
    fwd = lr.cross(Vector((0, 0, 1)))
    fwd.z = 0
    fwd.normalize()
    # 顔の前向き: 休みの姿勢で -Y を向いている(VRM)。それを頭の骨と一緒に回す
    b = P["head.x"]
    face = (mw.to_3x3() @ b.matrix.to_3x3() @ b.bone.matrix_local.to_3x3().inverted() @ Vector((0, -1, 0))).normalized()
    pitch = math.degrees(math.asin(max(-1, min(1, -face.z))))
    yaw = math.degrees(math.atan2(fwd.cross(face).z, fwd.dot(face)))
    c = head + (top - head) * 0.5
    d = fwd.copy()
    d.rotate(__import__("mathutils").Euler((0, 0, SIDE)))
    cam.location = c + d * 1.1 + Vector((0, 0, 0.02))
    cam.rotation_euler = (c - cam.location).to_track_quat('-Z', 'Y').to_euler()
    r.filepath = str(OUT / f"face_{f:04d}.png")
    bpy.ops.render.render(write_still=True)
    print("@@ face", f, "pitch(down+)", round(pitch, 1), "yaw", round(yaw, 1), "face.fwd", round(face.dot(fwd), 2), flush=True)
