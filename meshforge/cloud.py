"""Your own on-demand cloud GPU on Modal: deploy, generate, and a hard monthly spending guard.

Isolation: MeshForge uses only the Modal token saved in MeshForge (Windows Credential Manager) and points Modal at
its own config file, so any other Modal login on this PC (~/.modal.toml) is never read or changed.
Budget: before each job, this month's spend (Modal's billing API, cross-checked with a local GPU-seconds ledger) plus
the next job's estimate must stay under the limit (default $25, below Modal's $30 monthly free credit).
"""
import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from . import providers

ROOT = Path(__file__).resolve().parent.parent
HOME = Path(os.environ.get("MESHFORGE_HOME", Path(os.environ.get("LOCALAPPDATA", Path.home())) / "MeshForge"))
LEDGER = HOME / "cloud_usage.json"
SETTINGS = HOME / "cloud_settings.json"
MODAL_EXE = Path(sys.executable).with_name("modal.exe")
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)

APPS = {  # cloud model -> deploy file, Modal app/class, GPU $/second (modal.com/pricing, 2026-10-20)
    "hunyuan21": dict(file=ROOT / "cloud" / "modal_hunyuan21.py", app="meshforge-hunyuan21", cls="Hunyuan21",
                      gpu="L40S", rate=0.000542, idle=60, est_job=0.15),
}


def env():
    t = providers.get_key("modal", required=False)
    if not t or ":" not in t:
        raise SystemExit("No Modal token in MeshForge. Add it under API keys → Modal.")
    tid, sec = t.split(":", 1)
    return dict(os.environ, MODAL_TOKEN_ID=tid, MODAL_TOKEN_SECRET=sec, PYTHONIOENCODING="utf-8",
                MODAL_CONFIG_PATH=str(HOME / "modal.toml"))


def settings():
    try:
        return {"budget": 25.0} | json.loads(SETTINGS.read_text())
    except (OSError, ValueError):
        return {"budget": 25.0}


def set_budget(dollars: float):
    HOME.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(settings() | {"budget": max(0.0, float(dollars))}))


def _month():
    return datetime.date.today().strftime("%Y-%m")


def ledger_spend():
    try:
        rows = json.loads(LEDGER.read_text())
    except (OSError, ValueError):
        rows = []
    return round(sum(r["cost"] for r in rows if r["month"] == _month()), 4)


def _log_usage(app, seconds, cost, note=""):
    try:
        rows = json.loads(LEDGER.read_text())
    except (OSError, ValueError):
        rows = []
    rows.append({"month": _month(), "time": time.strftime("%Y-%m-%d %H:%M"), "app": app,
                 "seconds": round(seconds, 1), "cost": round(cost, 4), "note": note})
    HOME.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(rows, indent=1))


def modal_spend():
    """This month's real spend from Modal's billing API (complete hours only), or None if unavailable."""
    try:
        r = subprocess.run([str(MODAL_EXE), "billing", "report", "--for", "this month", "-r", "h", "--json"],
                           env=env(), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90, creationflags=NOWIN)
        rows = json.loads(r.stdout or "[]")
    except (OSError, ValueError, subprocess.SubprocessError, SystemExit):
        return None

    def cost(x):
        if isinstance(x, dict):
            for k in ("cost", "total_cost", "amount", "total"):
                if k in x and isinstance(x[k], (int, float, str)):
                    try:
                        return float(x[k])
                    except ValueError:
                        pass
            return sum(cost(v) for v in x.values() if isinstance(v, (dict, list)))
        if isinstance(x, list):
            return sum(cost(v) for v in x)
        return 0.0
    return round(cost(rows), 4)


def status():
    s = settings()
    real = modal_spend() if providers.get_key("modal", required=False) else None
    local = ledger_spend()
    spent = max(real or 0.0, local)
    return {"budget": s["budget"], "spent": round(spent, 2), "modal_reported": real, "local_estimate": local,
            "deployed": deployed(), "token": bool(providers.get_key("modal", required=False))}


def check_budget(app="hunyuan21"):
    s, est = settings(), APPS[app]["est_job"]
    spent = max(modal_spend() or 0.0, ledger_spend())
    if spent + est > s["budget"]:
        raise RuntimeError(f"Cloud budget reached: ${spent:.2f} spent this month, limit ${s['budget']:.2f}. "
                           "Raise the limit in API keys → Modal if you really want to continue.")
    return spent


def deployed(app="hunyuan21"):
    try:
        r = subprocess.run([str(MODAL_EXE), "app", "list", "--json"], env=env(), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60, creationflags=NOWIN)
        return any((a.get("Description") or a.get("description")) == APPS[app]["app"]
                   and str(a.get("State") or a.get("state") or "").lower().startswith("deployed")
                   for a in json.loads(r.stdout or "[]"))
    except (OSError, ValueError, subprocess.SubprocessError, SystemExit):
        return False


def deploy(app="hunyuan21", log=print):
    """Build the GPU image (first time ~15-30 min) and deploy. Idle cost: $0."""
    p = subprocess.Popen([str(MODAL_EXE), "deploy", str(APPS[app]["file"])], env=env(), stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", creationflags=NOWIN)
    for line in p.stdout:
        log(line.rstrip())
    if p.wait():
        raise RuntimeError("Modal deploy failed (see log)")


def generate(image_path, out_path, app="hunyuan21", seed=1234, log=print):
    """Run one generation on the deployed app; logs real GPU time to the ledger."""
    check_budget(app)
    a = APPS[app]
    code = (
        "import modal, sys, json\n"
        f"C = modal.Cls.from_name({a['app']!r}, {a['cls']!r})\n"
        "r = C().generate.remote(open(sys.argv[1], 'rb').read(), seed=int(sys.argv[3]))\n"
        "open(sys.argv[2], 'wb').write(r['glb'])\n"
        "print('TIMINGS ' + json.dumps(r['timings']))\n")
    image_path = _cutout_locally(image_path)
    t = time.time()
    r = subprocess.run([sys.executable, "-c", code, str(image_path), str(out_path), str(seed)], env=env(),
                       capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=NOWIN)
    wall = time.time() - t
    timings = next((json.loads(l[8:]) for l in r.stdout.splitlines() if l.startswith("TIMINGS ")), {})
    # container time ~= wall time of the call + the idle window before it shuts down
    _log_usage(app, wall + a["idle"], (wall + a["idle"]) * a["rate"], json.dumps(timings))
    if r.returncode or not Path(out_path).exists():
        raise RuntimeError("Modal generation failed: " + (r.stderr or r.stdout)[-800:])
    log(f"cloud {app}: {timings} wall {wall:.0f}s ~${(wall + a['idle']) * a['rate']:.3f}")
    return timings


def _cutout_locally(image_path):
    """Send a transparent PNG: the cloud's rembg can't separate white objects from white backgrounds (a white
    teapot became a flat panel); MeshForge's border flood-fill matte can. Needs the local PyTorch venv's PIL/numpy;
    without it the cloud removes the background itself."""
    py = HOME / "torch-venv" / "Scripts" / "python.exe"
    if not py.exists():
        return image_path
    import tempfile
    out = Path(tempfile.mkdtemp()) / (Path(image_path).stem + "_cutout.png")  # not in views/: would count as a view
    code = ("import sys; sys.path.insert(0, sys.argv[3]); from cutout import cutout; "
            "cutout(sys.argv[1]).save(sys.argv[2])")
    r = subprocess.run([str(py), "-c", code, str(image_path), str(out), str(ROOT / "meshforge")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=NOWIN)
    return out if r.returncode == 0 and out.exists() else image_path


def rec_modal_hunyuan21(views, out, opts):
    img = views.get("front") or next(iter(views.values()))
    generate(img, out, "hunyuan21", opts.get("seed", 1234) % 2**31, log=lambda m: None)  # app shows stages itself


providers.RECONSTRUCTORS["modal-hunyuan21"] = rec_modal_hunyuan21
providers.RECON_INFO["modal-hunyuan21"] = dict(
    label="Hunyuan3D-2.1 PBR · your Modal GPU", key="modal", views="1",
    note="Shape + PBR texture on your own on-demand L40S (~$0.05–0.10 per model, $30/month free credit). "
         "Turns off after 60 s idle. Spending guard stops at your monthly limit. Tencent licence: not EU/UK/KR.")
