"""F06: Levels / Brightness-Contrast / Posterize / Clamp."""

import bpy
from bpy.props import EnumProperty, FloatProperty, IntProperty

from ..core import blend
from ..core.channels import CHANNEL_ITEMS
from ._common import init_from_settings, poll_color_mesh, run_color_op
from .fill import SCOPE_ITEMS


class _LevelsBase:
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return poll_color_mesh(context)

    def invoke(self, context, event):
        init_from_settings(self, context, ('channels', 'scope'))
        return self.execute(context)

    def _run(self, context, func):
        return run_color_op(self, context, func, set(self.channels), self.scope)


def _channels():
    return EnumProperty(name="Channels", items=CHANNEL_ITEMS, options={'ENUM_FLAG'},
                        default={'R', 'G', 'B', 'A'})


def _scope():
    return EnumProperty(name="Scope", items=SCOPE_ITEMS, default='SELECTED')


class BADVC_OT_levels(_LevelsBase, bpy.types.Operator):
    """Levels: input range, gamma and output range (defaults are identity; tweak in Adjust Last Operation)"""
    bl_idname = "badvc.levels"
    bl_label = "Levels"

    in_black: FloatProperty(name="Input Black", min=0.0, max=1.0, default=0.0)
    in_white: FloatProperty(name="Input White", min=0.0, max=1.0, default=1.0)
    gamma: FloatProperty(name="Gamma", min=0.01, max=10.0, default=1.0)
    out_black: FloatProperty(name="Output Black", min=0.0, max=1.0, default=0.0)
    out_white: FloatProperty(name="Output White", min=0.0, max=1.0, default=1.0)
    channels: _channels()
    scope: _scope()

    def execute(self, context):
        return self._run(context, lambda c: blend.levels(
            c, self.in_black, self.in_white, self.gamma, self.out_black, self.out_white))


class BADVC_OT_brightness_contrast(_LevelsBase, bpy.types.Operator):
    """Brightness / Contrast (defaults are identity; tweak in Adjust Last Operation)"""
    bl_idname = "badvc.brightness_contrast"
    bl_label = "Brightness / Contrast"

    brightness: FloatProperty(name="Brightness", min=-1.0, max=1.0, default=0.0)
    contrast: FloatProperty(name="Contrast", min=-1.0, max=1.0, default=0.0)
    channels: _channels()
    scope: _scope()

    def execute(self, context):
        return self._run(context, lambda c: blend.brightness_contrast(c, self.brightness, self.contrast))


class BADVC_OT_posterize(_LevelsBase, bpy.types.Operator):
    """Quantize values to a number of steps"""
    bl_idname = "badvc.posterize"
    bl_label = "Posterize"

    steps: IntProperty(name="Steps", min=2, max=64, default=4)
    channels: _channels()
    scope: _scope()

    def execute(self, context):
        return self._run(context, lambda c: blend.posterize(c, self.steps))


class BADVC_OT_clamp_values(_LevelsBase, bpy.types.Operator):
    """Clamp values to a range (defaults are identity; tweak in Adjust Last Operation)"""
    bl_idname = "badvc.clamp_values"
    bl_label = "Clamp"

    min: FloatProperty(name="Min", min=0.0, max=1.0, default=0.0)
    max: FloatProperty(name="Max", min=0.0, max=1.0, default=1.0)
    channels: _channels()
    scope: _scope()

    def execute(self, context):
        return self._run(context, lambda c: blend.clamp(c, self.min, self.max))


classes = (BADVC_OT_levels, BADVC_OT_brightness_contrast, BADVC_OT_posterize, BADVC_OT_clamp_values)
