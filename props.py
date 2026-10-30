"""Add-on settings stored on Scene.badvc."""

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)

from .core.bake import SWIZZLE_ITEMS
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
        description="Mode, shared by Apply and the Brush",
        items=[
            ('MIX', "Mix", "Interpolate towards the color/value"),
            ('ADD', "Add", "Add color/value times strength"),
            ('SUB', "Sub", "Subtract color/value times strength"),
            ('BLUR', "Blur", "Interpolate towards the average of the neighbours"),
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
        description="Strength, shared by Apply and the Brush",
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
    # Interactive brush (F10). Color / value / blend_source are shared with Paint.
    brush_radius: IntProperty(
        name="Radius",
        description="Brush radius in pixels",
        min=1,
        soft_max=500,
        default=50,
        subtype='PIXEL',
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
    brush_spacing: FloatProperty(
        name="Spacing",
        description="Distance between dabs along the stroke, in percent of the brush radius",
        min=1.0,
        soft_max=100.0,
        max=500.0,
        default=10.0,
        subtype='PERCENTAGE',
    )
    brush_front_faces_only: BoolProperty(
        name="Front Faces Only",
        description="Ignore vertices facing away from the camera",
        default=True,
    )
    # Bake to channel (F09)
    bake_type: EnumProperty(
        name="Bake", description="What to bake into the channels",
        items=[('NORMAL', "Normal", "Normal vector components"),
               ('AO', "AO", "Ambient occlusion"),
               ('RANDOM', "Random", "Random value per part / face / vertex"),
               ('POSITION', "Position", "Height or distance")],
        default='NORMAL')
    bake_normal_space: EnumProperty(
        name="Space", description="Space of the baked normals",
        items=[('OBJECT', "Object", "Object space"), ('WORLD', "World", "World space")],
        default='OBJECT')
    bake_normal_source: EnumProperty(
        name="Source", description="Where the normals come from",
        items=[('MESH', "Mesh", "Own (split / custom) normals of the mesh"),
               ('PROXY', "Proxy", "Normals of the nearest surface point of another object"),
               ('SPHERICAL', "Spherical", "Direction from a center point")],
        default='MESH')
    bake_proxy: PointerProperty(
        name="Proxy", description="Mesh object whose surface normals are transferred",
        type=bpy.types.Object, poll=lambda self, obj: obj.type == 'MESH')
    bake_center: EnumProperty(
        name="Center", description="Center of the spherical normals",
        items=[('ORIGIN', "Origin", "Object origin"),
               ('BBOX', "Bounds", "Center of the mesh bounding box"),
               ('CURSOR', "Cursor", "3D cursor"),
               ('SELECTION', "Selection", "Center of the affected vertices")],
        default='ORIGIN')
    bake_normal_smooth: BoolProperty(
        name="Smooth", description="Use smooth vertex normals on Face Corner attributes "
                                   "(off: split/custom corner normals)", default=True)
    bake_swizzle_r: EnumProperty(name="R", description="Normal component written to R",
                                 items=SWIZZLE_ITEMS, default='POS_X')
    bake_swizzle_g: EnumProperty(name="G", description="Normal component written to G",
                                 items=SWIZZLE_ITEMS, default='POS_Y')
    bake_swizzle_b: EnumProperty(name="B", description="Normal component written to B",
                                 items=SWIZZLE_ITEMS, default='POS_Z')
    bake_swizzle_a: EnumProperty(name="A", description="Normal component written to A",
                                 items=SWIZZLE_ITEMS, default='NONE')
    bake_ao_samples: IntProperty(name="Samples", description="Rays per vertex",
                                 min=4, max=512, default=32)
    bake_ao_distance: FloatProperty(name="Distance", description="Maximum ray length (world units)",
                                    min=0.001, default=1.0, subtype='DISTANCE')
    bake_ao_bias: FloatProperty(name="Bias", description="Ray origin offset along the normal (world units)",
                                min=0.0, default=0.001, precision=4)
    bake_ao_include_selected: BoolProperty(
        name="Include Selected Objects", description="Other selected meshes also occlude", default=False)
    bake_random_per: EnumProperty(
        name="Per", description="Granularity of the random value",
        items=[('LOOSE_PART', "Loose Part", "One value per connected piece"),
               ('FACE', "Face", "One value per face"),
               ('VERTEX', "Vertex", "One value per vertex")],
        default='LOOSE_PART')
    bake_random_seed: IntProperty(name="Seed", description="Random seed", default=0)
    bake_random_min: FloatProperty(name="Min", min=0.0, max=1.0, default=0.0, subtype='FACTOR')
    bake_random_max: FloatProperty(name="Max", min=0.0, max=1.0, default=1.0, subtype='FACTOR')
    bake_random_per_channel: BoolProperty(
        name="Per Channel", description="Independent random value for every channel", default=False)
    bake_pos_mode: EnumProperty(
        name="Mode", description="What is measured",
        items=[('AXIS', "Axis", "Coordinate along an axis"),
               ('DISTANCE', "Distance", "Distance from a center")],
        default='AXIS')
    bake_pos_axis: EnumProperty(name="Axis", items=[('X', "X", ""), ('Y', "Y", ""), ('Z', "Z", "")],
                                default='Z')
    bake_pos_center: EnumProperty(
        name="Center", description="Center of the distance",
        items=[('ORIGIN', "Origin", "Origin of the space"),
               ('BBOX', "Bounds", "Center of the mesh bounding box"),
               ('CURSOR', "Cursor", "3D cursor"),
               ('PART', "Part", "Bounding box center of the vertex's own loose part")],
        default='BBOX')
    bake_pos_space: EnumProperty(
        name="Space", description="Coordinate space",
        items=[('LOCAL', "Local", "Object space"), ('WORLD', "World", "World space")], default='LOCAL')
    bake_pos_per_part: BoolProperty(
        name="Per Part", description="Normalise separately inside every loose part", default=False)
    bake_pos_invert: BoolProperty(name="Invert", description="Write 1 - value", default=False)


classes = (BADVC_PG_Settings,)
