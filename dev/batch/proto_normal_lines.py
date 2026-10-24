"""試作: 法線の折れ目から線を取ったら、今の線に何が足されるかを見る(本体は触らない)。

  blender -b --factory-startup --python proto_normal_lines.py -- <fp 済みの .blend> <work_dir>
  python proto_normal_lines.py <work_dir> [--deg 35]

1 段目(Blender): 白の線画・法線パス(カメラの向きに直す)・アルファを work_dir に npy で書く。
2 段目(ふつうの Python): 隣の画素と法線が deg 以上折れている所を線とみなし、今の線から
3px より離れた所(= 新しく足される線)を赤で重ねた new_lines.png を書く。
"""
import math
import sys
import tempfile
from pathlib import Path

try:
    import bpy
except ImportError:
    bpy = None


def export(src: Path, work: Path):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import fp_batch
    fp_batch.install_addon()
    import numpy as np
    compat = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.compat"))
    bpy.ops.wm.open_mainfile(filepath=str(src))
    sc = bpy.context.scene
    vl = bpy.context.view_layer
    sc.fp_preview_mode = "WHITE"
    vl.use_pass_normal = True
    tmp = Path(tempfile.mkdtemp())
    tree = compat.get_compositor_tree(sc)
    rl = next(n for n in tree.nodes if n.type == "R_LAYERS")
    fo = tree.nodes.new("CompositorNodeOutputFile")
    fo.base_path = str(tmp) + "/"
    fo.format.file_format = "OPEN_EXR"
    fo.format.color_depth = "32"
    fo.file_slots.clear()
    for k in ("Normal", "Alpha"):
        fo.file_slots.new(k)
        tree.links.new(rl.outputs[k], fo.inputs[k])
    work.mkdir(parents=True, exist_ok=True)
    sc.render.filepath = str(work / "white.png")
    bpy.ops.render.render(write_still=True)

    def load(path, ch):
        im = bpy.data.images.load(str(path))
        w, h = im.size
        a = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)[::-1]
        bpy.data.images.remove(im)
        return a[..., :ch]

    nrm = load(next(tmp.glob("Normal*.exr")), 3)
    R = np.array(sc.camera.matrix_world.to_3x3())
    np.save(work / "normal.npy", nrm @ R)                # カメラの向きの法線
    np.save(work / "alpha.npy", load(next(tmp.glob("Alpha*.exr")), 1)[..., 0])
    print("@@@ exported", work)


def analyse(work: Path, deg: float):
    import numpy as np
    from PIL import Image
    from scipy import ndimage as nd
    nc = np.load(work / "normal.npy")
    alpha = np.load(work / "alpha.npy")
    ln = np.linalg.norm(nc, axis=2)
    alpha = alpha * (ln > 0.5)          # 背景が不透明でもアルファは 1。法線の無い所(背景)を外す
    nc /= np.maximum(ln[..., None], 1e-6)
    h, w = alpha.shape
    cos_t = math.cos(math.radians(deg))
    edge = np.zeros((h, w), bool)
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        b = np.roll(nc, (-dy, -dx), (0, 1))
        ab = np.roll(alpha, (-dy, -dx), (0, 1))
        edge |= ((nc * b).sum(2) < cos_t) & (alpha > 0.5) & (ab > 0.5)
    im = Image.open(work / "white.png").convert("RGBA")
    im = Image.alpha_composite(Image.new("RGBA", im.size, "white"), im).convert("L").resize((w, h))
    gray = np.asarray(im) / 255.0
    have = gray < 0.6
    new = edge & ~nd.binary_dilation(have, iterations=3)
    rgb = np.stack([gray] * 3, -1) * 0.75 + 0.25
    rgb[have] = [0.3, 0.3, 0.3]
    rgb[new] = [1, 0, 0]
    out = work / f"new_lines_{deg:g}.png"
    Image.fromarray((rgb * 255).astype(np.uint8)).save(out)
    print(out)


if bpy is not None:
    A = sys.argv[sys.argv.index("--") + 1:]
    export(Path(A[0]).resolve(), Path(A[1]).resolve())
elif __name__ == "__main__":
    A = sys.argv[1:]
    for d in (A[A.index("--deg") + 1].split(",") if "--deg" in A else ["35"]):
        analyse(Path(A[0]).resolve(), float(d))
