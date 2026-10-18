# Blender headless post-processing, existing tools, agent skills, desktop stack (Oct 2026)

**Verified on Blender 5.2.2 LTS** (Python 3.13, RTX 3050 Ti, OptiX). The pipeline in `blender/pipeline.py` ran headless from start to finish. It took a 63k-triangle textured GLB to 5,000 triangles, baked Diffuse, Normal, Roughness and AO maps, and wrote GLB, FBX, OBJ, USDZ, STL and PLY, all in about 11 s.

## 1. bpy capabilities (5.2)

### Import and export

| Format | Import | Export | Notes |
|---|---|---|---|
| glTF/GLB | `import_scene.gltf` | `export_scene.gltf(export_format='GLB')` | Draco and (new in 5.2) meshopt compression, WebP images |
| FBX | `wm.fbx_import` (C++, 4.5+) | `export_scene.fbx(path_mode='COPY', embed_textures=True)` | |
| OBJ | `wm.obj_import` | `wm.obj_export` | The old `export_scene.obj` was removed in 4.0 |
| STL | `wm.stl_import` | `wm.stl_export` | |
| PLY | `wm.ply_import` | `wm.ply_export` | |
| USD / USDZ | `wm.usd_import` | `wm.usd_export` (`.usdz` extension) | `export_textures_mode='NEW'` (renamed in 5.0) |
| Alembic | yes | yes | |
| Collada (DAE) | **removed in 5.0** | **removed** | Convert outside Blender (Assimp) if needed |

### Cleanup (Edit Mode, everything selected)

- `remove_doubles` (merge by distance)
- `dissolve_degenerate`
- `delete_loose`
- `normals_make_consistent`
- `fill_holes(sides=0)`: unreliable on triangle soup. Voxel remesh closes holes more robustly.

### Remesh and decimate

- **Voxel remesh:** set `data.remesh_voxel_size`, then call `object.voxel_remesh()`. Output is watertight and manifold, but UVs are dropped; that's fine because we re-bake. Pick a voxel size of roughly bbox diagonal / 200–500.
- **QuadriFlow:** `object.quadriflow_remesh(mode='FACES', target_faces=N)` gives quads. Input must be manifold, so run voxel remesh first. The face count is approximate.
- **Decimate COLLAPSE** (quadric error): `ratio = target / tris` hits an exact triangle target. DISSOLVE suits hard-surface models. UNSUBDIV is useless on AI output.
- **5M+ triangles:** voxel remesh first, or pre-decimate outside Blender (meshoptimizer, fast-simplify, pymeshlab).

### UVs

- **Default:** `uv.smart_project` + `uv.pack_islands(shape_method='CONCAVE')`, with no dependencies.
- **Optional:** [xatlas](https://github.com/jpcy/xatlas) via [xatlas-python](https://github.com/mworchel/xatlas-python) packs better on decimated triangle soup. It's an extra dependency and slower.

### Cycles baking (headless)

- **GPU:** `prefs.compute_device_type='OPTIX'` (or CUDA, HIP, ONEAPI), then `refresh_devices()`, then `scene.cycles.device='GPU'`.
- **Native bake passes:** COMBINED, AO, SHADOW, POSITION, NORMAL, UV, ROUGHNESS, EMIT, ENVIRONMENT, DIFFUSE, GLOSSY, TRANSMISSION. There is **no** native metallic, height or curvature pass.
- **Selected to Active:** high-poly selected, low-poly selected **and active**, and an Image Texture node active in every material of the low-poly mesh.
- **Per-map settings:**
  - Base colour: `DIFFUSE` with `pass_filter={'COLOR'}`, sRGB.
  - Normal: tangent space, Non-Color.
  - Roughness: Non-Color.
  - AO: 64–256 samples.
  - Cage extrusion about 1% and max ray distance about 3% of the bbox diagonal.
- **Metallic and curvature:** temporarily rewire the high-poly material to Emission, bake `EMIT`, then restore it.
- **Height:** measure the high-to-low ray distance with `mathutils.bvhtree.BVHTree` and write `image.pixels`.
- **Normal or height from albedo only (no high-poly):** do it in NumPy (Sobel on luminance gives the normal; blurred luminance gives height). It's faster and deterministic. ML options are Marigold, StableNormal and DeepBump.
- **glTF wants AO and metallic packed into an ORM texture** (R = AO, G = roughness, B = metallic).
- **Exit codes:** Blender `-b` returns 0 even when the script throws, so wrap it in `try/except` and call `sys.exit(1)`.

### API breaks from 4.x to 5.x

- **4.0:**
  - Principled BSDF sockets renamed.
  - OBJ, STL and PLY exporters moved to `wm.*_export`.
- **4.1:** `use_auto_smooth` removed.
- **4.2:**
  - The Extensions system arrived (add-on modules are now `bl_ext.*`).
  - The EEVEE id became `BLENDER_EEVEE_NEXT`.
- **5.0:**
  - Collada removed.
  - `material.use_nodes` is a no-op; new materials already have a Principled BSDF.
  - `scene.node_tree` became `compositing_node_group`.
  - BGL removed.
  - USD export uses `export_textures_mode`.
  - The EEVEE id is `BLENDER_EEVEE` again.
- **5.1:** Python 3.13, so any wheels installed into Blender must be built for cp313.
- **5.2:**
  - `gpu.init()` is needed to use the GPU module in `-b`.
  - Geometry Nodes inputs moved to `modifier.properties.inputs`.
  - glTF meshopt export added.
- **Unchanged:** `object.bake` and the Cycles device-preferences API.

## 2. Existing open-source tools

| Project | What it does | Status |
|---|---|---|
| [blender-mcp](https://github.com/ahujasid/blender-mcp) | A socket server inside GUI Blender relays LLM tool calls. `generate_3d` calls Rodin, Hunyuan3D, Tripo or Meshy | MIT, ~31k stars. The socket has no auth. A good reference for provider APIs, but wrong for a headless batch app |
| [Hunyuan3D-2 Blender add-on](https://github.com/Tencent-Hunyuan/Hunyuan3D-2) | Thin client for a local FastAPI server that returns a GLB | Tencent license |
| [trellis_blender](https://github.com/FishWoWater/trellis_blender) | Thin client for a TRELLIS / TRELLIS.2 API server | Small |
| [dream-textures](https://github.com/carson-katri/dream-textures) | Local Stable Diffusion textures inside Blender | GPL-3.0, low activity |
| [Instant Meshes](https://github.com/wjakob/instant-meshes) | Quad remesher with a CLI (`-o out.obj -f faces in.obj`) | Stable, unmaintained |
| [QRemeshify](https://github.com/ksami/QRemeshify) | QuadWild-based; the best free quad topology | GPL-3.0; driven by UI operators, so test it headless first |
| Quad Remesher | Commercial | Users install it themselves |

**Gap MeshForge fills:** every add-on is a thin client. None does a robust automated pipeline of clean → retopo → bake → multi-export, in batch.

## 3. Agent skills

- [anthropics/skills](https://github.com/anthropics/skills): official. Has no Blender or 3D skill; `skill-creator` is useful for writing our own.
- [CloudAI-X/threejs-skills](https://github.com/CloudAI-X/threejs-skills): MIT, active, the most-installed three.js skills. **Used for the viewer.**
- `freshtechbro/claudedesignskills` → `blender-web-pipeline`: the closest match to our pipeline, but stale (pre-5.x).
- `roble3/cc-blender-skill` and the blender-mcp companion skills: unproven, or they assume a live MCP.
- Tauri and Electron skills: community authors, unknown.
- **Decision:** write our own project skill at `.claude/skills/blender-pipeline/` with the verified 5.x facts above. Review any third-party skill's scripts before installing it.

## 4. Desktop stack

| Option | Verdict |
|---|---|
| Electron | Mature, but a 150–250 MB installer and high RAM use |
| **Tauri 2** + React/three.js + Python sidecar | About 10 MB installer, sidecar support and NSIS/MSI out of the box. Recommended for the shipped app |
| Python + pywebview | One language and the fastest MVP; a weaker installer and update story |
| PySide6 | Large, and we'd still embed web tech for the 3D view |

**Shape of the app:**
- **Python sidecar:** FastAPI, an `asyncio` job queue with one semaphore per resource (ML GPU 1–2, Blender processes about cores/4, HTTP high), and SQLite state.
- **Blender jobs:** each runs as `blender -b --factory-startup -P pipeline.py -- <json>`. Cycles bakes are serialized.
- **Blender itself is not bundled:** it's detected on the machine (this keeps the installer small and avoids GPL distribution).
- **Packaging:**
  - PyInstaller in one-folder mode.
  - **Code signing is required:** Windows Smart App Control blocks unsigned executables.
