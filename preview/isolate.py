"""F07: Channel Isolate Preview. GPU overlay of one color channel in grayscale.

NEVER writes mesh data. All state lives on WindowManager (not saved in .blend).
The app handlers below only set a dirty flag (read-only exception to the
"no handlers" rule, see docs/DECISIONS.md).
"""

import traceback

import bpy
import gpu
import numpy as np
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty
from mathutils import Vector

from ..core.attributes import (
    get_active_color_attribute,
    read_colors,
    validate_color_attribute,
)
from ..core.channels import CHANNEL_INDEX
from ..core.topology import loop_vertex_indices

ISOLATE_ITEMS = [
    ('NONE', "Off", "No channel isolated"),
    ('R', "R", "Show the red channel as grayscale"),
    ('G', "G", "Show the green channel as grayscale"),
    ('B', "B", "Show the blue channel as grayscale"),
    ('A', "A", "Show the alpha channel as grayscale"),
]
_DRAW_MODES = ('OBJECT', 'VERTEX_PAINT', 'EDIT')
_LIGHT_VIEW = Vector((0.3, 0.4, 0.85)).normalized()  # view-space light direction

_VERT_SRC = """
void main()
{
  gl_Position = mvp * vec4(pos, 1.0);
  gl_Position.z -= 0.0005 * gl_Position.w;  // depth bias: avoid z-fighting with the mesh
  float shade = 1.0;
  if (light.w > 0.5) {
    // light.xyz: view-space headlight direction brought into object space on the CPU
    shade = 0.6 + 0.4 * max(dot(normalize(nor), light.xyz), 0.0);
  }
  v_color = vec4(vec3(val * shade), 1.0);
}
"""
_FRAG_SRC = """
void main()
{
  FragColor = v_color;
}
"""

# Module state (runtime only).
_state = {
    'handle': None,       # draw handler handle
    'dirty': True,
    'failed': False,      # draw callback raised: stay silent until re-enabled
    'key': None,
    'batch': None,
    'shader': None,
}


# ---------------------------------------------------------------- pure buffers

def build_buffers(mesh, attr, channel: str):
    """Per-corner buffers for the overlay (read-only on the mesh).

    Returns (pos (L,3) f32, nor (L,3) f32, val (L,) f32, indices (T,3) int32 of corner indices).
    Raises ValueError for invalid input or if attribute/mesh sizes do not match.
    """
    if channel not in CHANNEL_INDEX:
        raise ValueError(f"Invalid channel '{channel}'")
    error = validate_color_attribute(mesh, attr)
    if error:
        raise ValueError(error)
    n_verts, n_loops = len(mesh.vertices), len(mesh.loops)
    expected = n_verts if attr.domain == 'POINT' else n_loops
    if len(attr.data) != expected:
        raise ValueError("Attribute size does not match mesh (stale data)")

    lv = loop_vertex_indices(mesh)
    co = np.empty(n_verts * 3, dtype=np.float32)
    if n_verts:
        mesh.vertices.foreach_get('co', co)
    pos = co.reshape(-1, 3)[lv]

    nor = None
    if n_loops:
        try:
            buf = np.empty(n_loops * 3, dtype=np.float32)
            mesh.corner_normals.foreach_get('vector', buf)
            nor = buf.reshape(-1, 3)
        except Exception:
            nor = None
    if nor is None:
        vn = np.empty(n_verts * 3, dtype=np.float32)
        if n_verts:
            mesh.vertices.foreach_get('normal', vn)
        nor = vn.reshape(-1, 3)[lv]

    values = read_colors(mesh, attr)[:, CHANNEL_INDEX[channel]]
    val = values[lv] if attr.domain == 'POINT' else values

    mesh.calc_loop_triangles()  # Blender's read-only cache
    n_tris = len(mesh.loop_triangles)
    tri = np.empty(n_tris * 3, dtype=np.int32)
    if n_tris:
        mesh.loop_triangles.foreach_get('loops', tri)
    return (np.ascontiguousarray(pos, dtype=np.float32),
            np.ascontiguousarray(nor, dtype=np.float32),
            np.ascontiguousarray(val, dtype=np.float32),
            tri.reshape(-1, 3))


# ---------------------------------------------------------------- dirty / redraw

def tag_dirty() -> None:
    """Mark the cached overlay batch stale (cheap, safe to call anywhere)."""
    _state['dirty'] = True


def is_dirty() -> bool:
    return bool(_state['dirty'])


def clear_dirty() -> None:
    _state['dirty'] = False


def tag_redraw() -> None:
    """Redraw all 3D viewports (no-op without windows, e.g. in background mode)."""
    wm = getattr(bpy.context, 'window_manager', None)
    if wm is None:
        return
    for win in wm.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def _clear_cache() -> None:
    _state['key'] = None
    _state['batch'] = None
    _state['dirty'] = True


# ---------------------------------------------------------------- GPU

def _get_shader():
    if _state['shader'] is None:
        info = gpu.types.GPUShaderCreateInfo()
        info.push_constant('MAT4', 'mvp')
        info.push_constant('VEC4', 'light')  # push constants are limited to 128 bytes
        info.vertex_in(0, 'VEC3', 'pos')
        info.vertex_in(1, 'VEC3', 'nor')
        info.vertex_in(2, 'FLOAT', 'val')
        iface = gpu.types.GPUStageInterfaceInfo("badvc_isolate_iface")
        iface.smooth('VEC4', 'v_color')
        info.vertex_out(iface)
        info.fragment_out(0, 'VEC4', 'FragColor')
        info.vertex_source(_VERT_SRC)
        info.fragment_source(_FRAG_SRC)
        _state['shader'] = gpu.shader.create_from_info(info)
    return _state['shader']


def _make_batch(pos, nor, val, indices):
    fmt = gpu.types.GPUVertFormat()
    fmt.attr_add(id='pos', comp_type='F32', len=3, fetch_mode='FLOAT')
    fmt.attr_add(id='nor', comp_type='F32', len=3, fetch_mode='FLOAT')
    fmt.attr_add(id='val', comp_type='F32', len=1, fetch_mode='FLOAT')
    vbo = gpu.types.GPUVertBuf(fmt, len(pos))
    vbo.attr_fill('pos', pos)
    vbo.attr_fill('nor', nor)
    vbo.attr_fill('val', val.reshape(-1, 1))
    ibo = gpu.types.GPUIndexBuf(type='TRIS', seq=indices)
    return gpu.types.GPUBatch(type='TRIS', buf=vbo, elem=ibo)


def _draw_impl() -> None:
    ctx = bpy.context
    wm = ctx.window_manager
    channel = wm.badvc_isolate
    if channel == 'NONE':
        return
    obj = ctx.active_object
    rv = ctx.region_data
    if obj is None or obj.type != 'MESH' or obj.mode not in _DRAW_MODES or rv is None:
        return
    mesh = obj.data
    attr = get_active_color_attribute(mesh)
    if validate_color_attribute(mesh, attr) is not None:
        return
    shading = bool(wm.badvc_isolate_shading)
    key = (obj.name, mesh.as_pointer(), attr.name, attr.domain, channel, shading,
           len(mesh.vertices), len(mesh.loops))
    if _state['dirty'] or key != _state['key'] or _state['batch'] is None:
        try:
            buffers = build_buffers(mesh, attr, channel)
        except ValueError:
            _state['batch'] = None
            return  # stale/mismatching data (e.g. Edit Mode): skip the frame
        _state['batch'] = _make_batch(*buffers) if len(buffers[3]) else None
        _state['key'] = key
        _state['dirty'] = False
    batch = _state['batch']
    if batch is None:
        return

    shader = _get_shader()
    shader.bind()
    shader.uniform_float('mvp', rv.perspective_matrix @ obj.matrix_world)
    m3 = (rv.view_matrix @ obj.matrix_world).to_3x3()
    light = (m3.inverted_safe() @ _LIGHT_VIEW).normalized()
    shader.uniform_float('light', (light.x, light.y, light.z, 1.0 if shading else 0.0))
    gpu.state.blend_set('NONE')
    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.depth_mask_set(False)
    try:
        batch.draw(shader)
    finally:
        gpu.state.depth_mask_set(True)
        gpu.state.depth_test_set('NONE')


def _draw_callback() -> None:
    if _state['failed']:
        return
    try:
        _draw_impl()
    except Exception:
        _state['failed'] = True
        print("[BadVC] Isolate preview draw error (preview disabled until re-enabled):")
        traceback.print_exc()


# ---------------------------------------------------------------- read-only app handlers

@persistent
def _on_depsgraph_update(scene, depsgraph=None) -> None:
    """Only sets the dirty flag when the active mesh/object was updated. Writes nothing."""
    try:
        obj = bpy.context.view_layer.objects.active
        if obj is None or obj.type != 'MESH' or depsgraph is None:
            return
        mesh_name, obj_name = obj.data.name, obj.name
        for update in depsgraph.updates:
            idb = update.id
            if isinstance(idb, bpy.types.Mesh) and idb.name == mesh_name:
                _state['dirty'] = True
                return
            if isinstance(idb, bpy.types.Object) and idb.name == obj_name:
                _state['dirty'] = True
                return
    except Exception:
        _state['dirty'] = True


@persistent
def _on_undo_redo(*args) -> None:
    _state['dirty'] = True


@persistent
def _on_load_pre(*args) -> None:
    """New file: drop handlers and caches, reset the UI state. Writes no data."""
    disable()
    try:
        bpy.context.window_manager.badvc_isolate = 'NONE'
    except Exception:
        pass


def _app_handlers():
    h = bpy.app.handlers
    return ((h.depsgraph_update_post, _on_depsgraph_update),
            (h.undo_post, _on_undo_redo),
            (h.redo_post, _on_undo_redo),
            (h.load_pre, _on_load_pre))


def enable() -> None:
    """Install draw handler and read-only app handlers (idempotent)."""
    _state['failed'] = False
    _clear_cache()
    if _state['handle'] is None:
        _state['handle'] = bpy.types.SpaceView3D.draw_handler_add(
            _draw_callback, (), 'WINDOW', 'POST_VIEW')
    for lst, fn in _app_handlers():
        if fn not in lst:
            lst.append(fn)


def disable() -> None:
    """Remove draw handler, app handlers and caches (idempotent)."""
    if _state['handle'] is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_state['handle'], 'WINDOW')
        except Exception:
            pass
        _state['handle'] = None
    for lst, fn in _app_handlers():
        while fn in lst:
            lst.remove(fn)
    _clear_cache()
    tag_redraw()


def is_enabled() -> bool:
    return _state['handle'] is not None


def _on_isolate_update(self, context) -> None:
    if self.badvc_isolate == 'NONE':
        disable()
    else:
        enable()
        tag_redraw()


def _on_shading_update(self, context) -> None:
    tag_dirty()
    tag_redraw()


# ---------------------------------------------------------------- operator / registration

class BADVC_OT_isolate_channel(bpy.types.Operator):
    """Show one color channel as grayscale in the viewport (toggle); edits then affect only that channel"""
    bl_idname = "badvc.isolate_channel"
    bl_label = "Isolate Channel"
    # No UNDO / REGISTER: UI state only, must not replace the last-operation panel.
    bl_options = {'INTERNAL'}

    channel: EnumProperty(name="Channel", items=ISOLATE_ITEMS, default='R')

    def execute(self, context):
        wm = context.window_manager
        wm.badvc_isolate = 'NONE' if wm.badvc_isolate == self.channel else self.channel
        return {'FINISHED'}


classes = (BADVC_OT_isolate_channel,)


def register_props() -> None:
    bpy.types.WindowManager.badvc_isolate = EnumProperty(
        name="Isolate Channel",
        description="Channel shown as grayscale preview (not saved in the .blend)",
        items=ISOLATE_ITEMS,
        default='NONE',
        update=_on_isolate_update,
    )
    bpy.types.WindowManager.badvc_isolate_shading = BoolProperty(
        name="Shading",
        description="Apply light shading to the isolate preview to keep the shape readable",
        default=True,
        update=_on_shading_update,
    )


def unregister_props() -> None:
    # Stored values survive re-registration: reset them so state matches the (removed) handlers.
    for wm in bpy.data.window_managers:
        try:
            wm.badvc_isolate = 'NONE'
        except Exception:
            pass
    for name in ("badvc_isolate", "badvc_isolate_shading"):
        if hasattr(bpy.types.WindowManager, name):
            delattr(bpy.types.WindowManager, name)


def shutdown() -> None:
    """Remove everything this module installed (handlers, caches)."""
    disable()
    _state['shader'] = None
