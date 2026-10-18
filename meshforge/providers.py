"""Image and 3D providers. Each is one function; add a provider by adding a function + a dict entry."""
import base64
import mimetypes
import os
import shutil
import time
import urllib.parse
from pathlib import Path

import httpx
import keyring

KEY_HELP = {
    "cloudflare": "Free: 10,000 neurons/day (~170 FLUX images). dash.cloudflare.com -> copy Account ID; "
                  "My Profile -> API Tokens -> Create Token -> 'Workers AI' template. Store as ACCOUNT_ID:TOKEN.",
    "pollinations": "Free grant of pollen. enter.pollinations.ai/keys -> create an sk_ key.",
    "hf": "Optional but raises the free ZeroGPU quota from 2 to 5 min/day. "
          "huggingface.co/settings/tokens -> New token (read).",
    "fal": "Paid per generation (~$0.02-0.35). fal.ai/dashboard/keys.",
}


def get_key(name: str, required=True):
    """Env var MESHFORGE_<NAME> wins, then Windows Credential Manager (keyring)."""
    val = os.environ.get(f"MESHFORGE_{name.upper()}") or keyring.get_password("meshforge", name)
    if required and not val:
        raise SystemExit(f"No '{name}' key. Run: meshforge key set {name}\n  {KEY_HELP.get(name, '')}")
    return val


def set_key(name: str, value: str):
    keyring.set_password("meshforge", name, value)


# ---------- prompt shaping ----------

def view_prompt(description: str, view: str) -> str:
    """Prompt that gives reconstruction models what they like: one centred object, plain background,
    flat even light (so lighting is not baked into the texture)."""
    angle = {"front": "front view", "back": "back view, seen from behind", "left": "left side view, profile",
             "right": "right side view, profile", "top": "top-down view"}[view]
    return (f"{description}. Single object, {angle}, full object visible and centred, orthographic product shot, "
            "plain pure white background, soft even studio lighting, no harsh shadows, no text, highly detailed, "
            "sharp focus, 3D asset reference")


# ---------- image generation ----------

def img_cloudflare(prompt: str, out: Path, seed: int):
    account, token = get_key("cloudflare").split(":", 1)
    r = httpx.post(f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/black-forest-labs/flux-1-schnell",
                   headers={"Authorization": f"Bearer {token}"}, json={"prompt": prompt, "steps": 8, "seed": seed},
                   timeout=120)
    r.raise_for_status()
    out.write_bytes(base64.b64decode(r.json()["result"]["image"]))


def img_pollinations(prompt: str, out: Path, seed: int):
    r = httpx.get(f"https://gen.pollinations.ai/image/{urllib.parse.quote(prompt)}",
                  params={"model": "flux", "width": 1024, "height": 1024, "seed": seed, "nologo": "true"},
                  headers={"Authorization": f"Bearer {get_key('pollinations')}"}, timeout=180, follow_redirects=True)
    r.raise_for_status()
    out.write_bytes(r.content)


IMAGE_PROVIDERS = {"cloudflare": img_cloudflare, "pollinations": img_pollinations}


# ---------- 3D reconstruction ----------
# Each takes (views: {view: Path}, out: Path, opts: dict) and writes a raw textured GLB to `out`.

def _gradio(space):
    from gradio_client import Client  # heavy import, only when used
    return Client(space, token=get_key("hf", required=False), verbose=False)


def rec_hf_trellis2(views, out, opts):
    """microsoft/TRELLIS.2 Space: single image, PBR texture, best open quality. Free ZeroGPU quota."""
    from gradio_client import handle_file
    c = _gradio("microsoft/TRELLIS.2")
    c.predict(api_name="/start_session")
    img = c.predict(handle_file(str(views.get("front") or next(iter(views.values())))), api_name="/preprocess_image")
    c.predict(handle_file(img["path"] if isinstance(img, dict) else img), opts.get("seed", 0),
              str(opts.get("resolution", 1024)), api_name="/image_to_3d")
    glb, _ = c.predict(opts.get("raw_faces", 500000), opts.get("texture", 2048), api_name="/extract_glb")
    shutil.copy(glb, out)


def rec_hf_hunyuan_mv(views, out, opts):
    """tencent/Hunyuan3D-2mv Space: front/back/left/right conditioning. Note the Tencent license excludes EU/UK/KR."""
    from gradio_client import handle_file
    f = lambda v: handle_file(str(views[v])) if v in views else None
    c = _gradio("tencent/Hunyuan3D-2mv")
    res = c.predict(None, None, f("front"), f("back"), f("left"), f("right"), 30, 5.0, opts.get("seed", 1234),
                    opts.get("octree", 380), True, 8000, False, api_name="/generation_all")
    textured = res[1] if res[1] else res[0]
    shutil.copy(textured["value"] if isinstance(textured, dict) else textured, out)


def _data_uri(p: Path) -> str:
    return f"data:{mimetypes.guess_type(p.name)[0] or 'image/png'};base64,{base64.b64encode(p.read_bytes()).decode()}"


def _find_glb_url(obj):
    if isinstance(obj, dict):
        if isinstance(obj.get("url"), str) and (".glb" in obj["url"] or obj.get("content_type") == "model/gltf-binary"):
            return obj["url"]
        obj = list(obj.values())
    if isinstance(obj, list):
        for v in obj:
            if u := _find_glb_url(v):
                return u


def _fal(model: str, payload: dict, out: Path):
    h = {"Authorization": f"Key {get_key('fal')}"}
    job = httpx.post(f"https://queue.fal.run/{model}", headers=h, json=payload, timeout=60).raise_for_status().json()
    while (s := httpx.get(job["status_url"], headers=h, timeout=30).raise_for_status().json())["status"] != "COMPLETED":
        if s["status"] not in ("IN_QUEUE", "IN_PROGRESS"):
            raise RuntimeError(f"fal {model}: {s}")
        time.sleep(3)
    url = _find_glb_url(httpx.get(job["response_url"], headers=h, timeout=60).raise_for_status().json())
    if not url:
        raise RuntimeError(f"fal {model}: no GLB in response")
    out.write_bytes(httpx.get(url, timeout=300, follow_redirects=True).raise_for_status().content)


def rec_fal_trellis2(views, out, opts):
    _fal("fal-ai/trellis-2", {"image_url": _data_uri(views.get("front") or next(iter(views.values())))}, out)


def rec_fal_trellis_multi(views, out, opts):
    _fal("fal-ai/trellis/multi", {"image_urls": [_data_uri(p) for p in views.values()]}, out)


def rec_fal_hunyuan_mv(views, out, opts):
    missing = {"front", "back", "left"} - set(views)
    if missing:
        raise RuntimeError(f"fal hunyuan multi-view needs front, back and left; missing {sorted(missing)}")
    _fal("fal-ai/hunyuan3d/v2/multi-view",
         {f"{v}_image_url": _data_uri(views[v]) for v in ("front", "back", "left")} | {"textured_mesh": True}, out)


RECONSTRUCTORS = {
    "hf-trellis2": rec_hf_trellis2,
    "hf-hunyuan-mv": rec_hf_hunyuan_mv,
    "fal-trellis2": rec_fal_trellis2,
    "fal-trellis-multi": rec_fal_trellis_multi,
    "fal-hunyuan-mv": rec_fal_hunyuan_mv,
}
