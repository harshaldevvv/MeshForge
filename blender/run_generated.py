# Runs an LLM-written modeling script (already allow-list checked by meshforge.local.check_script)
# in an empty scene and exports everything it built as one GLB.
# The script gets a small modeling KIT (below) so models describe parts in real sizes instead of
# fighting Blender's transform rules (default cube = 2 m, scale vs size, rotations).
# Usage: blender -b --factory-startup -P blender/run_generated.py -- script.py out.glb
import bpy, bmesh, math, mathutils, random, sys, os, traceback

_mats = {}


def material(name, color, rough=0.6, metal=0.0, emit=0.0):
    """Get/create a material. color = (r, g, b) in 0..1."""
    if name in _mats:
        return _mats[name]
    m = bpy.data.materials.new(name)
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color[:3], 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit:
        b.inputs["Emission Color"].default_value = (*color[:3], 1)
        b.inputs["Emission Strength"].default_value = emit
    _mats[name] = m
    return m


def _finish(o, mat, bevel, rot, smooth=False):
    if rot:
        o.rotation_euler = tuple(math.radians(a) for a in rot)
    if mat is not None:
        o.data.materials.append(mat if not isinstance(mat, str) else material(mat, (0.7, 0.7, 0.7)))
    if bevel:
        m = o.modifiers.new("bevel", 'BEVEL')
        m.width, m.segments = bevel, 2
    if smooth:
        for p in o.data.polygons:
            p.use_smooth = True
    return o


def _axis_rot(axis):
    return {"Z": None, "X": (0, 90, 0), "Y": (90, 0, 0)}[axis.upper()]


def box(size, at=(0, 0, 0), mat=None, bevel=0.0, rot=None):
    """Box with full dimensions size=(x, y, z) metres. at = (x, y, z of the BOTTOM face)."""
    sx, sy, sz = size
    bpy.ops.mesh.primitive_cube_add(size=1, location=(at[0], at[1], at[2] + sz / 2))
    o = bpy.context.object
    o.scale = (sx, sy, sz)
    bpy.ops.object.transform_apply(scale=True)
    return _finish(o, mat, bevel, rot)


def cylinder(radius, height, at=(0, 0, 0), axis="Z", mat=None, bevel=0.0, verts=32, radius2=None):
    """Cylinder (or cone if radius2 is given). axis Z: at = centre of the bottom. axis X/Y: at = centre."""
    z = at[2] + height / 2 if axis.upper() == "Z" else at[2]
    if radius2 is None:
        bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=height, vertices=verts, location=(at[0], at[1], z))
    else:
        bpy.ops.mesh.primitive_cone_add(radius1=radius, radius2=radius2, depth=height, vertices=verts, location=(at[0], at[1], z))
    return _finish(bpy.context.object, mat, bevel, _axis_rot(axis), smooth=True)


def cone(radius, height, at=(0, 0, 0), axis="Z", mat=None, radius_top=0.0, verts=32):
    """Cone / tapered cylinder. axis Z: at = centre of the bottom."""
    return cylinder(radius, height, at, axis, mat, 0.0, verts, radius2=radius_top)


def sphere(radius, at=(0, 0, 0), mat=None, scale=(1, 1, 1)):
    """Sphere centred at `at`; scale stretches it into an ellipsoid."""
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=at, segments=32, ring_count=16)
    o = bpy.context.object
    o.scale = scale
    return _finish(o, mat, 0, None, smooth=True)


def torus(radius, thickness, at=(0, 0, 0), axis="Z", mat=None):
    """Ring centred at `at`; radius = ring radius, thickness = tube radius."""
    bpy.ops.mesh.primitive_torus_add(major_radius=radius, minor_radius=thickness, location=at)
    return _finish(bpy.context.object, mat, 0, _axis_rot(axis), smooth=True)


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


KIT = dict(material=material, box=box, cylinder=cylinder, cone=cone, sphere=sphere, torus=torus,
           mirror_x=mirror_x, array=array)

if __name__ == "__main__":
    code_path, out = (os.path.abspath(a) for a in sys.argv[sys.argv.index("--") + 1:][:2])
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        code = open(code_path, encoding="utf-8").read()
        exec(compile(code, "model_script.py", "exec"), {"__name__": "__main__", "bpy": bpy, "bmesh": bmesh,
             "math": math, "mathutils": mathutils, "random": random, **KIT})
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        meshes = [o for o in bpy.context.scene.objects if o.type in ('MESH', 'CURVE', 'SURFACE', 'META', 'FONT')]
        if not meshes:
            raise RuntimeError("the script created no mesh objects")
        bpy.ops.object.select_all(action='DESELECT')
        for o in meshes:
            o.select_set(True)
        bpy.context.view_layer.objects.active = meshes[0]
        bpy.ops.object.convert(target='MESH')  # applies modifiers, turns curves/text into meshes
        # stand it on the ground, centred (small models often get this wrong)
        pts = [o.matrix_world @ mathutils.Vector(c) for o in meshes for c in o.bound_box]
        lo = mathutils.Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        hi = mathutils.Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        shift = mathutils.Vector((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z))
        for o in meshes:
            o.location += shift
        bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', use_selection=True, export_apply=True)
        print(f"GEN_OK {len(meshes)} objects")
    except Exception:
        print("GEN_ERROR " + traceback.format_exc().strip().splitlines()[-1], file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(1)
