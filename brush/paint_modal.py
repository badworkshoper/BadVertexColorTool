"""F10: interactive brush - a modal "brush session" (many strokes, one undo step per stroke)."""

import traceback
from dataclasses import replace

import bpy
import numpy as np
from bpy_extras import view3d_utils
from mathutils import Vector

from ..core.attributes import (
    get_active_color_attribute,
    read_colors,
    validate_color_attribute,
    write_colors,
)
from ..core.channels import channels_to_indices
from ..ops._common import _after_write, effective_channels, is_isolated, poll_color_mesh
from ..preview import isolate
from . import core as bcore
from . import cursor_draw
from .stroke import BrushParams, build_cache, ray_cast_local, refresh_mask, stroke_at

UNDO_MESSAGE = "BadVC Brush Stroke"
# Object modes that are left for OBJECT mode while the session runs (restored on exit).
SWITCH_MODES = ('EDIT',)
MAX_DABS_PER_EVENT = 48
_UI_REGIONS = {'UI': 'show_region_ui', 'TOOLS': 'show_region_toolbar',
               'HEADER': 'show_region_header', 'TOOL_HEADER': 'show_region_tool_header'}
_STRENGTH_PX = 300.0  # mouse travel (px) for the full 0..1 strength range in Shift+F

_session = {'op': None}  # only one brush session at a time


def _window_region(area):
    return next((r for r in area.regions if r.type == 'WINDOW'), None) if area else None


def _over_ui(area, space, mx: int, my: int) -> bool:
    """True if window coords (mx, my) are over a visible non-WINDOW region of the area (sidebar, toolbar...)."""
    for r in area.regions:
        flag = _UI_REGIONS.get(r.type)
        if flag is None or not getattr(space, flag, True):
            continue
        if r.x <= mx < r.x + r.width and r.y <= my < r.y + r.height:
            return True
    return False


def _step_radius(radius: int, factor: float) -> int:
    new = max(1, int(round(radius * factor)))
    if new == radius:
        new = max(1, radius + (1 if factor > 1.0 else -1))
    return new


def brush_target(settings, isolated: bool) -> tuple:
    """RGBA brush target. While a channel is isolated it is always Value (color alpha would leak in)."""
    if not isolated and settings.blend_source == 'COLOR':
        return tuple(float(c) for c in settings.color)
    return (float(settings.value),) * 4


def is_exit_event(etype: str, value: str, ctrl: bool) -> bool:
    """Events that end the brush session: Esc, RMB, Enter, Ctrl+Tab (all on PRESS)."""
    if value != 'PRESS':
        return False
    return etype in {'ESC', 'RIGHTMOUSE', 'RET', 'NUMPAD_ENTER'} or (etype == 'TAB' and bool(ctrl))


class BADVC_OT_brush(bpy.types.Operator):
    """Paint vertex colors with an interactive brush (Mix / Add / Sub / Blur)"""
    bl_idname = "badvc.brush"
    bl_label = "Brush"
    bl_options = {'REGISTER'}  # no 'UNDO': one undo step per stroke is pushed manually

    @classmethod
    def poll(cls, context):
        return poll_color_mesh(context) and _session['op'] is None

    # ------------------------------------------------------------------ lifecycle

    def invoke(self, context, event):
        area = context.area
        region = _window_region(area)
        if (area is None or area.type != 'VIEW_3D' or region is None
                or context.space_data is None or context.space_data.region_3d is None):
            self.report({'WARNING'}, "Use from the 3D viewport")
            return {'CANCELLED'}
        obj = context.active_object
        mesh = obj.data
        attr = get_active_color_attribute(mesh)
        error = validate_color_attribute(mesh, attr)
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        if len(mesh.polygons) == 0:
            self.report({'WARNING'}, "Mesh has no faces")
            return {'CANCELLED'}

        self._area, self._window = area, context.window
        self._obj_name = obj.name
        self._orig_mode = obj.mode
        self._switched = False
        self._handle = None
        self._ui_set = False
        self._ui_cursor = False
        self._stroke = False
        self._stroke_dirty = False
        self._resize = None
        self._last = None
        self._carry = 0.0
        self._work = None
        self._header = None
        self._done = False
        self._state = {'pos': None, 'radius': 50.0, 'mode': 'MIX', 'strength': 0.5, 'failed': False}
        try:
            if self._orig_mode in SWITCH_MODES:
                bpy.ops.object.mode_set(mode='OBJECT')
                self._switched = True
            mesh = obj.data
            attr = get_active_color_attribute(mesh)
            self._attr_name, self._domain, self._attr_type = attr.name, attr.domain, attr.data_type
            self._sig = (len(mesh.vertices), len(mesh.loops), len(mesh.polygons))
            self._cache = build_cache(obj, attr.domain)
            refresh_mask(self._cache, obj, context.scene.badvc.scope, self._orig_mode)
        except Exception:
            traceback.print_exc()
            self._cleanup(context)
            self.report({'ERROR'}, "Could not start the brush (see console)")
            return {'CANCELLED'}

        _session['op'] = self
        self._handle = cursor_draw.add_handler(self._state)
        self._ui_set = True
        mx, my = event.mouse_x - region.x, event.mouse_y - region.y
        self._update_pointer(context, region, mx, my)
        self._sync_header(context)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _cleanup(self, context=None):
        """Remove draw handler, header and cursor; restore the object mode. Idempotent, called from every exit path."""
        if _session['op'] is self:
            _session['op'] = None
        cursor_draw.remove_handler(getattr(self, '_handle', None))
        self._handle = None
        if getattr(self, '_ui_set', False):
            self._ui_set = False
            try:
                self._area.header_text_set(None)
                self._window.cursor_modal_restore()
            except Exception:
                pass
        if getattr(self, '_switched', False):
            self._switched = False
            try:
                obj = bpy.data.objects.get(self._obj_name)
                if obj is not None and obj.mode == 'OBJECT':
                    with bpy.context.temp_override(active_object=obj, object=obj):
                        bpy.ops.object.mode_set(mode=self._orig_mode)
            except Exception:
                traceback.print_exc()
        try:
            self._area.tag_redraw()
            isolate.tag_redraw()
        except Exception:
            pass

    def cancel(self, context):
        self._cleanup(context)

    # ------------------------------------------------------------------ modal

    def modal(self, context, event):
        if self._done:
            return {'CANCELLED'}
        try:
            result = self._modal(context, event)
        except Exception:
            traceback.print_exc()
            self._cleanup(context)
            self._done = True
            return {'CANCELLED'}
        if result & {'FINISHED', 'CANCELLED'}:
            self._done = True
        return result

    def _exit(self, context, result=None):
        if self._stroke:
            self._end_stroke(context)
        self._cleanup(context)
        return result or {'FINISHED'}

    def _target_valid(self, context) -> bool:
        """The session object/attribute still exist unchanged (nothing is cached by pointer)."""
        obj = bpy.data.objects.get(self._obj_name)
        if obj is None or obj.type != 'MESH' or context.active_object is not obj:
            return False
        mesh = obj.data
        if (len(mesh.vertices), len(mesh.loops), len(mesh.polygons)) != self._sig:
            return False
        attr = mesh.color_attributes.get(self._attr_name)
        return (attr is not None and attr.domain == self._domain
                and attr.data_type == self._attr_type)

    def _modal(self, context, event):
        etype, value = event.type, event.value

        # Exit branches first (valid wherever the mouse is).
        if etype == 'Z' and value == 'PRESS' and (event.ctrl or event.oskey):
            # Let Blender run its own undo: end the session (mode restored) and pass the event on.
            return self._exit(context, {'FINISHED', 'PASS_THROUGH'})
        if self._resize is not None:
            return self._modal_resize(context, event)
        if is_exit_event(etype, value, event.ctrl):
            return self._exit(context)

        region = _window_region(self._area)
        space = self._area.spaces.active if self._area else None
        if region is None or space is None or space.type != 'VIEW_3D' or not self._target_valid(context):
            return self._exit(context, {'CANCELLED'})

        # Navigation always goes to Blender.
        if (etype == 'MIDDLEMOUSE' or etype.startswith(('WHEEL', 'TRACKPAD', 'NDOF', 'NUMPAD'))
                or etype in {'TIMER', 'TIMER_REPORT', 'INBETWEEN_MOUSEMOVE'}):
            return {'PASS_THROUGH'}

        mx, my = event.mouse_x - region.x, event.mouse_y - region.y
        inside = (0 <= mx < region.width and 0 <= my < region.height
                  and not _over_ui(self._area, space, event.mouse_x, event.mouse_y))
        settings = context.scene.badvc

        if etype == 'LEFTMOUSE' and value == 'RELEASE' and self._stroke:
            self._end_stroke(context)
            return {'RUNNING_MODAL'}
        if etype == 'LEFTMOUSE' and value == 'PRESS':
            if not inside:
                return {'PASS_THROUGH'}  # sidebar buttons etc.
            if not self._stroke:
                self._begin_stroke(context, event, region, space, (mx, my))
            return {'RUNNING_MODAL'}
        if etype == 'MOUSEMOVE':
            if not inside:
                self._state['pos'] = None
                self._last = None
                if self._ui_cursor:
                    self._window.cursor_modal_set('DEFAULT')
                    self._ui_cursor = False
                self._area.tag_redraw()
                return {'PASS_THROUGH'}
            self._update_pointer(context, region, mx, my)
            if self._stroke:
                self._stroke_move(context, event, region, space, (mx, my))
            return {'RUNNING_MODAL'}
        if value == 'PRESS' and not self._stroke and inside:
            if etype in {'LEFT_BRACKET', 'RIGHT_BRACKET'}:
                f = 0.9 if etype == 'LEFT_BRACKET' else 1.1
                settings.brush_radius = _step_radius(settings.brush_radius, f)
                self._update_pointer(context, region, mx, my)
                self._sync_header(context)
            elif etype == 'F':
                self._begin_resize(context, 'strength' if event.shift else 'radius', (mx, my))
            return {'RUNNING_MODAL'}
        if etype in {'LEFT_SHIFT', 'RIGHT_SHIFT', 'LEFT_CTRL', 'RIGHT_CTRL'}:
            self._update_pointer(context, region, mx, my, event)
            return {'RUNNING_MODAL'}
        if not inside and etype != 'MOUSEMOVE':
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}

    # ------------------------------------------------------------------ pointer / header / resize

    def _mode_for(self, context, event=None) -> str:
        mode = context.scene.badvc.blend_mode
        if event is not None:
            mode = bcore.effective_mode(mode, event.ctrl, event.shift)
        return mode

    def _update_pointer(self, context, region, mx, my, event=None):
        settings = context.scene.badvc
        st = self._state
        st['pos'] = (mx, my)
        st['radius'] = float(settings.brush_radius)
        st['strength'] = float(settings.blend_strength)
        st['mode'] = self._mode_for(context, event)
        if not self._ui_cursor:
            self._window.cursor_modal_set('CROSSHAIR')
            self._ui_cursor = True
        self._area.tag_redraw()

    def _sync_header(self, context, extra: str = ""):
        s = context.scene.badvc
        src = f"  |  Value {s.value:.2f}" if is_isolated(context) else ""
        text = (f"Brush {s.blend_mode.title()}  |  Radius {s.brush_radius}px  |  Strength {s.blend_strength:.2f}{src}  |  "
                f"{extra or 'LMB paint  [ ] radius  F / Shift+F resize radius / strength  Shift blur  Ctrl invert  Esc/RMB/Enter/Ctrl+Tab exit'}")
        if text != self._header:
            self._header = text
            self._area.header_text_set(text)

    def _begin_resize(self, context, kind: str, mouse):
        s = context.scene.badvc
        self._resize = {'kind': kind, 'center': mouse,
                        'start': s.brush_radius if kind == 'radius' else s.blend_strength}
        st = self._state
        st['pos'] = mouse
        self._sync_header(context, f"Resize {kind}: move mouse, LMB/F/Enter confirm, Esc cancel")
        self._area.tag_redraw()

    def _modal_resize(self, context, event):
        rs, st, s = self._resize, self._state, context.scene.badvc
        region = _window_region(self._area)
        if region is None:
            self._resize = None
            return self._exit(context, {'CANCELLED'})
        mx, my = event.mouse_x - region.x, event.mouse_y - region.y
        cx, cy = rs['center']
        etype, value = event.type, event.value
        if etype == 'MOUSEMOVE':
            if rs['kind'] == 'radius':
                st['radius'] = max(1.0, float(np.hypot(mx - cx, my - cy)))
            else:
                st['strength'] = float(np.clip(rs['start'] + (mx - cx) / _STRENGTH_PX, 0.0, 1.0))
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        confirm = (value == 'PRESS' and etype in {'LEFTMOUSE', 'F', 'RET', 'NUMPAD_ENTER'})
        cancel = (value == 'PRESS' and etype in {'ESC', 'RIGHTMOUSE'})
        if confirm:
            if rs['kind'] == 'radius':
                s.brush_radius = max(1, int(round(st['radius'])))
            else:
                s.blend_strength = st['strength']
        if confirm or cancel:
            self._resize = None
            self._update_pointer(context, region, mx, my)
            self._sync_header(context)
        if etype.startswith(('WHEEL', 'TRACKPAD', 'NDOF')) or etype == 'MIDDLEMOUSE':
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}

    # ------------------------------------------------------------------ strokes

    def _begin_stroke(self, context, event, region, space, mouse):
        """Snapshot colors/target/channels/mask, then place the first dab."""
        obj = bpy.data.objects[self._obj_name]
        mesh = obj.data
        settings = context.scene.badvc
        attr = mesh.color_attributes[self._attr_name]
        self._work = read_colors(mesh, attr)
        refresh_mask(self._cache, obj, settings.scope, self._orig_mode)
        self._target = brush_target(settings, is_isolated(context))
        self._channels = tuple(channels_to_indices(effective_channels(context)))
        self._stroke = True
        self._stroke_dirty = False
        self._carry = 0.0
        self._last = mouse
        self._dab_batch(context, event, region, space, [mouse])

    def _stroke_move(self, context, event, region, space, mouse):
        settings = context.scene.badvc
        radius_px = float(settings.brush_radius)
        spacing = max(1.0, settings.brush_spacing * 0.01 * radius_px)
        if self._last is None:
            self._last = mouse
            self._dab_batch(context, event, region, space, [mouse])
            return
        pts, self._carry = bcore.dab_path(self._last, mouse, spacing, self._carry)
        self._last = mouse
        if len(pts) > MAX_DABS_PER_EVENT:  # very fast move: thin out instead of stalling
            pts = pts[np.linspace(0, len(pts) - 1, MAX_DABS_PER_EVENT).astype(int)]
        if len(pts):
            self._dab_batch(context, event, region, space, pts)

    def _dab_batch(self, context, event, region, space, points):
        """Apply dabs at region-pixel points to the cached work array, then write once."""
        rv = space.region_3d
        settings = context.scene.badvc
        radius_px = float(settings.brush_radius)
        params = BrushParams(
            mode=self._mode_for(context, event), target=self._target, channels_idx=self._channels,
            strength=float(settings.blend_strength), falloff=settings.brush_falloff,
            front_only=bool(settings.brush_front_faces_only))
        persp = rv.is_perspective
        changed = 0
        for p in points:
            coord = (float(p[0]), float(p[1]))
            origin = view3d_utils.region_2d_to_origin_3d(region, rv, coord)
            vec = view3d_utils.region_2d_to_vector_3d(region, rv, coord)
            hit = ray_cast_local(self._cache, origin, vec)
            if hit is None:
                continue
            hit_w = hit[0]
            a = view3d_utils.region_2d_to_location_3d(region, rv, coord, Vector(hit_w))
            b = view3d_utils.region_2d_to_location_3d(region, rv, (coord[0] + radius_px, coord[1]), Vector(hit_w))
            radius_world = float((b - a).length)
            if radius_world <= 0.0:
                continue
            changed += stroke_at(
                self._cache, self._work, hit_w, radius_world, params,
                view_origin=np.array(origin) if persp else None,
                view_dir=None if persp else np.array(vec))
        if changed:
            self._stroke_dirty = True
            self._flush(context)

    def _flush(self, context):
        obj = bpy.data.objects[self._obj_name]
        mesh = obj.data
        write_colors(mesh, mesh.color_attributes[self._attr_name], self._work)
        _after_write(context)

    def _end_stroke(self, context):
        self._stroke = False
        self._last = None
        self._work = None
        if self._stroke_dirty:
            self._stroke_dirty = False
            bpy.ops.ed.undo_push(message=UNDO_MESSAGE)


classes = (BADVC_OT_brush,)
