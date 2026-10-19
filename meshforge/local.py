"""Offline models: hardware detection, a catalog with per-PC recommendations, a download manager,
and the local backends (registered into providers.IMAGE_PROVIDERS / RECONSTRUCTORS).

Three runtimes, all under MESHFORGE_HOME (default %LOCALAPPDATA%\\MeshForge):
  ollama   - coding LLMs that write Blender scripts (Ollama app, http://localhost:11434)
  sdcpp    - stable-diffusion.cpp sd-cli.exe for local images (no PyTorch)
  torch    - a private venv with PyTorch for TripoSR / Hunyuan3D-2mini
Research + sources: docs/research/05-local-models.md
"""
import ast
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import zipfile
from pathlib import Path

import httpx

from . import parametric, providers

HOME = Path(os.environ.get("MESHFORGE_HOME", Path(os.environ.get("LOCALAPPDATA", Path.home())) / "MeshForge"))
MODELS = HOME / "models"
OLLAMA = "http://127.0.0.1:11434"
ROOT = Path(__file__).resolve().parent.parent
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TRANSFORMERS_PIN = "transformers==4.48.3"  # shared torch venv: TripoSR + Hunyuan3D both need 4.x (5.x breaks checkpoints)

# kind: llm (writes Blender code) | llm-mesh (writes mesh text) | image | 3d (image -> 3D)
# vram: GB for comfortable GPU use; cpu: also usable without a GPU (slower); ram: GB system memory needed
CATALOG = [
    dict(id="qwen2.5-coder:1.5b", kind="llm", name="Qwen2.5-Coder 1.5B", size=1.0, vram=2, ram=4, cpu=True, tier=1,
         license="Apache-2.0", note="Tiny and fast. Simple props only."),
    dict(id="qwen3.5:2b", kind="llm", name="Qwen3.5 2B", size=3.0, vram=4, ram=6, cpu=True, tier=2,
         license="Apache-2.0", note="Small general model, decent code."),
    dict(id="qwen3.5:4b", kind="llm", name="Qwen3.5 4B", size=3.5, vram=4, ram=8, cpu=True, tier=3,
         license="Apache-2.0", note="Good balance for 4–6 GB GPUs."),
    dict(id="qwen2.5-coder:7b", kind="llm", name="Qwen2.5-Coder 7B", size=4.7, vram=6, ram=16, cpu=True, tier=4,
         license="Apache-2.0", note="Strong coder. Runs on 4 GB GPUs with RAM offload (slower)."),
    dict(id="qwen3.5:9b", kind="llm", name="Qwen3.5 9B", size=7.0, vram=8, ram=16, cpu=False, tier=5,
         license="Apache-2.0", note="Better shapes and proportions."),
    dict(id="qwen2.5-coder:14b", kind="llm", name="Qwen2.5-Coder 14B", size=9.0, vram=12, ram=16, cpu=False, tier=6,
         license="Apache-2.0", note="High quality scripts."),
    dict(id="gpt-oss:20b", kind="llm", name="gpt-oss 20B", size=14.0, vram=16, ram=16, cpu=False, tier=7,
         license="Apache-2.0", note="OpenAI open-weight reasoning model."),
    dict(id="qwen3-coder:30b", kind="llm", name="Qwen3-Coder 30B (MoE)", size=19.0, vram=24, ram=32, cpu=False, tier=8,
         license="Apache-2.0", note="Best local coder. 24 GB GPU or 12 GB + 32 GB RAM."),
    dict(id="hf.co/bartowski/LLaMA-Mesh-GGUF:Q4_K_M", kind="llm-mesh", name="LLaMA-Mesh 8B (NVIDIA)", size=4.9, vram=6,
         ram=8, cpu=True, tier=2, license="Non-commercial (NSCLv1 + Llama 3.1)",
         note="Writes the mesh directly. Under 500 faces, research quality."),
    dict(id="z-image-turbo", kind="image", name="Z-Image-Turbo 6B (Q3)", size=6.0, vram=4, ram=16, cpu=False, tier=4,
         license="Apache-2.0", note="Best local image quality for 4 GB GPUs.",
         files={"diffusion": ("leejet/Z-Image-Turbo-GGUF", "z_image_turbo-Q3_K.gguf"),
                "llm": ("unsloth/Qwen3-4B-Instruct-2507-GGUF", "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"),
                "vae": ("Comfy-Org/z_image_turbo", "split_files/vae/ae.safetensors")},
         args=["--cfg-scale", "1.0", "--steps", "8", "--offload-to-cpu", "-W", "768", "-H", "768"]),
    dict(id="flux2-klein-4b", kind="image", name="FLUX.2 klein 4B (Q4)", size=5.2, vram=4, ram=16, cpu=False, tier=3,
         license="Apache-2.0", note="Fast, sharp product shots.",
         files={"diffusion": ("leejet/FLUX.2-klein-4B-GGUF", "flux-2-klein-4b-Q4_0.gguf"),
                "llm": ("unsloth/Qwen3-4B-GGUF", "Qwen3-4B-Q4_K_M.gguf"),
                "vae": ("black-forest-labs/FLUX.2-small-decoder", "full_encoder_small_decoder.safetensors")},
         args=["--cfg-scale", "1.0", "--steps", "4", "--offload-to-cpu", "-W", "768", "-H", "768"]),
    dict(id="sd-turbo", kind="image", name="SD-Turbo", size=5.2, vram=2, ram=8, cpu=True, tier=1,
         license="Stability Community (free < $1M revenue)", note="Lowest requirements, 512 px, basic quality.",
         files={"model": ("stabilityai/sd-turbo", "sd_turbo.safetensors")},
         args=["--cfg-scale", "1.0", "--steps", "1", "-W", "512", "-H", "512"]),
    dict(id="flux1-schnell", kind="image", name="FLUX.1 schnell (Q4)", size=10.0, vram=6, ram=16, cpu=False, tier=5,
         license="Apache-2.0", note="Excellent prompt following. Bigger download.",
         files={"diffusion": ("leejet/FLUX.1-schnell-gguf", "flux1-schnell-q4_k.gguf"),
                "clip_l": ("comfyanonymous/flux_text_encoders", "clip_l.safetensors"),
                "t5xxl": ("city96/t5-v1_1-xxl-encoder-gguf", "t5-v1_1-xxl-encoder-Q4_K_M.gguf"),
                "vae": ("Comfy-Org/z_image_turbo", "split_files/vae/ae.safetensors")},
         args=["--cfg-scale", "1.0", "--steps", "4", "--sampling-method", "euler", "--offload-to-cpu",
               "-W", "768", "-H", "768"]),
    dict(id="triposr", kind="3d", name="TripoSR", size=5.2, vram=6, ram=8, cpu=True, tier=2, license="MIT",
         note="Image → textured mesh in seconds on GPU, ~1–3 min on CPU. Rough detail. Includes PyTorch (~3.5 GB)."),
    dict(id="hunyuan3d-2mv", kind="3d", name="Hunyuan3D-2mv multi-view (shape)", size=8.2, vram=6, ram=16, cpu=False,
         tier=4, multiview=True, license="Tencent Community: NOT licensed in the EU, UK or South Korea",
         note="Uses front/left/back/right images: crisp, accurate shapes (no texture; Blender bakes the colour). "
              "Runs on 4 GB GPUs using shared memory, ~4-6 min."),
    dict(id="hunyuan3d-2mini", kind="3d", name="Hunyuan3D-2mini (shape)", size=7.8, vram=6, ram=16, cpu=False, tier=3,
         license="Tencent Community: NOT licensed in the EU, UK or South Korea",
         note="Better shapes than TripoSR, no texture (Blender bakes a flat colour). Includes PyTorch."),
]
BY_ID = {m["id"]: m for m in CATALOG}
KIND_LABEL = {"llm": "Text → 3D (AI writes Blender code)", "llm-mesh": "Text → 3D (AI writes the mesh)",
              "image": "Text → image", "3d": "Image → 3D"}


# ---------- hardware ----------

def hardware():
    class MEM(ctypes.Structure):
        _fields_ = [("len", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                    ("avail", ctypes.c_ulonglong)] + [(f"x{i}", ctypes.c_ulonglong) for i in range(5)]
    m = MEM(len=ctypes.sizeof(MEM))
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    gpu, vram = None, 0.0
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10, creationflags=NOWIN).stdout.strip().splitlines()
        if out:
            name, mib = out[0].rsplit(",", 1)
            gpu, vram = name.strip(), round(int(mib) / 1024, 1)
    except (OSError, ValueError, subprocess.SubprocessError):
        pass  # ponytail: NVIDIA only; AMD/Intel VRAM via DXGI if anyone asks (sd.cpp Vulkan still works there)
    HOME.mkdir(parents=True, exist_ok=True)
    return dict(gpu=gpu, vram=vram, ram=round(m.total / 2**30, 1), cpus=os.cpu_count(),
                disk_free=round(shutil.disk_usage(HOME).free / 2**30, 1))


def fit(m, hw):
    """'good' = runs well, 'slow' = runs via CPU/offload, 'no' = too big for this PC."""
    if hw["ram"] < m["ram"] * 0.9:
        return "no"
    if hw["vram"] >= m["vram"]:
        return "good"
    if m["kind"] in ("llm", "llm-mesh") and hw["ram"] >= m["size"] + 4:  # Ollama spills layers to RAM
        return "slow"
    if m["cpu"] or (m["kind"] == "image" and hw["vram"] >= 3) or (m["kind"] == "3d" and hw["vram"] >= 4 and hw["ram"] >= 14):
        # 3d: NVIDIA drivers spill into system RAM, verified for Hunyuan3D-2mv on a 4 GB GPU
        return "slow"
    return "no"


def recommend(hw):
    """Best-tier 'good' model per kind, falling back to the best 'slow' one."""
    rec = {}
    for kind in KIND_LABEL:
        ms = [m for m in CATALOG if m["kind"] == kind]
        for want in ("good", "slow"):
            ok = [m for m in ms if fit(m, hw) == want]
            if ok:
                rec[kind] = max(ok, key=lambda m: m["tier"])["id"]
                break
    return rec


# ---------- install state ----------

def ollama_version():
    try:
        return httpx.get(f"{OLLAMA}/api/version", timeout=2).json()["version"]
    except (httpx.HTTPError, ValueError, KeyError):
        return None


def ollama_exe():
    p = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
    return str(p) if p.exists() else shutil.which("ollama")


def ensure_ollama():
    """Start the Ollama server if it is installed but not running."""
    if ollama_version():
        return True
    exe = ollama_exe()
    if not exe:
        return False
    subprocess.Popen([exe, "serve"], creationflags=NOWIN | getattr(subprocess, "DETACHED_PROCESS", 0),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(30):
        if ollama_version():
            return True
        threading.Event().wait(0.5)
    return False


def ollama_models():
    try:
        return {m["name"] for m in httpx.get(f"{OLLAMA}/api/tags", timeout=3).json().get("models", [])}
    except (httpx.HTTPError, ValueError):
        return set()


def _has_tag(names, tag):
    return tag in names or (":" not in tag and f"{tag}:latest" in names)


def sd_cli():
    found = sorted((HOME / "sdcpp").rglob("sd-cli.exe")) or sorted((HOME / "sdcpp").rglob("sd.exe"))
    return found[0] if found else None


def torch_python():
    p = HOME / "torch-venv" / "Scripts" / "python.exe"
    return p if p.exists() else None


def installed():
    names = ollama_models()
    out = {}
    for m in CATALOG:
        if m["kind"] in ("llm", "llm-mesh"):
            out[m["id"]] = _has_tag(names, m["id"])
        elif m["kind"] == "image":
            out[m["id"]] = bool(sd_cli()) and all((MODELS / Path(f).name).exists() for _, f in m["files"].values())
        else:
            out[m["id"]] = (HOME / "ready" / m["id"]).exists()
    out["instant"] = True
    return out


# ---------- downloads ----------

PROGRESS = {}  # id -> {status, done, total, msg}
_lock = threading.Lock()


def _set(mid, **kw):
    with _lock:
        PROGRESS.setdefault(mid, {"status": "queued", "done": 0, "total": 0, "msg": ""}).update(kw)


def _fetch(url, dest: Path, mid, label):
    """Resumable-ish streaming download with progress (skips files that already exist)."""
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with httpx.stream("GET", url, follow_redirects=True, timeout=httpx.Timeout(60, read=300)) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with tmp.open("wb") as fh:
            for chunk in r.iter_bytes(1 << 20):
                fh.write(chunk)
                done += len(chunk)
                _set(mid, done=done, total=total, msg=f"Downloading {label}")
    tmp.replace(dest)
    return dest


def _hf(repo, file):
    return f"https://huggingface.co/{repo}/resolve/main/{file}"


def _pip(py, mid, *args):
    _set(mid, msg="Installing Python packages: " + " ".join(a for a in args if not a.startswith("-"))[:80], done=0, total=0)
    r = subprocess.run([str(py), "-m", "pip", "install", "--disable-pip-version-check", *args],
                       capture_output=True, text=True, creationflags=NOWIN)
    if r.returncode:
        raise RuntimeError("pip failed: " + (r.stderr or r.stdout)[-600:])


def _ensure_torch(mid, hw):
    py = torch_python()
    if not py:
        _set(mid, msg="Creating Python environment")
        subprocess.run([sys.executable, "-m", "venv", str(HOME / "torch-venv")], check=True, creationflags=NOWIN)
        py = torch_python()
    if subprocess.run([str(py), "-c", "import torch"], capture_output=True, creationflags=NOWIN).returncode:
        index = "https://download.pytorch.org/whl/cu128" if hw["gpu"] else "https://download.pytorch.org/whl/cpu"
        _pip(py, mid, "torch", "torchvision", "--index-url", index)
    return py


def _install_ollama_model(mid):
    if not ensure_ollama():
        raise RuntimeError("Ollama is not installed. Click 'Install Ollama' first (free, from ollama.com).")
    with httpx.stream("POST", f"{OLLAMA}/api/pull", json={"model": mid, "stream": True}, timeout=None) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            ev = json.loads(line)
            if ev.get("error"):
                raise RuntimeError(ev["error"])
            _set(mid, done=ev.get("completed", 0), total=ev.get("total", 0), msg=ev.get("status", ""))


def _install_sdcpp(mid):
    if sd_cli():
        return
    _set(mid, msg="Finding stable-diffusion.cpp release")
    rel = httpx.get("https://api.github.com/repos/leejet/stable-diffusion.cpp/releases/latest", timeout=30,
                    follow_redirects=True).raise_for_status().json()
    asset = next(a for a in rel["assets"] if re.search(r"bin-win-vulkan-x64\.zip$", a["name"]))
    z = _fetch(asset["browser_download_url"], HOME / "downloads" / asset["name"], mid, "stable-diffusion.cpp (Vulkan)")
    with zipfile.ZipFile(z) as zf:
        zf.extractall(HOME / "sdcpp")
    if not sd_cli():
        raise RuntimeError("sd-cli.exe not found in the stable-diffusion.cpp release")


def _patch_triposr(src: Path):
    """Make TripoSR install without a compiler and bake textures on GPU (both verified on Windows)."""
    iso = src / "tsr" / "models" / "isosurface.py"
    code = iso.read_text(encoding="utf-8")
    if "torchmcubes" in code:  # torchmcubes needs a C++/CUDA compiler; PyMCubes ships wheels.
        # torchmcubes returns (z, y, x) and TripoSR swaps it back, so hand over the same order.
        code = code.replace("from torchmcubes import marching_cubes", (
            "import mcubes as _mc\n"
            "def marching_cubes(vol, thresh):\n"
            "    v, f = _mc.marching_cubes(vol.detach().cpu().numpy(), thresh)\n"
            "    return (torch.from_numpy(v[:, ::-1].copy().astype('float32')).to(vol.device),\n"
            "            torch.from_numpy(f.astype('int64')).to(vol.device))"))
        iso.write_text(code, encoding="utf-8")
    bake = src / "tsr" / "bake_texture.py"
    code = bake.read_text(encoding="utf-8")
    if "positions.to(scene_code.device)" not in code:  # positions built on CPU while the model is on CUDA
        code = code.replace("            positions,\n            scene_code,", "            positions.to(scene_code.device),\n            scene_code,")
        code = code.replace('queried_grid["color"].numpy()', 'queried_grid["color"].cpu().numpy()')
        bake.write_text(code, encoding="utf-8")


def _install_triposr(mid, hw):
    py = _ensure_torch(mid, hw)
    _pip(py, mid, "omegaconf", "einops", TRANSFORMERS_PIN, "trimesh", "rembg[cpu]", "huggingface-hub",
         "PyMCubes", "Pillow", "xatlas", "moderngl", "imageio")
    src = HOME / "triposr"
    if not (src / "tsr").exists():
        z = _fetch("https://github.com/VAST-AI-Research/TripoSR/archive/refs/heads/main.zip",
                   HOME / "downloads" / "TripoSR-main.zip", mid, "TripoSR code")
        with zipfile.ZipFile(z) as zf:
            zf.extractall(HOME / "downloads")
        shutil.rmtree(src, ignore_errors=True)
        shutil.move(str(HOME / "downloads" / "TripoSR-main"), src)
    _patch_triposr(src)
    _set(mid, msg="Downloading TripoSR weights (1.7 GB)")
    subprocess.run([str(py), "-c", "from huggingface_hub import hf_hub_download as d;"
                    "d('stabilityai/TripoSR','model.ckpt');d('stabilityai/TripoSR','config.yaml')"],
                   check=True, capture_output=True, creationflags=NOWIN)


HUNYUAN_FILES = {
    "hunyuan3d-2mini": ("tencent/Hunyuan3D-2mini", ["hunyuan3d-dit-v2-mini-turbo/*", "hunyuan3d-vae-v2-mini-turbo/*"]),
    "hunyuan3d-2mv": ("tencent/Hunyuan3D-2mv", ["hunyuan3d-dit-v2-mv-turbo/config.yaml",
                                              "hunyuan3d-dit-v2-mv-turbo/model.fp16.safetensors"]),
}


def _install_hunyuan(mid, hw):
    py = _ensure_torch(mid, hw)
    # hy3dgen alone pulls transformers 5.x (renames DINOv2 weights) and diffusers 0.41 (needs huggingface_hub 1.x)
    _pip(py, mid, "hy3dgen==2.0.2", "rembg[cpu]", TRANSFORMERS_PIN, "diffusers==0.34.0")
    repo, patterns = HUNYUAN_FILES[mid]
    _set(mid, msg=f"Downloading {BY_ID[mid]['name']} weights (~{BY_ID[mid]['size'] - 3.5:.1f} GB)")
    r = subprocess.run([str(py), "-c", f"from huggingface_hub import snapshot_download as s; s({repo!r}, allow_patterns={patterns!r})"],
                       capture_output=True, text=True, creationflags=NOWIN)
    if r.returncode:
        raise RuntimeError(r.stderr[-500:])


def install(mid):
    """Start a background download/install; progress in PROGRESS[mid]."""
    m = BY_ID[mid]
    if PROGRESS.get(mid, {}).get("status") == "running":
        return

    def work():
        _set(mid, status="running", done=0, total=0, msg="Starting", error=None)
        try:
            hw = hardware()
            if m["kind"] in ("llm", "llm-mesh"):
                _install_ollama_model(mid)
            elif m["kind"] == "image":
                _install_sdcpp(mid)
                for repo, f in m["files"].values():
                    _fetch(_hf(repo, f), MODELS / Path(f).name, mid, Path(f).name)
            else:
                (_install_triposr if mid == "triposr" else _install_hunyuan)(mid, hw)
                (HOME / "ready").mkdir(parents=True, exist_ok=True)
                (HOME / "ready" / mid).write_text("ok")
            _set(mid, status="done", msg="Installed")
        except Exception as e:
            _set(mid, status="failed", error=str(e), msg="Failed")

    threading.Thread(target=work, daemon=True).start()


def remove(mid):
    m = BY_ID[mid]
    if m["kind"] in ("llm", "llm-mesh"):
        httpx.request("DELETE", f"{OLLAMA}/api/delete", json={"model": mid}, timeout=30)
    elif m["kind"] == "image":
        shared = {Path(f).name for o in CATALOG if o["kind"] == "image" and o["id"] != mid and installed().get(o["id"])
                  for _, f in o["files"].values()}
        for _, f in m["files"].values():
            if Path(f).name not in shared:
                (MODELS / Path(f).name).unlink(missing_ok=True)
    else:
        (HOME / "ready" / mid).unlink(missing_ok=True)
    PROGRESS.pop(mid, None)


def install_ollama_app():
    """Install the Ollama app with winget (official package), user-initiated from the UI."""
    r = subprocess.run(["winget", "install", "--id", "Ollama.Ollama", "-e", "--silent",
                        "--accept-source-agreements", "--accept-package-agreements"],
                       capture_output=True, text=True, creationflags=NOWIN)
    return ensure_ollama() or r.returncode == 0


def status():
    hw = hardware()
    inst = installed()
    return dict(hardware=hw, recommended=recommend(hw), ollama=ollama_version(), ollama_installed=bool(ollama_exe()),
                kinds=KIND_LABEL, home=str(HOME),
                models=[m | {"fit": fit(m, hw), "installed": inst[m["id"]], "progress": PROGRESS.get(m["id"])}
                        for m in CATALOG])


# ---------- local image backend (stable-diffusion.cpp) ----------

def _sd_image(mid):
    def gen(prompt, out, seed):
        m, exe = BY_ID[mid], sd_cli()
        if not exe or not installed()[mid]:
            raise RuntimeError(f"{m['name']} is not downloaded. Open Local models and download it.")
        flag = {"diffusion": "--diffusion-model", "llm": "--llm", "vae": "--vae", "model": "-m",
                "clip_l": "--clip_l", "t5xxl": "--t5xxl"}
        cmd = [str(exe), "-p", prompt, "--seed", str(seed % 2**31), "-o", str(out), *m["args"]]
        if hardware()["vram"] < 8 and ("llm" in m["files"] or "t5xxl" in m["files"]):
            cmd += ["--backend", "te=cpu", "--vae-tiling"]  # text encoder OOMs on small GPUs; verified on 4 GB
        for role, (_, f) in m["files"].items():
            cmd += [flag[role], str(MODELS / Path(f).name)]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=NOWIN)
        if r.returncode or not Path(out).exists():
            raise RuntimeError(f"{m['name']} failed: {(r.stderr or r.stdout)[-400:]}")
    return gen


# ---------- local LLM -> Blender script backend ----------

SYSTEM = """You build 3D objects for Blender by writing a SHORT Python script using this ready-made kit
(already imported, sizes in metres, z is up, the ground is z=0, the object is centred on x=0, y=0):

  material(name, (r, g, b), rough=0.6, metal=0.0)        -> material (colours 0..1)
  box((sx, sy, sz), at=(x, y, z_bottom), mat=m, bevel=0.0, rot=(rx, ry, rz) degrees)
  cylinder(radius, height, at=(x, y, z_bottom), axis="Z", mat=m)   axis "X"/"Y" lies it down; then at = its centre
  cone(radius, height, at=(x, y, z_bottom), mat=m, radius_top=0.0)
  sphere(radius, at=(x, y, z_centre), mat=m, scale=(1, 1, 1))
  torus(radius, thickness, at=(x, y, z), axis="Z", mat=m)
  mirror_x(obj) -> copy on the other side      array(obj, count, offset=(dx, dy, dz)) -> list

Rules:
- box size is the FULL width/depth/height. 'at' z is the BOTTOM of the part, so a part on top of another
  starts where the other ends (e.g. a 0.4 m tall body ends at z=0.4; a lid on it uses at=(0, 0, 0.4)).
- Use realistic real-world dimensions and proportions. Use 6-30 parts so the object is clearly recognisable.
- Give every part a fitting material. Metal: metal=0.9, rough=0.35.
- No imports, no comments, no explanations. Output only the code in one ```python block."""

EXAMPLE = """```python
wood = material("wood", (0.42, 0.26, 0.12))
iron = material("iron", (0.12, 0.12, 0.13), rough=0.35, metal=0.9)
box((0.9, 0.55, 0.05), at=(0, 0, 0.7), mat=wood, bevel=0.01)
for x in (-0.4, 0.4):
    for y in (-0.22, 0.22):
        box((0.05, 0.05, 0.7), at=(x, y, 0), mat=wood)
box((0.8, 0.02, 0.08), at=(0, -0.24, 0.6), mat=wood)
box((0.8, 0.02, 0.08), at=(0, 0.24, 0.6), mat=wood)
box((0.3, 0.45, 0.12), at=(0, 0, 0.56), mat=wood, bevel=0.005)
cylinder(0.012, 0.03, at=(0, -0.24, 0.62), axis="Y", mat=iron)
```"""

ALLOWED_IMPORTS = {"bpy", "bmesh", "math", "mathutils", "random"}
BANNED_NAMES = {"open", "exec", "eval", "compile", "__import__", "getattr", "setattr", "delattr", "globals", "locals",
                "vars", "input", "breakpoint", "memoryview", "os", "sys", "subprocess", "shutil", "socket"}
BANNED_ATTR = re.compile(r"^(_.*|wm|export_.*|import_.*|script|scripts|handlers|app|utils|addon_utils|preferences|"
                         r"filepath.*|save.*|load.*|reload.*|quit_blender|system|popen|remove|unlink|rmdir|write.*)$")


def check_script(code: str):
    """Static allow-list check before an LLM-written script runs inside Blender."""
    tree = ast.parse(code)
    for n in ast.walk(tree):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            mods = [a.name.split(".")[0] for a in n.names] if isinstance(n, ast.Import) else [(n.module or "").split(".")[0]]
            bad = [m for m in mods if m not in ALLOWED_IMPORTS]
            if bad:
                raise ValueError(f"import of {bad} is not allowed")
        elif isinstance(n, ast.Name) and n.id in BANNED_NAMES:
            raise ValueError(f"use of '{n.id}' is not allowed")
        elif isinstance(n, ast.Attribute) and BANNED_ATTR.match(n.attr) and n.attr not in ("remove_doubles",):
            raise ValueError(f"access to '.{n.attr}' is not allowed")
        elif isinstance(n, (ast.Global, ast.Nonlocal, ast.AsyncFunctionDef, ast.Await)):
            raise ValueError("global/async code is not allowed")


def _extract_code(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)(?:```|$)", text, flags=re.S)
    if blocks:
        return max(blocks, key=len).strip()
    keep = []  # no fences: keep only lines that parse as code (small models mix prose in)
    for line in text.splitlines():
        try:
            ast.parse(line.strip() or "pass")
            keep.append(line)
        except SyntaxError:
            if line[:1] in (" ", "\t") and keep:  # indented continuation of a block
                keep.append(line)
    return "\n".join(keep).strip()


def _chat(model, messages, seed, fmt=None):
    r = httpx.post(f"{OLLAMA}/api/chat", timeout=httpx.Timeout(30, read=900), json={
        "model": model, "messages": messages, "stream": False, "think": False, **({"format": fmt} if fmt else {}),
        "options": {"temperature": 0.4, "seed": seed % 2**31, "num_ctx": 8192, "num_predict": 1500}})
    if r.is_error:  # older models reject "think"
        r = httpx.post(f"{OLLAMA}/api/chat", timeout=httpx.Timeout(30, read=900), json={
            "model": model, "messages": messages, "stream": False, **({"format": fmt} if fmt else {}),
            "options": {"temperature": 0.4, "seed": seed % 2**31, "num_ctx": 8192, "num_predict": 1500}})
    r.raise_for_status()
    return r.json()["message"]["content"]


def _run_in_blender(code_file: Path, out: Path):
    from .engine import find_blender
    r = subprocess.run([find_blender(), "-b", "--factory-startup", "-P", str(ROOT / "blender" / "run_generated.py"),
                        "--", str(code_file), str(out)], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", creationflags=NOWIN, timeout=300)
    err = "\n".join(l for l in (r.stderr + r.stdout).splitlines() if l.startswith("GEN_ERROR") or "Error" in l)
    if r.returncode or not out.exists():
        raise RuntimeError(err[-800:] or "Blender produced no model")


TEMPLATE_SYSTEM = """You turn a description of an object into settings for a parametric 3D generator.
Available templates:
{catalog}

Reply with JSON only: {{"template": "<name or none>", "params": {{...}}}}
- Pick the template that matches the object. If nothing fits, use "none".
- Fill the params that the description implies (sizes in metres, realistic proportions; colours as [r, g, b] 0-1).
  Leave out params the description does not mention."""


def _pick_template(mid, prompt, seed, prev=None, edit=None):
    """LLM chooses template + params. Keyword hit -> only that template's schema (shorter, more reliable)."""
    hint = parametric.match(prompt) if not prev else prev[0]
    names = [hint] if hint else list(parametric.TEMPLATES)
    cat = "\n".join(l for l in parametric.catalog_text().splitlines() if l.split(":")[0][2:] in names)
    msgs = [{"role": "system", "content": TEMPLATE_SYSTEM.format(catalog=cat)},
            {"role": "user", "content": "Describe: a small dark wooden crate with 5 planks"},
            {"role": "assistant", "content": '{"template": "crate", "params": {"width": 0.45, "depth": 0.45, '
                                            '"height": 0.45, "planks": 5, "wood": [0.24, 0.13, 0.06]}}'}]
    if prev and edit:
        msgs += [{"role": "user", "content": f"Describe: {prompt}"},
                 {"role": "assistant", "content": json.dumps({"template": prev[0], "params": prev[1]})},
                 {"role": "user", "content": f"Change it: {edit}. Reply with the full updated JSON."}]
    else:
        msgs.append({"role": "user", "content": f"Describe: {prompt}"})
    try:
        data = json.loads(_chat(mid, msgs, seed, fmt="json"))
        name = str(data.get("template", "none")).lower()
        if name in parametric.TEMPLATES:
            base = prev[1] if prev else parametric.defaults(name)
            return name, parametric.validate(name, {**base, **(data.get("params") or {})})
        return None
    except (ValueError, httpx.HTTPError, AttributeError):
        if hint:  # LLM answer unusable: fall back to the word parser
            return hint, parametric.apply_words(hint, prev[1] if prev else parametric.defaults(hint), edit or prompt)
        return None


def _build_template(job_dir, name, params, out):
    (job_dir / "template.json").write_text(json.dumps({"template": name, "params": params}, indent=1))
    code_file = job_dir / "model_script.py"
    code_file.write_text(parametric.script(name, params), encoding="utf-8")
    _run_in_blender(code_file, out)


def _saved_template(job_dir):
    f = job_dir / "template.json"
    if f.exists():
        d = json.loads(f.read_text())
        return d["template"], d["params"]


def _freeform(mid, prompt, job_dir, out, opts):
    code_file = job_dir / "model_script.py"
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": "Make: a wooden desk with a drawer"}, {"role": "assistant", "content": EXAMPLE}]
    if opts.get("edit") and code_file.exists():  # iterate on the previous script
        msgs += [{"role": "user", "content": f"Make: {prompt}"},
                 {"role": "assistant", "content": f"```python\n{code_file.read_text(encoding='utf-8')}\n```"},
                 {"role": "user", "content": f"Change it: {opts['edit']}. Output the full updated script."}]
    else:
        msgs.append({"role": "user", "content": f"Make: {prompt}"})
    last = None
    for attempt in range(3):  # generate -> check -> run; feed errors back for a repair
        code = _extract_code(_chat(mid, msgs, opts.get("seed", 0) + attempt))
        try:
            check_script(code)
            code_file.write_text(code, encoding="utf-8")
            _run_in_blender(code_file, out)
            return
        except (ValueError, SyntaxError, RuntimeError) as e:
            last = e
            msgs += [{"role": "assistant", "content": f"```python\n{code}\n```"},
                     {"role": "user", "content": f"That failed: {str(e)[:600]}\nFix it and output the full script."}]
    raise RuntimeError(f"The local model could not produce a working script after 3 tries: {last}")


def _llm_blender(mid):
    """Template first (reliable proportions), free-form Blender code only when no template fits."""
    def rec(views, out, opts):
        prompt, job_dir = opts.get("prompt", "").strip(), Path(opts["job_dir"])
        if not prompt:
            raise RuntimeError("This backend builds from a text description. Add a description.")
        ensure_ollama()  # start the server first, or the installed-check sees nothing
        if not installed()[mid]:
            raise RuntimeError(f"{BY_ID[mid]['name']} is not downloaded. Open Local models and download it.")
        edit, prev = opts.get("edit"), _saved_template(job_dir)
        if edit and not prev and (job_dir / "model_script.py").exists():
            return _freeform(mid, prompt, job_dir, out, opts)
        pick = _pick_template(mid, prompt, opts.get("seed", 0), prev, edit)
        if pick:
            return _build_template(job_dir, *pick, out)
        (job_dir / "template.json").unlink(missing_ok=True)
        _freeform(mid, prompt, job_dir, out, opts)
    return rec


def rec_instant(views, out, opts):
    """No AI at all: keyword match + word parser ("tall red chest with 3 bands, no lock")."""
    prompt, job_dir = opts.get("prompt", "").strip(), Path(opts["job_dir"])
    prev = _saved_template(job_dir)
    if opts.get("edit") and prev:
        return _build_template(job_dir, prev[0], parametric.apply_words(prev[0], prev[1], opts["edit"]), out)
    name = parametric.match(prompt)
    if not name:
        raise RuntimeError("No template matches this description. Templates: " + ", ".join(parametric.TEMPLATES)
                           + ". For anything else use a local LLM or an online backend.")
    _build_template(job_dir, name, parametric.apply_words(name, parametric.defaults(name), prompt), out)


def _llm_mesh(mid):
    def rec(views, out, opts):
        prompt, job_dir = opts.get("prompt", "").strip(), Path(opts["job_dir"])
        ensure_ollama()
        if not installed()[mid]:
            raise RuntimeError("LLaMA-Mesh is not downloaded. Open Local models and download it.")
        text = _chat(mid, [{"role": "user", "content": f"Create a 3D model of {prompt}."}], opts.get("seed", 0))
        v = [tuple(map(float, l.split()[1:4])) for l in text.splitlines() if re.match(r"^v\s", l)]
        f = [tuple(int(x.split("/")[0]) - 1 for x in l.split()[1:]) for l in text.splitlines() if re.match(r"^f\s", l)]
        if len(v) < 4 or not f:
            raise RuntimeError("LLaMA-Mesh returned no usable mesh; try again or a simpler description")
        code = ("import bpy\nme = bpy.data.meshes.new('m')\n"
                f"me.from_pydata({[tuple(round(c / 32 - 1, 4) for c in p) for p in v]!r}, [], {f!r})\n"
                "me.validate(); o = bpy.data.objects.new('mesh', me); bpy.context.scene.collection.objects.link(o)\n"
                "o.rotation_euler = (1.5708, 0, 0)\n")
        code_file = job_dir / "model_script.py"
        code_file.write_text(code, encoding="utf-8")
        _run_in_blender(code_file, out)
    return rec


# ---------- local image -> 3D (PyTorch venv) ----------

def _torch_3d(mid):
    def rec(views, out, opts):
        py = torch_python()
        if not py or not installed()[mid]:
            raise RuntimeError(f"{BY_ID[mid]['name']} is not downloaded. Open Local models and download it.")
        img = views.get("front") or next(iter(views.values()))
        extra = [f"{v}={p}" for v, p in views.items()]
        r = subprocess.run([str(py), str(ROOT / "meshforge" / "torch_runner.py"), mid, str(img), str(out), str(HOME), *extra],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=NOWIN)
        if r.returncode or not out.exists():
            raise RuntimeError(f"{BY_ID[mid]['name']} failed: {(r.stderr or r.stdout)[-600:]}")
    return rec


# ---------- register ----------

providers.RECONSTRUCTORS["local-templates"] = rec_instant
providers.RECON_INFO["local-templates"] = dict(
    label="Templates · instant (no AI needed)", key=None, views="text", input="text", local="instant", free=True,
    note=f"{len(parametric.TEMPLATES)} built-in generators ({', '.join(list(parametric.TEMPLATES)[:8])}…). "
         "Understands colours, sizes, counts and styles from your words. Works on any PC.")

for _m in CATALOG:
    _pid, _paid = "local-" + _m["id"].split("/")[-1].replace(":", "-"), dict(local=_m["id"], free=True)
    if _m["kind"] == "image":
        providers.IMAGE_PROVIDERS[_pid] = _sd_image(_m["id"])
        providers.IMAGE_INFO[_pid] = dict(label=f"{_m['name']} · local", key=None, **_paid)
    elif _m["kind"] in ("llm", "llm-mesh"):
        providers.RECONSTRUCTORS[_pid] = (_llm_blender if _m["kind"] == "llm" else _llm_mesh)(_m["id"])
        providers.RECON_INFO[_pid] = dict(label=f"{_m['name']} · local", key=None, views="text", input="text",
                                          note=_m["note"], **_paid)
    else:
        providers.RECONSTRUCTORS[_pid] = _torch_3d(_m["id"])
        providers.RECON_INFO[_pid] = dict(label=f"{_m['name']} · local", key=None, views="1-4" if _m.get("multiview") else "1",
                                          note=_m["note"], **_paid)


if __name__ == "__main__":  # self-check: python -m meshforge.local
    check_script("import bpy, math\nbpy.ops.mesh.primitive_cube_add(location=(0,0,1))\n"
                 "o=bpy.context.object\no.modifiers.new('b','BEVEL').width=0.02\n")
    for bad in ["import os", "open('x','w')", "bpy.ops.wm.save_as_mainfile(filepath='x')", "__import__('os')",
                "bpy.ops.export_scene.gltf(filepath='x')", "x.__class__", "bpy.app.handlers", "from subprocess import run"]:
        try:
            check_script(bad)
            raise AssertionError(f"not blocked: {bad}")
        except ValueError:
            pass
    assert _extract_code("blah\n```python\nprint(1)\n```\n") == "print(1)"
    hw = dict(gpu="X", vram=4.0, ram=15.4, cpus=12, disk_free=100)
    assert fit(BY_ID["qwen3-coder:30b"], hw) == "no" and fit(BY_ID["qwen2.5-coder:7b"], hw) == "slow"
    assert fit(BY_ID["z-image-turbo"], hw) == "good"
    r = recommend(hw)
    assert r["image"] == "z-image-turbo" and r["llm"] in ("qwen3.5:4b", "qwen2.5-coder:7b"), r
    assert recommend(dict(gpu=None, vram=0, ram=8, cpus=4, disk_free=50))["llm"] in ("qwen3.5:4b", "qwen3.5:2b")
    print("local ok", r)
