"""MeshForge command line. `meshforge -h` for help."""
import argparse
import getpass
import sys
from pathlib import Path

from . import engine, inputs, providers


def main(argv=None):
    ap = argparse.ArgumentParser(prog="meshforge", description="Text or images -> textured 3D models.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="generate models from a description, an image, a folder, a .txt or a .csv")
    r.add_argument("source", help='folder | image | list.txt | list.csv | "a description in quotes"')
    r.add_argument("-o", "--output", default="output")
    r.add_argument("--images", default="cloudflare", choices=providers.IMAGE_PROVIDERS, help="image generator for text jobs")
    r.add_argument("--backend", default="hf-trellis2", choices=providers.RECONSTRUCTORS)
    r.add_argument("--preset", default="game", choices=engine.PRESETS)
    r.add_argument("--views", default="front", help="views to generate for text jobs, e.g. front,back,left,right")
    r.add_argument("--seed", type=int)
    r.add_argument("--quads", action="store_true", help="quad topology (voxel remesh + QuadriFlow)")
    r.add_argument("--workers", type=int, default=3, help="jobs in flight at once")

    f = sub.add_parser("refine", help="re-run only the Blender stage on a finished job (seconds, no API cost)")
    f.add_argument("job_dir")
    f.add_argument("--preset", default="game", choices=engine.PRESETS)
    f.add_argument("--target", type=int, help="target triangles (0 = keep all)")
    f.add_argument("--texture", type=int, help="texture size in px, e.g. 1024, 4096")
    f.add_argument("--quads", action="store_true")

    e = sub.add_parser("export", help="bulk-export every finished job into one zip")
    e.add_argument("output", nargs="?", default="output")
    e.add_argument("--zip", default="meshforge_export.zip")
    e.add_argument("--formats", help="e.g. glb,fbx (default: all). Texture maps are always included.")

    k = sub.add_parser("key", help="store API keys in Windows Credential Manager")
    k.add_argument("action", choices=["set", "list"])
    k.add_argument("name", nargs="?", choices=list(providers.KEY_HELP))

    a = ap.parse_args(argv)

    if a.cmd == "run":
        jobs = inputs.collect(a.source)
        if not jobs:
            sys.exit(f"Nothing to do in {a.source}")
        print(f"{len(jobs)} job(s): {', '.join(j.name for j in jobs)}")
        ok, failed = engine.run_all(jobs, Path(a.output), a.images, a.backend, a.preset,
                                    [v.strip() for v in a.views.split(",")], a.seed, a.quads, a.workers)
        print(f"\n{len(ok)} done, {len(failed)} failed. Results in {Path(a.output).resolve()}")
        sys.exit(1 if failed else 0)
    if a.cmd == "refine":
        print(engine.refine(Path(a.job_dir), a.preset, a.target, a.texture, a.quads))
    if a.cmd == "export":
        fm = set(a.formats.split(",")) if a.formats else None
        print(engine.export_zip(Path(a.output), Path(a.zip), fm).resolve())
    if a.cmd == "key":
        if a.action == "list":
            for n, h in providers.KEY_HELP.items():
                print(f"{n:13} {'set' if providers.get_key(n, required=False) else '---'}   {h}")
        else:
            if not a.name:
                sys.exit("meshforge key set <name>")
            print(providers.KEY_HELP[a.name])
            value = _ask_key(a.name)
            if not value:
                sys.exit("nothing entered, key not changed")
            providers.set_key(a.name, value)
            print("saved")


def _ask_key(name):
    """Masked pop-up (paste works there, unlike hidden console input); console prompt if no GUI."""
    try:
        import tkinter as tk
        from tkinter import simpledialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        v = simpledialog.askstring("MeshForge", f"Paste your {name} key (Ctrl+V):\n\n{providers.KEY_HELP[name]}",
                                   show="*", parent=root)
        root.destroy()
        return (v or "").strip()
    except Exception:
        return getpass.getpass(f"{name} key (hidden): ").strip()


if __name__ == "__main__":
    main()
