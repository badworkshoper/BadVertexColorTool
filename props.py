"""Add-on settings stored on Scene.badvc."""

import bpy
from bpy.props import (
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
)

from .core.channels import CHANNEL_ITEMS


class BADVC_PG_Settings(bpy.types.PropertyGroup):
    target_channels: EnumProperty(
        name="Channels",
        description="Color channels affected by operations",
        items=CHANNEL_ITEMS,
        options={'ENUM_FLAG'},
        default={'R', 'G', 'B', 'A'},
    )
    scope: EnumProperty(
        name="Scope",
        description="Which elements are affected",
        items=[
            ('ALL', "All", "Affect the whole mesh"),
            ('SELECTED', "Selected", "Affect only selected elements"),
        ],
        default='SELECTED',
    )
    color: FloatVectorProperty(
        name="Color",
        description="Color used for filling",
        subtype='COLOR',
        size=4,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0, 1.0),
    )
    value: FloatProperty(
        name="Value",
        description="Channel value",
        min=0.0,
        max=1.0,
        default=1.0,
    )
    # Brush settings (declaration only, used by F10).
    brush_radius: IntProperty(
        name="Radius",
        description="Brush radius in pixels",
        min=1,
        soft_max=500,
        default=50,
        subtype='PIXEL',
    )
    brush_strength: FloatProperty(
        name="Strength",
        description="Brush strength",
        min=0.0,
        max=1.0,
        default=0.5,
    )
    brush_falloff: EnumProperty(
        name="Falloff",
        description="Brush falloff shape",
        items=[
            ('SMOOTH', "Smooth", ""),
            ('LINEAR', "Linear", ""),
            ('SHARP', "Sharp", ""),
            ('CONSTANT', "Constant", ""),
        ],
        default='SMOOTH',
    )


classes = (BADVC_PG_Settings,)
