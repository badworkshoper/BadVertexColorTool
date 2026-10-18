"""F03: set a single channel value / sample channel averages."""

import bpy
import numpy as np
from bpy.props import EnumProperty, FloatProperty

from ..core.channels import CHANNEL_ITEMS
from ._common import init_from_settings, poll_color_mesh, run_color_op, sample_mean
from .fill import SCOPE_ITEMS


class BADVC_OT_set_channel_value(bpy.types.Operator):
    """Set one color channel to a value"""
    bl_idname = "badvc.set_channel_value"
    bl_label = "Set Channel Value"
    bl_options = {'REGISTER', 'UNDO'}

    channel: EnumProperty(name="Channel", items=CHANNEL_ITEMS, default='R')
    value: FloatProperty(name="Value", min=0.0, max=1.0, default=1.0, subtype='FACTOR')
    scope: EnumProperty(name="Scope", items=SCOPE_ITEMS, default='SELECTED')

    @classmethod
    def poll(cls, context):
        return poll_color_mesh(context)

    def invoke(self, context, event):
        init_from_settings(self, context, ('scope',))
        return self.execute(context)

    def execute(self, context):
        v = self.value
        return run_color_op(self, context, lambda c: np.full_like(c, v),
                            {self.channel}, self.scope)


class BADVC_OT_sample_channels(bpy.types.Operator):
    """Read the average R, G, B, A of the affected elements into the Channel Values sliders"""
    bl_idname = "badvc.sample_channels"
    bl_label = "Sample Channels"
    # No UNDO: the mesh is not modified, only a scene UI setting changes.
    bl_options = {'REGISTER'}

    scope: EnumProperty(name="Scope", items=SCOPE_ITEMS, default='SELECTED')

    @classmethod
    def poll(cls, context):
        return poll_color_mesh(context)

    def invoke(self, context, event):
        init_from_settings(self, context, ('scope',))
        return self.execute(context)

    def execute(self, context):
        try:
            mean = sample_mean(context, context.active_object, self.scope)
        except ValueError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        if mean is None:
            self.report({'WARNING'}, "Nothing selected")
            return {'CANCELLED'}
        context.scene.badvc.channel_values = tuple(float(x) for x in mean)
        return {'FINISHED'}


classes = (BADVC_OT_set_channel_value, BADVC_OT_sample_channels)
