# State of the art: 1–4 images or text to a textured 3D mesh (Oct 2026)

## TL;DR for MeshForge

- **Nothing at good quality fits in 4 GB of VRAM.** The smallest open models list about 5–6 GB in their own docs: Hunyuan3D-2mini needs 5 GB for shape ([ComfyUI docs](https://docs.comfy.org/tutorials/3d/hunyuan3D-2)), TripoSR and SF3D about 6 GB, and Zero123++ about 5 GB. On low-VRAM machines (like an RTX 3050 Ti 4 GB), every generative stage must run on **cloud or hosted inference**. Run Blender post-processing locally.
- **Best open model today: TRELLIS.2** (MIT, PBR, single image, 24 GB, officially Linux-only). Its derivative **Pixal3D** (MIT, SIGGRAPH 2026) adds pixel-aligned conditioning ([ComfyUI blog](https://blog.comfy.org/p/trellis2-and-pixal3d-are-now-native)).
- **True multi-view conditioning in open weights is rare.** Hunyuan3D-2mv takes front, left and back views (shape only; the license excludes the EU, UK and South Korea). Original TRELLIS has a tuning-free multi-image mode. Hosted Hunyuan3D 3.x accepts 2–4 views.
- **Text-to-3D in practice means text to image (or multi-view) to an image-to-3D model.** Microsoft recommends this over its own text-conditioned TRELLIS ([TRELLIS](https://github.com/microsoft/TRELLIS)).

## 1. Feed-forward image-to-3D models

| Model | License | VRAM | Inputs | Output / PBR | Notes |
|---|---|---|---|---|---|
| **TRELLIS** (Dec 2024) | MIT | ≥16 GB | 1 image; multi-image (tuning-free); text models | Gaussians, radiance field, GLB (baked colour) | Linux-tested. [repo](https://github.com/microsoft/TRELLIS) |
| **TRELLIS.2-4B** (Dec 2025) | MIT | ≥24 GB (community GGUF Q4 reportedly 8 GB at 512³, unverified) | 1 image; PBR texturing of an existing mesh | GLB with base colour, roughness, metallic, opacity | O-Voxel, 512³–1536³. On an H100: ~3 s at 512³, ~60 s at 1536³. [repo](https://github.com/microsoft/TRELLIS.2) |
| **Pixal3D** (May 2026) | MIT | not stated; low-VRAM mode | 1 image | GLB with PBR | Pixel-aligned back-projection. [HF](https://huggingface.co/TencentARC/Pixal3D), [arXiv](https://arxiv.org/pdf/2605.10922) |
| **Hunyuan3D 2.0** | Tencent community license; **excludes EU/UK/KR** | 6 GB shape, 16 GB with texture | 1 image | GLB/OBJ; RGB texture plus Delight | [repo](https://github.com/Tencent-Hunyuan/Hunyuan3D-2) |
| **Hunyuan3D-2mini** | same | 5 GB | 1 image | shape only | |
| **Hunyuan3D-2mv** | same | ~6 GB | front / left / back | shape only | [HF](https://huggingface.co/tencent/Hunyuan3D-2mv) |
| **Hunyuan3D 2.1** | same | 10 GB shape, 29 GB both | 1 image; paint uses 6 views at 512 | **PBR** | [repo](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1) |
| **Hunyuan3D 3.0 / 3.1** | hosted API only | n/a | text, 1 image, **2–4 views** | PBR, parts, UV, low-poly "Smart Topology" | [ComfyUI node](https://docs.comfy.org/tutorials/partner-nodes/hunyuan3d/hunyuan3d-3-0) |
| **Stable Fast 3D** | Stability Community (free under $1M revenue) | ~6 GB | 1 image | UV GLB, per-object roughness/metallic | Under 1 s. [repo](https://github.com/Stability-AI/stable-fast-3d) |
| **SPAR3D** | Stability Community | ~7–10.5 GB | 1 image; editable point cloud | GLB, built-in remesh | [repo](https://github.com/Stability-AI/stable-point-aware-3d) |
| **TripoSR** | MIT | ~6 GB | 1 image | vertex colour or baked texture | 2024 quality. [repo](https://github.com/VAST-AI-Research/TripoSR) |
| **InstantMesh** | Apache-2.0 (Zero123++ weights NC) | ? | 1 image to 6 views to LRM | OBJ | [repo](https://github.com/TencentARC/InstantMesh) |
| **TripoSG** | MIT | ≥8 GB | 1 image | geometry, face cap | [repo](https://github.com/VAST-AI-Research/TripoSG) |
| **Step1X-3D** | Apache-2.0 | 27–29 GB | 1 image | textured GLB | [repo](https://github.com/stepfun-ai/Step1X-3D) |
| **Direct3D-S2** | MIT | 10–24 GB | 1 image | geometry, sparse SDF 1024³ | [repo](https://github.com/DreamTechAI/Direct3D-S2) |
| **SAM 3D Objects** | SAM License (gated) | ? | image + mask, cluttered scenes | Gaussian splat | [repo](https://github.com/facebookresearch/sam-3d-objects) |
| **PartCrafter** | MIT | ≥8 GB | 1 image + part count | separate part meshes | [repo](https://github.com/wgsxm/PartCrafter) |

## 2. Multi-view generation: text or one image to consistent views

| Model | License | Views | Notes |
|---|---|---|---|
| Zero123++ | weights **CC-BY-NC** | 6 views | [repo](https://github.com/SUDO-AI-3D/zero123plus) |
| MVDream | MIT / OpenRAIL | 4 views at 256 px | needs slow SDS. [repo](https://github.com/bytedance/MVDream) |
| Era3D | **AGPL-3.0** | 6 views with normals | [repo](https://github.com/pengHTYX/Era3D) |
| MV-Adapter | **Apache-2.0** | 2–6 views, SDXL or SD2.1; can also texture a mesh | Best licence for an open app. [repo](https://github.com/huanngzh/MV-Adapter) |

**How commercial apps get turnaround views:**
- **Editing models with camera LoRAs**, for example Qwen-Image-Edit "Multiple Angles" ([Replicate](https://replicate.com/qwen/qwen-edit-multiangle/readme)).
- **Prompting a general image model for a character turnaround sheet**, then cropping each view.
- **Caveat:** expect small drift between views. Models conditioned on several views tolerate drift; photogrammetry does not.

## 3. Classical reconstruction: how many images it really needs

- **Photogrammetry** ([COLMAP](https://github.com/colmap/colmap), [Meshroom](https://github.com/alicevision/Meshroom)): needs dozens of overlapping photos. With 2–4 images, especially generated ones, registration usually fails ([FSGS](https://arxiv.org/pdf/2312.00451)).
- **Gaussian splatting and NeRF:** sparse-view variants work from about 3 views, but leave floaters and undefined unseen sides. The output is not a clean mesh ([SparseGS](https://arxiv.org/pdf/2312.00206)).
- **DUSt3R / MASt3R:** work from 2 images, but non-commercial and visible surfaces only.
- **VGGT:** takes 1 to hundreds of views; a commercial checkpoint exists ([repo](https://github.com/facebookresearch/vggt)).
- **Verdict:** classical methods only rebuild what the cameras see. Use them as a pose and depth prior, or for real photo sets of 20+ images, not as the main path for 2–4 images.

## 4. Geometry pipeline (the math)

- **Implicit field to mesh:** generators predict an SDF or occupancy field, and **marching cubes** extracts the surface. [DMTet](https://arxiv.org/abs/2111.04276) and [FlexiCubes](https://arxiv.org/abs/2308.05371) are differentiable alternatives that keep features sharper.
- **Sparse voxel latents:** TRELLIS SLAT ([arXiv 2412.01506](https://arxiv.org/abs/2412.01506)) and TRELLIS.2 O-Voxel store only surface voxels, which makes 1024³–1536³ feasible. Raw output is millions of irregular triangles.
- **UV unwrap:** [xatlas](https://github.com/jpcy/xatlas) is the de facto chart packer; Blender's Smart UV Project is the fallback.
- **Texture back-projection:**
  1. Project view pixels onto UV texels, weighted by the angle between view and surface normal.
  2. Inpaint texels no view covers.
  3. Expect seams and blur at grazing angles.
- **PBR:**
  - TRELLIS.2 decodes per-texel PBR.
  - SF3D gives one roughness/metallic value per object.
  - Hunyuan's **Delight** model removes lighting baked into the photo.
- **Remesh:** [Instant Meshes](https://github.com/wjakob/instant-meshes), Blender QuadriFlow, or Voxel remesh.
- **Decimate:** quadric error metrics ([Garland & Heckbert 1997](https://www.cs.cmu.edu/~garland/Papers/quadrics.pdf)), as in Blender's Decimate (Collapse) modifier.
- **Low poly:** decimate or remesh, then **re-bake** normal and colour maps from the high-poly mesh (Cycles "Selected to Active"). Without the re-bake, detail is lost.

## 5. Honest quality from 2–4 images

| Approach | Realistic tier |
|---|---|
| TRELLIS.2 / Pixal3D, front image only | game prop to near-hero geometry; back side hallucinated |
| Hunyuan3D-2mv + Paint 2.1 | game prop; back side follows the given views; territory licence issue |
| Hunyuan3D 3.x hosted, 2–4 views | game prop to hero-ish (vendor claim); paid cloud |
| SF3D / TripoSR / SPAR3D | rough blockout |
| Photogrammetry / 3DGS / NeRF from 2–4 views | unusable as a full asset |

**Failure modes:**
- **Back-side hallucination:** single-view models invent geometry and texture they can't see.
- **Thin parts:** straps and legs break or merge at the voxel resolution limit.
- **Texture seams and blur:** at grazing angles and in inpainted regions.
- **Baked lighting:** photo lighting ends up in the albedo, unless a Delight step or native PBR is used.
- **Topology:** dense triangle soup; animation-ready quads always need a remesh plus re-bake.
- **Alpha:** TRELLIS.2 exports GLB as OPAQUE.

## Caveats

Some VRAM figures (TRELLIS.2 GGUF at 8 GB) and all hosted prices come from community or vendor pages. The SPAR3D and Inria 3DGS licence texts were not checked.
