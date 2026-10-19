"""Hunyuan3D-2.1 (shape + PBR texture) as an on-demand GPU function on Modal.

Deploy (MeshForge does this for you from the app, using the Modal token you saved in MeshForge):
    modal deploy cloud/modal_hunyuan21.py
Then MeshForge calls Hunyuan21().generate(png_bytes, ...) and gets a textured GLB back.

- GPU: L40S 48 GB (shape ~10 GB + paint ~21 GB stay loaded together).
- Billing: per second while a container runs; it shuts down after SCALEDOWN seconds idle.
- Weights live in a Modal Volume, so they download once, not on every cold start.
- Everything used here is ungated (tencent/Hunyuan3D-2.1, facebook/dinov2-giant, Real-ESRGAN).
  Licence: Tencent Hunyuan 3D 2.1 Community License (NOT for use in the EU, UK or South Korea).
"""
import modal

APP_NAME = "meshforge-hunyuan21"
GPU = "L40S"
SCALEDOWN = 60  # seconds idle before the GPU turns itself off
REPO = "/opt/Hunyuan3D-2.1"

image = (
    modal.Image.from_registry("nvidia/cuda:12.4.1-devel-ubuntu22.04", add_python="3.10")
    .apt_install("git", "wget", "build-essential", "ninja-build", "libgl1", "libglib2.0-0", "libsm6", "libxrender1",
                 "libxext6", "libxi6", "libxkbcommon0", "libxfixes3", "libxxf86vm1")
    .pip_install("torch==2.5.1", "torchvision==0.20.1", "torchaudio==2.5.1",
                 index_url="https://download.pytorch.org/whl/cu124")
    .run_commands(f"git clone --depth 1 https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1.git {REPO}")
    # skip the demo web stack, and bpy==4.0 (no longer on PyPI; only used for an optional OBJ->GLB step that
    # Tencent also provides without Blender in hy3dpaint/convert_utils.py)
    .run_commands(f"cd {REPO} && grep -v -E '^(gradio|fastapi|uvicorn|pythreejs|bpy|--extra-index-url)' requirements.txt > req.txt && "
                  "pip install -r req.txt")
    .run_commands(f"sed -i 's/^import bpy$/try:\\n    import bpy\\nexcept ImportError:\\n    bpy = None/' "
                  f"{REPO}/hy3dpaint/DifferentiableRenderer/mesh_utils.py")
    .env({"TORCH_CUDA_ARCH_LIST": "8.0;8.6;8.9;9.0", "HF_HOME": "/cache/hf",
          "CC": "gcc", "CXX": "g++"})  # Modal's Python is clang-built; the image has gcc
    .pip_install("wheel", "setuptools")  # needed by the --no-build-isolation builds below
    .run_commands(f"cd {REPO}/hy3dpaint/custom_rasterizer && pip install --no-build-isolation -e .", gpu=GPU)
    .run_commands(f"cd {REPO}/hy3dpaint/DifferentiableRenderer && bash compile_mesh_painter.sh")
    .run_commands(f"mkdir -p {REPO}/hy3dpaint/ckpt && wget -q -O {REPO}/hy3dpaint/ckpt/RealESRGAN_x4plus.pth "
                  "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth")
)

app = modal.App(APP_NAME, image=image)
cache = modal.Volume.from_name("meshforge-hf-cache", create_if_missing=True)


@app.cls(gpu=GPU, volumes={"/cache": cache}, timeout=1800, scaledown_window=SCALEDOWN, max_containers=1)
class Hunyuan21:
    @modal.enter()
    def load(self):
        import os
        import sys
        import time
        t = time.time()
        os.chdir(REPO)  # the paint config uses repo-relative paths
        sys.path[:0] = [REPO, f"{REPO}/hy3dshape", f"{REPO}/hy3dpaint"]
        from torchvision_fix import apply_fix  # basicsr/realesrgan expect an older torchvision API
        apply_fix()
        from hy3dshape.pipelines import Hunyuan3DDiTFlowMatchingPipeline
        from textureGenPipeline import Hunyuan3DPaintConfig, Hunyuan3DPaintPipeline
        self.shape = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained("tencent/Hunyuan3D-2.1")
        cfg = Hunyuan3DPaintConfig(max_num_view=6, resolution=512)
        cfg.realesrgan_ckpt_path = f"{REPO}/hy3dpaint/ckpt/RealESRGAN_x4plus.pth"
        cfg.multiview_cfg_path = f"{REPO}/hy3dpaint/cfgs/hunyuan-paint-pbr.yaml"
        self.paint = Hunyuan3DPaintPipeline(cfg)
        cache.commit()  # keep downloaded weights for the next cold start
        self.load_seconds = round(time.time() - t)
        print(f"loaded in {self.load_seconds}s")

    @modal.method()
    def generate(self, png: bytes, seed: int = 1234, texture: bool = True, steps: int = 30,
                 octree_resolution: int = 380) -> dict:
        """png: object image (ideally background already removed). Returns {"glb": bytes, "timings": {...}}."""
        import io
        import tempfile
        import time

        import torch
        from PIL import Image

        t0 = time.time()
        img = Image.open(io.BytesIO(png)).convert("RGBA")
        if img.getchannel("A").getextrema()[0] > 250:  # no transparency: let Hunyuan remove the background
            from hy3dshape.rembg import BackgroundRemover
            img = BackgroundRemover()(img.convert("RGB"))
        work = tempfile.mkdtemp()
        img.save(f"{work}/input.png")
        mesh = self.shape(image=img, num_inference_steps=steps, octree_resolution=octree_resolution,
                          generator=torch.manual_seed(seed))[0]
        mesh.export(f"{work}/shape.obj")
        t1 = time.time()
        out = f"{work}/shape.glb"
        if texture:
            from convert_utils import create_glb_with_pbr_materials  # Blender-free, keeps PBR maps
            obj = self.paint(mesh_path=f"{work}/shape.obj", image_path=f"{work}/input.png",
                             output_mesh_path=f"{work}/textured.obj", save_glb=False)
            create_glb_with_pbr_materials(obj, {"albedo": obj.replace(".obj", ".jpg"),
                                                "metallic": obj.replace(".obj", "_metallic.jpg"),
                                                "roughness": obj.replace(".obj", "_roughness.jpg")}, out)
        else:
            mesh.export(out)
        t2 = time.time()
        return {"glb": open(out, "rb").read(),
                "timings": {"shape_s": round(t1 - t0, 1), "paint_s": round(t2 - t1, 1),
                            "load_s": getattr(self, "load_seconds", 0)}}


@app.local_entrypoint()
def main(image: str, out: str = "hunyuan21.glb"):
    """Quick test: modal run cloud/modal_hunyuan21.py --image path.png"""
    r = Hunyuan21().generate.remote(open(image, "rb").read())
    open(out, "wb").write(r["glb"])
    print("saved", out, r["timings"])
