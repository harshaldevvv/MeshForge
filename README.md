# MeshForge

Open-source Windows app that turns a text description or a set of photos into textured, game-ready 3D models, from 500-triangle low poly to million-triangle meshes, exported in every common format with PBR texture maps.

**Status:** phase 1 (engine and command-line tool) works. The desktop UI is next. See the [architecture and build plan](docs/ARCHITECTURE.md).

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

## API keys (free options)

```
meshforge key list           # shows every key, whether it's set, and how to get it
meshforge key set hf         # free: raises the free GPU quota for 3D generation
meshforge key set cloudflare # free: ~170 images/day, for text-to-3D
```

Keys are stored in Windows Credential Manager. Environment variables `MESHFORGE_<NAME>` override them.

| Key | Used for | Cost | Get it |
|---|---|---|---|
| `hf` | 3D generation through free Hugging Face Spaces (TRELLIS.2, Hunyuan3D-2mv) | Free: 5 GPU-min/day (2 without a key) | [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) → New token → Read |
| `cloudflare` | Text → image (FLUX) | Free: 10,000 neurons/day | [dash.cloudflare.com](https://dash.cloudflare.com): copy the Account ID, then My Profile → API Tokens → "Workers AI" template. Store as `ACCOUNT_ID:TOKEN` |
| `pollinations` | Text → image | Free grant | [enter.pollinations.ai/keys](https://enter.pollinations.ai/keys) |
| `fal` | Paid 3D backends (no daily limit) | ~$0.02–0.35 per model | [fal.ai/dashboard/keys](https://fal.ai/dashboard/keys) |

## Use

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

## License

MIT
