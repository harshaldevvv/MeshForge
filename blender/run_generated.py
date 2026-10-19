# Runs a generated modeling script in an empty scene and exports everything it built as one GLB.
# Scripts are either a template call written by MeshForge (make("chest", width=...)) or LLM-written code
# that already passed meshforge.local.check_script. Both get the modeling kit (kit.py) and make().
# Usage: blender -b --factory-startup -P blender/run_generated.py -- script.py out.glb
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmesh, bpy, math, mathutils, random  # noqa: E401,E402
import kit  # noqa: E402
import templates  # noqa: E402


def make(name, **params):
    """Build a parametric template (see templates.py)."""
    return templates.BUILDERS[name](**params)


if __name__ == "__main__":
    code_path, out = (os.path.abspath(a) for a in sys.argv[sys.argv.index("--") + 1:][:2])
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        kit._mats.clear()
        code = open(code_path, encoding="utf-8").read()
        exec(compile(code, "model_script.py", "exec"), {"__name__": "__main__", "bpy": bpy, "bmesh": bmesh,
             "math": math, "mathutils": mathutils, "random": random, "make": make, **kit.KIT})
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
        lo = [min(p[i] for p in pts) for i in range(3)]
        hi = [max(p[i] for p in pts) for i in range(3)]
        shift = mathutils.Vector((-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]))
        for o in meshes:
            o.location += shift
        bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', use_selection=True, export_apply=True)
        print(f"GEN_OK {len(meshes)} objects")
    except Exception:
        print("GEN_ERROR " + traceback.format_exc().strip().splitlines()[-1], file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(1)
