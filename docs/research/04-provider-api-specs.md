# Provider API specs (verified against official docs, 2026-10-19)

Reference for `meshforge/providers.py`.

**Tags used below:**
- **[doc]**: read from official docs.
- **[3p]**: third-party source.
- **AMBIGUOUS**: the docs disagree or are silent.

**Recent breaking changes:**
- Tripo's v2 API shuts down on 2026-10-31 (use v3).
- Together dropped FLUX.1-schnell-Free.
- Hugging Face free accounts get no Inference credits.
- Gemini has no free image tier.

## Image generation

| Provider | Call | Auth | Result | Price / free |
|---|---|---|---|---|
| Cloudflare | `POST api.cloudflare.com/client/v4/accounts/{id}/ai/run/@cf/black-forest-labs/flux-1-schnell` `{prompt, steps≤8, seed}` | Bearer token | `result.image` (b64) | **10,000 neurons/day free** |
| Pollinations | `GET gen.pollinations.ai/image/{prompt}?model=flux&width&height&seed` | Bearer `sk_` | raw bytes | free pollen grant; flux 0.002 pollen |
| Google Gemini | `POST generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-image:generateContent` `{contents, generationConfig:{responseModalities:["IMAGE"], imageConfig:{aspectRatio:"1:1", imageSize:"1K"}}}` | `x-goog-api-key` | first part with `inlineData.data` | no free tier; $0.034–0.134 per image |
| OpenAI | `POST api.openai.com/v1/images/generations` `{model:"gpt-image-1-mini", prompt, size:"1024x1024", quality}`. **No `response_format`, no seed** | Bearer | `data[0].b64_json` | gpt-image-1-mini $0.005 (low) |
| xAI | `POST api.x.ai/v1/images/generations` `{model:"grok-imagine-image", prompt, response_format:"b64_json", aspect_ratio:"1:1"}` | Bearer | `data[0].b64_json` | $0.02–0.05 |
| Together | `POST api.together.ai/v1/images/generations` `{model:"black-forest-labs/FLUX.2-dev", width, height, steps, seed, response_format:"base64"}` | Bearer | `data[0].b64_json` | $0.0154 |
| fal FLUX | queue `POST queue.fal.run/fal-ai/flux/schnell` → `status_url` / `response_url` (use the returned URLs) | `Key <key>` | `images[0].url` | $0.003/MP |
| Replicate | `POST api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions` + `Prefer: wait` | Bearer `r8_` | `output[0]` URL (download with auth) | $0.003 |
| Stability | `POST api.stability.ai/v2beta/stable-image/generate/core`, multipart, `Accept: image/*` | Bearer | raw bytes | 3 credits ($0.03) |
| HF Inference (nscale) | `POST router.huggingface.co/nscale/v1/images/generations` `{model:"black-forest-labs/FLUX.1-schnell", response_format:"b64_json"}` | Bearer `hf_` | `data[0].b64_json` | buy credits; PRO $2/month included |
| Leonardo | v2 async; the polling endpoint is not documented (AMBIGUOUS) | Bearer | — | **not integrated yet** |

**OpenAI-compatible** (`{base}/images/generations` → `data[0].b64_json`): OpenAI, xAI, Pollinations (`gen.pollinations.ai/v1`), HF nscale. Together is partly compatible. A generic "custom" provider covers these and similar services.

## 3D generation

| Provider | Flow | Result | Price |
|---|---|---|---|
| HF Space TRELLIS.2 / Hunyuan3D-2mv | `gradio_client` | file | free ZeroGPU quota (5 min/day with a token) |
| fal `trellis-2` | queue, `{image_url}` | `model_glb.url` | $0.05 |
| fal `trellis/multi` | queue, `{image_urls}` | `model_mesh.url` | $0.02 |
| fal `hunyuan3d/v2/multi-view` | queue, `{front/back/left_image_url, textured_mesh:true}` | `model_mesh.url` | $0.16 (×3 textured, AMBIGUOUS) |
| Tripo v3 | `POST openapi.tripo3d.ai/v3/files` (multipart) → `file_token`; `POST /v3/generation/image-to-model {input, model:"v3.1-20260211", texture, pbr}` or `/multiview-to-model {inputs:[{front},{left},{back},{right}]}`; poll `GET /v3/tasks/{id}` | `data.output.model_url` | credits (~$0.01 each) |
| Meshy | `POST api.meshy.ai/openapi/v1/image-to-3d {image_url (data URI ok), ai_model:"latest", should_texture, enable_pbr}` or `/multi-image-to-3d {image_urls}`; poll `GET …/{id}` | `model_urls.glb` | 20–35 credits |
| Hyper3D Rodin | multipart `POST api.hyper3d.com/api/v2/rodin` (images[], tier) → `POST /status {subscription_key}` → `POST /download {task_uuid}` | list item ending `.glb` | Business plan needed |
| Tencent Hunyuan 3D (intl) | TC3-HMAC-SHA256 signed `SubmitHunyuanTo3DProJob` / `QueryHunyuanTo3DProJob` at `hunyuan.intl.tencentcloudapi.com`, region `ap-singapore` | `ResultFile3Ds[].Url` | 200 free credits; ~$0.50–0.70/model |
| Replicate `firtoz/trellis` | `POST /v1/predictions {version, input:{images, generate_model:true}}` | `output.model_file` | per GPU-second |
| Stability SF3D / SPAR3D | multipart `POST api.stability.ai/v2beta/3d/stable-fast-3d` (or `stable-point-aware-3d`) | raw GLB | 10 / 4 credits |

Full detail, including key-creation steps, is in the provider registry (`KEYS`) in `meshforge/providers.py`.
