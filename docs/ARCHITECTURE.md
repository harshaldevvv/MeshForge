# MeshForge architecture and build plan

Based on the research in [`docs/research/`](research/). Read [01](research/01-sota-models.md) (models), [02](research/02-competitors-and-apis.md) (competitors and APIs) and [03](research/03-blender-and-stack.md) (Blender and stack).

## The honest answer: how good can 2–4 images get?

- **Blender cannot turn images into a 3D model by itself.** No Blender add-on can either: every add-on is a thin client for an ML model.
- **The model makes the shape. Blender makes it usable:** cleanup, low-poly or high-poly topology, UVs, baked PBR maps and every export format.
- **With 2–4 views, photogrammetry fails.** It needs about 20 or more overlapping real photos. So MeshForge uses **generative reconstruction**:
  - TRELLIS.2 or Pixal3D for one image (best open quality, PBR).
  - Hunyuan3D-2mv, Tripo, Meshy, Rodin or Hunyuan 3.x for multiple views.
- **Realistic quality:**
  - Game-prop to near-hero geometry on the visible side, with a plausible back side.
  - Multi-view input (front, left, back, right) markedly improves the back and sides.
  - Thin parts (straps, legs) and fine engraved detail are the weak spots.
  - Expect to regenerate some models; the competitors' own users report about 1 in 10 is perfect first try. **Fast per-model iteration is the core feature, not an extra.**
- **Photo sets of 20+ real photos** get an optional photogrammetry path (COLMAP), which gives true-to-life detail.

## Hardware reality

Every good open model needs 6–24 GB of VRAM. On a 4 GB GPU (like the RTX 3050 Ti), reconstruction runs on **hosted backends**, while Blender post-processing runs locally (verified: about 25 s per model). The app detects VRAM and enables local models only when they fit.

## Pipeline (each stage re-runnable per model)

```
 describe ─► [1 Prompt expand] ─► [2 Views] ─► [3 Reconstruct] ─► [4 Refine in Blender] ─► [5 Export]
                                    ▲ upload        ▲ any backend      ▲ detail preset          GLB FBX OBJ USDZ STL PLY
                                    │ own images    │                  │ target faces, quads    + albedo normal roughness
                                                                       │ texture res, maps        metallic AO height ORM
```

1. **Prompt expansion:** turn the user's description into a structured turnaround prompt: plain background, orthographic, front/left/back/right views, neutral lighting with no harsh shadows (which avoids baked-in lighting).
2. **Views:** generate one turnaround sheet and crop it, or generate each angle with reference-image conditioning, or let the user upload images. Background removal (rembg) runs on every view.
3. **Reconstruct:** run the chosen backend (see below). Output is a raw GLB.
4. **Refine:** run `blender/pipeline.py`: cleanup, then remesh or decimate to the preset, then UV, then bake high-to-low (albedo, normal, roughness, AO; metallic and height through the EMIT/BVH methods), then export.
5. **Export:** per model or bulk zip, in every format, plus loose texture maps.

## Detail presets

| Preset | Triangles | Topology | Textures |
|---|---|---|---|
| Low poly | 500 – 5k | decimate, optional quads | 1K |
| Game | 10k – 50k | decimate or QuadriFlow quads | 2K |
| High | 200k – 1M | light decimate | 4K |
| Ultra / raw | millions (backend raw, up to 1536³ on TRELLIS.2) | none | 4K–8K |
| Custom | any number | voxel, QuadriFlow, decimate or Instant Meshes | 512 – 8K |

## Providers (bring your own key, with free options first)

**Image generation:**
- Cloudflare Workers AI (free: 10k neurons/day ≈ 170 FLUX images)
- Pollinations (free grant)
- Together FLUX-schnell-Free
- Gemini Nano Banana (paid, best multi-reference consistency)
- OpenAI gpt-image
- fal, Replicate, Stability, xAI
- **Manual upload** (always available)

**3D reconstruction:**
- Hugging Face ZeroGPU Spaces (free daily quota): TRELLIS.2, Hunyuan3D-2mv, Hunyuan3D-2.1
- fal: `trellis-2`, `trellis/multi`, `hunyuan3d/v2/multi-view`
- Tripo, Meshy, Rodin and Tencent Hunyuan 3D (user's own key)
- Local TRELLIS.2 or Hunyuan when VRAM allows
- COLMAP for 20+ photo sets

Each provider is a small module with one function: `generate(inputs, params) -> path`. An in-app guide with screenshots walks the user through getting each free key. Keys are stored in Windows Credential Manager (`keyring`), never in plain files.

## Batch input

- **Folder of folders:** each subfolder is one object.
- **Flat folder:** images are grouped by name prefix, with the view taken from the suffix: `chair_front.png`, `chair_back.png`, `chair_left.jpg`, and so on. Recognised suffixes include `front/back/left/right/top/bottom/f/b/l/r/0/90/180/270`.
- **Text list:** one description per line, or a CSV with columns `name, description, detail preset`.
- Any number of jobs can be queued. Concurrency is limited per resource: hosted API calls in parallel, Blender processes about cores/4, GPU bakes one at a time.

## Iteration per model

Every model card has:
- **Regenerate from stage N** with edited params: new views, a different backend or seed, a new topology target, retexturing, re-baking at a higher resolution.
- **Instant tweaks** that re-run only Blender, in seconds: face count, quads on/off, smoothing, scale, origin and centring, texture resolution, maps on/off.
- **Version history** for each model, so you can compare and roll back.

## Stack

| Layer | Choice | Why |
|---|---|---|
| Shell | **Tauri 2** (NSIS installer, ~10 MB) | Small, native WebView2, built-in sidecar support |
| UI | React + Vite + three.js | Viewer with channel isolation (albedo, normal, roughness and so on), wireframe, UV checker |
| Engine | Python sidecar: FastAPI + asyncio job queue + SQLite | ML and HTTP clients live in Python; spawns Blender |
| 3D processing | Blender 5.x headless (detected, not bundled) | Verified pipeline; avoids GPL bundling |
| Packaging | PyInstaller in one-folder mode, code-signed | Smart App Control blocks unsigned executables |

**Developers** can run the engine alone (`python -m meshforge serve` or the CLI `meshforge run folder/`) without the desktop shell.

## Build phases

1. **Engine CLI:** providers (Cloudflare, Pollinations, upload; HF TRELLIS.2 and Hunyuan-2mv; fal), Blender stage, batch folder parsing, exports. *Done when:* `meshforge run ./examples` turns a folder into exported models.
2. **Desktop UI:** job queue, model cards, three.js viewer with map inspection, key-setup guide, bulk export.
3. **Iteration:** stage-level regenerate, instant tweaks, versions.
4. **More backends:** Tripo, Meshy, Rodin, Tencent, local models with VRAM gating, COLMAP photo sets, extra maps (metallic, height, curvature, ORM), quad remesh via Instant Meshes.
5. **Release:** signed installer and GitHub Releases.
