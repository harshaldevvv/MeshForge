"""Runs inside MeshForge's private PyTorch venv (not the app's Python).
Usage: python torch_runner.py <model_id> <image> <out.glb> <meshforge_home>"""
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

mid, img_path, out, home = sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4])
VIEWS = dict(a.split("=", 1) for a in sys.argv[5:])  # extra views: front=... left=... back=... right=...
device = "cuda" if torch.cuda.is_available() else "cpu"
T0 = time.time()
log = lambda m: print(f"[{time.time() - T0:6.1f}s] {m}", file=sys.stderr, flush=True)


def cutout(img):
    """RGBA with background removed. Plain backgrounds (what our image prompts ask for) use a fast
    border flood-fill; busy ones fall back to rembg (slow on CPU)."""
    from PIL import ImageDraw
    img = Image.open(img).convert("RGBA")
    a = np.asarray(img)
    if a[..., 3].min() < 250:
        return img
    rgb = a[..., :3].astype(np.int16)
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    if border.std(axis=0).max() < 12:  # uniform background
        mask = Image.new("L", img.size, 255)
        work = img.convert("RGB")
        w, h = img.size
        for seed in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]:
            ImageDraw.floodfill(work, seed, (255, 0, 255), thresh=28)
        bg = np.all(np.asarray(work) == (255, 0, 255), axis=-1)
        # second pass: soft grey cast shadows touching the background (low saturation, not dark like metal)
        f = a[..., :3].astype(np.float32)
        sat = (f.max(-1) - f.min(-1)) / np.maximum(f.max(-1), 1)
        shadowish = (sat < 0.12) & (f.mean(-1) > 120)
        work2 = Image.fromarray(np.where((bg | ~shadowish)[..., None], np.where(bg[..., None], 255, 0), 128).astype(np.uint8)[..., 0])
        for y in range(0, h, 4):  # grow background into connected shadow pixels
            for x in (0, w - 1):
                if work2.getpixel((x, y)) == 255:
                    ImageDraw.floodfill(work2, (x, y), 254, thresh=130)
        for x in range(0, w, 4):
            for y in (0, h - 1):
                if work2.getpixel((x, y)) == 255:
                    ImageDraw.floodfill(work2, (x, y), 254, thresh=130)
        bg |= np.asarray(work2) == 254
        out = a.copy()
        out[bg, 3] = 0
        return Image.fromarray(out)
    import rembg
    return rembg.remove(img.convert("RGB"), session=rembg.new_session())


if mid == "triposr":
    sys.path.insert(0, str(home / "triposr"))
    import trimesh
    from tsr.system import TSR
    from tsr.utils import resize_foreground

    model = TSR.from_pretrained("stabilityai/TripoSR", config_name="config.yaml", weight_name="model.ckpt")
    log("model loaded")
    model.renderer.set_chunk_size(4096 if device == "cuda" else 2048)
    try:
        model.to(device)
        torch.zeros(1, device=device)
    except torch.cuda.OutOfMemoryError:
        device = "cpu"
        model.to(device)
    im = np.asarray(resize_foreground(cutout(img_path), 0.85)).astype(np.float32) / 255.0
    im = Image.fromarray(((im[:, :, :3] * im[:, :, 3:4] + (1 - im[:, :, 3:4]) * 0.5) * 255).astype(np.uint8))
    log("image prepared")
    with torch.no_grad():
        try:
            codes = model([im], device=device)
        except torch.cuda.OutOfMemoryError:  # 4 GB GPUs: fall back to CPU
            torch.cuda.empty_cache()
            device = "cpu"
            model.to(device)
            codes = model([im], device=device)
    log(f"scene codes on {device}")
    res = 256 if device == "cuda" else 192
    try:  # proper UV texture (needs OpenGL via moderngl)
        from tsr.bake_texture import bake_texture
        mesh = model.extract_mesh(codes, False, resolution=res)[0]
        parts = mesh.split(only_watertight=False)  # drop floaters (before UV seams exist)
        if len(parts) > 1:
            big = max(len(q.faces) for q in parts)
            mesh = trimesh.util.concatenate([q for q in parts if len(q.faces) >= 0.02 * big])
        log(f"mesh extracted ({len(parts)} pieces -> kept main)")
        # cast shadows in the input image become a thin flat skirt at the base (TripoSR's native up is +z):
        # drop bottom-layer faces that lie outside the footprint of the object just above them
        v, f = mesh.vertices, mesh.faces
        z0, h = v[:, 2].min(), np.ptp(v[:, 2])
        band = v[(v[:, 2] > z0 + 0.14 * h) & (v[:, 2] < z0 + 0.35 * h)]
        if len(band):
            lo_xy, hi_xy = band[:, :2].min(0), band[:, :2].max(0)
            ext = (hi_xy - lo_xy).max()
            fz = v[f][:, :, 2].max(1)
            fxy = v[f][:, :, :2].mean(1)
            # footprint = 2D occupancy grid of the body just above the base, padded by 2 cells
            g = 64
            vmin, span = v[:, :2].min(0), np.ptp(v[:, :2], axis=0).max() + 1e-6
            cell = lambda p: np.clip(((p - vmin) / span * (g - 1)).astype(int), 0, g - 1)
            occ = np.zeros((g, g), bool)
            occ[tuple(cell(band[:, :2]).T)] = True
            for _ in range(2):
                occ = occ | np.roll(occ, 1, 0) | np.roll(occ, -1, 0) | np.roll(occ, 1, 1) | np.roll(occ, -1, 1)
            outside = ~occ[tuple(cell(fxy).T)]
            skirt = (fz < z0 + 0.12 * h) & outside
            # a cast shadow spills to one side; a real flared base (lamp, candlestick) spreads evenly
            lopsided = skirt.any() and np.linalg.norm(fxy[skirt].mean(0) - (lo_xy + hi_xy) / 2) > 0.3 * ext
            if skirt.sum() > 0.002 * len(f) and lopsided:
                mesh.update_faces(~skirt)
                mesh.remove_unreferenced_vertices()
                parts = mesh.split(only_watertight=False)  # leftover shards of the cut sheet
                big = max(len(q.faces) for q in parts)
                mesh = trimesh.util.concatenate([q for q in parts if len(q.faces) >= 0.02 * big])
                log(f"removed shadow skirt ({int(skirt.sum())} faces)")
        b = bake_texture(mesh, model, codes[0], 1024)  # Blender re-bakes at the chosen size
        tex = Image.fromarray((b["colors"] * 255).astype(np.uint8)).transpose(Image.FLIP_TOP_BOTTOM)
        tm = trimesh.Trimesh(mesh.vertices[b["vmapping"]], b["indices"], process=False,
                             visual=trimesh.visual.TextureVisuals(uv=b["uvs"], material=trimesh.visual.material.PBRMaterial(
                                 baseColorTexture=tex, metallicFactor=0.0, roughnessFactor=0.7)))  # glTF default metallic is 1.0
    except Exception as e:  # fall back to vertex colours
        print(f"texture bake unavailable ({e}); using vertex colours", file=sys.stderr)
        tm = model.extract_mesh(codes, True, resolution=res)[0]
    log("mesh + texture done")
    from tsr.utils import to_gradio_3d_orientation  # TripoSR's own fix: its native axes are not glTF Y-up
    to_gradio_3d_orientation(tm).export(out)

elif mid == "hunyuan3d-2mv":
    from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline

    imgs = {v: cutout(VIEWS[v]) for v in ("front", "left", "back", "right") if v in VIEWS} or {"front": cutout(img_path)}
    log(f"views: {list(imgs)}")
    # 4.7 GB fp16; on 4 GB GPUs the NVIDIA driver spills into system RAM (slower, but works: peak ~5 GB, verified)
    pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
        "tencent/Hunyuan3D-2mv", subfolder="hunyuan3d-dit-v2-mv-turbo", variant="fp16", use_safetensors=True, device=device)
    if hasattr(pipe, "enable_flashvdm"):
        pipe.enable_flashvdm()
    log("model loaded")
    mesh = pipe(image=imgs, num_inference_steps=5, octree_resolution=320, num_chunks=4000,
                generator=torch.manual_seed(1234), output_type="trimesh")[0]
    log(f"generated {len(mesh.faces)} faces")
    mesh.export(out)

elif mid == "hunyuan3d-2mini":
    from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline

    pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
        "tencent/Hunyuan3D-2mini", subfolder="hunyuan3d-dit-v2-mini-turbo", use_safetensors=True, device=device)
    if hasattr(pipe, "enable_flashvdm"):
        pipe.enable_flashvdm()
    mesh = pipe(image=cutout(img_path), num_inference_steps=5, octree_resolution=320, num_chunks=8000,
                generator=torch.manual_seed(0), output_type="trimesh")[0]
    mesh.export(out)
else:
    sys.exit(f"unknown local 3D model {mid}")
print("TORCH_OK", device)
