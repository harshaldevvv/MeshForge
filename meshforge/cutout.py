"""Background removal shared by torch_runner.py and projection.py (PyTorch venv)."""
import numpy as np
from PIL import Image


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
