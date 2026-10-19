"""Image and 3D providers (bring your own key) + the key registry the UI renders.

Add a provider: write one function, add it to IMAGE_PROVIDERS / RECONSTRUCTORS with an *_INFO entry,
and (if it needs a new key) a KEYS entry with where/how to get the key.
Request formats: docs/research/04-provider-api-specs.md. Local (offline) backends live in local.py.
"""
import base64
import datetime
import hashlib
import hmac
import json
import mimetypes
import os
import shutil
import time
import urllib.parse
from pathlib import Path

import httpx
import keyring

# ---------- key registry: what each key is for and how to get it ----------
# uses: "image", "3d"; free: short free-tier note or None (paid only)
KEYS = {
    "cloudflare": dict(name="Cloudflare Workers AI", uses=["image"], free="10,000 neurons/day free (~170 images)",
        price="then $0.011 per 1,000 neurons", url="https://dash.cloudflare.com/?to=/:account/ai/workers-ai",
        format="ACCOUNT_ID:TOKEN", steps=[
            "Create a free Cloudflare account and sign in.",
            "Open AI → Workers AI and click 'Use REST API'.",
            "Copy your Account ID shown on that page.",
            "Click 'Create a Workers AI API Token' → 'Create API Token' and copy the token.",
            "Paste here as ACCOUNT_ID:TOKEN (account id, a colon, then the token)."]),
    "pollinations": dict(name="Pollinations", uses=["image"], free="free pollen grant (FLUX costs 0.002 pollen)",
        price="buy pollen for more", url="https://enter.pollinations.ai/keys", format="sk_...", steps=[
            "Sign in at enter.pollinations.ai.", "Open Keys and create a secret key (starts with sk_).", "Paste it here."]),
    "gemini": dict(name="Google Gemini (Nano Banana)", uses=["image"], free=None,
        price="$0.034–0.134 per image; no free image tier", url="https://aistudio.google.com/apikey", format="key", steps=[
            "Sign in to Google AI Studio.", "Click 'Create API key' (import a Google Cloud project first if asked).",
            "Enable billing on the project (image output is paid only).", "Copy the key and paste it here."]),
    "openai": dict(name="OpenAI (GPT Image)", uses=["image"], free=None, price="gpt-image-1-mini from ~$0.005 per image",
        url="https://platform.openai.com/api-keys", format="sk-...", steps=[
            "Sign in at platform.openai.com and add a payment method under Billing.",
            "Open API keys → 'Create new secret key'.", "Copy it (shown once) and paste it here."]),
    "xai": dict(name="xAI (Grok Imagine)", uses=["image"], free=None, price="$0.02–0.05 per image",
        url="https://console.x.ai", format="key", steps=[
            "Sign in at console.x.ai and load credits.", "Open API Keys → create a key.", "Copy it and paste it here."]),
    "together": dict(name="Together AI (FLUX.2)", uses=["image"], free=None, price="FLUX.2 [dev] ~$0.015 per image",
        url="https://api.together.ai/settings/projects/~current/api-keys", format="key", steps=[
            "Sign up at together.ai and add credit.", "Settings → API Keys → 'Create key'.", "Copy it (shown once) and paste it here."]),
    "fal": dict(name="fal.ai", uses=["image", "3d"], free=None,
        price="FLUX ~$0.003/image · TRELLIS.2 $0.05 · Hunyuan multi-view ~$0.16 per model",
        url="https://fal.ai/dashboard/keys", format="key", steps=[
            "Sign up at fal.ai and add credit under Billing.", "Dashboard → Keys → 'Create Key', give it a name.",
            "Copy it (shown once) and paste it here."]),
    "replicate": dict(name="Replicate", uses=["image", "3d"], free=None, price="FLUX schnell $0.003/image · TRELLIS per GPU-second",
        url="https://replicate.com/account/api-tokens", format="r8_...", steps=[
            "Sign in at replicate.com and set up billing.", "Account → API tokens → create a token.", "Copy it and paste it here."]),
    "stability": dict(name="Stability AI", uses=["image", "3d"], free="a few free credits on signup",
        price="image 3 credits · Stable Fast 3D 10 · SPAR3D 4 (≈$0.01/credit)",
        url="https://platform.stability.ai/account/keys", format="sk-...", steps=[
            "Sign in at platform.stability.ai.", "Account → API Keys → copy your key.", "Paste it here."]),
    "hf": dict(name="Hugging Face", uses=["image", "3d"],
        free="free GPU quota for 3D Spaces: 5 min/day (~2 models); PRO $9/month = 40 min/day",
        price="text-to-image via Inference Providers needs bought credits (PRO includes $2/month)",
        url="https://huggingface.co/settings/tokens", format="hf_...", steps=[
            "Create a free account at huggingface.co.", "Settings → Access Tokens → 'Create new token'.",
            "For 3D only, type 'Read' is enough. For images, use 'Fine-grained' and tick 'Make calls to Inference Providers'.",
            "Copy it and paste it here."]),
    "tripo": dict(name="Tripo AI", uses=["3d"], free="free credits on first key (check your dashboard)",
        price="~$0.20–0.40 per textured model", url="https://platform.tripo3d.ai", format="tsk_...", steps=[
            "Sign in at platform.tripo3d.ai.", "Open 'API Keys' → 'Create Key'.", "Copy it (shown once, starts with tsk_) and paste it here."]),
    "meshy": dict(name="Meshy", uses=["3d"], free=None, price="20–35 credits per model (API needs a paid plan)",
        url="https://www.meshy.ai/developers/keys", format="msy_...", steps=[
            "Subscribe to a Meshy plan that includes API access.", "Developers → API Keys → 'Create API Key'.",
            "Copy it (shown once) and paste it here."]),
    "rodin": dict(name="Hyper3D Rodin", uses=["3d"], free=None, price="0.5 credit per model; API needs the Business plan",
        url="https://hyper3d.ai/workspace/api-dashboard", format="key", steps=[
            "Subscribe to the Rodin Business plan.", "Open the API dashboard and create a key.", "Paste it here."]),
    "tencent": dict(name="Tencent Hunyuan 3D", uses=["3d"], free="200 free credits (~5–8 models)",
        price="then ~$0.50–0.70 per model", url="https://console.tencentcloud.com/cam/capi",
        format="SECRET_ID:SECRET_KEY", steps=[
            "Create a Tencent Cloud international account and activate the Hunyuan (HY) 3D service.",
            "Open CAM → API Keys → 'Create Key'. The SecretKey is shown only once.",
            "Paste here as SECRET_ID:SECRET_KEY."]),
    "custom": dict(name="Custom OpenAI-compatible images", uses=["image"], free=None,
        price="whatever your provider charges", url="https://platform.openai.com/docs/api-reference/images",
        format='{"base_url": "https://…/v1", "model": "…", "api_key": "…"}', steps=[
            "Use any service with an OpenAI-style /v1/images/generations endpoint "
            "(e.g. OpenRouter-style gateways, LocalAI, your own server).",
            'Paste a JSON object: {"base_url": "https://host/v1", "model": "model-name", "api_key": "key"}.']),
}


def get_key(name: str, required=True):
    """Env var MESHFORGE_<NAME> wins, then Windows Credential Manager (keyring). Keys never touch project files."""
    val = os.environ.get(f"MESHFORGE_{name.upper()}") or keyring.get_password("meshforge", name)
    if required and not val:
        k = KEYS.get(name, {})
        raise SystemExit(f"No '{name}' key. Add it in the app (API keys) or run: meshforge key set {name}\n"
                         f"  Get one: {k.get('url', '')}")
    return val


def set_key(name: str, value: str):
    keyring.set_password("meshforge", name, value)


def delete_key(name: str):
    try:
        keyring.delete_password("meshforge", name)
    except keyring.errors.PasswordDeleteError:
        pass


# ---------- prompt shaping ----------

def view_prompt(description: str, view: str) -> str:
    """One centred object, plain background, flat even light (so lighting is not baked into the texture)."""
    angle = {"front": "front view", "back": "back view, seen from behind", "left": "left side view, profile",
             "right": "right side view, profile", "top": "top-down view"}[view]
    return (f"{description}. Single object, {angle}, full object visible and centred, orthographic product shot, "
            "plain pure white background, isolated, no cast shadow, soft even studio lighting, no text, highly detailed, "
            "sharp focus, 3D asset reference")


def _ok(r: httpx.Response) -> httpx.Response:
    if r.is_error:
        raise RuntimeError(f"{r.request.url.host} {r.status_code}: {r.text[:300]}")
    return r


def _b64(data: str) -> bytes:
    return base64.b64decode(data.split(",", 1)[1] if data.startswith("data:") else data)


# ---------- image generation: fn(prompt, out_path, seed) ----------

def img_cloudflare(prompt, out, seed):
    account, token = get_key("cloudflare").split(":", 1)
    r = _ok(httpx.post(f"https://api.cloudflare.com/client/v4/accounts/{account.strip()}/ai/run/@cf/black-forest-labs/flux-1-schnell",
                       headers={"Authorization": f"Bearer {token.strip()}"},
                       json={"prompt": prompt[:2048], "steps": 8, "seed": seed}, timeout=120))
    out.write_bytes(_b64(r.json()["result"]["image"]))


def img_pollinations(prompt, out, seed):
    r = _ok(httpx.get(f"https://gen.pollinations.ai/image/{urllib.parse.quote(prompt)}",
                      params={"model": "flux", "width": 1024, "height": 1024, "seed": seed},
                      headers={"Authorization": f"Bearer {get_key('pollinations')}"}, timeout=180, follow_redirects=True))
    out.write_bytes(r.content)


def img_gemini(prompt, out, seed):
    r = _ok(httpx.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-image:generateContent",
                       headers={"x-goog-api-key": get_key("gemini")}, timeout=180, json={
                           "contents": [{"parts": [{"text": prompt}]}],
                           "generationConfig": {"responseModalities": ["IMAGE"],
                                                "imageConfig": {"aspectRatio": "1:1", "imageSize": "1K"}}}))
    parts = r.json()["candidates"][0]["content"]["parts"]
    data = next((p["inlineData"]["data"] for p in parts if "inlineData" in p), None)
    if not data:
        raise RuntimeError("Gemini returned no image (prompt may have been refused)")
    out.write_bytes(_b64(data))


def _openai_images(base, key, body, out, timeout=180):
    r = _ok(httpx.post(f"{base.rstrip('/')}/images/generations", headers={"Authorization": f"Bearer {key}"},
                       json=body, timeout=timeout))
    d = r.json()["data"][0]
    out.write_bytes(_b64(d["b64_json"]) if d.get("b64_json") else
                    _ok(httpx.get(d["url"], timeout=120, follow_redirects=True)).content)


def img_openai(prompt, out, seed):
    _openai_images("https://api.openai.com/v1", get_key("openai"),
                   {"model": "gpt-image-1-mini", "prompt": prompt, "size": "1024x1024", "quality": "medium", "n": 1}, out)


def img_xai(prompt, out, seed):
    _openai_images("https://api.x.ai/v1", get_key("xai"), {"model": "grok-imagine-image", "prompt": prompt, "n": 1,
                                                          "response_format": "b64_json", "aspect_ratio": "1:1"}, out)


def img_together(prompt, out, seed):
    _openai_images("https://api.together.ai/v1", get_key("together"),
                   {"model": "black-forest-labs/FLUX.2-dev", "prompt": prompt, "width": 1024, "height": 1024,
                    "steps": 20, "seed": seed, "n": 1, "response_format": "base64"}, out)


def img_hf(prompt, out, seed):
    _openai_images("https://router.huggingface.co/nscale/v1", get_key("hf"),
                   {"model": "black-forest-labs/FLUX.1-schnell", "prompt": prompt, "response_format": "b64_json"}, out)


def img_custom(prompt, out, seed):
    try:
        c = json.loads(get_key("custom"))
    except ValueError:
        raise RuntimeError('Custom key must be JSON: {"base_url": "...", "model": "...", "api_key": "..."}')
    _openai_images(c["base_url"], c.get("api_key", ""), {"model": c["model"], "prompt": prompt, "n": 1,
                                                         "size": "1024x1024", "response_format": "b64_json"}, out)


def img_fal(prompt, out, seed):
    res = _fal("fal-ai/flux/schnell", {"prompt": prompt, "image_size": "square_hd", "num_inference_steps": 4,
                                       "seed": seed, "num_images": 1, "output_format": "png"})
    out.write_bytes(_ok(httpx.get(res["images"][0]["url"], timeout=120, follow_redirects=True)).content)


def img_replicate(prompt, out, seed):
    p = _replicate("models/black-forest-labs/flux-schnell/predictions",
                   {"input": {"prompt": prompt, "aspect_ratio": "1:1", "num_outputs": 1, "seed": seed,
                              "output_format": "png", "megapixels": "1"}})
    out.write_bytes(_replicate_download(p["output"][0]))


def img_stability(prompt, out, seed):
    r = _ok(httpx.post("https://api.stability.ai/v2beta/stable-image/generate/core",
                       headers={"Authorization": f"Bearer {get_key('stability')}", "Accept": "image/*"},
                       files={"none": ""}, data={"prompt": prompt, "aspect_ratio": "1:1", "seed": seed % 4294967294,
                                                 "output_format": "png"}, timeout=180))
    out.write_bytes(r.content)


IMAGE_PROVIDERS = {
    "cloudflare": img_cloudflare, "pollinations": img_pollinations, "gemini": img_gemini, "openai": img_openai,
    "xai": img_xai, "together": img_together, "fal": img_fal, "replicate": img_replicate, "stability": img_stability,
    "hf": img_hf, "custom": img_custom,
}
IMAGE_INFO = {  # label shown in the UI; key = KEYS id (None = no key)
    "cloudflare": dict(label="Cloudflare FLUX.1 schnell (free daily)", key="cloudflare", free=True),
    "pollinations": dict(label="Pollinations FLUX (free grant)", key="pollinations", free=True),
    "gemini": dict(label="Google Gemini Nano Banana 2", key="gemini"),
    "openai": dict(label="OpenAI gpt-image-1-mini", key="openai"),
    "xai": dict(label="xAI Grok Imagine", key="xai"),
    "together": dict(label="Together FLUX.2 [dev]", key="together"),
    "fal": dict(label="fal FLUX.1 schnell", key="fal"),
    "replicate": dict(label="Replicate FLUX schnell", key="replicate"),
    "stability": dict(label="Stability Stable Image Core", key="stability"),
    "hf": dict(label="Hugging Face FLUX.1 schnell", key="hf"),
    "custom": dict(label="Custom OpenAI-compatible", key="custom"),
}


# ---------- 3D: fn(views {view: Path}, out_path, opts) writes a raw GLB ----------

def _gradio(space):
    from gradio_client import Client  # heavy import, only when used
    return Client(space, token=get_key("hf", required=False), verbose=False)


def _front(views):
    return views.get("front") or next(iter(views.values()))


def rec_hf_trellis2(views, out, opts):
    from gradio_client import handle_file
    c = _gradio("microsoft/TRELLIS.2")
    c.predict(api_name="/start_session")
    img = c.predict(handle_file(str(_front(views))), api_name="/preprocess_image")
    c.predict(handle_file(img["path"] if isinstance(img, dict) else img), opts.get("seed", 0),
              str(opts.get("resolution", 1024)), api_name="/image_to_3d")
    glb, _ = c.predict(opts.get("raw_faces", 500000), opts.get("texture", 2048), api_name="/extract_glb")
    shutil.copy(glb, out)


def rec_hf_hunyuan_mv(views, out, opts):
    from gradio_client import handle_file
    f = lambda v: handle_file(str(views[v])) if v in views else None
    c = _gradio("tencent/Hunyuan3D-2mv")
    res = c.predict(None, None, f("front"), f("back"), f("left"), f("right"), 30, 5.0, opts.get("seed", 1234) % 10_000_000,
                    opts.get("octree", 380), True, 8000, False, api_name="/generation_all")
    textured = res[1] if res[1] else res[0]
    shutil.copy(textured["value"] if isinstance(textured, dict) else textured, out)


def _data_uri(p: Path) -> str:
    return f"data:{mimetypes.guess_type(p.name)[0] or 'image/png'};base64,{base64.b64encode(p.read_bytes()).decode()}"


def _download(url, out, headers=None):
    out.write_bytes(_ok(httpx.get(url, headers=headers, timeout=600, follow_redirects=True)).content)


def _fal(model: str, payload: dict) -> dict:
    """fal queue: submit, poll the returned status_url, fetch the returned response_url."""
    h = {"Authorization": f"Key {get_key('fal')}"}
    job = _ok(httpx.post(f"https://queue.fal.run/{model}", headers=h, json=payload, timeout=120)).json()
    while (s := _ok(httpx.get(job["status_url"], headers=h, timeout=30)).json())["status"] != "COMPLETED":
        time.sleep(3)
    res = _ok(httpx.get(job["response_url"], headers=h, timeout=60)).json()
    if s.get("error") or res.get("error"):
        raise RuntimeError(f"fal {model}: {s.get('error') or res.get('error')}")
    return res


def rec_fal_trellis2(views, out, opts):
    res = _fal("fal-ai/trellis-2", {"image_url": _data_uri(_front(views)), "seed": opts.get("seed", 0) % 2**31,
                                    "texture_size": str(min(opts.get("texture", 2048), 4096)),
                                    "decimation_target": opts.get("raw_faces", 500000)})
    _download(res["model_glb"]["url"], out)


def rec_fal_trellis_multi(views, out, opts):
    res = _fal("fal-ai/trellis/multi", {"image_urls": [_data_uri(p) for p in views.values()],
                                        "texture_size": "2048", "seed": opts.get("seed", 0) % 2**31})
    _download(res["model_mesh"]["url"], out)


def rec_fal_hunyuan_mv(views, out, opts):
    missing = {"front", "back", "left"} - set(views)
    if missing:
        raise RuntimeError(f"Hunyuan multi-view needs front, back and left images; missing {sorted(missing)}")
    res = _fal("fal-ai/hunyuan3d/v2/multi-view", {f"{v}_image_url": _data_uri(views[v]) for v in ("front", "back", "left")}
               | {"textured_mesh": True, "seed": opts.get("seed", 0) % 2**31})
    _download(res["model_mesh"]["url"], out)


def _tripo(path, **kw):
    r = _ok(httpx.request(kw.pop("method", "POST"), f"https://openapi.tripo3d.ai/v3/{path}",
                          headers={"Authorization": f"Bearer {get_key('tripo')}"}, timeout=120, **kw)).json()
    if r.get("code") != 0:
        raise RuntimeError(f"Tripo: {r.get('message')} {r.get('suggestion', '')}")
    return r["data"]


def _tripo_run(endpoint, body, out):
    task = _tripo(f"generation/{endpoint}", json=body | {"model": "v3.1-20260211", "texture": True, "pbr": True})["task_id"]
    while (t := _tripo(f"tasks/{task}", method="GET"))["status"] in ("queued", "running"):
        time.sleep(4)
    if t["status"] != "success":
        raise RuntimeError(f"Tripo task {t['status']}: {t.get('error_message', '')}")
    _download(t["output"]["model_url"], out)


def _tripo_upload(p: Path) -> str:
    with p.open("rb") as fh:
        return _tripo("files", files={"file": (p.name, fh, mimetypes.guess_type(p.name)[0] or "image/png")})["file_token"]


def rec_tripo(views, out, opts):
    _tripo_run("image-to-model", {"input": _tripo_upload(_front(views))}, out)


def rec_tripo_multi(views, out, opts):
    if "front" not in views or len(views) < 2:
        raise RuntimeError("Tripo multi-view needs a front image and at least one more view")
    _tripo_run("multiview-to-model", {"inputs": [{v: _tripo_upload(views[v])} for v in ("front", "left", "back", "right")
                                                 if v in views]}, out)


def _meshy(endpoint, body, out):
    h = {"Authorization": f"Bearer {get_key('meshy')}"}
    base = f"https://api.meshy.ai/openapi/v1/{endpoint}"
    tid = _ok(httpx.post(base, headers=h, json=body | {"ai_model": "latest", "should_texture": True, "enable_pbr": True},
                         timeout=120)).json()["result"]
    while (t := _ok(httpx.get(f"{base}/{tid}", headers=h, timeout=30)).json())["status"] in ("PENDING", "IN_PROGRESS"):
        time.sleep(5)
    if t["status"] != "SUCCEEDED" or "glb" not in t.get("model_urls", {}):
        raise RuntimeError(f"Meshy task {t['status']}: {t.get('task_error', {}).get('message', '')}")
    _download(t["model_urls"]["glb"], out)


def rec_meshy(views, out, opts):
    _meshy("image-to-3d", {"image_url": _data_uri(_front(views))}, out)


def rec_meshy_multi(views, out, opts):
    _meshy("multi-image-to-3d", {"image_urls": [_data_uri(p) for p in list(views.values())[:4]]}, out)


def rec_rodin(views, out, opts):
    h = {"Authorization": f"Bearer {get_key('rodin')}"}
    files = [("images", (p.name, p.read_bytes(), mimetypes.guess_type(p.name)[0] or "image/png"))
             for p in [_front(views)] + [p for v, p in views.items() if p != _front(views)][:4]]
    job = _ok(httpx.post("https://api.hyper3d.com/api/v2/rodin", headers=h, files=files, timeout=180, data={
        "tier": "Gen-2.5-Medium", "geometry_file_format": "glb", "mesh_mode": "Raw", "quality": "medium"})).json()
    if job.get("error"):
        raise RuntimeError(f"Rodin: {job['error']}")
    while True:
        jobs = _ok(httpx.post("https://api.hyper3d.com/api/v2/status", headers=h, timeout=30,
                              json={"subscription_key": job["jobs"]["subscription_key"]})).json()["jobs"]
        if any(j["status"] == "Failed" for j in jobs):
            raise RuntimeError("Rodin generation failed")
        if all(j["status"] == "Done" for j in jobs):
            break
        time.sleep(5)
    files = _ok(httpx.post("https://api.hyper3d.com/api/v2/download", headers=h, timeout=30,
                           json={"task_uuid": job["uuid"]})).json()["list"]
    _download(next(f["url"] for f in files if f["name"].lower().endswith(".glb")), out)


def _tencent(action, body):
    """Tencent Cloud API v3 TC3-HMAC-SHA256 signing (stdlib only)."""
    sid, skey = get_key("tencent").split(":", 1)
    host, service, ts = "hunyuan.intl.tencentcloudapi.com", "hunyuan", int(time.time())
    date = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%d")
    payload = json.dumps(body)
    ct = "application/json; charset=utf-8"
    canonical = (f"POST\n/\n\ncontent-type:{ct}\nhost:{host}\nx-tc-action:{action.lower()}\n\n"
                 f"content-type;host;x-tc-action\n{hashlib.sha256(payload.encode()).hexdigest()}")
    scope = f"{date}/{service}/tc3_request"
    to_sign = f"TC3-HMAC-SHA256\n{ts}\n{scope}\n{hashlib.sha256(canonical.encode()).hexdigest()}"
    k = hmac.new(("TC3" + skey.strip()).encode(), date.encode(), hashlib.sha256).digest()
    k = hmac.new(k, service.encode(), hashlib.sha256).digest()
    k = hmac.new(k, b"tc3_request", hashlib.sha256).digest()
    sig = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
    r = _ok(httpx.post(f"https://{host}", content=payload, timeout=120, headers={
        "Authorization": f"TC3-HMAC-SHA256 Credential={sid.strip()}/{scope}, SignedHeaders=content-type;host;x-tc-action, Signature={sig}",
        "Content-Type": ct, "Host": host, "X-TC-Action": action, "X-TC-Version": "2023-09-01",
        "X-TC-Timestamp": str(ts), "X-TC-Region": "ap-singapore"})).json()["Response"]
    if "Error" in r:
        raise RuntimeError(f"Tencent {r['Error']['Code']}: {r['Error']['Message']}")
    return r


def rec_tencent(views, out, opts):
    b64 = lambda p: base64.b64encode(p.read_bytes()).decode()
    body = {"Model": "3.1", "ImageBase64": b64(_front(views)), "EnablePBR": True}
    extra = [{"ViewType": v, "ViewImageBase64": b64(p)} for v, p in views.items() if v in ("back", "left", "right")]
    if extra:
        body["MultiViewImages"] = extra
    job = _tencent("SubmitHunyuanTo3DProJob", body)["JobId"]
    while (r := _tencent("QueryHunyuanTo3DProJob", {"JobId": job}))["Status"] in ("WAIT", "RUN"):
        time.sleep(5)
    if r["Status"] != "DONE":
        raise RuntimeError(f"Tencent job failed: {r.get('ErrorMessage', '')}")
    urls = [f["Url"] for f in r.get("ResultFile3Ds", [])]
    glb = next((u for u in urls if urllib.parse.urlparse(u).path.lower().endswith(".glb")), None)
    if not glb:
        raise RuntimeError(f"Tencent returned no GLB: {urls}")
    _download(glb, out)


def _replicate(path, body):
    h = {"Authorization": f"Bearer {get_key('replicate')}", "Prefer": "wait=60"}
    p = _ok(httpx.post(f"https://api.replicate.com/v1/{path}", headers=h, json=body, timeout=120)).json()
    while p["status"] in ("starting", "processing"):
        time.sleep(4)
        p = _ok(httpx.get(p["urls"]["get"], headers=h, timeout=30)).json()
    if p["status"] != "succeeded":
        raise RuntimeError(f"Replicate {p['status']}: {p.get('error')}")
    return p


def _replicate_download(url):
    return _ok(httpx.get(url, headers={"Authorization": f"Bearer {get_key('replicate')}"}, timeout=600,
                         follow_redirects=True)).content


def rec_replicate_trellis(views, out, opts):
    p = _replicate("predictions", {"version": "firtoz/trellis:e8f6c45206993f297372f5436b90350817bd9b4a0d52d2a76df50c1c8afa2b3c",
                                   "input": {"images": [_data_uri(p) for p in views.values()], "generate_model": True,
                                             "texture_size": 2048, "seed": opts.get("seed", 0) % 2**31,
                                             "randomize_seed": False}})
    out.write_bytes(_replicate_download(p["output"]["model_file"]))


def _stability_3d(endpoint, views, out, data):
    p = _front(views)
    r = _ok(httpx.post(f"https://api.stability.ai/v2beta/3d/{endpoint}", timeout=300,
                       headers={"Authorization": f"Bearer {get_key('stability')}"},
                       files={"image": (p.name, p.read_bytes(), mimetypes.guess_type(p.name)[0] or "image/png")}, data=data))
    out.write_bytes(r.content)


def rec_stability_sf3d(views, out, opts):
    _stability_3d("stable-fast-3d", views, out, {"texture_resolution": "2048", "remesh": "none"})


def rec_stability_spar3d(views, out, opts):
    _stability_3d("stable-point-aware-3d", views, out, {"texture_resolution": "2048", "remesh": "none",
                                                        "seed": str(opts.get("seed", 0) % 4294967294)})


RECONSTRUCTORS = {
    "hf-trellis2": rec_hf_trellis2, "hf-hunyuan-mv": rec_hf_hunyuan_mv,
    "fal-trellis2": rec_fal_trellis2, "fal-trellis-multi": rec_fal_trellis_multi, "fal-hunyuan-mv": rec_fal_hunyuan_mv,
    "tripo": rec_tripo, "tripo-multi": rec_tripo_multi, "meshy": rec_meshy, "meshy-multi": rec_meshy_multi,
    "rodin": rec_rodin, "tencent": rec_tencent, "replicate-trellis": rec_replicate_trellis,
    "stability-sf3d": rec_stability_sf3d, "stability-spar3d": rec_stability_spar3d,
}
# views: how many images it uses; note: one line for the UI
RECON_INFO = {
    "hf-trellis2": dict(label="TRELLIS.2 · Hugging Face (free quota)", key="hf", views="1", free=True,
                        note="Best open model. Free ~2 models/day; a token is optional but raises the quota."),
    "hf-hunyuan-mv": dict(label="Hunyuan3D-2mv · Hugging Face (free quota)", key="hf", views="1-4", free=True,
                          note="Uses front/back/left/right. Tencent license excludes EU/UK/South Korea."),
    "fal-trellis2": dict(label="TRELLIS.2 · fal", key="fal", views="1", note="$0.05 per model, no daily limit."),
    "fal-trellis-multi": dict(label="TRELLIS multi-image · fal", key="fal", views="1-4", note="$0.02 per model."),
    "fal-hunyuan-mv": dict(label="Hunyuan3D-2 multi-view · fal", key="fal", views="3-4", note="Needs front, back, left."),
    "tripo": dict(label="Tripo v3.1", key="tripo", views="1", note="Strong commercial quality, PBR."),
    "tripo-multi": dict(label="Tripo v3.1 multi-view", key="tripo", views="2-4", note="Front plus left/back/right."),
    "meshy": dict(label="Meshy 7.1", key="meshy", views="1", note="Commercial, PBR. API needs a paid plan."),
    "meshy-multi": dict(label="Meshy 7.1 multi-image", key="meshy", views="1-4", note="Up to 4 views."),
    "rodin": dict(label="Hyper3D Rodin Gen-2.5", key="rodin", views="1-5", note="Top-tier textures. Business plan."),
    "tencent": dict(label="Tencent Hunyuan 3D 3.1", key="tencent", views="1-4", note="200 free credits, then paid."),
    "replicate-trellis": dict(label="TRELLIS · Replicate", key="replicate", views="1-4", note="Pay per GPU-second."),
    "stability-sf3d": dict(label="Stable Fast 3D · Stability", key="stability", views="1", note="Very fast, simpler shapes."),
    "stability-spar3d": dict(label="SPAR3D · Stability", key="stability", views="1", note="Fast, better back sides."),
}

from . import local  # noqa: E402,F401  registers offline backends into the dicts above
