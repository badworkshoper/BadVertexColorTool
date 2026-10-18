"""F02: Invert operator."""

import bpy
from bpy.props import EnumProperty

from ..core.channels import CHANNEL_ITEMS
from ._common import init_from_settings, poll_color_mesh, run_color_op
from .fill import SCOPE_ITEMS


class BADVC_OT_invert(bpy.types.Operator):
    """Invert (1 - x) the selected channels"""
    bl_idname = "badvc.invert"
    bl_label = "Invert"
    bl_options = {'REGISTER', 'UNDO'}

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
        return run_color_op(self, context, lambda c: 1.0 - c, set(self.channels), self.scope)


classes = (BADVC_OT_invert,)
