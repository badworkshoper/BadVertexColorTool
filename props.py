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
from .core.gradient import EASING_ITEMS


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
    blend_mode: EnumProperty(
        name="Mode",
        description="Blend mode, shared by the Blend filter and the Brush",
        items=[
            ('MIX', "Mix", "Interpolate towards the color/value"),
            ('ADD', "Add", "Add color/value times strength"),
            ('SUB', "Sub", "Subtract color/value times strength"),
        ],
        default='MIX',
    )
    blend_source: EnumProperty(
        name="Source",
        description="What the blend uses, shared by the Blend filter and the Brush",
        items=[
            ('COLOR', "Color", "Use the color picker"),
            ('VALUE', "Value", "Use a single value in all channels"),
        ],
        default='COLOR',
    )
    blend_strength: FloatProperty(
        name="Strength",
        description="Blend strength, shared by the Blend filter and the Brush",
        min=0.0,
        max=1.0,
        default=0.5,
        subtype='FACTOR',
    )
    blur_iterations: IntProperty(
        name="Iterations",
        description="Number of blur iterations",
        min=1,
        max=100,
        default=3,
    )
    blur_strength: FloatProperty(
        name="Blur Strength",
        description="Blend factor towards the neighbour average per iteration",
        min=0.0,
        max=1.0,
        default=0.5,
        subtype='FACTOR',
    )
    gradient_source: EnumProperty(
        name="Source",
        description="What the gradient interpolates",
        items=[
            ('VALUE', "Value", "Two values, written to the selected channels"),
            ('COLOR', "Color", "Two colors"),
        ],
        default='VALUE',
    )
    gradient_start_value: FloatProperty(
        name="Start", description="Value at the start of the gradient",
        min=0.0, max=1.0, default=0.0, subtype='FACTOR')
    gradient_end_value: FloatProperty(
        name="End", description="Value at the end of the gradient",
        min=0.0, max=1.0, default=1.0, subtype='FACTOR')
    gradient_color_a: FloatVectorProperty(
        name="Color A", description="Color at the start of the gradient",
        subtype='COLOR_GAMMA', size=4, min=0.0, max=1.0, default=(0.0, 0.0, 0.0, 1.0))
    gradient_color_b: FloatVectorProperty(
        name="Color B", description="Color at the end of the gradient",
        subtype='COLOR_GAMMA', size=4, min=0.0, max=1.0, default=(1.0, 1.0, 1.0, 1.0))
    gradient_easing: EnumProperty(
        name="Easing", description="Gradient curve", items=EASING_ITEMS, default='LINEAR')
    gradient_axis: EnumProperty(
        name="Axis", description="Gradient axis",
        items=[('X', "X", ""), ('Y', "Y", ""), ('Z', "Z", "")], default='Z')
    gradient_space: EnumProperty(
        name="Space", description="Coordinate space of the axis",
        items=[('LOCAL', "Local", "Object space"), ('WORLD', "World", "World space")],
        default='LOCAL')
    gradient_shape: EnumProperty(
        name="Shape", description="Gradient shape",
        items=[('LINEAR', "Linear", "Along the axis"), ('RADIAL', "Radial", "Distance from the center")],
        default='LINEAR')
    gradient_method: EnumProperty(
        name="Method", description="How t is measured between the vertices",
        items=[
            ('LINEAR', "Linear", "Projection on the segment between the points"),
            ('GEODESIC', "Geodesic", "Distance along mesh edges"),
        ],
        default='LINEAR')
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
