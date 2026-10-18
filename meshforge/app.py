"""Desktop app: a native window (pywebview / Edge WebView2) showing ui/index.html from a localhost server.
  GET  /            -> ui/
  GET  /files/...   -> the output folder (models, maps, views) for the 3D viewer
  POST /api/<name>  -> Api.<name>(**json)   (same page also works in a normal browser, minus native dialogs)
"""
import json
import os
import random
import shutil
import subprocess
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import webview

from . import engine, inputs, providers

UI = Path(__file__).resolve().parent.parent / "ui"
OUT = Path(os.environ.get("MESHFORGE_OUTPUT", Path.home() / "Documents" / "MeshForge"))
STAGES = ("queued", "images", "reconstructing", "refining", "done", "failed")


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        if path.startswith("/files/"):
            self.directory, path = str(OUT), path[len("/files"):]
        else:
            self.directory = str(UI)
        return super().translate_path(path)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")  # refined models must reload
        super().end_headers()

    def log_message(self, *a):
        pass

    def do_POST(self):
        # Custom header => cross-site pages can't send this without a CORS preflight we never answer (CSRF);
        # Host check stops DNS rebinding.
        if self.headers.get("X-MeshForge") != "1" or self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
            return self.send_error(403)
        name = self.path.removeprefix("/api/")
        fn = getattr(API, name, None)
        if name.startswith("_") or not callable(fn):
            return self.send_error(404)
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            result, code = fn(**body), 200
        except Exception as e:
            result, code = {"error": str(e)}, 500
        data = json.dumps(result).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class Api:
    def __init__(self):
        self.window = None
        self.live = {}  # name -> {status, error, log, started}
        self.lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=3)  # remote stages in parallel; engine serializes Blender

    # ---------- state ----------
    def state(self):
        jobs = {}
        for meta_file in OUT.glob("*/job.json"):
            d = meta_file.parent
            try:
                meta = json.loads(meta_file.read_text())
            except ValueError:
                continue
            jobs[d.name] = meta | {"status": "done", "updated": meta_file.stat().st_mtime}
        with self.lock:
            for name, j in self.live.items():
                if j["status"] != "done" or name not in jobs:
                    jobs[name] = jobs.get(name, {"name": name}) | j
        for name, j in jobs.items():
            d = OUT / name
            front = sorted((d / "views").glob("front.*")) or sorted((d / "views").glob("*.*"))
            j["thumb"] = f"/files/{name}/views/{front[0].name}" if front else None
            final = d / "final"
            j["files"] = sorted(f.name for f in final.iterdir()) if final.exists() else []
            j["version"] = int(final.stat().st_mtime) if final.exists() else 0
        return {
            "jobs": sorted(jobs.values(), key=lambda j: -j.get("updated", j.get("started", 0))),
            "keys": {n: bool(providers.get_key(n, required=False)) for n in providers.KEY_HELP},
            "key_help": providers.KEY_HELP,
            "backends": list(providers.RECONSTRUCTORS), "image_providers": list(providers.IMAGE_PROVIDERS),
            "presets": engine.PRESETS, "output": str(OUT),
        }

    # ---------- dialogs ----------
    def pick_images(self):
        if not self.window:
            return []
        r = self.window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True,
                                           file_types=("Images (*.png;*.jpg;*.jpeg;*.webp;*.bmp)",))
        return list(r or [])

    def pick_folder(self):
        if not self.window:
            return None
        r = self.window.create_file_dialog(webview.FileDialog.FOLDER)
        return r[0] if r else None

    def pick_list(self):
        if not self.window:
            return None
        r = self.window.create_file_dialog(webview.FileDialog.OPEN, file_types=("Description lists (*.txt;*.csv)",))
        return r[0] if r else None

    # ---------- jobs ----------
    def _unique(self, name):
        n, i = name, 2
        while (OUT / n).exists() or n in self.live:
            n, i = f"{name}_{i}", i + 1
        return n

    def _start(self, job, opts, seed=None):
        def log(msg):
            with self.lock:
                self.live[job.name]["log"].append(msg.strip())

        def stage(s):
            with self.lock:
                self.live[job.name]["status"] = s

        def work():
            try:
                engine.run_job(job, OUT, opts.get("image_provider", "cloudflare"), opts.get("backend", "hf-trellis2"),
                               opts.get("preset", "game"), opts.get("views") or ["front"],
                               random.randrange(2**31) if seed is None else seed, bool(opts.get("quads")), log, stage)
                stage("done")
            except BaseException as e:  # SystemExit from a missing key must not kill the worker
                with self.lock:
                    self.live[job.name].update(status="failed", error=str(e))

        with self.lock:
            self.live[job.name] = {"name": job.name, "prompt": job.prompt, "status": "queued", "error": None,
                                   "log": [], "started": time.time(), "updated": time.time()}
        self.pool.submit(work)

    def submit(self, opts):
        """opts: prompt | images (paths) | folder | list file, plus backend, preset, views, quads, image_provider."""
        if opts.get("folder"):
            jobs = inputs.collect(opts["folder"])
        elif opts.get("list"):
            jobs = inputs.collect(opts["list"])
        elif opts.get("images"):
            imgs = [Path(p) for p in opts["images"]]
            base = (opts.get("name") or inputs.split_view(imgs[0].stem)[0]).strip()
            jobs = [inputs.Job(name=inputs._slug(base), views=inputs._views_from_files(imgs), prompt=opts.get("prompt", ""))]
        elif (opts.get("prompt") or "").strip():
            p = opts["prompt"].strip()
            jobs = [inputs.Job(name=inputs._slug(opts.get("name") or p)[:40], prompt=p)]
        else:
            return {"error": "Describe an object, or add images or a folder."}
        if not jobs:
            return {"error": "No images or descriptions found there."}
        OUT.mkdir(parents=True, exist_ok=True)
        for j in jobs:
            j.name = self._unique(j.name)
            self._start(j, opts | ({"preset": j.preset} if j.preset else {}))
        return {"started": [j.name for j in jobs]}

    def regenerate(self, name, opts):
        """Re-run reconstruction + Blender with a new seed. new_images=True also redraws generated views."""
        d = OUT / name
        meta = json.loads((d / "job.json").read_text()) if (d / "job.json").exists() else {}
        if opts.get("new_images") and meta.get("prompt"):
            shutil.rmtree(d / "views", ignore_errors=True)
        views = {p.stem: p for p in sorted((d / "views").glob("*.*"))} if (d / "views").exists() else {}
        job = inputs.Job(name=name, prompt=meta.get("prompt", ""), views=views)
        self.live.pop(name, None)
        self._start(job, {**meta, **opts})
        return True

    def refine(self, name, opts):
        """Blender stage only - seconds, no API cost."""
        with self.lock:
            prev = self.live.get(name, {})
            self.live[name] = {"name": name, "status": "refining", "error": None, "log": prev.get("log", []),
                               "started": time.time(), "updated": time.time()}

        def work():
            try:
                d = OUT / name
                target = opts.get("target")
                engine.refine(d, opts.get("preset", "game"), int(target) if target not in (None, "") else None,
                              int(opts["texture"]) if opts.get("texture") else None, bool(opts.get("quads")),
                              log=lambda m: self.live[name]["log"].append(m.strip()))
                meta_file = d / "job.json"
                meta = json.loads(meta_file.read_text()) if meta_file.exists() else {"name": name}
                meta_file.write_text(json.dumps(meta | {k: opts[k] for k in ("preset", "target", "texture", "quads")
                                                        if k in opts}, indent=2))
                self.live[name]["status"] = "done"
            except BaseException as e:
                self.live[name].update(status="failed", error=str(e))

        self.pool.submit(work)
        return True

    # ---------- misc ----------
    def set_key(self, name, value):
        if name in providers.KEY_HELP and value.strip():
            providers.set_key(name, value.strip())
            return True
        return False

    def open_url(self, url):
        if url.startswith("https://"):
            webbrowser.open(url)

    def open_folder(self, name=""):
        path = (OUT / name).resolve()
        if path.is_dir() and OUT.resolve() in (path, *path.parents):
            subprocess.Popen(["explorer", str(path)])

    def export(self, formats, path=None):
        r = path or self.window and self.window.create_file_dialog(webview.FileDialog.SAVE, save_filename="meshforge_export.zip",
                                           file_types=("Zip (*.zip)",))
        if not self.window and not r:
            r = str(OUT / "meshforge_export.zip")  # browser mode: no native save dialog
        if not r:
            return None
        target = r if isinstance(r, str) else r[0]
        return str(engine.export_zip(OUT, Path(target), set(formats) or None))


API = Api()


def main(port=0, window=True):
    OUT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{server.server_port}/index.html"
    if not window:  # `meshforge ui --browser`: serve only, open in any browser
        print(f"MeshForge UI: {url}")
        return server.serve_forever()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    API.window = webview.create_window("MeshForge", url, width=1440, height=900, min_size=(1000, 650),
                                       background_color="#111317")
    webview.start(debug=bool(os.environ.get("MESHFORGE_DEBUG")))


if __name__ == "__main__":
    main()
