"""Add-on settings stored on Scene.badvc."""

import bpy
from bpy.props import (
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    StringProperty,
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
        subtype='COLOR_GAMMA',
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
    channel_values: FloatVectorProperty(
        name="Channel Values",
        description="Per-channel values for the Channel Values panel (no automatic mesh writes)",
        size=4,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0, 1.0),
    )
    transfer_source: StringProperty(
        name="Source",
        description="Name of the source color attribute for Channel Transfer",
    )
    transfer_src_channel: EnumProperty(
        name="From",
        description="Source channel",
        items=CHANNEL_ITEMS,
        default='R',
    )
    transfer_dst_channel: EnumProperty(
        name="To",
        description="Destination channel",
        items=CHANNEL_ITEMS,
        default='G',
    )
    transfer_mode: EnumProperty(
        name="Mode",
        description="Transfer a single channel or the selected channels of the whole color",
        items=[
            ('CHANNEL', "Channel", "Transfer one channel to another"),
            ('COLOR', "Color", "Transfer the target channels (same channel to same channel)"),
        ],
        default='CHANNEL',
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
