"""Multi-view texture projection: colour a mesh from front/left/back/right images.

Runs in the PyTorch venv (numpy + trimesh + PIL). Each image is aligned to the mesh by its silhouette
(object bbox in the photo <-> projected mesh bbox), every vertex takes colour from the views that can see
it (per-view z-buffer), weighted by how squarely it faces that camera; unseen vertices copy the nearest
coloured one. Result: per-vertex colours, which the Blender pipeline bakes into the low-poly texture.

Mesh convention: glTF Y-up, front faces +Z (verified for Hunyuan3D-2mv and TripoSR's orientation fix).
CLI: python projection.py in.glb out.glb front=a.png left=b.png back=c.png right=d.png
"""
import sys

import numpy as np
import trimesh
from PIL import Image

# view -> (direction from object to camera, image-right axis); image-up is always +Y
CAMS = {"front": ((0, 0, 1), (1, 0, 0)), "back": ((0, 0, -1), (-1, 0, 0)),
        "right": ((1, 0, 0), (0, 0, -1)), "left": ((-1, 0, 0), (0, 0, 1))}


def _linear(c):
    """sRGB 0..1 -> linear (glTF vertex colours are linear)."""
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def project(mesh, images, base=None, base_weight=0.25, sharp=3.0):
    """images: {view: RGBA PIL image with background alpha=0}. base: optional (n,3) linear colours to blend in."""
    V, N = mesh.vertices, mesh.vertex_normals
    acc, w = np.zeros((len(V), 3)), np.zeros(len(V))
    if base is not None:
        acc += base * base_weight
        w += base_weight
    up = np.array([0.0, 1.0, 0.0])
    for view, img in images.items():
        if view not in CAMS:
            continue
        d, r = (np.array(a, float) for a in CAMS[view])
        from PIL import ImageFilter
        img = img.convert("RGBA")
        a = np.asarray(img).astype(np.float32) / 255.0
        H, W = a.shape[:2]
        ys, xs = np.nonzero(a[..., 3] > 0.5)  # silhouette bbox from the full mask
        # sample only well inside the silhouette: edge pixels are blended with the background
        inner = np.asarray(img.getchannel("A").filter(ImageFilter.MinFilter(7))) > 128
        a[..., 3] = inner
        if len(xs) < 50:
            continue
        X, Y, D = V @ r, V @ up, V @ d
        s = (ys.max() - ys.min()) / max(np.ptp(Y), 1e-9)  # height sets the scale (silhouette alignment)
        u = (xs.min() + xs.max()) / 2 + (X - (X.min() + X.max()) / 2) * s
        v = ys.max() - (Y - Y.min()) * s
        ui, vi = np.clip(np.rint(u), 0, W - 1).astype(int), np.clip(np.rint(v), 0, H - 1).astype(int)
        g = 4  # z-buffer on a coarse grid so vertex splats leave no holes
        zb = np.full((H // g + 1, W // g + 1), -np.inf)
        np.maximum.at(zb, (vi // g, ui // g), D)
        visible = D >= zb[vi // g, ui // g] - 0.02 * np.ptp(D)
        facing = np.clip(N @ d, 0, 1) ** sharp
        wt = facing * visible * (a[vi, ui, 3] > 0.5)
        acc += _linear(a[vi, ui, :3]) * wt[:, None]
        w += wt
    seen = w > 1e-6
    col = np.where(seen[:, None], acc / np.maximum(w, 1e-9)[:, None], 0.0)
    if (~seen).any() and seen.any():  # top/bottom/crevices no view saw: nearest coloured vertex
        from scipy.spatial import cKDTree
        _, idx = cKDTree(V[seen]).query(V[~seen])
        col[~seen] = col[seen][idx]
    rgba = np.concatenate([np.clip(col, 0, 1) * 255, np.full((len(V), 1), 255)], 1).astype(np.uint8)
    mesh.visual = trimesh.visual.ColorVisuals(mesh, vertex_colors=rgba)
    return mesh, float(seen.mean())


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    views = dict(a.split("=", 1) for a in sys.argv[3:])
    m = trimesh.load(src, force="mesh")
    from cutout import cutout
    m, cov = project(m, {k: cutout(p) for k, p in views.items()})
    m.export(dst)
    print(f"projected {list(views)}; {cov:.0%} of vertices seen by a camera")
