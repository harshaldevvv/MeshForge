---
name: blender-pipeline
description: Verified Blender 5.x headless bpy facts for MeshForge's mesh post-processing (cleanup, remesh/decimate, UV, Cycles hi-to-lo baking, multi-format export). Use when writing or changing anything under blender/ or any code that spawns Blender.
---

# Blender 5.x headless pipeline

Reference implementation: `blender/pipeline.py` (verified on Blender 5.2.2). Full research: `docs/research/03-blender-and-stack.md`.

## Run

```
blender -b --factory-startup -P blender/pipeline.py -- in.glb outdir <target_tris>
```

- `-b` exits 0 even when the script raises. Keep the `try/except` → `sys.exit(1)` wrapper.
- Errors print `MESHFORGE_ERROR:` on stderr.
- Each job runs in its own process. Serialize Cycles bakes (they share the GPU); cleanup can run in parallel.

## Facts that bite (4.x → 5.x)

- **Exporters:** `wm.obj_export`, `wm.stl_export`, `wm.ply_export`, `wm.usd_export` (`.usdz` extension, `export_textures_mode='NEW'`), `export_scene.gltf`, `export_scene.fbx`. Collada is **removed** in 5.0.
- **Materials:**
  - `material.use_nodes` is a no-op in 5.x.
  - New materials already have `node_tree` with a "Principled BSDF".
  - `scene.node_tree` became `scene.compositing_node_group`.
- **Python:** Blender's Python is 3.13 (5.1+), so any wheel installed into Blender must be cp313.
- **GPU:** set `prefs.compute_device_type` (OPTIX/CUDA/HIP/ONEAPI), call `refresh_devices()`, set `d.use`, then `scene.cycles.device='GPU'`. Fall back to CPU.

## Recipes

- **Cleanup:** `remove_doubles`, then `dissolve_degenerate`, then `delete_loose`, then `normals_make_consistent` (Edit Mode, everything selected).
- **Exact triangle target:** Decimate COLLAPSE with `ratio = target / tris` and `use_collapse_triangulate=True`.
- **Watertight / triangle soup:** voxel remesh (`data.remesh_voxel_size ≈ diag/300`, then `object.voxel_remesh()`). This drops UVs.
- **Quads:** voxel remesh first, then `object.quadriflow_remesh(mode='FACES', target_faces=N)`. The face count is approximate.
- **UV:** `uv.smart_project` + `uv.pack_islands(shape_method='CONCAVE')`. xatlas is optional and better.
- **Bake (Selected to Active):**
  - Selection: high-poly selected, low-poly selected **and active**, Image Texture node active in the low-poly material.
  - Distances: `cage_extrusion ≈ 1%` and `max_ray_distance ≈ 3%` of the bbox diagonal.
  - Base colour: `DIFFUSE` with `pass_filter={'COLOR'}` into an sRGB image.
  - Normal, roughness and AO: Non-Color images.
- **Passes Blender doesn't have** (metallic, curvature, height):
  - Metallic and curvature: rewire to Emission and bake `EMIT`.
  - Height: BVHTree ray distance written to `image.pixels`.
  - Normal or height from albedo only: NumPy Sobel outside Blender.
- **glTF AO and metallic:** pack an ORM texture (R = AO, G = roughness, B = metallic).
