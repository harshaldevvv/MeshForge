"""Run jobs: views -> reconstruct -> refine (Blender). Every stage writes into output/<job>/ so any
stage can be re-run on its own (e.g. `meshforge refine` re-does only the Blender part in seconds)."""
import glob
import json
import os
import random
import shutil
import subprocess
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import providers
from .inputs import Job

# target triangles (0 = keep everything), texture px, faces requested from the backend
PRESETS = {
    "low": dict(target=3000, texture=1024, raw_faces=200000),
    "game": dict(target=30000, texture=2048, raw_faces=500000),
    "high": dict(target=300000, texture=4096, raw_faces=1000000),
    "ultra": dict(target=0, texture=4096, raw_faces=1000000),
}
PIPELINE = Path(__file__).resolve().parent.parent / "blender" / "pipeline.py"
_blender_lock = threading.Lock()  # ponytail: one Blender at a time (bakes share the GPU); split cleanup/bake locks if CPU-bound


def find_blender() -> str:
    if os.environ.get("MESHFORGE_BLENDER"):
        return os.environ["MESHFORGE_BLENDER"]
    found = sorted(glob.glob(r"C:\Program Files\Blender Foundation\Blender *\blender.exe"),
                   key=lambda p: [int(x) for x in p.split("Blender ")[-1].split("\\")[0].split(".") if x.isdigit()])
    exe = found[-1] if found else shutil.which("blender")
    if not exe:
        raise SystemExit("Blender 5.x not found. Install it from blender.org or set MESHFORGE_BLENDER.")
    return exe


def refine(job_dir: Path, preset="game", target=None, texture=None, quads=False, log=print):
    """Blender stage only: raw.glb -> final/ (model in every format + texture maps)."""
    p = PRESETS[preset] | {k: v for k, v in dict(target=target, texture=texture).items() if v is not None}
    final = job_dir / "final"
    shutil.rmtree(final, ignore_errors=True)
    cmd = [find_blender(), "-b", "--factory-startup", "-P", str(PIPELINE), "--",
           str(job_dir / "raw.glb"), str(final), str(p["target"]), str(p["texture"]), "1" if quads else "0"]
    with _blender_lock:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    for line in r.stdout.splitlines():
        if line.startswith("MESHFORGE_TRIS"):
            log(f"  [{job_dir.name}] triangles {line.split(':', 1)[1].strip()}")
    if r.returncode != 0:
        err = [l for l in (r.stderr + r.stdout).splitlines() if "MESHFORGE_ERROR" in l or "Error" in l]
        raise RuntimeError("Blender failed: " + ("; ".join(err[-3:]) or r.stderr[-500:]))
    return final


def run_job(job: Job, out_root: Path, image_provider: str, backend: str, preset: str, view_names, seed, quads, log,
            stage=lambda s: None, edit=None):
    d = out_root / job.name
    (d / "views").mkdir(parents=True, exist_ok=True)
    preset = job.preset or preset
    t0 = time.time()

    views = {}
    for v, src in job.views.items():
        dst = d / "views" / f"{v}{Path(src).suffix.lower()}"
        if Path(src).resolve() != dst.resolve():  # regenerate passes the job's own views
            shutil.copy(src, dst)
        views[v] = dst
    text_backend = providers.RECON_INFO.get(backend, {}).get("input") == "text"
    if job.prompt and not views and not text_backend:
        stage("images")
        gen = providers.IMAGE_PROVIDERS[image_provider]
        for v in view_names:
            log(f"  [{job.name}] generating {v} view ({image_provider})")
            dst = d / "views" / f"{v}.png"
            gen(providers.view_prompt(job.prompt, v), dst, seed)
            views[v] = dst

    stage("reconstructing")
    log(f"  [{job.name}] reconstructing from {sorted(views)} ({backend})")
    if text_backend and not job.prompt:
        raise RuntimeError(f"{backend} builds from a text description; this job has only images")
    providers.RECONSTRUCTORS[backend](views, d / "raw.glb", PRESETS[preset] | {
        "seed": seed, "prompt": job.prompt, "job_dir": str(d), "edit": edit})

    stage("refining")
    log(f"  [{job.name}] refining in Blender (preset {preset})")
    refine(d, preset, quads=quads, log=log)

    meta = dict(name=job.name, prompt=job.prompt, views={k: v.name for k, v in views.items()}, backend=backend,
                image_provider=image_provider if job.prompt and not job.views and not text_backend else None, preset=preset, seed=seed,
                quads=quads, seconds=round(time.time() - t0))
    (d / "job.json").write_text(json.dumps(meta, indent=2))
    return d


def run_all(jobs, out_root: Path, image_provider="cloudflare", backend="hf-trellis2", preset="game",
            view_names=("front",), seed=None, quads=False, workers=3, log=print):
    """Remote stages run in parallel (`workers`); Blender runs one job at a time."""
    seed = random.randrange(2**31) if seed is None else seed
    ok, failed = [], []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(run_job, j, out_root, image_provider, backend, preset, view_names, seed, quads, log): j
                for j in jobs}
        for f in as_completed(futs):
            j = futs[f]
            try:
                ok.append(f.result())
                log(f"done  {j.name}")
            except Exception as e:  # one bad job must not kill the batch
                failed.append((j.name, str(e)))
                log(f"FAIL  {j.name}: {e}")
    return ok, failed


def export_zip(out_root: Path, zip_path: Path, formats=None):
    """Bulk export: every job's final/ folder (optionally only some formats) into one zip."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out_root.glob("*/final/*")):
            if f.suffix == ".png" or not formats or f.suffix.lstrip(".") in formats or f.suffix == ".mtl":
                z.write(f, f"{f.parent.parent.name}/{f.name}")
    return zip_path
