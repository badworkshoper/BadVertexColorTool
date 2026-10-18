"""F01: Fill operators."""

import bpy
import numpy as np
from bpy.props import EnumProperty, FloatProperty, FloatVectorProperty

from ..core.channels import CHANNEL_ITEMS
from ._common import init_from_settings, poll_color_mesh, run_color_op

SCOPE_ITEMS = [
    ('ALL', "All", "Affect the whole mesh"),
    ('SELECTED', "Selected", "Affect only selected elements"),
]


class BADVC_OT_fill(bpy.types.Operator):
    """Fill the active color attribute with a color"""
    bl_idname = "badvc.fill"
    bl_label = "Fill Color"
    bl_options = {'REGISTER', 'UNDO'}

    color: FloatVectorProperty(name="Color", subtype='COLOR_GAMMA', size=4, min=0.0, max=1.0,
                               default=(1.0, 1.0, 1.0, 1.0))
    channels: EnumProperty(name="Channels", items=CHANNEL_ITEMS, options={'ENUM_FLAG'},
                           default={'R', 'G', 'B', 'A'})
    scope: EnumProperty(name="Scope", items=SCOPE_ITEMS, default='SELECTED')

    @classmethod
    def poll(cls, context):
        return poll_color_mesh(context)

    def invoke(self, context, event):
        init_from_settings(self, context, ('color', 'channels', 'scope'))
        return self.execute(context)

    def execute(self, context):
        color = np.array(self.color, dtype=np.float32)
        return run_color_op(self, context, lambda c: np.broadcast_to(color, c.shape),
                            set(self.channels), self.scope)


class BADVC_OT_fill_value(bpy.types.Operator):
    """Fill the selected channels with a single value"""
    bl_idname = "badvc.fill_value"
    bl_label = "Fill Value"
    bl_options = {'REGISTER', 'UNDO'}

    value: FloatProperty(name="Value", min=0.0, max=1.0, default=1.0, subtype='FACTOR')
    channels: EnumProperty(name="Channels", items=CHANNEL_ITEMS, options={'ENUM_FLAG'},
                           default={'R', 'G', 'B', 'A'})
    scope: EnumProperty(name="Scope", items=SCOPE_ITEMS, default='SELECTED')

    @classmethod
    def poll(cls, context):
        return poll_color_mesh(context)

    def invoke(self, context, event):
        init_from_settings(self, context, ('channels', 'scope'))
        return self.execute(context)

    def execute(self, context):
        v = self.value
        return run_color_op(self, context, lambda c: np.full_like(c, v),
                            set(self.channels), self.scope)


classes = (BADVC_OT_fill, BADVC_OT_fill_value)
