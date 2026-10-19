# Headless post-processing: cleanup -> decimate to target -> UV -> bake hi->lo -> multi-format export.
# Usage: blender -b --factory-startup -P blender/pipeline.py -- in.glb outdir <target_tris|0=keep> [texture_px] [quads 0|1]
# Verified on Blender 5.2.2 LTS.
import bpy, sys, os


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    src, out, target = os.path.abspath(args[0]), os.path.abspath(args[1]), int(args[2])  # relative paths break bake save + FBX embed
    res = int(args[3]) if len(args) > 3 else 2048
    quads = len(args) > 4 and args[4] == "1"
    os.makedirs(out, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    p = bpy.context.preferences.addons['cycles'].preferences
    for dev in ('OPTIX', 'CUDA', 'HIP', 'ONEAPI'):
        try:
            p.compute_device_type = dev
            p.refresh_devices()
            if any(d.type != 'CPU' for d in p.devices):
                break
        except TypeError:
            continue
    gpu = False
    for d in p.devices:
        d.use = d.type != 'CPU'
        gpu |= d.use
    sc.cycles.device = 'GPU' if gpu else 'CPU'
    sc.cycles.samples = 16
    sc.cycles.use_denoising = False

    # import + join
    bpy.ops.import_scene.gltf(filepath=src)
    ms = [o for o in sc.objects if o.type == 'MESH']
    if not ms:
        raise RuntimeError("no mesh in input")
    bpy.ops.object.select_all(action='DESELECT')
    for o in ms:
        o.select_set(True)
    bpy.context.view_layer.objects.active = ms[0]
    if len(ms) > 1:
        bpy.ops.object.join()
    hi = bpy.context.object
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    diag = max(hi.dimensions.length, 1e-6)
    if not any(s.material for s in hi.material_slots):  # shape-only models (Hunyuan3D) come without a material
        clay = bpy.data.materials.new("clay")
        pb = clay.node_tree.nodes["Principled BSDF"]
        pb.inputs["Base Color"].default_value = (0.8, 0.8, 0.8, 1)
        pb.inputs["Metallic"].default_value = 0.0
        pb.inputs["Roughness"].default_value = 0.6
        if hi.data.color_attributes:  # multi-view projected colours (meshforge/projection.py)
            vc = clay.node_tree.nodes.new("ShaderNodeVertexColor")
            vc.layer_name = hi.data.color_attributes[0].name
            clay.node_tree.links.new(vc.outputs["Color"], pb.inputs["Base Color"])
            print("MESHFORGE_MAP: vertex colours")
        hi.data.materials.clear()
        hi.data.materials.append(clay)

    # cleanup
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.remove_doubles(threshold=1e-5)
    bpy.ops.mesh.dissolve_degenerate(threshold=1e-6)
    bpy.ops.mesh.delete_loose(use_verts=True, use_edges=True, use_faces=False)
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')

    # low-poly copy, decimated to the target triangle count
    lo = hi.copy()
    lo.data = hi.data.copy()
    lo.name = "low"
    sc.collection.objects.link(lo)
    bpy.ops.object.select_all(action='DESELECT')
    lo.select_set(True)
    bpy.context.view_layer.objects.active = lo
    count = lambda: sum(len(f.vertices) - 2 for f in lo.data.polygons)
    tris = count()

    def decimate(to):
        if to and to < count():
            m = lo.modifiers.new("dec", 'DECIMATE')
            m.decimate_type = 'COLLAPSE'
            m.ratio = to / count()
            m.use_collapse_triangulate = True
            bpy.ops.object.modifier_apply(modifier="dec")

    if quads:
        goal = target or tris
        lo.data.remesh_voxel_size = diag / 300  # watertight, closes holes in AI triangle soup
        bpy.ops.object.voxel_remesh()
        # QuadriFlow rejects many voxel meshes (non-manifold vertices); fall back to decimate + join tris
        if 'FINISHED' not in bpy.ops.object.quadriflow_remesh(mode='FACES', target_faces=max(100, goal // 2), seed=0):
            decimate(goal)
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.tris_convert_to_quads()
            bpy.ops.object.mode_set(mode='OBJECT')
    else:
        decimate(target)
    quad_n = sum(1 for f in lo.data.polygons if len(f.vertices) == 4)
    print(f"MESHFORGE_TRIS: {tris} -> {count()} ({quad_n} quads)")

    # UVs
    for uv in list(lo.data.uv_layers):
        lo.data.uv_layers.remove(uv)
    lo.data.uv_layers.new(name="UVMap")
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.003, margin_method='SCALED')
    bpy.ops.uv.pack_islands(rotate=True, margin=0.003, shape_method='CONCAVE')
    bpy.ops.object.mode_set(mode='OBJECT')

    # bake material (5.x: node_tree already exists with a Principled BSDF)
    lo.data.materials.clear()
    mat = bpy.data.materials.new("baked")
    lo.data.materials.append(mat)
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]

    def bake(kind, cs, name=None, **kw):
        name = name or kind.lower()
        img = bpy.data.images.new(name, res, res)
        img.colorspace_settings.name = cs
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = img
        nt.nodes.active = n
        bpy.ops.object.select_all(action='DESELECT')
        hi.select_set(True)
        lo.select_set(True)
        bpy.context.view_layer.objects.active = lo
        bpy.ops.object.bake(type=kind, use_selected_to_active=True, cage_extrusion=0.01 * diag,
                            max_ray_distance=0.03 * diag, margin=16, margin_type='EXTEND',
                            target='IMAGE_TEXTURES', save_mode='INTERNAL', **kw)
        img.filepath_raw = os.path.join(out, f"{name}.png")
        img.file_format = 'PNG'
        img.save()
        return n

    emit_max = [1.0]

    def bake_input(socket, name, cs):
        """Bake any Principled BSDF input of the high-poly materials via an Emission pass.
        (The DIFFUSE pass returns black for metallic surfaces, and glTF's default metallic is 1.0.)"""
        saved = []
        for slot in hi.material_slots:
            m = slot.material
            if not m or not m.node_tree:
                continue
            t = m.node_tree
            p = next((x for x in t.nodes if x.type == 'BSDF_PRINCIPLED'), None)
            outn = next((x for x in t.nodes if x.type == 'OUTPUT_MATERIAL' and x.is_active_output), None)
            if not p or not outn:
                continue
            em = t.nodes.new("ShaderNodeEmission")
            src = p.inputs[socket]
            strength = p.inputs["Emission Strength"]
            if socket == "Emission Color" and not src.is_linked and not strength.is_linked:
                f = strength.default_value / emit_max[0]  # relative glow; non-glowing parts stay black
                em.inputs["Color"].default_value = (*(c * f for c in src.default_value[:3]), 1)
            elif src.is_linked:
                t.links.new(src.links[0].from_socket, em.inputs["Color"])
            else:
                v = src.default_value
                em.inputs["Color"].default_value = (*v[:3], 1) if hasattr(v, "__len__") else (v, v, v, 1)
            prev = outn.inputs["Surface"].links[0].from_socket if outn.inputs["Surface"].is_linked else None
            t.links.new(em.outputs[0], outn.inputs["Surface"])
            saved.append((t, em, outn, prev))
        n = bake('EMIT', cs, name=name)
        for t, em, outn, prev in saved:
            if prev:
                t.links.new(prev, outn.inputs["Surface"])
            t.nodes.remove(em)
        return n

    dn = bake_input("Base Color", "diffuse", 'sRGB')
    nt.links.new(dn.outputs[0], bsdf.inputs["Base Color"])
    nt.links.new(bake_input("Metallic", "metallic", 'Non-Color').outputs[0], bsdf.inputs["Metallic"])

    # glass and glowing parts would otherwise be flattened into opaque, unlit colour
    import numpy as np
    pbs = [next((x for x in s.material.node_tree.nodes if x.type == 'BSDF_PRINCIPLED'), None)
           for s in hi.material_slots if s.material and s.material.node_tree]
    pbs = [p for p in pbs if p]
    if any(p.inputs["Alpha"].is_linked or p.inputs["Alpha"].default_value < 0.999 for p in pbs):
        an = bake_input("Alpha", "alpha", 'Non-Color')
        px = lambda im: (lambda a: (im.pixels.foreach_get(a), a)[1])(np.empty(len(im.pixels), np.float32))
        d, a = px(dn.image), px(an.image)
        d[3::4] = a[0::4]  # alpha into the diffuse PNG's alpha channel (what glTF expects)
        dn.image.alpha_mode = 'STRAIGHT'
        dn.image.pixels.foreach_set(d)
        dn.image.save()
        nt.links.new(dn.outputs["Alpha"], bsdf.inputs["Alpha"])
        mat.surface_render_method = 'BLENDED'
        print("MESHFORGE_MAP: alpha")
    glow = max([p.inputs["Emission Strength"].default_value for p in pbs if not p.inputs["Emission Strength"].is_linked] or [0])
    if glow > 0:
        emit_max[0] = glow
        nt.links.new(bake_input("Emission Color", "emission", 'sRGB').outputs[0], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = glow
        print("MESHFORGE_MAP: emission")
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(bake('NORMAL', 'Non-Color', normal_space='TANGENT').outputs[0], nm.inputs["Color"])
    nt.links.new(nm.outputs[0], bsdf.inputs["Normal"])
    nt.links.new(bake('ROUGHNESS', 'Non-Color').outputs[0], bsdf.inputs["Roughness"])
    sc.cycles.samples = 128
    bake('AO', 'Non-Color')  # ponytail: AO ships as a file only; pack into ORM when glTF AO matters

    # export low only
    bpy.data.objects.remove(hi)
    bpy.ops.object.select_all(action='DESELECT')
    lo.select_set(True)
    P = lambda e: os.path.join(out, "model." + e)
    bpy.ops.export_scene.gltf(filepath=P("glb"), export_format='GLB', use_selection=True)
    bpy.ops.export_scene.fbx(filepath=P("fbx"), use_selection=True, path_mode='COPY', embed_textures=True)
    bpy.ops.wm.obj_export(filepath=P("obj"), export_selected_objects=True, path_mode='COPY', export_materials=True)
    bpy.ops.wm.usd_export(filepath=P("usdz"), selected_objects_only=True, export_textures_mode='NEW',
                          generate_preview_surface=True)
    bpy.ops.wm.stl_export(filepath=P("stl"), export_selected_objects=True)
    bpy.ops.wm.ply_export(filepath=P("ply"), export_selected_objects=True)

    # small preview for the model card (fast workbench render with the baked texture)
    import mathutils
    pts = [lo.matrix_world @ mathutils.Vector(c) for c in lo.bound_box]
    ctr = sum(pts, mathutils.Vector()) / 8
    r = max((p - ctr).length for p in pts)
    bpy.ops.object.camera_add(location=ctr + mathutils.Vector((0.55, -1, 0.45)).normalized() * r * 2.7)
    cam = bpy.context.object
    cam.rotation_euler = (ctr - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sc.camera = cam
    nt.nodes.active = next(n for n in nt.nodes if n.type == 'TEX_IMAGE' and n.image and n.image.name == "diffuse")
    sc.render.engine = 'BLENDER_WORKBENCH'
    sc.display.shading.color_type = 'TEXTURE'
    sc.display.shading.light = 'STUDIO'
    sc.render.film_transparent = True
    sc.render.resolution_x = sc.render.resolution_y = 384
    sc.render.image_settings.file_format = 'PNG'
    sc.render.filepath = os.path.join(out, "preview.png")
    bpy.ops.render.render(write_still=True)


try:
    main()
except Exception as e:  # blender -b exits 0 on script errors otherwise
    print(f"MESHFORGE_ERROR: {e}", file=sys.stderr)
    sys.exit(1)
