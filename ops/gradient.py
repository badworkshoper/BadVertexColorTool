"""F08a: gradient operators (axis, between vertices) + Start/End vertex groups.

Shared core for F08b (mouse gesture): `run_gradient` takes any `t_func(mesh, mask, domain) -> t (N,)`
(NaN = leave untouched) and does easing, values and the masked / per-channel write.
"""

from types import SimpleNamespace

import bmesh
import bpy
import numpy as np
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty

from ..core import gradient as G
from ..core.channels import CHANNEL_ITEMS
from ..core.selection import vertex_selection
from ..core.topology import edge_vertex_pairs, loop_vertex_indices
from ._common import init_from_settings, poll_color_mesh, run_full_op
from .fill import SCOPE_ITEMS

SOURCE_ITEMS = [
    ('VALUE', "Value", "Gradient between two values, written to all selected channels"),
    ('COLOR', "Color", "Gradient between two colors"),
]

# operator prop -> Scene.badvc prop (not in SETTINGS_MAP: 'source' is taken by transfer there)
_GRADIENT_SETTINGS = {
    'source': 'gradient_source', 'start_value': 'gradient_start_value',
    'end_value': 'gradient_end_value', 'color_a': 'gradient_color_a',
    'color_b': 'gradient_color_b', 'easing': 'gradient_easing',
}


def _init_gradient(op, context, extra: dict | None = None) -> None:
    """Copy unset gradient props from Scene.badvc (+ extra mapping), channels/scope as usual."""
    init_from_settings(op, context, ('channels', 'scope'))
    settings = context.scene.badvc
    for name, src in {**_GRADIENT_SETTINGS, **(extra or {})}.items():
        if op.properties.is_property_set(name):
            continue
        value = getattr(settings, src)
        setattr(op, name, tuple(value) if name.startswith('color') else value)


# --------------------------------------------------------------------------- shared core

def vertex_positions(mesh) -> np.ndarray:
    """(V, 3) float64 local vertex coordinates (OBJECT mode data)."""
    co = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    if len(co):
        mesh.vertices.foreach_get('co', co)
    return co.reshape(-1, 3).astype(np.float64)


def vertex_to_domain(values: np.ndarray, mesh, domain: str) -> np.ndarray:
    """Per-vertex array (V, ...) -> domain elements (POINT: as is, CORNER: gather by loop vertex)."""
    return values if domain == 'POINT' else values[loop_vertex_indices(mesh)]


def run_gradient(op, context, t_func, props) -> set:
    """Write a gradient. t_func(mesh, mask, domain) -> t (N,) over the domain (NaN = skip).

    props: object with source, start_value, end_value, color_a, color_b, easing,
    channels, scope (an operator). Only mask x effective channels are written.
    """
    skipped = [0]

    def func(colors, mask, mesh, domain):
        t = np.asarray(t_func(mesh, mask, domain), dtype=np.float32)
        valid = mask & np.isfinite(t)
        skipped[0] = int(mask.sum() - valid.sum())
        t = G.ease(t[valid], props.easing)
        out = colors.copy()
        out[valid] = G.gradient_values(t, props.source, props.start_value, props.end_value,
                                       props.color_a, props.color_b)
        return out

    result = run_full_op(op, context, func, set(props.channels), props.scope)
    if result == {'FINISHED'} and skipped[0]:
        op.report({'WARNING'}, f"{skipped[0]} elements not reachable, left unchanged")
    return result


class _GradientProps:
    """Props shared by all gradient operators."""
    source: EnumProperty(name="Source", items=SOURCE_ITEMS, default='VALUE')
    start_value: FloatProperty(name="Start Value", min=0.0, max=1.0, default=0.0, subtype='FACTOR')
    end_value: FloatProperty(name="End Value", min=0.0, max=1.0, default=1.0, subtype='FACTOR')
    color_a: FloatVectorProperty(name="Color A", subtype='COLOR_GAMMA', size=4, min=0.0, max=1.0,
                                 default=(0.0, 0.0, 0.0, 1.0))
    color_b: FloatVectorProperty(name="Color B", subtype='COLOR_GAMMA', size=4, min=0.0, max=1.0,
                                 default=(1.0, 1.0, 1.0, 1.0))
    easing: EnumProperty(name="Easing", items=G.EASING_ITEMS, default='LINEAR')
    channels: EnumProperty(name="Channels", items=CHANNEL_ITEMS, options={'ENUM_FLAG'},
                           default={'R', 'G', 'B', 'A'})
    scope: EnumProperty(name="Scope", items=SCOPE_ITEMS, default='SELECTED')


# --------------------------------------------------------------------------- axis gradient

class BADVC_OT_gradient_axis(_GradientProps, bpy.types.Operator):
    """Gradient along an axis (or radial), stretched over the affected elements"""
    bl_idname = "badvc.gradient_axis"
    bl_label = "Axis Gradient"
    bl_options = {'REGISTER', 'UNDO'}

    axis: EnumProperty(name="Axis", items=[('X', "X", ""), ('Y', "Y", ""), ('Z', "Z", "")], default='Z')
    space: EnumProperty(name="Space", items=[
        ('LOCAL', "Local", "Object space"), ('WORLD', "World", "World space")], default='LOCAL')
    shape: EnumProperty(name="Shape", items=[
        ('LINEAR', "Linear", "Along the axis"), ('RADIAL', "Radial", "Distance from the center")],
        default='LINEAR')
    flip: BoolProperty(name="Flip", description="Reverse the gradient direction", default=False)

    @classmethod
    def poll(cls, context):
        return poll_color_mesh(context)

    def invoke(self, context, event):
        _init_gradient(self, context, {'axis': 'gradient_axis', 'space': 'gradient_space',
                                       'shape': 'gradient_shape'})
        return self.execute(context)

    def execute(self, context):
        obj = context.active_object
        axis_vec = np.zeros(3)
        axis_vec['XYZ'.index(self.axis)] = 1.0
        world = self.space == 'WORLD'
        radial = self.shape == 'RADIAL'
        flip = self.flip
        mw = np.array(obj.matrix_world, dtype=np.float64)

        def t_func(mesh, mask, domain):
            pos = vertex_positions(mesh)
            if world:
                pos = pos @ mw[:3, :3].T + mw[:3, 3]
            pts = vertex_to_domain(pos, mesh, domain)
            t = np.full(len(pts), np.nan, dtype=np.float32)
            t[mask] = G.axis_t(pts[mask], axis_vec, radial)
            if flip:
                t = 1.0 - t
            return t

        return run_gradient(self, context, t_func, self)


# --------------------------------------------------------------------------- Start/End groups

_groups: dict[str, dict] = {}  # runtime only (not saved): obj.name -> mesh ptr, n_verts, start, end


def _selected_vertices(obj) -> np.ndarray:
    """Indices of selected vertices (read-only; Edit Mode data is synced via update_from_editmode)."""
    if obj.mode == 'EDIT':
        obj.update_from_editmode()
    return np.flatnonzero(vertex_selection(obj.data))


def get_group(obj, which: str) -> np.ndarray:
    """Stored vertex indices of 'start'/'end' (empty if unset or the topology changed)."""
    g = _groups.get(obj.name)
    if g is None or g['ptr'] != obj.data.as_pointer() or g['n'] != len(obj.data.vertices):
        _groups.pop(obj.name, None)
        return np.zeros(0, dtype=np.int64)
    return g[which]


def _set_group(obj, which: str, idx) -> None:
    g = _groups.get(obj.name)
    n = len(obj.data.vertices)
    if g is None or g['ptr'] != obj.data.as_pointer() or g['n'] != n:
        g = {'ptr': obj.data.as_pointer(), 'n': n,
             'start': np.zeros(0, dtype=np.int64), 'end': np.zeros(0, dtype=np.int64)}
        _groups[obj.name] = g
    g[which] = np.asarray(idx, dtype=np.int64)


def clear_groups() -> None:
    _groups.clear()


class BADVC_OT_gradient_set_group(bpy.types.Operator):
    """Remember the selected vertices as the Start / End group (runtime only, mesh is not modified)"""
    bl_idname = "badvc.gradient_set_group"
    bl_label = "Set Gradient Group"
    bl_options = {'INTERNAL'}

    which: EnumProperty(name="Group", items=[
        ('START', "Start", ""), ('END', "End", ""), ('CLEAR', "Clear", "")], default='START')

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.mode in ('OBJECT', 'EDIT')

    def execute(self, context):
        obj = context.active_object
        if self.which == 'CLEAR':
            _groups.pop(obj.name, None)
        else:
            idx = _selected_vertices(obj)
            if idx.size == 0:
                self.report({'WARNING'}, "No vertices selected")
                return {'CANCELLED'}
            _set_group(obj, self.which.lower(), idx)
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


# --------------------------------------------------------------------------- between vertices

def _two_selected_ordered(obj, idx: np.ndarray):
    """(start, end, used_history) for exactly two selected vertices in Edit Mode (bmesh read-only)."""
    bm = bmesh.from_edit_mesh(obj.data)
    chosen = set(int(i) for i in idx)
    hist = [e.index for e in bm.select_history if isinstance(e, bmesh.types.BMVert) and e.index in chosen]
    if len(hist) >= 2:
        return hist[0], hist[1], True
    return int(idx[0]), int(idx[1]), False


class BADVC_OT_gradient_between(_GradientProps, bpy.types.Operator):
    """Gradient between two vertices or between Start/End vertex groups"""
    bl_idname = "badvc.gradient_between"
    bl_label = "Gradient Between Vertices"
    bl_options = {'REGISTER', 'UNDO'}

    method: EnumProperty(name="Method", items=[
        ('LINEAR', "Linear", "Projection on the segment between the points"),
        ('GEODESIC', "Geodesic", "Distance along mesh edges")], default='LINEAR')

    @classmethod
    def poll(cls, context):
        return poll_color_mesh(context)

    def invoke(self, context, event):
        _init_gradient(self, context, {'method': 'gradient_method'})
        return self.execute(context)

    def execute(self, context):
        obj = context.active_object
        start, end = get_group(obj, 'start'), get_group(obj, 'end')
        scope = self.scope
        if not (start.size and end.size):
            # Quick mode: exactly 2 selected vertices in Edit Mode (read BEFORE leaving Edit Mode).
            idx = _selected_vertices(obj) if obj.mode == 'EDIT' else np.zeros(0, dtype=np.int64)
            if idx.size != 2:
                self.report({'WARNING'}, "Select exactly 2 vertices or set Start/End groups")
                return {'CANCELLED'}
            a, b, used_history = _two_selected_ordered(obj, idx)
            if not used_history:
                self.report({'INFO'}, "No selection history, using vertex index order")
            start, end = np.array([a]), np.array([b])
            scope = 'ALL'  # only 2 vertices are selected: the gradient covers the whole mesh

        geodesic = self.method == 'GEODESIC'

        def t_func(mesh, mask, domain):
            pos = vertex_positions(mesh)
            if geodesic:
                edges = edge_vertex_pairs(mesh)
                lens = np.linalg.norm(pos[edges[:, 0]] - pos[edges[:, 1]], axis=1) if len(edges) else np.zeros(0)
                t_v = G.geodesic_t(len(pos), edges, lens, start, end)
            else:
                t_v = G.segment_t(pos, pos[start].mean(axis=0), pos[end].mean(axis=0))
            return vertex_to_domain(t_v, mesh, domain)

        props = SimpleNamespace(scope=scope, **{n: getattr(self, n) for n in (
            'source', 'start_value', 'end_value', 'color_a', 'color_b', 'easing', 'channels')})
        return run_gradient(self, context, t_func, props)


# --------------------------------------------------------------------------- swap

class BADVC_OT_gradient_swap_ends(bpy.types.Operator):
    """Swap gradient start and end (values and colors)"""
    bl_idname = "badvc.gradient_swap_ends"
    bl_label = "Swap Gradient Ends"
    bl_options = {'UNDO'}

    def execute(self, context):
        s = context.scene.badvc
        s.gradient_start_value, s.gradient_end_value = s.gradient_end_value, s.gradient_start_value
        a, b = tuple(s.gradient_color_a), tuple(s.gradient_color_b)
        s.gradient_color_a, s.gradient_color_b = b, a
        return {'FINISHED'}


classes = (BADVC_OT_gradient_axis, BADVC_OT_gradient_between,
           BADVC_OT_gradient_set_group, BADVC_OT_gradient_swap_ends)
