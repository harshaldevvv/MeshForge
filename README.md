# MeshForge

Open-source Windows app that turns a text description or a set of photos into textured, game-ready 3D models, from 500-triangle low poly to million-triangle meshes, exported in every common format with PBR texture maps.

**Status:** phase 1 (engine and CLI) and phase 2 (desktop app) work. Next: deeper iteration tools, more backends and maps, then a signed installer. See the [architecture and build plan](docs/ARCHITECTURE.md).

## How it works

```
description ─► images (your API key, free options) ─► AI 3D reconstruction ─► Blender refine ─► export
   or your own photos ─────────────────────────────┘    TRELLIS.2 / Hunyuan3D     cleanup, decimate/quads,
                                                                                  UV, bake albedo/normal/
                                                                                  roughness/AO
```

Blender cannot build a model from images by itself; the AI model makes the shape. MeshForge then uses Blender to make the result usable: clean topology at the detail level you choose, a proper UV layout, baked texture maps, and every export format. For what quality to expect from 1–4 images, read [the research](docs/research/01-sota-models.md).

## Install

Requires Windows, Python 3.10+, and [Blender 5.x](https://www.blender.org/download/) (detected automatically, or set `MESHFORGE_BLENDER`).

```
git clone https://github.com/harshaldevvv/MeshForge
cd MeshForge
python -m venv .venv
.venv\Scripts\pip install -e .
```

## Three ways to generate

| | What you need | Cost | Best for |
|---|---|---|---|
| **Local (offline)** | Download models in the app (**Local models**) | Free, unlimited | Privacy, no keys, low-poly props, batch runs |
| **Free online** | Optional free keys (Hugging Face, Cloudflare, Pollinations) | Free daily quotas | Best open quality (TRELLIS.2) at a few models a day |
| **Your paid key** | Any key below | Pay per use | Volume and top commercial quality (Tripo, Meshy, Rodin…) |

## Local models (offline)

Open **Local models** in the app. It detects your GPU, VRAM, RAM and disk, then marks each model as **Recommended**, **Runs well**, **Slow on this PC** or **Too big**. One click downloads a model with progress, and installed models appear in the pickers.

- **Templates (instant, no AI).** 22 parametric generators built into the app: chest, crate, barrel, table, chair, stool, bench, bookshelf, cabinet, lamp/lantern, sword, axe, shield, bottle/potion, mug, vase, candle, tree, rock, door, fence and goblet. Plain words set the parameters: *"a large dark walnut treasure chest with gold metal and 3 bands"*, *"2 m tall bookshelf with 6 shelves"*, *"blue kite shield"*, *"chest without a lock"*. It works on any PC in about 30 seconds, mostly baking time.
- **Text → 3D (local LLM + templates).** An [Ollama](https://ollama.com) model (Qwen2.5-Coder or Qwen3.5, 1 GB to 19 GB) picks the template and fills in its settings as JSON. The app validates and clamps every value, so proportions stay sensible. When no template fits, the model writes a free-form Blender script instead. That script uses a modeling kit and passes an allow-list safety check, and any errors are fed back for an automatic repair. **Edit with AI** changes the settings ("wider, domed lid, only 2 bands") or rewrites the free-form script.
- **Text → 3D (AI writes the mesh).** LLaMA-Mesh (NVIDIA) outputs the mesh directly. It's limited to under 500 faces and is non-commercial.
- **Text → image.** Uses [stable-diffusion.cpp](https://github.com/leejet/stable-diffusion.cpp), with no PyTorch needed:
  - **Z-Image-Turbo** and **FLUX.2 klein 4B** (Apache-2.0) run on 4 GB GPUs.
  - **SD-Turbo** for weak PCs.
  - **FLUX.1 schnell** for 6 GB+.
  - Ollama itself can't generate images on Windows yet; see the [research](docs/research/05-local-models.md).
- **Image → 3D.**
  - **TripoSR** (MIT): GPU or CPU.
  - **Hunyuan3D-2mini**: shape only, 6 GB+. Its license excludes the EU, UK and South Korea.

Models are stored in `%LOCALAPPDATA%\MeshForge`; override with `MESHFORGE_HOME`.

## API keys

Add keys in the app (**API keys**: grouped into image, 3D, and both, each with step-by-step instructions and a link) or with `meshforge key set <name>`. Keys are stored only in Windows Credential Manager on your PC, never in files. `MESHFORGE_<NAME>` environment variables override them.

| Key | Images | 3D | Free tier | Get it |
|---|---|---|---|---|
| `cloudflare` | FLUX.1 schnell | | 10,000 neurons/day (~170 images) | [dash.cloudflare.com](https://dash.cloudflare.com/?to=/:account/ai/workers-ai) |
| `pollinations` | FLUX | | free pollen grant | [enter.pollinations.ai/keys](https://enter.pollinations.ai/keys) |
| `hf` | FLUX.1 schnell (credits) | TRELLIS.2, Hunyuan3D-2mv Spaces | 5 GPU-min/day (~2 models) | [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) |
| `gemini` | Nano Banana 2 | | none | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| `openai` | gpt-image-1-mini | | none | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `xai` | Grok Imagine | | none | [console.x.ai](https://console.x.ai) |
| `together` | FLUX.2 [dev] | | none | [api.together.ai](https://api.together.ai/settings/projects/~current/api-keys) |
| `fal` | FLUX schnell | TRELLIS.2, TRELLIS multi, Hunyuan multi-view | none | [fal.ai/dashboard/keys](https://fal.ai/dashboard/keys) |
| `replicate` | FLUX schnell | TRELLIS | none | [replicate.com/account/api-tokens](https://replicate.com/account/api-tokens) |
| `stability` | Stable Image Core | Stable Fast 3D, SPAR3D | a few signup credits | [platform.stability.ai](https://platform.stability.ai/account/keys) |
| `tripo` | | Tripo v3.1 (single and multi-view) | first-key credits | [platform.tripo3d.ai](https://platform.tripo3d.ai) |
| `meshy` | | Meshy 7.1 (single and multi-image) | none (paid plan) | [meshy.ai/developers/keys](https://www.meshy.ai/developers/keys) |
| `rodin` | | Hyper3D Rodin Gen-2.5 | none (Business plan) | [hyper3d.ai](https://hyper3d.ai/workspace/api-dashboard) |
| `tencent` | | Hunyuan 3D 3.1 | 200 credits | [Tencent Cloud CAM](https://console.tencentcloud.com/cam/capi) |
| `custom` | any OpenAI-compatible `/images/generations` | | — | JSON `{"base_url", "model", "api_key"}` |

Request formats were verified against each provider's docs ([specs](docs/research/04-provider-api-specs.md)). See [What has been tested](#what-has-been-tested) for which providers have run end to end. The rest are implemented from the docs and need a key to verify.

## Desktop app

```
meshforge ui
```

**Generating:** describe an object, or add images, a batch folder or a description list. Then pick a backend and detail level and press **Generate**. Jobs run in parallel, and each card shows its stage live.

**Each model card opens a 3D viewer** where you can orbit and zoom. It shows:
- **Lit:** full PBR shading.
- **Albedo, Normal map, Roughness, AO:** the exact baked maps, one at a time.
- **Clay:** shape only, no texture.
- **UV checker:** shows texture stretching and seams.
- **Wireframe** overlay, **Turntable** rotation, and **Raw model** (the untouched AI output, for comparison).
- Triangle and vertex counts.

**Per model you can also:**
- **Apply** a new detail level, triangle target, texture size or quad topology. This re-runs only Blender and takes seconds, with no API cost.
- **Regenerate** with a new seed, or with new images for text jobs.
- **Download** any format or map.

**API keys** opens a panel where you paste keys; pasting works there. **Export all** writes one zip of every model.

Models are saved to `Documents\MeshForge` (change it with `MESHFORGE_OUTPUT`). `meshforge ui --browser` serves the same UI to any browser, minus the native file pickers.

## Command line

```
meshforge run "a weathered bronze knight helmet with a red plume"     # text → model
meshforge run photo.png --preset low                                   # one image
meshforge run my_objects/                                              # a whole folder (batch)
meshforge run list.txt --views front,back,left,right --backend hf-hunyuan-mv
meshforge refine output/helmet --preset low --quads                    # instant re-do of the Blender stage only
meshforge export output --zip all.zip --formats glb,fbx                # bulk export
```

**Batch inputs:**
- A **folder of folders**: each subfolder is one object.
- A **flat folder**: images are grouped by name, with the view read from the suffix (`chair_front.png`, `chair_back.png`, `chair_left.jpg`). Recognised suffixes are front/back/left/right/top/bottom, f/b/l/r and 0/90/180/270.
- A **.txt** file with one description per line, or a **.csv** with columns `name, description, preset`.

**Detail presets** (`--preset`):

| Preset | Triangles | Textures |
|---|---|---|
| `low` | 3,000 | 1K |
| `game` (default) | 30,000 | 2K |
| `high` | 300,000 | 4K |
| `ultra` | keep everything from the model (up to ~1M) | 4K |

Override with `refine --target N --texture PX`. Add `--quads` for quad-dominant topology.

**Backends** (`--backend`):
- `hf-trellis2`: default. Free, one image, best open quality.
- `hf-hunyuan-mv`: free, takes front/back/left/right views. The Tencent license excludes the EU, UK and South Korea.
- `fal-trellis2`, `fal-trellis-multi`, `fal-hunyuan-mv`: paid, with no quota.

**Output** for each model lands in `output/<name>/`:
- `views/` holds the input images.
- `raw.glb` is the model straight from the AI backend.
- `final/` holds `model.glb/.fbx/.obj/.usdz/.stl/.ply`, plus `diffuse.png`, `normal.png`, `roughness.png` and `ao.png`.
- `job.json` records the settings used.

The Blender stage on its own (no AI) also works on any GLB:

```
blender -b --factory-startup -P blender/pipeline.py -- in.glb out/ 5000 2048 0
```

## Research

- [Image/text-to-3D models, papers and math](docs/research/01-sota-models.md)
- [Competitors, image APIs, hosted 3D](docs/research/02-competitors-and-apis.md)
- [Blender 5.x headless pipeline and desktop stack](docs/research/03-blender-and-stack.md)

## What has been tested

All of this was run on a laptop with an RTX 3050 Ti (4 GB VRAM), 16 GB RAM and a Ryzen 5 5600H.

| Route | Result | Time |
|---|---|---|
| Image → TRELLIS.2 (Hugging Face free) → Blender | Very good: pawn with wood-grain texture, 30k triangles | ~2.5 min |
| Blender refine: low poly, quads, every format, maps | Works: 488k → 3,000 triangles with detail kept in the normal map; 75% quads in quad mode | 15–45 s |
| **Offline:** text → Z-Image-Turbo → TripoSR → Blender | Good: recognisable textured teapot and chest, no keys | ~3 min |
| **Offline:** Z-Image-Turbo image alone | Excellent product-shot quality | 1.5–4 min at 768 px |
| **Offline:** TripoSR image → 3D alone | Rough but correct shape and texture, floaters removed | ~1 min |
| **Offline:** templates, instant (no AI) | Very good: clean, well-proportioned props; a batch of 12 from a .txt list with 0 failures | ~30 s each |
| **Offline:** Qwen3.5 4B picks template + settings | Good: always a proper object; settings follow the description | ~45–75 s |
| Edit with AI on template models | Correct: "flat lid with feet and 4 bands" and "wider, domed lid, 2 bands" both applied exactly | 35–45 s |
| **Offline:** Qwen3.5 4B free-form Blender script (no template) | Works, but rough: recognisable layout, poor proportions | ~2 min |
| Hunyuan3D-2mv (Hugging Face free) | Not verified: the free daily quota ran out | — |
| Paid providers (fal, Tripo, Meshy, Rodin, Tencent, Replicate, Stability, OpenAI, Gemini, xAI, Together) and Cloudflare/Pollinations | Implemented from official docs; need a key to verify | — |

**Honest take on local LLM modeling.** Small models (≤ 4B) can't reason well about 3D layout, which is why MeshForge has them fill template settings instead of inventing geometry. For objects without a template, free-form scripts from small models stay rough. Use 7B+ models, or the offline image route (Z-Image + TripoSR), for those.

## License

MIT
