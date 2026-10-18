# MeshForge

Open-source Windows app that turns a text description or a set of photos into a textured 3D model.

**Status: research done, engine in progress.**

- [Architecture and build plan](docs/ARCHITECTURE.md)
- Research: [models and papers](docs/research/01-sota-models.md), [competitors and APIs](docs/research/02-competitors-and-apis.md), [Blender and desktop stack](docs/research/03-blender-and-stack.md)
- Working now: [`blender/pipeline.py`](blender/pipeline.py), which takes any GLB through cleanup, decimation to a target, UV unwrap, a high-to-low bake (albedo, normal, roughness, AO) and export to GLB, FBX, OBJ, USDZ, STL and PLY. Requires Blender 5.x:

```
blender -b --factory-startup -P blender/pipeline.py -- in.glb out/ 5000
```

## Planned pipeline

1. **Describe**: write what you want in as much detail as you like.
2. **Images**: generate multi-angle reference images with your own image API key (free options documented), or upload your own.
3. **Reconstruct**: turn 1 to 4+ views into a textured mesh.
4. **Refine in Blender**: cleanup, low-poly or multi-million-triangle remesh, UV unwrap, PBR texture bake.
5. **Iterate and export**: tweak and regenerate per model, then bulk export (GLB, FBX, OBJ, USDZ, STL) with texture maps (albedo, normal, roughness, height, AO).

Batch mode: point it at a folder of folders (one object each) or a pile of named images.

## License

MIT
