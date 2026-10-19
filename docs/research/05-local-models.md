# Local (offline) models (researched 2026-10-19)

## Key facts

- **Ollama cannot generate images on Windows.**
  - Image generation shipped macOS-only in January 2026.
  - It was removed from the runner in v0.32.6 ([issue 17893](https://github.com/ollama/ollama/issues/17893)) and is still absent in v0.40.x ([issue 18863](https://github.com/ollama/ollama/issues/18863)).
  - MeshForge uses **stable-diffusion.cpp** for local images instead.
- **stable-diffusion.cpp** ([repo](https://github.com/leejet/stable-diffusion.cpp), MIT):
  - The Windows Vulkan build is 28 MB and works on NVIDIA, AMD and Intel GPUs.
  - It runs SD-Turbo, SDXL, FLUX.1, FLUX.2 klein, Z-Image and Qwen-Image.
  - The binary is `sd-cli.exe`.
- **Z-Image-Turbo** (Apache-2.0) runs on 4 GB of VRAM with `--offload-to-cpu` ([docs](https://github.com/leejet/stable-diffusion.cpp/blob/master/docs/z_image.md)). It's the default local image model.
- **Ollama coding models** write Blender (bpy) scripts that build objects from primitives. This gives clean low-poly topology and works on any PC.
- **TripoSR** (MIT):
  - Its `torchmcubes` dependency needs a compiler on Windows. MeshForge swaps it for PyMCubes, which ships wheels.
  - About 6 GB of VRAM, or CPU with a lower marching-cubes resolution.
- **Hunyuan3D-2mini** (shape only):
  - Installs with `pip install hy3dgen`, about 6 GB of VRAM.
  - The Tencent license excludes the EU, UK and South Korea.
- **Skipped:**
  - Local TRELLIS.2: 24 GB, Linux, compiled extensions.
  - Pixal3D and SAM 3D: same problems.
  - SPAR3D and SF3D: compiled extensions, gated weights.
  - `qwen2.5-coder:3b` and codestral: non-commercial licenses.

## Catalog

| id | kind | download | min VRAM (CPU?) | license |
|---|---|---|---|---|
| qwen2.5-coder:1.5b | LLM → Blender | 1 GB | CPU ok | Apache-2.0 |
| qwen3.5:2b / 4b / 9b | LLM → Blender | 3 / 3.5 / 7 GB | CPU ok / 4 / 8 GB | Apache-2.0 |
| qwen2.5-coder:7b / 14b | LLM → Blender | 4.7 / 9 GB | 6 / 12 GB | Apache-2.0 |
| gpt-oss:20b, qwen3-coder:30b | LLM → Blender | 14 / 19 GB | 16 / 24 GB | Apache-2.0 |
| LLaMA-Mesh Q4_K_M | LLM → mesh text | 4.9 GB | 6 GB | non-commercial |
| Z-Image-Turbo Q3 | image | ~6 GB | 4 GB | Apache-2.0 |
| FLUX.2 klein 4B Q4 | image | ~5.2 GB | 4 GB | Apache-2.0 |
| SD-Turbo | image | 5.2 GB | CPU ok | Stability Community |
| FLUX.1 schnell Q4 | image | ~10 GB | 6 GB | Apache-2.0 |
| TripoSR | image → 3D | 1.7 GB + PyTorch | 6 GB / CPU | MIT |
| Hunyuan3D-2mini (shape) | image → 3D | 4.3 GB + PyTorch | 6 GB | Tencent (no EU/UK/KR) |
