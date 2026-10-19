"""Parametric object generators ("templates"). A local LLM (or a keyword matcher) only picks a template
and fills its parameters; the geometry below guarantees sensible proportions.

TEMPLATES is plain data (importable outside Blender, used by the app to prompt + validate).
BUILDERS need Blender. Axes: x = width, y = depth (front faces -y), z = up, ground z = 0, metres.
Param spec: ("float", min, max, default) | ("int", min, max, default) | ("enum", [choices], default)
            | ("bool", default) | ("color", (r, g, b) default)
"""
import math
import random

try:
    import bpy
    import bmesh
    import mathutils
    from kit import material, box, cylinder, cone, sphere, torus, lathe, prism
except ImportError:  # imported by the app for TEMPLATES only
    pass

WOOD, DARK_WOOD, IRON = (0.45, 0.27, 0.12), (0.24, 0.13, 0.06), (0.11, 0.11, 0.12)
STEEL, GOLD, LEATHER = (0.62, 0.63, 0.66), (0.83, 0.6, 0.22), (0.28, 0.16, 0.08)

C = lambda d: ("color", d)
TEMPLATES = {
    "chest": dict(desc="treasure chest / trunk / strongbox", keywords=["chest", "trunk", "treasure", "strongbox", "coffer"],
                  params=dict(width=("float", .3, 2, .8), depth=("float", .2, 1.2, .5), height=("float", .2, 1.2, .5),
                              lid=("enum", ["dome", "flat"], "dome"), wood=C(WOOD), metal=C(IRON),
                              bands=("int", 0, 5, 2), lock=("bool", True), corner_caps=("bool", True), feet=("bool", False))),
    "crate": dict(desc="wooden crate / box with planks", keywords=["crate", "box", "wooden box", "shipping"],
                  params=dict(width=("float", .2, 2, .6), depth=("float", .2, 2, .6), height=("float", .2, 2, .6),
                              planks=("int", 2, 8, 4), wood=C(WOOD), frame=("bool", True), braces=("bool", True))),
    "barrel": dict(desc="barrel / keg / cask", keywords=["barrel", "keg", "cask"],
                   params=dict(height=("float", .3, 1.6, .9), radius=("float", .1, .7, .3), bulge=("float", 0, .3, .14),
                               hoops=("int", 2, 4, 3), wood=C(WOOD), metal=C(IRON), lid=("bool", True))),
    "table": dict(desc="table / desk / dining table / coffee table", keywords=["table", "desk"],
                  params=dict(width=("float", .4, 3, 1.2), depth=("float", .3, 1.5, .7), height=("float", .3, 1.1, .75),
                              top_thickness=("float", .015, .12, .04), legs=("enum", ["square", "round", "tapered"], "square"),
                              round_top=("bool", False), apron=("bool", True), wood=C(WOOD))),
    "chair": dict(desc="chair / dining chair / armchair", keywords=["chair", "armchair"],
                  params=dict(seat_height=("float", .3, .6, .45), seat_width=("float", .35, .7, .45),
                              seat_depth=("float", .35, .6, .44), back_height=("float", .2, .8, .45),
                              back=("enum", ["slats", "solid", "spindles"], "slats"), slats=("int", 2, 7, 3),
                              armrests=("bool", False), cushion=("bool", False), wood=C(WOOD), cushion_color=C((0.55, 0.12, 0.1)))),
    "stool": dict(desc="stool / bar stool / tabouret", keywords=["stool"],
                  params=dict(height=("float", .3, .9, .6), seat_radius=("float", .12, .3, .18), legs=("int", 3, 4, 3),
                              round_seat=("bool", True), wood=C(WOOD))),
    "bench": dict(desc="bench / park bench", keywords=["bench", "pew"],
                  params=dict(length=("float", .6, 3, 1.4), height=("float", .3, .6, .45), depth=("float", .25, .6, .4),
                              backrest=("bool", False), wood=C(WOOD), metal_legs=("bool", False), metal=C(IRON))),
    "bookshelf": dict(desc="bookshelf / bookcase / shelving unit", keywords=["bookshelf", "bookcase", "shelf", "shelves"],
                      params=dict(width=("float", .4, 2.5, .9), height=("float", .5, 2.6, 1.8), depth=("float", .2, .6, .32),
                                  shelves=("int", 1, 8, 4), books=("bool", True), back_panel=("bool", True), wood=C(WOOD))),
    "cabinet": dict(desc="cabinet / dresser / chest of drawers / nightstand / cupboard",
                    keywords=["cabinet", "dresser", "drawer", "nightstand", "cupboard", "wardrobe", "sideboard"],
                    params=dict(width=("float", .3, 2.5, .8), height=("float", .3, 2.4, .9), depth=("float", .25, .8, .45),
                                drawers=("int", 0, 6, 3), doors=("int", 0, 2, 0), legs=("bool", False), wood=C(WOOD), handle=C(GOLD))),
    "lamp": dict(desc="lamp / table lamp / floor lamp / lantern", keywords=["lamp", "lantern", "light"],
                 params=dict(kind=("enum", ["table", "floor", "lantern"], "table"), height=("float", .2, 2, .5),
                             shade_radius=("float", .05, .4, .17), base_color=C((0.15, 0.15, 0.16)),
                             shade_color=C((0.93, 0.88, 0.76)), glow=("bool", True))),
    "sword": dict(desc="sword / longsword / dagger / blade", keywords=["sword", "dagger", "blade", "katana", "sabre", "saber"],
                  params=dict(blade_length=("float", .15, 1.4, .8), blade_width=("float", .015, .12, .05),
                              guard_width=("float", .04, .4, .2), grip_length=("float", .06, .4, .16), pommel=("bool", True),
                              blade_color=C(STEEL), guard_color=C(GOLD), grip_color=C(LEATHER))),
    "axe": dict(desc="axe / battle axe / hatchet", keywords=["axe", "hatchet"],
                params=dict(handle_length=("float", .3, 1.4, .8), head_width=("float", .08, .4, .18), double=("bool", False),
                            metal=C(STEEL), wood=C(WOOD))),
    "shield": dict(desc="shield (round, kite or heater)", keywords=["shield", "buckler"],
                   params=dict(kind=("enum", ["round", "kite", "heater"], "round"), size=("float", .3, 1.4, .7),
                               face_color=C((0.55, 0.1, 0.08)), rim_color=C(IRON), boss=("bool", True), rim=("bool", True))),
    "bottle": dict(desc="bottle / potion / jar / flask", keywords=["bottle", "potion", "jar", "flask", "vial", "wine"],
                   params=dict(kind=("enum", ["wine", "potion", "jar", "flask"], "wine"), height=("float", .06, .6, .3),
                               radius=("float", .02, .2, .045), glass_color=C((0.15, 0.4, 0.2)), cork=("bool", True),
                               label=("bool", True), label_color=C((0.9, 0.85, 0.7)), liquid_glow=("bool", False))),
    "mug": dict(desc="mug / cup / tankard", keywords=["mug", "cup", "tankard", "coffee"],
                params=dict(height=("float", .05, .25, .1), radius=("float", .025, .1, .045), handle=("bool", True),
                            color=C((0.9, 0.9, 0.88)))),
    "vase": dict(desc="vase / urn / pot / amphora", keywords=["vase", "urn", "pot", "amphora", "planter"],
                 params=dict(height=("float", .1, 1.2, .4), radius=("float", .04, .4, .13), neck=("float", .2, .8, .45),
                             color=C((0.2, 0.35, 0.6)), glossy=("bool", True))),
    "candle": dict(desc="candle / candlestick", keywords=["candle", "candlestick"],
                   params=dict(height=("float", .04, .4, .15), radius=("float", .01, .06, .022), holder=("bool", True),
                               wax_color=C((0.95, 0.92, 0.82)), holder_color=C(GOLD))),
    "tree": dict(desc="low-poly tree (pine or round)", keywords=["tree", "pine", "fir", "oak"],
                 params=dict(kind=("enum", ["pine", "round"], "pine"), height=("float", 1, 12, 4),
                             trunk_color=C((0.3, 0.18, 0.1)), leaf_color=C((0.15, 0.4, 0.15)))),
    "rock": dict(desc="rock / boulder / stone", keywords=["rock", "boulder", "stone"],
                 params=dict(size=("float", .1, 4, .6), seed=("int", 0, 999, 1), color=C((0.45, 0.44, 0.42)),
                             flat=("float", 0, .6, .25))),
    "door": dict(desc="door with frame", keywords=["door", "gate"],
                 params=dict(width=("float", .5, 2, .9), height=("float", 1.5, 3, 2.05), panels=("int", 1, 6, 4),
                             frame=("bool", True), wood=C(DARK_WOOD), handle=C(GOLD))),
    "fence": dict(desc="fence section", keywords=["fence", "railing", "picket"],
                  params=dict(length=("float", .5, 6, 2), height=("float", .4, 2, 1), posts=("int", 2, 10, 3),
                              rails=("int", 1, 4, 2), pickets=("bool", True), wood=C(WOOD))),
    "goblet": dict(desc="goblet / chalice / wine glass", keywords=["goblet", "chalice", "wine glass", "grail"],
                   params=dict(height=("float", .08, .4, .18), radius=("float", .03, .12, .045), color=C(GOLD),
                               metallic=("bool", True))),
}


# ---------- helpers ----------

def _squash(o, sz=1.0, sx=1.0, sy=1.0):
    """Scale in world axes (after any rotation)."""
    bpy.ops.object.select_all(action='DESELECT')
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.transform_apply(rotation=True, scale=True)
    o.scale = (sx, sy, sz)
    bpy.ops.object.transform_apply(scale=True)
    return o


def _rod(p1, p2, radius, mat, verts=16):
    """Cylinder from point p1 to point p2."""
    a, b = mathutils.Vector(p1), mathutils.Vector(p2)
    d = b - a
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=d.length, vertices=verts, location=(a + b) / 2)
    o = bpy.context.object
    o.rotation_euler = d.to_track_quat('Z', 'Y').to_euler()
    o.data.materials.append(mat)
    for p in o.data.polygons:
        p.use_smooth = True
    return o


def _wood(c):
    return material("wood", c, 0.72)


def _metal(c, rough=0.35):
    return material("metal", c, rough, 0.9)


# ---------- builders ----------

def chest(width, depth, height, lid, wood, metal, bands, lock, corner_caps, feet):
    W, D, H = width, depth, height
    wm, mm = _wood(wood), _metal(metal)
    z0 = 0.035 if feet else 0.0
    hb = H * (0.6 if lid == "dome" else 0.72)
    hl = H - hb
    e = max(0.005, W * 0.01)
    if feet:
        f = min(W, D) * 0.12
        for sx in (-1, 1):
            for sy in (-1, 1):
                box((f, f, z0), at=(sx * (W / 2 - f / 2), sy * (D / 2 - f / 2), 0), mat=mm)
    box((W, D, hb), at=(0, 0, z0), mat=wm, bevel=0.006)
    r = D / 2

    def lid_part(length, rr, x=0.0, mat=wm):
        if lid == "dome":
            return _squash(cylinder(rr, length, at=(x, 0, z0 + hb), axis="X", mat=mat, verts=48), sz=hl / r)
        return box((length, 2 * rr, hl + (rr - r)), at=(x, 0, z0 + hb), mat=mat, bevel=0.006)

    lid_part(W * 1.005, r * 1.01)
    bw = max(0.025, W * 0.05)
    for i in range(bands):
        x = -W / 2 + W * (i + 1) / (bands + 1)
        box((bw, D + 2 * e, hb + 0.002), at=(x, 0, z0 - 0.001), mat=mm, bevel=0.002)
        lid_part(bw, r * 1.01 + e, x, mm)
    if corner_caps:
        c = min(W, D, hb) * 0.18
        for sx in (-1, 1):
            for sy in (-1, 1):
                for zz in (z0 - 0.002, z0 + hb - c + 0.002):
                    box((c + e, c + e, c), at=(sx * (W / 2 - c / 2 + e / 2), sy * (D / 2 - c / 2 + e / 2), zz), mat=mm, bevel=0.002)
    if lock:
        pw, ph = W * 0.11, hb * 0.32
        box((pw, 0.02, ph), at=(0, -D / 2 - 0.008, z0 + hb - ph + 0.005), mat=mm, bevel=0.003)
        box((pw * 0.45, 0.02, hl * 0.35), at=(0, -D / 2 - 0.012, z0 + hb - 0.01), mat=mm, bevel=0.002)
        cylinder(pw * 0.12, 0.012, at=(0, -D / 2 - 0.02, z0 + hb - ph * 0.55), axis="Y", mat=material("hole", (0.02, 0.02, 0.02)))


def crate(width, depth, height, planks, wood, frame, braces):
    W, D, H = width, depth, height
    wm = _wood(wood)
    dark = _wood(tuple(c * 0.7 for c in wood))
    t, gap = 0.02, H * 0.012
    box((W - 2 * t, D - 2 * t, H - 2 * t), at=(0, 0, t), mat=dark)  # inner core hides gaps
    ph = (H - gap * (planks + 1)) / planks
    for i in range(planks):
        z = gap + i * (ph + gap)
        for sy in (-1, 1):
            box((W, t, ph), at=(0, sy * (D / 2 - t / 2), z), mat=wm, bevel=0.003)
        for sx in (-1, 1):
            box((t, D - 2 * t, ph), at=(sx * (W / 2 - t / 2), 0, z), mat=wm, bevel=0.003)
    box((W - 2 * t, D - 2 * t, t), at=(0, 0, H - t), mat=wm, bevel=0.003)
    if frame:
        f = min(W, D, H) * 0.09
        for sx in (-1, 1):
            for sy in (-1, 1):
                box((f, f, H), at=(sx * (W / 2 - f / 2 + 0.004), sy * (D / 2 - f / 2 + 0.004), 0), mat=wm, bevel=0.004)
        for zz in (0, H - f):
            for sy in (-1, 1):
                box((W, f, f), at=(0, sy * (D / 2 - f / 2 + 0.006), zz), mat=wm, bevel=0.004)
            for sx in (-1, 1):
                box((f, D, f), at=(sx * (W / 2 - f / 2 + 0.006), 0, zz), mat=wm, bevel=0.004)
    if braces:  # diagonal brace inside the frame on front and back
        f = min(W, D, H) * 0.09 if frame else 0.0
        iw, ih = W - 2 * f, H - 2 * f
        ang = math.degrees(math.atan2(ih, iw))
        bt = min(W, H) * 0.08
        for sy in (-1, 1):
            box((math.hypot(iw, ih) - bt * 1.2, 0.02, bt), at=(0, sy * (D / 2 + 0.008), H / 2 - bt / 2),
                mat=wm, bevel=0.003, rot=(0, ang, 0))


def barrel(height, radius, bulge, hoops, wood, metal, lid):
    H, R = height, radius
    wm, mm = _wood(wood), _metal(metal, 0.45)
    rend = R * (1 - bulge)
    rad = lambda t: rend + (R - rend) * math.sin(math.pi * t)
    n = 16
    prof = [(0, 0)] + [(rad(i / n), H * i / n) for i in range(n + 1)]
    if lid:
        prof += [(rend * 0.93, H), (rend * 0.93, H - 0.025), (0, H - 0.025)]
    else:
        prof += [(0, H)]
    lathe(prof, mat=wm, segments=40)
    ts = {2: (0.12, 0.88), 3: (0.1, 0.5, 0.9), 4: (0.09, 0.3, 0.7, 0.91)}[hoops]
    for t in ts:
        torus(rad(t) + 0.004, 0.009, at=(0, 0, H * t), mat=mm, scale=(1, 1, 2.2))


def table(width, depth, height, top_thickness, legs, round_top, apron, wood):
    W, D, H, T = width, depth, height, top_thickness
    wm = _wood(wood)
    lh = H - T
    lt = max(0.03, min(W, D) * 0.06)
    if round_top:
        cylinder(W / 2, T, at=(0, 0, lh), mat=wm, bevel=0.004, verts=64)
        pos = [(math.cos(a) * W * 0.3, math.sin(a) * W * 0.3) for a in (math.pi / 4, 3 * math.pi / 4, 5 * math.pi / 4, 7 * math.pi / 4)]
    else:
        box((W, D, T), at=(0, 0, lh), mat=wm, bevel=0.006)
        ix, iy = W / 2 - lt * 1.2, D / 2 - lt * 1.2
        pos = [(sx * ix, sy * iy) for sx in (-1, 1) for sy in (-1, 1)]
    for x, y in pos:
        if legs == "square":
            box((lt, lt, lh), at=(x, y, 0), mat=wm, bevel=0.003)
        elif legs == "round":
            cylinder(lt / 2, lh, at=(x, y, 0), mat=wm, verts=24)
        else:
            cylinder(lt * 0.28, lh, at=(x, y, 0), mat=wm, verts=24, radius2=lt * 0.55)
    if apron and not round_top:
        ah = min(0.1, lh * 0.15)
        for sy in (-1, 1):
            box((2 * ix, lt * 0.5, ah), at=(0, sy * iy, lh - ah), mat=wm)
        for sx in (-1, 1):
            box((lt * 0.5, 2 * iy, ah), at=(sx * ix, 0, lh - ah), mat=wm)


def chair(seat_height, seat_width, seat_depth, back_height, back, slats, armrests, cushion, wood, cushion_color):
    SH, SW, SD, BH = seat_height, seat_width, seat_depth, back_height
    wm = _wood(wood)
    lt, st = 0.035, 0.035
    ix, iy = SW / 2 - lt / 2, SD / 2 - lt / 2
    for sx in (-1, 1):
        box((lt, lt, SH - st), at=(sx * ix, -iy, 0), mat=wm, bevel=0.003)
        box((lt, lt, SH + BH), at=(sx * ix, iy, 0), mat=wm, bevel=0.003)  # back posts
    box((SW, SD, st), at=(0, 0, SH - st), mat=wm, bevel=0.005)
    for sy in (-1, 1):  # stretchers
        box((SW - lt, lt * 0.5, lt * 0.6), at=(0, sy * iy, SH * 0.25), mat=wm)
    for sx in (-1, 1):
        box((lt * 0.5, SD - lt, lt * 0.6), at=(sx * ix, 0, SH * 0.2), mat=wm)
    rail = BH * 0.16
    box((SW - lt, lt * 0.8, rail), at=(0, iy, SH + BH - rail), mat=wm, bevel=0.003)
    span_z, span_h = SH + 0.02, BH - rail - 0.02
    if back == "solid":
        box((SW - lt, lt * 0.5, span_h), at=(0, iy, span_z), mat=wm, bevel=0.003)
    else:
        k = slats if back == "slats" else slats + 2
        for i in range(k):
            x = -ix + (2 * ix) * (i + 1) / (k + 1)
            if back == "slats":
                box(((2 * ix) / (k + 1) * 0.55, lt * 0.4, span_h), at=(x, iy, span_z), mat=wm, bevel=0.002)
            else:
                cylinder(0.009, span_h, at=(x, iy, span_z), mat=wm, verts=12)
    if armrests:
        for sx in (-1, 1):
            box((lt * 0.8, lt * 0.8, 0.22), at=(sx * ix, -iy, SH), mat=wm, bevel=0.002)
            box((lt * 1.3, SD, lt * 0.7), at=(sx * ix, 0, SH + 0.22), mat=wm, bevel=0.004)
    if cushion:
        box((SW * 0.94, SD * 0.94, 0.05), at=(0, 0, SH), mat=material("fabric", cushion_color, 0.9), bevel=0.018)


def stool(height, seat_radius, legs, round_seat, wood):
    H, R = height, seat_radius
    wm = _wood(wood)
    st = 0.035
    if round_seat:
        cylinder(R, st, at=(0, 0, H - st), mat=wm, bevel=0.006, verts=48)
    else:
        box((R * 2, R * 2, st), at=(0, 0, H - st), mat=wm, bevel=0.006)
    for i in range(legs):
        a = 2 * math.pi * i / legs + math.pi / legs
        top = (math.cos(a) * R * 0.65, math.sin(a) * R * 0.65, H - st)
        bot = (math.cos(a) * R * 1.05, math.sin(a) * R * 1.05, 0)
        _rod(bot, top, 0.016, wm)
    rz = H * 0.35
    for i in range(legs):
        a0, a1 = [2 * math.pi * j / legs + math.pi / legs for j in (i, i + 1)]
        rr = R * (1.05 - 0.4 * 0.35)
        _rod((math.cos(a0) * rr, math.sin(a0) * rr, rz), (math.cos(a1) * rr, math.sin(a1) * rr, rz), 0.009, wm)


def bench(length, height, depth, backrest, wood, metal_legs, metal):
    L, H, D = length, height, depth
    wm = _wood(wood)
    lm = _metal(metal, 0.5) if metal_legs else wm
    n, t = 4, 0.03
    sw = (D - 0.01 * (n - 1)) / n
    for i in range(n):
        box((L, sw, t), at=(0, -D / 2 + sw / 2 + i * (sw + 0.01), H - t), mat=wm, bevel=0.003)
    for sx in (-1, 1):
        x = sx * (L / 2 - 0.12)
        for sy in (-1, 1):
            box((0.05, 0.05, H - t), at=(x, sy * (D / 2 - 0.05), 0), mat=lm, bevel=0.003)
        box((0.05, D, 0.05), at=(x, 0, H - t - 0.05), mat=lm)
        if backrest:
            box((0.05, 0.05, 0.45), at=(x, D / 2 - 0.03, H - t), mat=lm, bevel=0.003, rot=(-10, 0, 0))
    if backrest:
        for k in range(2):
            box((L, 0.025, 0.09), at=(0, D / 2 + 0.01, H + 0.15 + k * 0.15), mat=wm, bevel=0.003, rot=(-10, 0, 0))


def bookshelf(width, height, depth, shelves, books, back_panel, wood):
    W, H, D = width, height, depth
    wm = _wood(wood)
    t = 0.022
    for sx in (-1, 1):
        box((t, D, H), at=(sx * (W / 2 - t / 2), 0, 0), mat=wm, bevel=0.002)
    box((W, D, t), at=(0, 0, H - t), mat=wm, bevel=0.002)
    box((W - 2 * t, D, 0.06), at=(0, 0, 0), mat=wm)
    if back_panel:
        box((W - 2 * t, 0.008, H - t), at=(0, D / 2 - 0.004, 0), mat=_wood(tuple(c * 0.8 for c in wood)))
    gap = (H - 0.06 - t) / (shelves + 1)
    levels = [0.06 + i * gap for i in range(shelves + 1)]
    for z in levels[1:]:
        box((W - 2 * t, D - 0.01, t), at=(0, -0.005, z - t / 2), mat=wm)
    if books:
        rnd = random.Random(7)
        palette = [(0.5, 0.1, 0.08), (0.1, 0.25, 0.45), (0.15, 0.35, 0.18), (0.6, 0.45, 0.15), (0.3, 0.12, 0.3), (0.85, 0.8, 0.7)]
        for z in levels:
            x, end = -W / 2 + t + 0.01, W / 2 - t - 0.01 - rnd.uniform(0, W * 0.25)
            base = z + (t / 2 if z > 0.06 else 0)
            while x < end:
                bw = rnd.uniform(0.018, 0.045)
                bh = min(gap - t - 0.02, rnd.uniform(0.17, 0.28))
                box((bw, D * rnd.uniform(0.6, 0.8), bh), at=(x + bw / 2, -D * 0.05, base), bevel=0.002,
                    mat=material("book", rnd.choice(palette), 0.6))
                x += bw + 0.002


def cabinet(width, height, depth, drawers, doors, legs, wood, handle):
    W, H, D = width, height, depth
    wm, hm = _wood(wood), _metal(handle, 0.3)
    z0 = 0.1 if legs else 0.0
    if legs:
        for sx in (-1, 1):
            for sy in (-1, 1):
                cylinder(0.018, z0, at=(sx * (W / 2 - 0.05), sy * (D / 2 - 0.05), 0), mat=wm, radius2=0.025)
    box((W, D, H - z0), at=(0, 0, z0), mat=wm, bevel=0.004)
    box((W + 0.02, D + 0.02, 0.025), at=(0, 0, H), mat=wm, bevel=0.005)
    m, fy = 0.02, -D / 2 - 0.009
    body = H - z0 - 2 * m
    dh = (body * (0.55 if doors else 1.0)) / max(drawers, 1) if drawers else 0
    z = z0 + H - z0 - m
    for i in range(drawers):
        z -= dh
        box((W - 2 * m, 0.018, dh - 0.012), at=(0, fy, z + 0.006), mat=wm, bevel=0.003)
        cylinder(0.008, W * 0.18, at=(0, fy - 0.022, z + dh / 2), axis="X", mat=hm)
    if doors:
        rem = z - (z0 + m)
        dw = (W - 2 * m) / doors
        for i in range(doors):
            x = -W / 2 + m + dw * (i + 0.5)
            box((dw - 0.01, 0.018, rem - 0.012), at=(x, fy, z0 + m + 0.006), mat=wm, bevel=0.003)
            hx = x + (dw * 0.35 if doors == 1 else (dw * 0.38 if i == 0 else -dw * 0.38))
            cylinder(0.008, rem * 0.25, at=(hx, fy - 0.022, z0 + m + rem * 0.4), mat=hm)


def lamp(kind, height, shade_radius, base_color, shade_color, glow):
    H, R = height, shade_radius
    bm = material("base", base_color, 0.35, 0.6)
    sm = material("shade", shade_color, 0.85, emit=0.6 if glow else 0)
    bulb = material("bulb", (1, 0.85, 0.55), 0.3, emit=8 if glow else 0)
    if kind == "lantern":
        w = R * 1.4
        box((w * 1.15, w * 1.15, H * 0.06), at=(0, 0, 0), mat=bm, bevel=0.004)
        for sx in (-1, 1):
            for sy in (-1, 1):
                box((0.012, 0.012, H * 0.62), at=(sx * w / 2, sy * w / 2, H * 0.06), mat=bm)
        box((w * 0.98, w * 0.98, H * 0.6), at=(0, 0, H * 0.07), mat=material("glass", (1, 0.9, 0.7), 0.05, alpha=0.35,
                                                                            emit=0.8 if glow else 0))
        cone(w * 0.8, H * 0.22, at=(0, 0, H * 0.68), mat=bm, verts=4).rotation_euler.z = math.pi / 4
        torus(H * 0.07, 0.008, at=(0, 0, H * 0.95), axis="Y", mat=bm)
        cylinder(w * 0.12, H * 0.25, at=(0, 0, H * 0.07), mat=material("wax", (0.95, 0.92, 0.82), 0.6))
        sphere(w * 0.06, at=(0, 0, H * 0.36), mat=bulb, scale=(1, 1, 1.8))
        return
    if kind == "floor":
        cylinder(R * 1.3, 0.03, at=(0, 0, 0), mat=bm, bevel=0.005, verts=48)
        cylinder(0.012, H - R * 1.1, at=(0, 0, 0.03), mat=bm)
        sh, top = R * 1.2, H
    else:
        lathe([(0, 0), (R * 0.75, 0), (R * 0.75, 0.02), (R * 0.45, 0.05), (R * 0.3, H * 0.25), (R * 0.12, H * 0.42),
               (0.012, H * 0.45), (0, H * 0.45)], mat=bm)
        cylinder(0.01, H * 0.25, at=(0, 0, H * 0.45), mat=bm)
        sh, top = R * 1.0, H
    sphere(R * 0.18, at=(0, 0, top - sh * 0.7), mat=bulb)
    lathe([(R, top - sh), (R * 0.62, top), (R * 0.6, top), (R * 0.97, top - sh)], mat=sm, closed=False)


def sword(blade_length, blade_width, guard_width, grip_length, pommel, blade_color, guard_color, grip_color):
    L, w, G, g = blade_length, blade_width, guard_width, grip_length
    steel, gm, lm = _metal(blade_color, 0.2), _metal(guard_color, 0.3), material("grip", grip_color, 0.85)
    z = 0.0
    if pommel:
        sphere(w * 0.55, at=(0, 0, w * 0.55), mat=gm)
        z = w * 0.9
    cylinder(w * 0.32, g, at=(0, 0, z), mat=lm, verts=16)
    for k in range(int(g / 0.02)):
        torus(w * 0.33, 0.003, at=(0, 0, z + 0.01 + k * 0.02), mat=lm)
    z += g
    box((G, w * 0.6, w * 0.45), at=(0, 0, z), mat=gm, bevel=0.004)
    for sx in (-1, 1):
        sphere(w * 0.3, at=(sx * G / 2, 0, z + w * 0.22), mat=gm)
    z += w * 0.45
    tip = min(L * 0.25, w * 2.5)
    prism([(-w / 2, 0), (w / 2, 0), (w * 0.42, L - tip), (0, L), (-w * 0.42, L - tip)], max(0.006, w * 0.14),
          at=(0, 0, z), mat=steel, axis="Y", bevel=0.0015)


def axe(handle_length, head_width, double, metal, wood):
    L, hw = handle_length, head_width
    mm, wm = _metal(metal, 0.3), _wood(wood)
    cylinder(0.017, L, at=(0, 0, 0), mat=wm, radius2=0.014)
    hz = L * 0.88
    blade = [(0.02, -hw * 0.18), (hw * 0.55, -hw * 0.5), (hw, -hw * 0.6), (hw, hw * 0.6), (hw * 0.55, hw * 0.5), (0.02, hw * 0.18)]
    prism(blade, 0.018, at=(0, 0, hz), mat=mm, axis="Y", bevel=0.002)
    if double:
        prism([(-x, z) for x, z in reversed(blade)], 0.018, at=(0, 0, hz), mat=mm, axis="Y", bevel=0.002)
    else:
        box((hw * 0.25, 0.03, hw * 0.3), at=(-hw * 0.12, 0, hz - hw * 0.15), mat=mm, bevel=0.003)
    cylinder(0.024, hw * 0.4, at=(0, 0, hz - hw * 0.2), mat=mm)


def shield(kind, size, face_color, rim_color, boss, rim):
    S = size
    fm, rm = material("face", face_color, 0.6), _metal(rim_color, 0.4)
    if kind == "round":
        cylinder(S / 2, 0.03, at=(0, 0, S / 2), axis="Y", mat=fm, verts=64)
        if rim:
            torus(S / 2, 0.018, at=(0, 0, S / 2), axis="Y", mat=rm)
        if boss:
            sphere(S * 0.12, at=(0, -0.01, S / 2), mat=rm, scale=(1, 0.6, 1))
        return
    if kind == "kite":
        pts = [(0, 0), (S * 0.42, S * 0.55), (S * 0.4, S * 0.95), (S * 0.2, S * 1.05), (-S * 0.2, S * 1.05),
               (-S * 0.4, S * 0.95), (-S * 0.42, S * 0.55)]
    else:  # heater
        pts = [(0, 0)] + [(S * 0.45 * math.sin(a), S * 0.35 * (1 - math.cos(a))) for a in [i * math.pi / 2 / 8 for i in range(1, 9)]]
        pts += [(S * 0.45, S * 0.85), (-S * 0.45, S * 0.85)] + [(-x, z) for x, z in reversed(pts[1:])]
    prism(pts, 0.03, at=(0, 0, 0), mat=fm, axis="Y", bevel=0.004)
    if rim:
        c = sum(z for _, z in pts) / len(pts)
        o = prism(pts, 0.022, at=(0, 0.008, 0), mat=rm, axis="Y")
        o.scale = (1.05, 1, 1.04)
        o.location.z = -c * 0.04
    if boss:
        sphere(S * 0.1, at=(0, -0.012, S * 0.55), mat=rm, scale=(1, 0.6, 1))


def bottle(kind, height, radius, glass_color, cork, label, label_color, liquid_glow):
    H, R = height, radius
    gm = material("glass", glass_color, 0.05, emit=1.5 if liquid_glow else 0, alpha=0.55)
    profs = {
        "wine": [(0, 0), (R, 0), (R, H * 0.62), (R * 0.85, H * 0.7), (R * 0.32, H * 0.82), (R * 0.28, H), (0, H)],
        "potion": [(0, 0), (R * 0.6, 0), (R, H * 0.2), (R, H * 0.45), (R * 0.6, H * 0.62), (R * 0.28, H * 0.68),
                   (R * 0.28, H * 0.92), (R * 0.36, H * 0.95), (R * 0.32, H), (0, H)],
        "jar": [(0, 0), (R, 0), (R, H * 0.85), (R * 0.85, H * 0.9), (R * 0.85, H), (0, H)],
        "flask": [(0, 0), (R, 0), (R * 0.98, H * 0.08), (R * 0.4, H * 0.62), (R * 0.22, H * 0.7), (R * 0.22, H), (0, H)],
    }
    p = profs[kind]
    lathe(p, mat=gm)
    neck_r, top = p[-2][0], H
    if cork:
        if kind == "jar":
            cylinder(R * 0.9, H * 0.08, at=(0, 0, H), mat=_metal((0.6, 0.6, 0.6)), verts=48)
        else:
            cylinder(neck_r * 0.95, H * 0.1, at=(0, 0, top - H * 0.04), mat=material("cork", (0.6, 0.45, 0.28), 0.9), radius2=neck_r * 1.1)
    if label and kind in ("wine", "jar"):
        cylinder(R * 1.006, H * 0.25, at=(0, 0, H * 0.22), mat=material("label", label_color, 0.8), verts=48)


def mug(height, radius, handle, color):
    H, R = height, radius
    t = max(0.004, R * 0.09)
    cm = material("ceramic", color, 0.25)
    lathe([(0, 0), (R * 0.92, 0), (R, t), (R, H), (R - t, H), (R - t, t * 1.5), (0, t * 1.5)], mat=cm)
    if handle:
        torus(H * 0.3, t * 1.1, at=(R + H * 0.18, 0, H * 0.5), axis="Y", mat=cm, scale=(0.75, 1, 1))


def vase(height, radius, neck, color, glossy):
    H, R = height, radius
    vm = material("glaze", color, 0.15 if glossy else 0.7)
    nr = R * (1 - neck * 0.8)
    lathe([(0, 0), (R * 0.55, 0), (R * 0.85, H * 0.15), (R, H * 0.38), (R * 0.85, H * 0.6), (nr, H * 0.8),
           (nr * 0.92, H * 0.9), (nr * 1.25, H), (nr * 1.15, H), (nr * 0.8, H * 0.92), (0, H * 0.9)], mat=vm, segments=56)


def candle(height, radius, holder, wax_color, holder_color):
    H, R = height, radius
    z = 0.0
    if holder:
        hm = _metal(holder_color, 0.3)
        lathe([(0, 0), (R * 3, 0), (R * 3, 0.008), (R * 1.4, 0.016), (R * 1.25, 0.04), (R * 1.3, 0.05), (0, 0.05)], mat=hm)
        z = 0.05
    cylinder(R, H, at=(0, 0, z), mat=material("wax", wax_color, 0.6), verts=24)
    cylinder(0.0015, 0.012, at=(0, 0, z + H), mat=material("wick", (0.05, 0.05, 0.05)))
    sphere(R * 0.35, at=(0, 0, z + H + 0.02), mat=material("flame", (1, 0.6, 0.15), emit=10), scale=(1, 1, 2.2))


def tree(kind, height, trunk_color, leaf_color):
    H = height
    tm, lm = material("bark", trunk_color, 0.9), material("leaves", leaf_color, 0.8)
    if kind == "pine":
        cylinder(H * 0.035, H * 0.3, at=(0, 0, 0), mat=tm, verts=8)
        for i, (r, z, h) in enumerate([(0.3, 0.18, 0.4), (0.24, 0.4, 0.35), (0.17, 0.6, 0.32), (0.1, 0.78, 0.22)]):
            cone(H * r, H * h, at=(0, 0, H * z), mat=lm, verts=8)
    else:
        cylinder(H * 0.05, H * 0.5, at=(0, 0, 0), mat=tm, verts=8, radius2=H * 0.035)
        rnd = random.Random(3)
        for x, y, z, r in [(0, 0, 0.66, 0.28), (0.14, 0.05, 0.56, 0.2), (-0.13, -0.06, 0.58, 0.21), (0.03, -0.12, 0.78, 0.18)]:
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=H * r, location=(H * x, H * y, H * z))
            o = bpy.context.object
            o.rotation_euler = (rnd.random(), rnd.random(), rnd.random())
            o.data.materials.append(lm)


def rock(size, seed, color, flat):
    S = size
    rnd = random.Random(seed)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=S / 2, location=(0, 0, 0))
    o = bpy.context.object
    for v in o.data.vertices:
        v.co *= rnd.uniform(0.78, 1.12)
        v.co.z *= (1 - flat)
    o.scale = (rnd.uniform(0.9, 1.3), rnd.uniform(0.8, 1.1), 1)
    o.data.materials.append(material("stone", color, 0.95))
    o.modifiers.new("dec", 'DECIMATE').ratio = 0.6


def door(width, height, panels, frame, wood, handle):
    W, H = width, height
    wm, hm = _wood(wood), _metal(handle, 0.3)
    t = 0.045
    box((W, t, H), at=(0, 0, 0), mat=wm, bevel=0.004)
    cols = 1 if panels < 4 else 2
    rows = max(1, panels // cols)
    m = 0.09
    pw, ph = (W - m * (cols + 1)) / cols, (H - m * (rows + 1)) / rows
    for c in range(cols):
        for r in range(rows):
            box((pw, 0.012, ph), at=(-W / 2 + m + pw / 2 + c * (pw + m), -t / 2 - 0.004, m + r * (ph + m)), mat=wm, bevel=0.01)
    sphere(0.028, at=(W / 2 - 0.08, -t / 2 - 0.05, H * 0.47), mat=hm)
    cylinder(0.01, 0.05, at=(W / 2 - 0.08, -t / 2 - 0.025, H * 0.47), axis="Y", mat=hm)
    if frame:
        f = 0.07
        for sx in (-1, 1):
            box((f, t * 2.2, H + f), at=(sx * (W / 2 + f / 2), 0, 0), mat=wm, bevel=0.004)
        box((W + 2 * f, t * 2.2, f), at=(0, 0, H), mat=wm, bevel=0.004)


def fence(length, height, posts, rails, pickets, wood):
    L, H = length, height
    wm = _wood(wood)
    p = 0.08
    for i in range(posts):
        x = -L / 2 + L * i / (posts - 1)
        box((p, p, H * 1.05), at=(x, 0, 0), mat=wm, bevel=0.005)
        cone(p * 0.72, p * 0.6, at=(x, 0, H * 1.05), mat=wm, verts=4).rotation_euler.z = math.pi / 4
    for k in range(rails):
        z = H * (0.25 + 0.55 * k / max(rails - 1, 1))
        box((L, 0.03, 0.07), at=(0, p / 2 + 0.015, z), mat=wm, bevel=0.003)
    if pickets:
        n = int(L / 0.12)
        for i in range(n):
            x = -L / 2 + (i + 0.5) * L / n
            prism([(-0.035, 0), (0.035, 0), (0.035, H * 0.88), (0, H * 0.95), (-0.035, H * 0.88)], 0.018,
                  at=(x, p / 2 + 0.04, 0.03), mat=wm, axis="Y")


def goblet(height, radius, color, metallic):
    H, R = height, radius
    gm = material("goblet", color, 0.25, 0.95 if metallic else 0.0)
    lathe([(0, 0), (R * 0.9, 0), (R * 0.9, H * 0.02), (R * 0.2, H * 0.08), (R * 0.12, H * 0.4), (R * 0.25, H * 0.48),
           (R * 0.8, H * 0.6), (R, H), (R * 0.93, H), (R * 0.72, H * 0.62), (R * 0.15, H * 0.52), (0, H * 0.52)], mat=gm)


BUILDERS = {n: globals()[n] for n in TEMPLATES}
