"""Modeling kit used by templates.py and by LLM-written scripts (inside Blender only).
Sizes in metres, z up, ground at z=0. Parts are placed by their BOTTOM (z) so stacking is easy."""
import math

import bmesh
import bpy
import mathutils

_mats = {}


def material(name, color, rough=0.6, metal=0.0, emit=0.0, alpha=1.0):
    """Get/create a material. color = (r, g, b) in 0..1."""
    key = (name, tuple(round(c, 3) for c in color[:3]), rough, metal, emit, alpha)
    if key in _mats:
        return _mats[key]
    m = bpy.data.materials.new(name)
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color[:3], 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit:
        b.inputs["Emission Color"].default_value = (*color[:3], 1)
        b.inputs["Emission Strength"].default_value = emit
    if alpha < 1:
        b.inputs["Alpha"].default_value = alpha
        b.inputs["Transmission Weight"].default_value = 1 - alpha
    _mats[key] = m
    return m


def _finish(o, mat, bevel, rot, smooth=False):
    if rot:
        o.rotation_euler = tuple(math.radians(a) for a in rot)
    if mat is not None:
        o.data.materials.append(mat if not isinstance(mat, str) else material(mat, (0.7, 0.7, 0.7)))
    if bevel:
        m = o.modifiers.new("bevel", 'BEVEL')
        m.width, m.segments, m.limit_method = bevel, 2, 'ANGLE'
    if smooth:
        for p in o.data.polygons:
            p.use_smooth = True
    return o


def _axis_rot(axis):
    return {"Z": None, "X": (0, 90, 0), "Y": (90, 0, 0)}[axis.upper()]


def box(size, at=(0, 0, 0), mat=None, bevel=0.0, rot=None):
    """Box with full dimensions size=(x, y, z). at = (x, y, z of the BOTTOM face)."""
    sx, sy, sz = size
    bpy.ops.mesh.primitive_cube_add(size=1, location=(at[0], at[1], at[2] + sz / 2))
    o = bpy.context.object
    o.scale = (sx, sy, sz)
    bpy.ops.object.transform_apply(scale=True)
    return _finish(o, mat, bevel, rot)


def cylinder(radius, height, at=(0, 0, 0), axis="Z", mat=None, bevel=0.0, verts=32, radius2=None):
    """Cylinder (cone if radius2 given). axis Z: at = centre of the bottom. axis X/Y: at = centre."""
    z = at[2] + height / 2 if axis.upper() == "Z" else at[2]
    if radius2 is None:
        bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=height, vertices=verts, location=(at[0], at[1], z))
    else:
        bpy.ops.mesh.primitive_cone_add(radius1=radius, radius2=radius2, depth=height, vertices=verts,
                                        location=(at[0], at[1], z))
    return _finish(bpy.context.object, mat, bevel, _axis_rot(axis), smooth=verts > 12)


def cone(radius, height, at=(0, 0, 0), axis="Z", mat=None, radius_top=0.0, verts=32):
    return cylinder(radius, height, at, axis, mat, 0.0, verts, radius2=radius_top)


def sphere(radius, at=(0, 0, 0), mat=None, scale=(1, 1, 1), segments=32):
    """Sphere centred at `at`; scale stretches it into an ellipsoid."""
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=at, segments=segments, ring_count=max(8, segments // 2))
    o = bpy.context.object
    o.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    return _finish(o, mat, 0, None, smooth=segments > 8)


def torus(radius, thickness, at=(0, 0, 0), axis="Z", mat=None, scale=(1, 1, 1)):
    """Ring centred at `at`; radius = ring radius, thickness = tube radius."""
    bpy.ops.mesh.primitive_torus_add(major_radius=radius, minor_radius=thickness, location=at,
                                     major_segments=48, minor_segments=12)
    o = bpy.context.object
    o.scale = scale
    return _finish(o, mat, 0, _axis_rot(axis), smooth=True)


def lathe(profile, at=(0, 0, 0), mat=None, segments=48, closed=True):
    """Turned/revolved shape. profile = [(radius, z), ...] from bottom to top (z relative to at)."""
    me = bpy.data.meshes.new("lathe")
    bm = bmesh.new()
    pts = [(r, z) for r, z in profile]
    rings = []
    for i in range(segments):
        a = 2 * math.pi * i / segments
        rings.append([bm.verts.new((r * math.cos(a), r * math.sin(a), z)) for r, z in pts])
    for i in range(segments):
        r0, r1 = rings[i], rings[(i + 1) % segments]
        for j in range(len(pts) - 1):
            vs = [r0[j], r1[j], r1[j + 1], r0[j + 1]]
            if len({v.co.to_tuple(6) for v in vs}) >= 3:
                bm.faces.new(vs)
    if closed:
        for j in (0, len(pts) - 1):
            if pts[j][0] > 1e-5:
                ring = [rings[i][j] for i in range(segments)]
                bm.faces.new(ring if j else list(reversed(ring)))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new("lathe", me)
    bpy.context.scene.collection.objects.link(o)
    o.location = at
    return _finish(o, mat, 0, None, smooth=True)


def prism(points, height, at=(0, 0, 0), mat=None, bevel=0.0, axis="Z"):
    """Extruded flat shape. points = [(x, y), ...] outline; extruded `height` along axis (Z: up from at.z,
    Y: centred on at.y, outline in x/z)."""
    me = bpy.data.meshes.new("prism")
    bm = bmesh.new()
    if axis.upper() == "Z":
        bot = [bm.verts.new((x, y, 0)) for x, y in points]
        top = [bm.verts.new((x, y, height)) for x, y in points]
    else:  # Y: outline drawn in x/z, thickness along y
        bot = [bm.verts.new((x, -height / 2, z)) for x, z in points]
        top = [bm.verts.new((x, height / 2, z)) for x, z in points]
    bm.faces.new(list(reversed(bot)))
    bm.faces.new(top)
    n = len(points)
    for i in range(n):
        bm.faces.new([bot[i], bot[(i + 1) % n], top[(i + 1) % n], top[i]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new("prism", me)
    bpy.context.scene.collection.objects.link(o)
    o.location = at
    return _finish(o, mat, bevel, None)


def mirror_x(obj):
    """Copy of obj mirrored to the other side of x=0."""
    c = obj.copy()
    c.data = obj.data.copy()
    c.location.x = -obj.location.x
    c.rotation_euler.z = -obj.rotation_euler.z
    bpy.context.scene.collection.objects.link(c)
    return c


def array(obj, count, offset):
    """count copies of obj, each shifted by offset=(dx, dy, dz)."""
    out = [obj]
    for i in range(1, count):
        c = obj.copy()
        c.data = obj.data.copy()
        c.location = obj.location + mathutils.Vector(offset) * i
        bpy.context.scene.collection.objects.link(c)
        out.append(c)
    return out


KIT = dict(material=material, box=box, cylinder=cylinder, cone=cone, sphere=sphere, torus=torus, lathe=lathe,
           prism=prism, mirror_x=mirror_x, array=array)
