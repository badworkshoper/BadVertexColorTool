"""F08a: gradient operators (axis, between vertices) + Start/End vertex groups.

Shared core for F08b (mouse gesture): `run_gradient` takes any `t_func(mesh, mask, domain) -> t (N,)`
(NaN = leave untouched) and does easing, values and the masked / per-channel write.
"""

from types import SimpleNamespace

import traceback

import bmesh
import bpy
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader
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
    bm.verts.index_update()  # BMVert indices may be stale
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


# --------------------------------------------------------------------------- mouse gesture (F08b)

_SNAP_STEP = np.radians(15.0)
_MIN_DRAG_PX = 3.0
_HEADER_TEXT = "Drag to draw gradient (LMB) | Shift: snap 15° | Esc/RMB: cancel"


def _matrix_to_list(matrix) -> list:
    """4x4 mathutils.Matrix -> 16 floats, row by row (restore with np.reshape(4, 4))."""
    return [float(v) for row in matrix for v in row]


def project_to_region(points: np.ndarray, matrix_list, region_size) -> np.ndarray:
    """World points (N, 3) -> region pixel coords (N, 2); NaN for points behind the camera (w <= 1e-6)."""
    m = np.asarray(matrix_list, dtype=np.float64).reshape(4, 4)
    p = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    clip = p @ m[:, :3].T + m[:, 3]
    w = clip[:, 3]
    ok = w > 1e-6
    screen = np.full((len(p), 2), np.nan)
    ndc = clip[ok, :2] / w[ok, None]
    screen[ok] = (ndc * 0.5 + 0.5) * np.asarray(region_size, dtype=np.float64)
    return screen


def _snap_end(start, end):
    d = np.asarray(end, dtype=np.float64) - np.asarray(start, dtype=np.float64)
    length = float(np.hypot(*d))
    ang = round(float(np.arctan2(d[1], d[0])) / _SNAP_STEP) * _SNAP_STEP
    return (start[0] + length * np.cos(ang), start[1] + length * np.sin(ang))


def _window_region(area):
    return next((r for r in area.regions if r.type == 'WINDOW'), None) if area else None


_draw_shader = [None]


def _draw_gesture(state: dict) -> None:
    """POST_PIXEL callback: gesture line, end markers, circle for RADIAL. Silent after a failure."""
    if state['failed'] or state['start'] is None:
        return
    try:
        if _draw_shader[0] is None:
            _draw_shader[0] = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
        shader = _draw_shader[0]
        a = np.asarray(state['start'], dtype=np.float32)
        b = np.asarray(state['end'], dtype=np.float32)
        strips = [(np.array([a, b]), (1.0, 1.0, 1.0, 0.9))]
        box = np.array([[-5, -5], [5, -5], [5, 5], [-5, 5], [-5, -5]], dtype=np.float32)
        yellow = (1.0, 0.8, 0.1, 1.0)
        strips += [(c + box, yellow) for c in (a, b)]
        if state['shape'] == 'RADIAL':
            r = float(np.hypot(*(b - a)))
            ang = np.linspace(0.0, 2.0 * np.pi, 65, dtype=np.float32)
            strips.append((a + r * np.stack([np.cos(ang), np.sin(ang)], axis=1), yellow))
        region = bpy.context.region
        gpu.state.blend_set('ALPHA')
        shader.bind()
        shader.uniform_float('viewportSize', (region.width, region.height))
        shader.uniform_float('lineWidth', 2.0)
        for strip, color in strips:
            shader.uniform_float('color', color)
            batch_for_shader(shader, 'LINE_STRIP', {"pos": strip.astype(np.float32)}).draw(shader)
    except Exception:
        state['failed'] = True
        print("[BadVC] Gradient gesture draw error:")
        traceback.print_exc()
    finally:
        gpu.state.blend_set('NONE')


class BADVC_OT_gradient_gesture(_GradientProps, bpy.types.Operator):
    """Draw a gradient with the mouse in the 3D viewport (drag from start to end)"""
    bl_idname = "badvc.gradient_gesture"
    bl_label = "Gradient by Gesture"
    bl_options = {'REGISTER', 'UNDO'}

    shape: EnumProperty(name="Shape", items=[
        ('LINEAR', "Linear", "Along the gesture line"),
        ('RADIAL', "Radial", "Distance from the gesture start")], default='LINEAR')
    start: FloatVectorProperty(name="Start", size=2, default=(0.0, 0.0),
                               description="Gesture start in viewport pixels")
    end: FloatVectorProperty(name="End", size=2, default=(0.0, 0.0),
                             description="Gesture end in viewport pixels")
    view_matrix: FloatVectorProperty(name="View Matrix", size=16, default=(0.0,) * 16,
                                     options={'HIDDEN', 'SKIP_SAVE'})
    region_size: FloatVectorProperty(name="Region Size", size=2, default=(0.0, 0.0),
                                     options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return poll_color_mesh(context)

    def _cleanup(self):
        """Remove draw handler, header text and cursor. Idempotent, called from every exit path."""
        handle = getattr(self, '_handle', None)
        if handle is not None:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(handle, 'WINDOW')
            except Exception:
                pass
            self._handle = None
        if getattr(self, '_ui_set', False):
            self._ui_set = False
            try:
                self._area.header_text_set(None)
                self._area.tag_redraw()
                self._window.cursor_modal_restore()
            except Exception:
                pass

    def invoke(self, context, event):
        _init_gradient(self, context, {'shape': 'gradient_shape'})
        area = context.area
        region = _window_region(area)
        if (area is None or area.type != 'VIEW_3D' or region is None
                or context.space_data is None or context.space_data.region_3d is None):
            self.report({'WARNING'}, "Use from the 3D viewport")
            return {'CANCELLED'}
        self._area, self._window = area, context.window
        self._state = {'start': None, 'end': None, 'shape': self.shape, 'failed': False}
        self._dragging = False
        self._handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw_gesture, (self._state,), 'WINDOW', 'POST_PIXEL')
        area.header_text_set(_HEADER_TEXT)
        context.window.cursor_modal_set('CROSSHAIR')
        self._ui_set = True
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        try:
            return self._modal(context, event)
        except Exception:
            self._cleanup()
            traceback.print_exc()
            return {'CANCELLED'}

    def _modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._cleanup()
            return {'CANCELLED'}
        region = _window_region(self._area)
        if region is None:
            self._cleanup()
            return {'CANCELLED'}
        mouse = (event.mouse_x - region.x, event.mouse_y - region.y)
        inside = 0 <= mouse[0] < region.width and 0 <= mouse[1] < region.height
        st = self._state

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and inside and not self._dragging:
            self._dragging = True
            st['start'] = st['end'] = mouse
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if self._dragging and event.type == 'MOUSEMOVE':
            st['end'] = _snap_end(st['start'], mouse) if event.shift else mouse
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if self._dragging and event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            start, end = st['start'], st['end']
            self._cleanup()
            if np.hypot(end[0] - start[0], end[1] - start[1]) < _MIN_DRAG_PX:
                return {'CANCELLED'}
            rv = self._area.spaces.active.region_3d
            self.start, self.end = start, end
            self.view_matrix = _matrix_to_list(rv.perspective_matrix)
            self.region_size = (region.width, region.height)
            return self.execute(context)
        if not self._dragging and (event.type == 'MIDDLEMOUSE' or event.type.startswith('WHEEL')
                                   or event.type.startswith('TRACKPAD')):
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}

    def execute(self, context):
        if not any(self.view_matrix):
            self.report({'WARNING'}, "Use from the 3D viewport")
            return {'CANCELLED'}
        start = np.array(self.start, dtype=np.float64)
        d = np.array(self.end, dtype=np.float64) - start
        length2 = float(d @ d)
        if length2 < 1e-12:
            self.report({'WARNING'}, "Gradient gesture is too short")
            return {'CANCELLED'}
        radial = self.shape == 'RADIAL'
        matrix_list, size = list(self.view_matrix), tuple(self.region_size)
        mw = np.array(context.active_object.matrix_world, dtype=np.float64)

        def t_func(mesh, mask, domain):
            world = vertex_positions(mesh) @ mw[:3, :3].T + mw[:3, 3]
            screen = project_to_region(world, matrix_list, size)  # NaN behind the camera
            with np.errstate(invalid='ignore'):
                if radial:
                    t = np.linalg.norm(screen - start, axis=1) / np.sqrt(length2)
                else:
                    t = (screen - start) @ d / length2
                t = np.clip(t, 0.0, 1.0)
            return vertex_to_domain(t, mesh, domain)

        return run_gradient(self, context, t_func, self)


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


classes = (BADVC_OT_gradient_axis, BADVC_OT_gradient_between, BADVC_OT_gradient_gesture,
           BADVC_OT_gradient_set_group, BADVC_OT_gradient_swap_ends)
