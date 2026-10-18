# Competitors, image APIs and hosted 3D inference (Oct 2026)

Research date: 2026-10-19. We read the official docs wherever a vendor publishes them. **[unverified]** means the figure comes from a third-party page or was missing from the official one. Some aggregators sell competing products, so read their numbers with that in mind.

## Key takeaways

1. **The Gemini API has no free tier for image output.** Every Nano Banana model shows "Not available" for free image output ([pricing, 2026-10-16](https://ai.google.dev/gemini-api/docs/pricing)). The cheapest paid option is $0.0336 per 1K image. Posts claiming "500 free images/day" are out of date.
2. **Hugging Face free accounts no longer get Inference Providers credits.** Only PRO users get $2/month ([HF](https://huggingface.co/docs/inference-providers/pricing)). ZeroGPU Spaces are still free within a daily quota.
3. **Free image paths that still work:** Cloudflare Workers AI (10,000 neurons/day, roughly 170 FLUX-schnell images) and Pollinations (cheap pollen pricing with a free grant). Together's FLUX.1-schnell-Free endpoint may also work; its status is uncertain.
4. **Free image-to-3D paths:**
   - Hugging Face ZeroGPU Spaces through `gradio_client`: TRELLIS.2 and Hunyuan3D-2 / 2mv / 2.1. Quota is 2 min/day without a token, 5 min with a free account, 40 min with PRO.
   - Tencent Hunyuan 3D Global gives 200 one-time credits.
   - Meshy's free plan has **no API access**.
5. **Multi-view input** is supported by Meshy (1–4 views), Tripo (2–4, keyed front/left/back/right), Rodin (1–5), Hunyuan3D-2mv (HF Space and fal) and fal `trellis/multi`. TRELLIS.2 takes a single image only.

## A. Commercial 3D generators

### API capabilities

| Vendor | Multi-image | Polycount / topology | Texture / PBR | Formats | Other endpoints |
|---|---|---|---|---|---|
| **Meshy** | 1–4 views ([doc](https://docs.meshy.ai/en/api/multi-image-to-3d)) | `should_remesh`, `topology` tri/quad, `target_polycount` 100–300k; smart-topology T2.5 (≤30k triangles) ([doc](https://docs.meshy.ai/en/api/image-to-3d)) | `enable_pbr`, 2k/4k/8k textures, `texture_prompt`, `remove_lighting` | glb, obj, fbx, stl, usdz, 3mf | Remesh, Retexture, Rig, Animation, UV Unwrap, Convert |
| **Tripo** | 2–4 views, front required ([doc](https://developers.tripo3d.com/en/docs/generation-multiview-to-model/standard.md)) | `face_limit` (≤2M triangles, ≤150k quads), `quad`, `smart_low_poly` 500–20k | PBR on by default, texture quality up to 8K, `delight` | GLB; FBX when quad | Texture, Retopology, Smart UV, Segmentation, Rig, Convert |
| **Hyper3D Rodin** | 1–5 images ([spec](https://docs.hyper3d.ai/en/api-specification/rodin-gen2-5)) | Quality tiers (Extreme-High up to 10M faces), Raw/Quad mesh mode, face-count override | 2K–12K textures | GLB, OBJ, FBX, USDZ, STL | Smart Low-Poly |
| **CSM.ai** | Multiview-to-3D | Retopology on Enterprise only | PBR on Enterprise | GLB, OBJ, USDZ | Acquired by Google around Jan 2026; API future unclear ([source](https://www.gunder.com/en/news-insights/client-news/gunderson-dettmer-represents-common-sense-machines-in-acquisition-by-google)) |
| **Hunyuan 3D Global** (Tencent Cloud) | Multi-view (3.1) | Professional and Express APIs | PBR | — | 3 concurrent tasks ([doc](https://www.tencentcloud.com/document/product/1284/75281)) |
| **3D AI Studio** (new, Mar 2026) | Aggregates TRELLIS.2 and Hunyuan ([PR](https://3daistudio.com/media/press-releases/3dai-studio-public-api-launch)) | Smart retopology | PBR | GLB, OBJ, FBX, STL, PLY | Texturing, repair, convert |
| **Hitem3D** | Image-to-3D, PBR toggle ([changelog](https://docs.hitem3d.ai/en/api/getting-started/changelog)) | — | PBR | — | Depth-map and segmentation APIs |
| Luma Genie, Kaedim, Sloyd, Spline, Masterpiece X | No public self-serve generation API found (Sloyd: Enterprise only) | Sloyd always outputs low poly (1k–15k triangles) | — | — | — |

### Pricing

| Vendor | Cost per generation | Free tier / API access |
|---|---|---|
| Meshy | Image-to-3D 20–35 credits; remesh 5, retexture 10, rig 5 ([pricing](https://docs.meshy.ai/en/api/pricing)) | Free plan has 100 credits/month but **no API**. API starts at Pro |
| Tripo | 20 untextured / 30 standard / 40 detailed; quad +5, smart low-poly +10 ([pricing](https://developers.tripo3d.com/en/pricing)) | Free API credits [unverified]. Failed tasks are refunded |
| Rodin | 0.5 credit base ([spec](https://docs.hyper3d.ai/en/api-specification/rodin-gen2-5)) | API requires the Business plan at $120/month ([pricing](https://hyper3d.ai/pricing?lang=en)) |
| Hunyuan 3D Global | $15 per 1k credits | **200 free credits** one-time |

### What the vendors do (lessons for MeshForge)

- **Async jobs.** Every vendor uses submit, then poll, then download, usually with a preview stage before a refine stage. Geometry and texture are **separate, re-runnable stages** (Meshy Retexture, Tripo texture endpoint).
- **Delighting on by default.** Both Meshy (`remove_lighting`) and Tripo (`delight`) remove the photo's lighting so it isn't baked into the albedo.
- **Three tiers from low to high poly:**
  1. Raw high-res mesh (up to 2M–10M faces).
  2. Remesh or decimate to a target face count.
  3. A dedicated clean low-poly mode (500–30k faces).

  Quad output is a paid toggle.
- **Texture quality is sold as resolution and channels:** 2K to 8K (12K on Rodin), plus PBR metallic, roughness and normal maps, and prompt- or image-guided retexturing.
- **What users value:** clean, game-ready quad topology, auto-rigging, texture fidelity, then speed and price. Reviews say roughly 1 in 10 generations is client-ready without rework, which is why **fast iteration and per-model tweaking** matter.

## B. Bring-your-own-key image generation

| Provider | Free allowance | Paid reference | How to get a key |
|---|---|---|---|
| **Cloudflare Workers AI** | **10,000 neurons/day**, about 170 FLUX-schnell 1024² images (our estimate) ([pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)) | $0.011 per 1k neurons | Create a Cloudflare account, copy the Account ID, then create an API token with Workers AI permission. Call `POST /accounts/{id}/ai/run/@cf/black-forest-labs/flux-1-schnell` ([model](https://developers.cloudflare.com/workers-ai/models/flux-1-schnell/)) |
| **Pollinations** | Free pollen grant for `paid_only:false` models [grant size unverified] ([docs](https://gen.pollinations.ai/docs/llm.txt)) | flux.1-schnell 0.002 pollen per image ([models](https://gen.pollinations.ai/image/models)) | Sign in at enter.pollinations.ai/keys and create an `sk_` key. Call `GET https://gen.pollinations.ai/image/{prompt}?model=…` |
| **Google Gemini (Nano Banana)** | None for image output | $0.0336–0.134 per image; accepts up to 14 reference images, which suits multi-angle views ([guide](https://ai.google.dev/gemini-api/docs/image-generation)) | Go to aistudio.google.com, then "Get API key", then enable billing |
| **Together AI** | `FLUX.1-schnell-Free` listed ([support](https://support.together.ai/articles/2644979080-what-models-does-together-ai-support)) | — | api.together.ai, then Settings, then API Keys |
| Hugging Face | Free users get no credits; PRO users get $2/month | Pass-through | huggingface.co/settings/tokens |
| fal.ai | Promotional signup credits [unverified] | Charged per successful output | fal.ai/dashboard/keys |
| Replicate | Trial [unverified] | Per second | replicate.com/account/api-tokens |
| OpenAI gpt-image | None | gpt-image-1-mini is the cheapest ([pricing](https://developers.openai.com/api/docs/pricing)) | platform.openai.com/api-keys |
| Stability AI | 25 one-time credits [unverified] | $0.01/credit | platform.stability.ai |
| xAI | None | $0.02–0.05 per image ([models](https://docs.x.ai/docs/models)) | console.x.ai |
| Leonardo | 150 tokens/day on the web app | Pay-as-you-go API | app.leonardo.ai, then API Access |

## C. Hosted image-to-3D

| Route | Multi-view | Cost | Notes |
|---|---|---|---|
| HF Space `microsoft/TRELLIS.2` | No | Free (ZeroGPU quota) | Check the endpoint signature with `Client(...).view_api()` |
| HF Space `tencent/Hunyuan3D-2` | No | Free (quota) | Shape plus texture |
| HF Space `tencent/Hunyuan3D-2mv` | **Yes** (front, left, back; right optional) | Free (quota) | Shape only |
| HF Space `tencent/Hunyuan3D-2.1` | No | Free (quota) | PBR |
| ZeroGPU quotas | — | 2 min/day without a token, 5 min free account, 40 min PRO ([docs](https://huggingface.co/docs/hub/spaces-zerogpu)) | Pass the user's `hf_token`. A free account gets about 2–4 generations per day |
| fal `fal-ai/trellis-2` | No | $0.25–0.35 ([fal](https://fal.ai/models/fal-ai/trellis-2)) | GLB |
| fal `fal-ai/trellis/multi` | **Yes** | $0.02 ([fal](https://fal.ai/models/fal-ai/trellis/multi)) | TRELLIS v1 |
| fal `fal-ai/hunyuan3d/v2/multi-view` | **Yes** (front, back, left) | $0.16 ([fal](https://fal.ai/models/fal-ai/hunyuan3d/v2/multi-view)) | GLB |
| Replicate `firtoz/trellis` | No | ~$0.033 per run ([replicate](https://replicate.com/firtoz/trellis)) | `texture_size`, `mesh_simplify` |
| Tripo direct | **Yes** (2–4) | 30 credits textured | Best native low-poly and quad controls |
| Meshy direct | **Yes** (1–4) | Paid plan required | — |
| Tencent Hunyuan 3D Global | **Yes** (3.1) | 200 free credits | Tencent Cloud account |

## Recheck before shipping

- Tripo free credits and its USD price.
- Rodin face-count presets.
- Pollinations' free grant size.
- The Together free endpoint.
- Exact `gradio_client` signatures for each Space (Spaces pin different Gradio versions).
- Whether the CSM, Luma Genie and Masterpiece X APIs are still live.
