"""Parametric templates on the app side: load the schema from blender/templates.py, validate/clamp params,
pick a template + params from plain words (no LLM needed), and turn a choice into a Blender script."""
import importlib.util
import re
from pathlib import Path

_spec = importlib.util.spec_from_file_location("mf_templates", Path(__file__).resolve().parent.parent / "blender" / "templates.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
TEMPLATES = _mod.TEMPLATES

COLORS = {
    "red": (0.6, 0.08, 0.06), "crimson": (0.55, 0.03, 0.08), "orange": (0.85, 0.38, 0.08), "yellow": (0.9, 0.75, 0.15),
    "gold": (0.83, 0.6, 0.22), "golden": (0.83, 0.6, 0.22), "brass": (0.75, 0.58, 0.28), "bronze": (0.55, 0.36, 0.18),
    "copper": (0.72, 0.4, 0.24), "green": (0.15, 0.42, 0.15), "emerald": (0.05, 0.45, 0.25), "teal": (0.1, 0.45, 0.45),
    "blue": (0.1, 0.25, 0.6), "navy": (0.05, 0.08, 0.3), "cyan": (0.2, 0.6, 0.75), "purple": (0.35, 0.12, 0.45),
    "violet": (0.45, 0.2, 0.6), "pink": (0.85, 0.45, 0.55), "white": (0.92, 0.92, 0.9), "ivory": (0.93, 0.9, 0.8),
    "cream": (0.93, 0.88, 0.75), "black": (0.04, 0.04, 0.045), "grey": (0.45, 0.45, 0.46), "gray": (0.45, 0.45, 0.46),
    "silver": (0.75, 0.76, 0.78), "steel": (0.62, 0.63, 0.66), "iron": (0.11, 0.11, 0.12), "brown": (0.35, 0.2, 0.1),
    "oak": (0.5, 0.33, 0.16), "pine": (0.7, 0.52, 0.3), "walnut": (0.28, 0.16, 0.08), "mahogany": (0.35, 0.12, 0.07),
    "ebony": (0.08, 0.06, 0.05), "birch": (0.8, 0.68, 0.5), "beige": (0.8, 0.72, 0.58), "stone": (0.45, 0.44, 0.42),
}
SHADE = {"dark": 0.55, "light": 1.35, "pale": 1.45, "deep": 0.7, "bright": 1.2}
SCALE_WORDS = {"huge": 1.6, "giant": 1.8, "large": 1.3, "big": 1.3, "bigger": 1.3, "larger": 1.3, "small": 0.75,
               "smaller": 0.75, "tiny": 0.55, "little": 0.75, "mini": 0.6}
DIM_WORDS = {"tall": "height", "taller": "height", "high": "height", "short": "height", "shorter": "height",
             "wide": "width", "wider": "width", "narrow": "width", "long": "length", "longer": "length", "deep": "depth"}
IMPLY = {  # words that imply settings
    "chair": {"armchair": {"armrests": True, "cushion": True}, "upholster": {"cushion": True, "back": "solid"}},
    "axe": {"battle axe": {"head_width": 0.26}, "hatchet": {"handle_length": 0.4, "head_width": 0.12}},
    "sword": {"dagger": {"blade_length": 0.25, "guard_width": 0.09, "grip_length": 0.1},
              "greatsword": {"blade_length": 1.2, "blade_width": 0.07, "grip_length": 0.3, "guard_width": 0.32}},
    "lamp": {"floor lamp": {"kind": "floor", "height": 1.6, "shade_radius": 0.22}, "lantern": {"kind": "lantern", "height": 0.35}},
    "table": {"coffee table": {"height": 0.42}, "desk": {"width": 1.3, "depth": 0.65}, "round table": {"round_top": True}},
    "cabinet": {"nightstand": {"width": 0.45, "height": 0.55, "drawers": 2}, "wardrobe": {"height": 2.0, "width": 1.1, "drawers": 1, "doors": 2}},
    "tree": {"oak": {"kind": "round"}},
    "bottle": {"glow": {"liquid_glow": True}},
}
SIZE_PARAMS = ("width", "depth", "height", "length", "radius", "size", "blade_length", "handle_length", "seat_height",
               "shade_radius", "seat_radius")


def defaults(name):
    return {k: v[-1] for k, v in TEMPLATES[name]["params"].items()}


def _color(v, fallback):
    if isinstance(v, str):
        h = v.strip().lstrip("#")
        if re.fullmatch(r"[0-9a-fA-F]{6}", h):
            return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
        return COLORS.get(v.strip().lower(), fallback)
    try:
        c = [float(x) for x in list(v)[:3]]
        if max(c) > 1.0:  # 0-255 given
            c = [x / 255 for x in c]
        return tuple(min(1.0, max(0.0, x)) for x in c) if len(c) == 3 else fallback
    except (TypeError, ValueError):
        return fallback


def validate(name, params):
    """Clamp/coerce params to the template's schema; unknown keys dropped, missing ones defaulted."""
    out = defaults(name)
    for k, spec in TEMPLATES[name]["params"].items():
        if k not in (params or {}):
            continue
        v, kind = params[k], spec[0]
        try:
            if kind == "float":
                out[k] = round(min(spec[2], max(spec[1], float(v))), 4)
            elif kind == "int":
                out[k] = int(min(spec[2], max(spec[1], round(float(v)))))
            elif kind == "bool":
                out[k] = v if isinstance(v, bool) else str(v).lower() in ("true", "yes", "1", "on")
            elif kind == "enum":
                out[k] = str(v).lower() if str(v).lower() in spec[1] else spec[2]
            elif kind == "color":
                out[k] = _color(v, spec[1])
        except (TypeError, ValueError):
            pass
    return out


def match(text):
    """Best template for a description by keyword (longest keyword wins), or None."""
    t = text.lower()
    best = None
    for name, spec in TEMPLATES.items():
        for kw in spec["keywords"]:
            if re.search(rf"\b{re.escape(kw)}s?\b", t) and (best is None or len(kw) > best[1]):
                best = (name, len(kw))
    return best[0] if best else None


def apply_words(name, params, text):
    """Instant, LLM-free understanding of descriptions/edits: colours, sizes, counts, styles, yes/no parts."""
    p = dict(params)
    spec = TEMPLATES[name]["params"]
    t = text.lower()
    color_keys = [k for k, s in spec.items() if s[0] == "color"]

    def col(word, shade=None):
        c = COLORS[word]
        f = SHADE.get(shade, 1.0)
        return tuple(min(1.0, x * f) for x in c)

    used = set()
    for k in color_keys:  # "dark wood", "gold metal", "red shade", "blue glass"
        base = k.split("_")[0]
        m = re.search(rf"(?:(dark|light|pale|deep|bright)\s+)?(\w+)\s+{base}", t)
        if m and m.group(2) in COLORS:
            p[k] = col(m.group(2), m.group(1))
            used.add(m.start(2))
    if color_keys:  # any other colour word -> the first colour param
        for m in re.finditer(r"(?:(dark|light|pale|deep|bright)\s+)?\b(" + "|".join(COLORS) + r")\b", t):
            if m.start(2) not in used and m.group(2) not in ("iron", "steel", "stone", "pine", "oak") or name == "rock":
                if m.start(2) in used:
                    continue
                p[color_keys[0]] = col(m.group(2), m.group(1))
                break
    for k, s in spec.items():
        word = k.replace("_", " ").rstrip("s")
        if s[0] == "enum":
            for choice in s[1]:
                if re.search(rf"\b{choice}\b", t):
                    p[k] = choice
        elif s[0] == "int":
            m = re.search(rf"\b(\d+)\s+{re.escape(word)}", t)
            if m:
                p[k] = int(m.group(1))
        elif s[0] == "bool":
            if re.search(rf"\b(no|without|remove)\s+((the|a|an|any)\s+)?{re.escape(word)}", t):
                p[k] = False
            elif re.search(rf"\b{re.escape(word)}", t):  # "double axe", "cushioned", "with a lock"
                p[k] = True
    for phrase, sets in IMPLY.get(name, {}).items():
        if re.search(rf"\b{phrase}", t):
            p.update(sets)
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(m|cm|mm)\s*(tall|high|wide|long|deep)", t):  # explicit sizes
        v = float(m.group(1)) * {"m": 1, "cm": 0.01, "mm": 0.001}[m.group(2)]
        key = DIM_WORDS[m.group(3)]
        if key in spec:
            p[key] = v
    for w, f in SCALE_WORDS.items():
        if re.search(rf"\b{w}\b", t):
            for k in SIZE_PARAMS:
                if k in p and isinstance(p[k], (int, float)):
                    p[k] = p[k] * f
            break
    for w, key in DIM_WORDS.items():
        if re.search(rf"\b{w}\b", t) and not re.search(rf"\d\s*(m|cm|mm)\s*{w}", t):
            k = key if key in spec else ("blade_length" if "blade_length" in spec and key == "length" else None)
            if k:
                p[k] = p[k] * (0.75 if w in ("short", "shorter", "narrow") else 1.3)
    return validate(name, p)


def script(name, params):
    return f"make({name!r}, **{params!r})\n"


def catalog_text():
    """Compact template list for the LLM prompt."""
    lines = []
    for name, s in TEMPLATES.items():
        ps = []
        for k, v in s["params"].items():
            if v[0] in ("float", "int"):
                ps.append(f"{k}({v[1]}-{v[2]})")
            elif v[0] == "enum":
                ps.append(f"{k}({'|'.join(v[1])})")
            elif v[0] == "bool":
                ps.append(f"{k}(true/false)")
            else:
                ps.append(f"{k}([r,g,b] 0-1)")
        lines.append(f"- {name}: {s['desc']}. params: {', '.join(ps)}")
    return "\n".join(lines)


if __name__ == "__main__":  # self-check: python -m meshforge.parametric
    assert match("a wooden treasure chest with iron bands") == "chest"
    assert match("a tall bookshelf full of books") == "bookshelf"
    assert match("an alien spaceship") is None
    p = apply_words("chest", defaults("chest"), "a large dark walnut chest with gold metal, 4 bands, no lock, flat lid")
    assert p["bands"] == 4 and p["lock"] is False and p["lid"] == "flat" and p["width"] > 0.8, p
    assert p["metal"] == COLORS["gold"] and p["wood"][0] < COLORS["walnut"][0], p
    q = apply_words("bookshelf", defaults("bookshelf"), "2 m tall bookshelf with 6 shelves")
    assert q["height"] == 2.0 and q["shelves"] == 6, q
    r = apply_words("shield", defaults("shield"), "blue kite shield")
    assert r["kind"] == "kite" and r["face_color"] == COLORS["blue"], r
    a = apply_words("axe", defaults("axe"), "a double battle axe")
    assert a["double"] is True and a["head_width"] == 0.26, a
    c = apply_words("chair", defaults("chair"), "a red cushioned armchair")
    assert c["cushion"] and c["armrests"] and c["cushion_color"] == COLORS["red"], c
    assert apply_words("chest", defaults("chest"), "chest without a lock")["lock"] is False
    v = validate("barrel", {"height": 99, "hoops": "7", "wood": "#ff0000", "bogus": 1})
    assert v["height"] == 1.6 and v["hoops"] == 4 and v["wood"] == (1.0, 0.0, 0.0) and "bogus" not in v
    print("parametric ok:", len(TEMPLATES), "templates")
