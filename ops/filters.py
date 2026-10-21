"""F05: one-shot filters (Mix / Add / Sub, Blur)."""

import bpy
import numpy as np
from bpy.props import EnumProperty, FloatProperty, FloatVectorProperty, IntProperty

from ..core import blend
from ..core.channels import CHANNEL_ITEMS
from ..core.topology import (
    corner_to_point,
    edge_vertex_pairs,
    loop_vertex_indices,
    vertex_neighbor_mean,
)
from ._common import effective_source, init_from_settings, poll_color_mesh, run_color_op, run_full_op
from .fill import SCOPE_ITEMS

_MODE_FUNCS = {'MIX': blend.mix, 'ADD': blend.add, 'SUB': blend.sub}


def _init_extra(op, context, mapping: dict) -> None:
    """Copy Scene.badvc props (op prop -> settings prop) that were not set explicitly."""
    settings = context.scene.badvc
    for name, src in mapping.items():
        if op.properties.is_property_set(name):
            continue
        setattr(op, name, getattr(settings, src))


class BADVC_OT_filter_blend(bpy.types.Operator):
    """Mix / Add / Subtract a color or value into the selected channels"""
    bl_idname = "badvc.filter_blend"
    bl_label = "Filter"
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(name="Mode", items=[
        ('MIX', "Mix", "Interpolate towards the color/value"),
        ('ADD', "Add", "Add color/value times strength"),
        ('SUB', "Sub", "Subtract color/value times strength"),
    ], default='MIX')
    source: EnumProperty(name="Source", items=[
        ('COLOR', "Color", "Use the color"),
        ('VALUE', "Value", "Use a single value in all channels"),
    ], default='COLOR')
    color: FloatVectorProperty(name="Color", subtype='COLOR_GAMMA', size=4, min=0.0, max=1.0,
                               default=(1.0, 1.0, 1.0, 1.0))
    value: FloatProperty(name="Value", min=0.0, max=1.0, default=1.0, subtype='FACTOR')
    strength: FloatProperty(name="Strength", min=0.0, max=1.0, default=0.5, subtype='FACTOR')
    channels: EnumProperty(name="Channels", items=CHANNEL_ITEMS, options={'ENUM_FLAG'},
                           default={'R', 'G', 'B', 'A'})
    scope: EnumProperty(name="Scope", items=SCOPE_ITEMS, default='SELECTED')

    @classmethod
    def poll(cls, context):
        return poll_color_mesh(context)

    def invoke(self, context, event):
        init_from_settings(self, context, ('color', 'value', 'channels', 'scope'))
        explicit_source = self.properties.is_property_set('source')
        _init_extra(self, context, {'source': 'blend_source', 'strength': 'blend_strength'})
        if not explicit_source:
            self.source = effective_source(context, self.source)  # isolated: always Value
        if context.scene.badvc.blend_mode != 'BLUR':  # BLUR belongs to badvc.blur
            _init_extra(self, context, {'mode': 'blend_mode'})
        return self.execute(context)

    def execute(self, context):
        if self.source == 'COLOR':
            b = np.array(self.color, dtype=np.float32)
        else:
            b = np.full(4, self.value, dtype=np.float32)
        fn = _MODE_FUNCS[self.mode]
        strength = self.strength
        return run_color_op(self, context, lambda c: fn(c, np.broadcast_to(b, c.shape), strength),
                            set(self.channels), self.scope)


def blur_full(colors: np.ndarray, mask: np.ndarray, mesh, domain: str,
              iterations: int, strength: float) -> np.ndarray:
    """Blur over edge adjacency. Returns the full array; caller writes only masked rows.

    POINT: each iteration lerp(c, neighbor_mean(c), strength) for masked vertices;
    unmasked vertices take part in the mean but keep their value.
    CORNER: the per-vertex field (corner mean) is blurred for N iterations
    (all vertices, temporary array); masked corners then become
    lerp(corner, blurred[loop_vertex], strength). Unmasked corners are untouched.
    """
    edges = edge_vertex_pairs(mesh)
    n_verts = len(mesh.vertices)
    if domain == 'POINT':
        c = colors.copy()
        for _ in range(iterations):
            mean = vertex_neighbor_mean(c, edges, n_verts)
            c[mask] = blend.mix(c[mask], mean[mask], strength)
        return c
    v = corner_to_point(colors, mesh)
    for _ in range(iterations):
        v = blend.mix(v, vertex_neighbor_mean(v, edges, n_verts), strength)
    target = v[loop_vertex_indices(mesh)]
    out = colors.copy()
    out[mask] = blend.mix(colors[mask], target[mask], strength)
    return out


class BADVC_OT_blur(bpy.types.Operator):
    """Blur the active color attribute over mesh edges"""
    bl_idname = "badvc.blur"
    bl_label = "Blur"
    bl_options = {'REGISTER', 'UNDO'}

    iterations: IntProperty(name="Iterations", min=1, max=100, default=3)
    strength: FloatProperty(name="Strength", min=0.0, max=1.0, default=0.5, subtype='FACTOR')
    channels: EnumProperty(name="Channels", items=CHANNEL_ITEMS, options={'ENUM_FLAG'},
                           default={'R', 'G', 'B', 'A'})
    scope: EnumProperty(name="Scope", items=SCOPE_ITEMS, default='SELECTED')

    @classmethod
    def poll(cls, context):
        return poll_color_mesh(context)

    def invoke(self, context, event):
        init_from_settings(self, context, ('channels', 'scope'))
        _init_extra(self, context, {'iterations': 'blur_iterations', 'strength': 'blend_strength'})
        return self.execute(context)

    def execute(self, context):
        its, st = self.iterations, self.strength
        return run_full_op(self, context, lambda c, m, mesh, d: blur_full(c, m, mesh, d, its, st),
                           set(self.channels), self.scope)


classes = (BADVC_OT_filter_blend, BADVC_OT_blur)
