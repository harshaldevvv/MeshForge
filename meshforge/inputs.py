"""Turn whatever the user points at into a list of jobs.

Accepted inputs:
  - a folder of folders      -> one job per subfolder (its images are the views)
  - a flat folder of images  -> grouped by name prefix + view suffix (chair_front.png, chair_back.png)
  - a single image           -> one job
  - a .txt file              -> one text job per non-empty line
  - a .csv file              -> columns: name, description[, preset]
  - a plain string           -> one text job
"""
import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
VIEW_ALIASES = {
    "front": "front", "f": "front", "0": "front",
    "right": "right", "r": "right", "90": "right",
    "back": "back", "b": "back", "180": "back", "rear": "back",
    "left": "left", "l": "left", "270": "left",
    "top": "top", "bottom": "bottom",
}
_SUFFIX = re.compile(r"^(.*?)[ _\-.]+(" + "|".join(sorted(VIEW_ALIASES, key=len, reverse=True)) + r")$", re.I)


@dataclass
class Job:
    name: str
    prompt: str = ""
    views: dict = field(default_factory=dict)  # view name -> image path
    preset: str | None = None


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", s).strip("_")[:60] or "model"


def split_view(stem: str):
    """'chair_front' -> ('chair', 'front'); 'chair' -> ('chair', None)."""
    m = _SUFFIX.match(stem)
    if m and m.group(1):
        return m.group(1), VIEW_ALIASES[m.group(2).lower()]
    return stem, None


def _views_from_files(files):
    """Assign view names to a single object's images; unnamed ones fill the free slots in order."""
    views, rest = {}, []
    for f in sorted(files):
        _, v = split_view(f.stem)
        if v and v not in views:
            views[v] = f
        else:
            rest.append(f)
    for f in rest:
        free = next((v for v in ("front", "back", "left", "right", "top", "bottom") if v not in views), None)
        if free is None:
            break
        views[free] = f
    return views


def _images(folder: Path):
    return [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXT]


def collect(source: str) -> list[Job]:
    p = Path(source)
    if not p.exists():
        return [Job(name=_slug(source)[:40], prompt=source)]
    if p.is_file():
        ext = p.suffix.lower()
        if ext in IMAGE_EXT:
            name, _ = split_view(p.stem)
            return [Job(name=_slug(name), views={"front": p})]
        if ext == ".csv":
            with p.open(newline="", encoding="utf-8") as fh:
                rows = [r for r in csv.reader(fh) if r and r[0].strip() and r[0].strip().lower() != "name"]
            return [Job(name=_slug(r[0]), prompt=r[1].strip() if len(r) > 1 else r[0],
                        preset=(r[2].strip() or None) if len(r) > 2 else None) for r in rows]
        lines = [l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
        return [Job(name=f"{i + 1:03d}_{_slug(l)[:40]}", prompt=l) for i, l in enumerate(lines)]

    jobs = []
    for sub in sorted(d for d in p.iterdir() if d.is_dir()):
        imgs = _images(sub)
        if imgs:
            jobs.append(Job(name=_slug(sub.name), views=_views_from_files(imgs)))
    groups = {}
    for f in _images(p):
        groups.setdefault(split_view(f.stem)[0], []).append(f)
    for name, files in sorted(groups.items()):
        jobs.append(Job(name=_slug(name), views=_views_from_files(files)))
    return jobs


if __name__ == "__main__":  # self-check: python -m meshforge.inputs
    import tempfile

    assert split_view("chair_front") == ("chair", "front")
    assert split_view("red-car.back") == ("red-car", "back")
    assert split_view("lamp 90") == ("lamp", "right")
    assert split_view("frontdoor") == ("frontdoor", None)
    assert split_view("left") == ("left", None)
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        (t / "robot").mkdir()
        for n in ["robot/a.png", "robot/b_back.png", "chair_front.png", "chair_left.jpg", "vase.png", "notes.md"]:
            (t / n).write_bytes(b"x")
        jobs = {j.name: j for j in collect(str(t))}
        assert set(jobs) == {"robot", "chair", "vase"}, jobs
        assert set(jobs["robot"].views) == {"back", "front"}
        assert jobs["robot"].views["back"].name == "b_back.png"
        assert set(jobs["chair"].views) == {"front", "left"}
        (t / "list.txt").write_text("a red fox\n\nwooden chair\n")
        assert [j.prompt for j in collect(str(t / "list.txt"))] == ["a red fox", "wooden chair"]
        (t / "l.csv").write_text("name,description,preset\nfox,a fox,low\n")
        j = collect(str(t / "l.csv"))[0]
        assert (j.name, j.prompt, j.preset) == ("fox", "a fox", "low")
    assert collect("a tiny dragon")[0].prompt == "a tiny dragon"
    print("inputs ok")
