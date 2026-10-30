"""F09: bake to channel operators (Normal with swizzle, AO, Random, Position).

All write through `run_full_op` (only mask x effective channels). Geometry is read inside the
OBJECT-mode callback. Documented exceptions to "no Python loops over elements": the nearest-point
search for proxy normals (`BVHTree.find_nearest`) and AO ray casts (`BVHTree.ray_cast`).
"""

import bpy
import numpy as np
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty
from mathutils.bvhtree import BVHTree

from ..core import bake as B
from ..core.attributes import validate_color_attribute, write_colors
from ..core.channels import CHANNEL_ITEMS
from ..core.mode import ensure_object_mode
from ..core.topology import loop_vertex_indices, loose_parts
from ._common import _after_write, init_from_settings, poll_color_mesh, run_full_op
from .fill import SCOPE_ITEMS
from .gradient import vertex_positions, vertex_to_domain

_AO_CHUNK_RAYS = 200_000  # rays per chunk (bounds the direction array memory)


# --------------------------------------------------------------------------- helpers

def _init_bake(op, context, mapping: dict) -> None:
    """Copy unset props from Scene.badvc (operator prop -> settings prop), channels/scope as usual."""
    init_from_settings(op, context, ('channels', 'scope'))
    settings = context.scene.badvc
    for name, src in mapping.items():
        if op.properties.is_property_set(name):
            continue
        value = getattr(settings, src)
        if name == 'proxy':
            value = value.name if value is not None else ""
        setattr(op, name, value)


def _vec3(collection, n: int, attr: str = 'vector') -> np.ndarray:
    out = np.empty(n * 3, dtype=np.float32)
    if n:
        collection.foreach_get(attr, out)
    return out.reshape(-1, 3).astype(np.float64)


def _matrix(obj) -> np.ndarray:
    return np.array(obj.matrix_world, dtype=np.float64)


def _to_world(points: np.ndarray, mw: np.ndarray) -> np.ndarray:
    return points @ mw[:3, :3].T + mw[:3, 3]


def masked_vertices(mask: np.ndarray, mesh, domain: str) -> np.ndarray:
    """Bool (V,): vertices that own a masked element (POINT: the mask itself, CORNER: vertices of masked corners)."""
    if domain == 'POINT':
        return mask.copy()
    out = np.zeros(len(mesh.vertices), dtype=bool)
    out[loop_vertex_indices(mesh)[mask]] = True
    return out


def evaluated_world_geometry(obj, depsgraph):
    """(world verts (V,3), triangles (T,3) int32, world vertex normals (V,3)) of the evaluated mesh."""
    eo = obj.evaluated_get(depsgraph)
    me = eo.to_mesh()
    try:
        co = vertex_positions(me)
        nor = _vec3(me.vertex_normals, len(me.vertices))
        me.calc_loop_triangles()
        tris = np.empty(len(me.loop_triangles) * 3, dtype=np.int32)
        if len(tris):
            me.loop_triangles.foreach_get('vertices', tris)
        tris = tris.reshape(-1, 3)
    finally:
        eo.to_mesh_clear()
    mw = _matrix(obj)
    return _to_world(co, mw), tris, B.transform_normals(nor, mw[:3, :3])


def build_world_bvh(objs, depsgraph):
    """BVHTree (world space) of the evaluated meshes of objs. Returns (bvh, verts, tris, normals) of ALL objects."""
    verts, tris, nors, offset = [], [], [], 0
    for obj in objs:
        v, t, n = evaluated_world_geometry(obj, depsgraph)
        verts.append(v)
        tris.append(t + offset)
        nors.append(n)
        offset += len(v)
    verts = np.concatenate(verts) if verts else np.zeros((0, 3))
    tris = np.concatenate(tris) if tris else np.zeros((0, 3), dtype=np.int32)
    nors = np.concatenate(nors) if nors else np.zeros((0, 3))
    bvh = BVHTree.FromPolygons(verts.tolist(), tris.tolist(), all_triangles=True)
    return bvh, verts, tris, nors


def proxy_normals_world(bvh, verts, tris, nors, points_world: np.ndarray) -> np.ndarray:
    """World normals of the nearest proxy surface point for every point (N, 3).

    Smooth: barycentric interpolation of the proxy vertex normals at the nearest point
    (face normal as a fallback). The nearest-point search is a Python loop over the points -
    DOCUMENTED EXCEPTION to the "no Python loops" rule (BVHTree.find_nearest has no batch API).
    """
    n = len(points_world)
    locs = np.zeros((n, 3))
    face_nor = np.zeros((n, 3))
    idx = np.zeros(n, dtype=np.int64)
    find = bvh.find_nearest
    for i, p in enumerate(points_world.tolist()):
        loc, nrm, tri, _dist = find(p)
        if loc is None:
            raise ValueError("Proxy has no surface to sample")
        locs[i] = loc
        face_nor[i] = nrm
        idx[i] = tri
    t = tris[idx]
    return B.interpolate_triangle_normals(locs, verts[t], nors[t], face_nor)


# --------------------------------------------------------------------------- normal

class _BakeProps:
    channels: EnumProperty(name="Channels", items=CHANNEL_ITEMS, options={'ENUM_FLAG'},
                           default={'R', 'G', 'B', 'A'})
    scope: EnumProperty(name="Scope", items=SCOPE_ITEMS, default='SELECTED')


class BADVC_OT_bake_normal(_BakeProps, bpy.types.Operator):
    """Bake normals into channels. Written channels = swizzle != None and selected channels"""
    bl_idname = "badvc.bake_normal"
    bl_label = "Bake Normal"
    bl_options = {'REGISTER', 'UNDO'}

    space: EnumProperty(name="Space", items=[
        ('OBJECT', "Object", "Object space"), ('WORLD', "World", "World space")], default='OBJECT')
    source: EnumProperty(name="Source", items=[
        ('MESH', "Mesh", "Own (split / custom) normals"),
        ('PROXY', "Proxy", "Nearest surface point of the proxy object"),
        ('SPHERICAL', "Spherical", "Direction from a center")], default='MESH')
    proxy: StringProperty(name="Proxy", description="Name of the proxy mesh object")
    center: EnumProperty(name="Center", items=[
        ('ORIGIN', "Origin", "Object origin"), ('BBOX', "Bounds", "Mesh bounding box center"),
        ('CURSOR', "Cursor", "3D cursor"), ('SELECTION', "Selection", "Center of the affected vertices")],
        default='ORIGIN')
    smooth: BoolProperty(name="Smooth", default=True,
                         description="Use smooth vertex normals on Face Corner attributes "
                                     "(off: split/custom corner normals)")
    swizzle_r: EnumProperty(name="R", items=B.SWIZZLE_ITEMS, default='POS_X')
    swizzle_g: EnumProperty(name="G", items=B.SWIZZLE_ITEMS, default='POS_Y')
    swizzle_b: EnumProperty(name="B", items=B.SWIZZLE_ITEMS, default='POS_Z')
    swizzle_a: EnumProperty(name="A", items=B.SWIZZLE_ITEMS, default='NONE')

    @classmethod
    def poll(cls, context):
        return poll_color_mesh(context)

    def invoke(self, context, event):
        _init_bake(self, context, {
            'space': 'bake_normal_space', 'source': 'bake_normal_source', 'proxy': 'bake_proxy',
            'center': 'bake_center', 'smooth': 'bake_normal_smooth',
            'swizzle_r': 'bake_swizzle_r', 'swizzle_g': 'bake_swizzle_g',
            'swizzle_b': 'bake_swizzle_b', 'swizzle_a': 'bake_swizzle_a'})
        return self.execute(context)

    def execute(self, context):
        obj = context.active_object
        swizzle = (self.swizzle_r, self.swizzle_g, self.swizzle_b, self.swizzle_a)
        writable = B.swizzle_channels(swizzle) & set(self.channels)
        if not writable:
            self.report({'WARNING'}, "No channels: check swizzle and channel selection")
            return {'CANCELLED'}

        proxy = None
        if self.source == 'PROXY':
            proxy = bpy.data.objects.get(self.proxy)
            if proxy is None or proxy.type != 'MESH':
                self.report({'ERROR'}, "Proxy must be a mesh object")
                return {'CANCELLED'}
            if proxy == obj:
                self.report({'ERROR'}, "Proxy must be a different object")
                return {'CANCELLED'}

        source, space, center_mode, smooth = self.source, self.space, self.center, self.smooth
        mw = _matrix(obj)
        cursor = np.array(context.scene.cursor.location, dtype=np.float64)
        depsgraph = context.evaluated_depsgraph_get()

        def func(colors, mask, mesh, domain):
            nv = len(mesh.vertices)
            vmask = masked_vertices(mask, mesh, domain)
            n_obj = None  # (V|L, 3) object space or None when n_world_v is set
            n_world_v = None
            if source == 'MESH':
                if domain == 'POINT' or smooth:
                    n_obj = vertex_to_domain(_vec3(mesh.vertex_normals, nv), mesh, domain)
                else:
                    n_obj = _vec3(mesh.corner_normals, len(mesh.loops))
            elif source == 'SPHERICAL':
                pos = vertex_positions(mesh)
                if center_mode == 'ORIGIN':
                    c = np.zeros(3)
                elif center_mode == 'BBOX':
                    c = B.bbox_center(pos)
                elif center_mode == 'CURSOR':
                    c = np.linalg.inv(mw) @ np.append(cursor, 1.0)
                    c = c[:3]
                else:
                    c = B.bbox_center(pos[vmask])
                n_obj = vertex_to_domain(B.spherical_normals(pos, c), mesh, domain)
            else:
                bvh, pv, pt, pn = build_world_bvh([proxy], depsgraph)
                world = _to_world(vertex_positions(mesh), mw)
                n_world_v = np.zeros((nv, 3))
                n_world_v[:] = (0.0, 0.0, 1.0)
                idx = np.flatnonzero(vmask)
                if idx.size:
                    n_world_v[idx] = proxy_normals_world(bvh, pv, pt, pn, world[idx])

            if n_world_v is not None:
                n_dom = vertex_to_domain(n_world_v, mesh, domain)
                if space == 'OBJECT':
                    n_dom = B.transform_normals(n_dom, mw[:3, :3], inverse=True)
            else:
                n_dom = B.normalize_rows(n_obj)
                if space == 'WORLD':
                    n_dom = B.transform_normals(n_dom, mw[:3, :3])
            return B.encode_normals(n_dom, swizzle)

        return run_full_op(self, context, func, writable, self.scope)


class BADVC_OT_bake_smooth_normal(bpy.types.Operator):
    """Preset: bake smooth vertex normals into a color attribute (created if missing).
    Writes all four channels on the whole mesh; ignores Scope, channel selection and isolation"""
    bl_idname = "badvc.bake_smooth_normal"
    bl_label = "Bake Smooth Normal"
    bl_options = {'REGISTER', 'UNDO'}

    attribute_name: StringProperty(name="Attribute", default="NormalColor")
    space: EnumProperty(name="Space", items=[
        ('OBJECT', "Object", "Object space"), ('WORLD', "World", "World space")], default='OBJECT')
    swizzle_r: EnumProperty(name="R", items=B.SWIZZLE_ITEMS, default='NEG_X')
    swizzle_g: EnumProperty(name="G", items=B.SWIZZLE_ITEMS, default='POS_Z')
    swizzle_b: EnumProperty(name="B", items=B.SWIZZLE_ITEMS, default='NEG_Y')
    swizzle_a: EnumProperty(name="A", items=B.SWIZZLE_ITEMS, default='NONE')

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.mode in ('OBJECT', 'EDIT', 'VERTEX_PAINT')

    def invoke(self, context, event):
        settings = context.scene.badvc
        for name, src in (('space', 'bake_normal_space'), ('swizzle_r', 'bake_swizzle_r'),
                          ('swizzle_g', 'bake_swizzle_g'), ('swizzle_b', 'bake_swizzle_b'),
                          ('swizzle_a', 'bake_swizzle_a')):
            if not self.properties.is_property_set(name):
                setattr(self, name, getattr(settings, src))
        return self.execute(context)

    def execute(self, context):
        obj = context.active_object
        name = self.attribute_name.strip()
        if not name:
            self.report({'ERROR'}, "Attribute name is empty")
            return {'CANCELLED'}
        swizzle = (self.swizzle_r, self.swizzle_g, self.swizzle_b, self.swizzle_a)
        mw = _matrix(obj)
        created = False
        with ensure_object_mode(obj):
            mesh = obj.data
            attr = mesh.color_attributes.get(name)
            if attr is None:
                if mesh.attributes.get(name) is not None:
                    self.report({'ERROR'}, f"Attribute '{name}' exists and is not a color attribute")
                    return {'CANCELLED'}
                mesh.color_attributes.new(name, 'FLOAT_COLOR', 'POINT')
                attr = mesh.color_attributes.get(name)  # re-fetch: the old reference is invalidated
                created = True
            error = validate_color_attribute(mesh, attr)
            if error:
                self.report({'ERROR'}, error)
                return {'CANCELLED'}
            mesh.color_attributes.active_color = attr
            n = B.normalize_rows(vertex_to_domain(_vec3(mesh.vertex_normals, len(mesh.vertices)),
                                                  mesh, attr.domain))
            if self.space == 'WORLD':
                n = B.transform_normals(n, mw[:3, :3])
            values = B.encode_normals(n, swizzle)
            if swizzle[3] == 'NONE':
                values[:, 3] = 1.0
            write_colors(mesh, attr, values)
            _after_write(context)
        self.report({'INFO'}, f"Baked smooth normals to '{name}'" + (" (created)" if created else ""))
        return {'FINISHED'}


# --------------------------------------------------------------------------- AO

class BADVC_OT_bake_ao(_BakeProps, bpy.types.Operator):
    """Bake ambient occlusion (ray casts in the normal hemisphere) into the selected channels"""
    bl_idname = "badvc.bake_ao"
    bl_label = "Bake AO"
    bl_options = {'REGISTER', 'UNDO'}

    samples: IntProperty(name="Samples", description="Rays per vertex", min=4, max=512, default=32)
    distance: FloatProperty(name="Distance", description="Maximum ray length (world units)",
                            min=0.001, default=1.0, subtype='DISTANCE')
    bias: FloatProperty(name="Bias", description="Ray origin offset along the normal (world units)",
                        min=0.0, default=0.001, precision=4)
    include_selected: BoolProperty(name="Include Selected Objects",
                                   description="Other selected meshes also occlude", default=False)

    @classmethod
    def poll(cls, context):
        return poll_color_mesh(context)

    def invoke(self, context, event):
        _init_bake(self, context, {
            'samples': 'bake_ao_samples', 'distance': 'bake_ao_distance', 'bias': 'bake_ao_bias',
            'include_selected': 'bake_ao_include_selected'})
        return self.execute(context)

    def execute(self, context):
        obj = context.active_object
        occluders = [obj]
        if self.include_selected:
            occluders += [o for o in context.selected_objects if o.type == 'MESH' and o != obj]
        depsgraph = context.evaluated_depsgraph_get()
        wm = context.window_manager
        samples, distance, bias = self.samples, self.distance, self.bias
        mw = _matrix(obj)

        def func(colors, mask, mesh, domain):
            nv = len(mesh.vertices)
            idx = np.flatnonzero(masked_vertices(mask, mesh, domain))
            ao_v = np.ones(nv, dtype=np.float64)
            if idx.size:
                bvh = build_world_bvh(occluders, depsgraph)[0]
                world = _to_world(vertex_positions(mesh)[idx], mw)
                nor = B.transform_normals(_vec3(mesh.vertex_normals, nv)[idx], mw[:3, :3])
                origins = world + nor * bias
                angles = np.random.default_rng(0).uniform(0.0, 2.0 * np.pi, size=nv)[idx]  # mask independent
                hits = np.zeros(len(idx), dtype=np.int64)
                chunk = max(1, _AO_CHUNK_RAYS // samples)
                ray_cast = bvh.ray_cast
                wm.progress_begin(0, 1000)
                try:
                    for s in range(0, len(idx), chunk):
                        e = min(s + chunk, len(idx))
                        dirs = B.hemisphere_directions(nor[s:e], samples, angles[s:e]).tolist()
                        # DOCUMENTED EXCEPTION to "no Python loops": BVHTree.ray_cast has no batch API.
                        for o, ds, i in zip(origins[s:e].tolist(), dirs, range(s, e)):
                            h = 0
                            for d in ds:
                                if ray_cast(o, d, distance)[0] is not None:
                                    h += 1
                            hits[i] = h
                        wm.progress_update(int(1000 * e / len(idx)))
                finally:
                    wm.progress_end()
                ao_v[idx] = B.occlusion_to_ao(hits, samples)
            vals = vertex_to_domain(ao_v, mesh, domain).astype(np.float32)
            return np.repeat(vals[:, None], 4, axis=1)

        return run_full_op(self, context, func, set(self.channels), self.scope)


# --------------------------------------------------------------------------- random

class BADVC_OT_bake_random(_BakeProps, bpy.types.Operator):
    """Bake a random value per loose part / face / vertex into the selected channels"""
    bl_idname = "badvc.bake_random"
    bl_label = "Bake Random"
    bl_options = {'REGISTER', 'UNDO'}

    per: EnumProperty(name="Per", items=[
        ('LOOSE_PART', "Loose Part", "One value per connected piece"),
        ('FACE', "Face", "One value per face"),
        ('VERTEX', "Vertex", "One value per vertex")], default='LOOSE_PART')
    seed: IntProperty(name="Seed", default=0)
    min_value: FloatProperty(name="Min", min=0.0, max=1.0, default=0.0, subtype='FACTOR')
    max_value: FloatProperty(name="Max", min=0.0, max=1.0, default=1.0, subtype='FACTOR')
    per_channel: BoolProperty(name="Per Channel", description="Independent value for every channel",
                              default=False)

    @classmethod
    def poll(cls, context):
        return poll_color_mesh(context)

    def invoke(self, context, event):
        _init_bake(self, context, {
            'per': 'bake_random_per', 'seed': 'bake_random_seed', 'min_value': 'bake_random_min',
            'max_value': 'bake_random_max', 'per_channel': 'bake_random_per_channel'})
        return self.execute(context)

    def execute(self, context):
        per, seed, lo, hi, per_channel = self.per, self.seed, self.min_value, self.max_value, self.per_channel
        averaged = [False]

        def func(colors, mask, mesh, domain):
            nv, nf = len(mesh.vertices), len(mesh.polygons)
            if per == 'LOOSE_PART':
                labels = loose_parts(mesh)
                table = B.random_table(seed, int(labels.max()) + 1 if nv else 0, per_channel, lo, hi)
                return vertex_to_domain(table[labels], mesh, domain)
            if per == 'VERTEX':
                return vertex_to_domain(B.random_table(seed, nv, per_channel, lo, hi), mesh, domain)
            table = B.random_table(seed, nf, per_channel, lo, hi)
            starts = np.empty(nf, dtype=np.int32)
            if nf:
                mesh.polygons.foreach_get('loop_start', starts)
            sizes = np.diff(np.append(starts, len(mesh.loops)))
            corner_vals = np.repeat(table, sizes, axis=0)
            if domain == 'CORNER':
                return corner_vals
            averaged[0] = True
            return B.corner_values_to_vertices(corner_vals, loop_vertex_indices(mesh), nv, fill=min(lo, hi))

        result = run_full_op(self, context, func, set(self.channels), self.scope)
        if result == {'FINISHED'} and averaged[0]:
            self.report({'INFO'}, "Per Face on Point domain: averaged at shared vertices")
        return result


# --------------------------------------------------------------------------- position

class BADVC_OT_bake_position(_BakeProps, bpy.types.Operator):
    """Bake height (axis) or distance from a center, normalised to 0..1, into the selected channels"""
    bl_idname = "badvc.bake_position"
    bl_label = "Bake Position"
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(name="Mode", items=[
        ('AXIS', "Axis", "Coordinate along an axis, min..max"),
        ('DISTANCE', "Distance", "Distance from a center divided by the maximum")], default='AXIS')
    axis: EnumProperty(name="Axis", items=[('X', "X", ""), ('Y', "Y", ""), ('Z', "Z", "")], default='Z')
    center: EnumProperty(name="Center", items=[
        ('ORIGIN', "Origin", "Origin of the space"), ('BBOX', "Bounds", "Mesh bounding box center"),
        ('CURSOR', "Cursor", "3D cursor"),
        ('PART', "Part", "Bounding box center of the loose part")], default='BBOX')
    space: EnumProperty(name="Space", items=[
        ('LOCAL', "Local", "Object space"), ('WORLD', "World", "World space")], default='LOCAL')
    per_part: BoolProperty(name="Per Part", description="Normalise inside every loose part", default=False)
    invert: BoolProperty(name="Invert", description="Write 1 - value", default=False)

    @classmethod
    def poll(cls, context):
        return poll_color_mesh(context)

    def invoke(self, context, event):
        _init_bake(self, context, {
            'mode': 'bake_pos_mode', 'axis': 'bake_pos_axis', 'center': 'bake_pos_center',
            'space': 'bake_pos_space', 'per_part': 'bake_pos_per_part', 'invert': 'bake_pos_invert'})
        return self.execute(context)

    def execute(self, context):
        obj = context.active_object
        mode, axis, center_mode, world = self.mode, 'XYZ'.index(self.axis), self.center, self.space == 'WORLD'
        per_part, invert = self.per_part, self.invert
        mw = _matrix(obj)
        cursor = np.array(context.scene.cursor.location, dtype=np.float64)
        if not world:
            cursor = (np.linalg.inv(mw) @ np.append(cursor, 1.0))[:3]
        needs_parts = per_part or (mode == 'DISTANCE' and center_mode == 'PART')

        def func(colors, mask, mesh, domain):
            pos = vertex_positions(mesh)
            if world:
                pos = _to_world(pos, mw)
            labels = loose_parts(mesh) if needs_parts else None
            if mode == 'AXIS':
                s_v = pos[:, axis]
            else:
                if center_mode == 'ORIGIN':
                    c = np.zeros(3)
                elif center_mode == 'BBOX':
                    c = B.bbox_center(pos)
                elif center_mode == 'CURSOR':
                    c = cursor
                else:
                    c = B.part_bbox_centers(pos, labels)[labels]
                s_v = np.linalg.norm(pos - c, axis=1)
            lab_dom = vertex_to_domain(labels, mesh, domain) if per_part else None
            t = B.normalize_scalar(vertex_to_domain(s_v, mesh, domain), mask, lab_dom,
                                   'MINMAX' if mode == 'AXIS' else 'MAX')
            if invert:
                t = 1.0 - t
            return np.repeat(t[:, None].astype(np.float32), 4, axis=1)

        return run_full_op(self, context, func, set(self.channels), self.scope)


classes = (BADVC_OT_bake_normal, BADVC_OT_bake_smooth_normal, BADVC_OT_bake_ao, BADVC_OT_bake_random, BADVC_OT_bake_position)
