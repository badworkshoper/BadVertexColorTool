"""Sidebar panel. Read-only except for explicit user actions."""

import bpy

from ..ops._common import effective_channels, poll_color_mesh
from ..ops.gradient import get_group


class BADVC_PT_main(bpy.types.Panel):
    bl_label = "Vertex Colors"
    bl_idname = "BADVC_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "BadVC"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            layout.label(text="Select a mesh object", icon='INFO')
            return

        mesh = obj.data
        if mesh.color_attributes.active_color is None:
            layout.label(text="No active color attribute", icon='ERROR')

        settings = context.scene.badvc
        wm = context.window_manager
        iso = wm.badvc_isolate
        row = layout.row(align=True)
        row.enabled = iso == 'NONE'
        row.prop(settings, "target_channels", expand=True)
        if iso != 'NONE':
            layout.label(text=f"Isolated: {iso} \u2014 edits affect only this channel", icon='HIDE_OFF')
        row = layout.row(align=True)
        row.label(text="Isolate:")
        for ch in "RGBA":
            op = row.operator("badvc.isolate_channel", text=ch, depress=(iso == ch))
            op.channel = ch
        if iso != 'NONE':
            op = row.operator("badvc.isolate_channel", text="", icon='X')
            op.channel = 'NONE'
        layout.prop(wm, "badvc_isolate_shading", text="Shading")
        row = layout.row(align=True)
        row.prop(settings, "scope", expand=True)


class _SubPanel:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "BadVC"
    bl_parent_id = "BADVC_PT_main"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'


class BADVC_PT_paint(_SubPanel, bpy.types.Panel):
    bl_label = "Paint"
    bl_idname = "BADVC_PT_paint"

    def draw(self, context):
        layout = self.layout
        layout.enabled = poll_color_mesh(context)
        settings = context.scene.badvc

        layout.prop(settings, "color", text="")
        layout.prop(settings, "value", text="Value", slider=True)

        row = layout.row(align=True)
        op = row.operator("badvc.fill", text="Fill with Color")
        op.color = settings.color
        op.channels = effective_channels(context)
        op.scope = settings.scope
        op = row.operator("badvc.fill_value", text="Fill with Value")
        op.value = settings.value
        op.channels = effective_channels(context)
        op.scope = settings.scope

        op = layout.operator("badvc.invert", text="Invert", icon='ARROW_LEFTRIGHT')
        op.channels = effective_channels(context)
        op.scope = settings.scope

        layout.separator()
        layout.label(text="Blend")
        row = layout.row(align=True)
        row.prop(settings, "blend_mode", expand=True)
        row = layout.row(align=True)
        row.prop(settings, "blend_source", expand=True)
        layout.prop(settings, "blend_strength", text="Strength", slider=True)
        op = layout.operator("badvc.filter_blend", text="Apply")
        op.mode = settings.blend_mode
        op.source = settings.blend_source
        op.strength = settings.blend_strength
        op.color = settings.color
        op.value = settings.value
        op.channels = effective_channels(context)
        op.scope = settings.scope

        layout.separator()
        layout.label(text="Blur")
        row = layout.row(align=True)
        row.prop(settings, "blur_iterations", text="Iterations")
        row.prop(settings, "blur_strength", text="Strength", slider=True)
        op = layout.operator("badvc.blur", text="Blur")
        op.iterations = settings.blur_iterations
        op.strength = settings.blur_strength
        op.channels = effective_channels(context)
        op.scope = settings.scope

        layout.separator()
        layout.label(text="Brush")
        row = layout.row(align=True)
        row.prop(settings, "brush_mode", expand=True)
        layout.prop(settings, "brush_radius", text="Radius")
        layout.prop(settings, "brush_strength", text="Strength", slider=True)
        layout.prop(settings, "brush_falloff", text="Falloff")
        layout.prop(settings, "brush_spacing", text="Spacing")
        layout.prop(settings, "brush_front_faces_only")
        row = layout.row()
        row.scale_y = 1.5
        row.operator_context = 'INVOKE_DEFAULT'
        row.operator("badvc.brush", text="Brush", icon='BRUSH_DATA')
        layout.label(text="Esc/RMB/Enter: exit · [ ] radius · Shift: blur · Ctrl: invert")


class BADVC_PT_gradient(_SubPanel, bpy.types.Panel):
    bl_label = "Gradient"
    bl_idname = "BADVC_PT_gradient"

    def draw(self, context):
        layout = self.layout
        layout.enabled = poll_color_mesh(context)
        settings = context.scene.badvc
        obj = context.active_object

        row = layout.row(align=True)
        row.prop(settings, "gradient_source", expand=True)
        row = layout.row(align=True)
        if settings.gradient_source == 'VALUE':
            row.prop(settings, "gradient_start_value", text="Start", slider=True)
            row.prop(settings, "gradient_end_value", text="End", slider=True)
        else:
            row.prop(settings, "gradient_color_a", text="")
            row.prop(settings, "gradient_color_b", text="")
        row.operator("badvc.gradient_swap_ends", text="", icon='ARROW_LEFTRIGHT')
        layout.prop(settings, "gradient_easing", text="Easing")

        def common(op):
            op.source = settings.gradient_source
            op.start_value = settings.gradient_start_value
            op.end_value = settings.gradient_end_value
            op.color_a = settings.gradient_color_a
            op.color_b = settings.gradient_color_b
            op.easing = settings.gradient_easing
            op.channels = effective_channels(context)
            op.scope = settings.scope

        box = layout.box()
        box.label(text="Axis")
        row = box.row(align=True)
        row.prop(settings, "gradient_axis", expand=True)
        row = box.row(align=True)
        row.prop(settings, "gradient_space", expand=True)
        row = box.row(align=True)
        row.prop(settings, "gradient_shape", expand=True)
        row = box.row(align=True)
        for text, flip in (("Apply Axis Gradient", False), ("Flipped", True)):
            op = row.operator("badvc.gradient_axis", text=text)
            common(op)
            op.axis = settings.gradient_axis
            op.space = settings.gradient_space
            op.shape = settings.gradient_shape
            op.flip = flip

        box = layout.box()
        box.label(text="Gesture")
        row = box.row(align=True)
        row.prop(settings, "gradient_shape", expand=True)
        row = box.row(align=True)
        row.operator_context = 'INVOKE_DEFAULT'
        op = row.operator("badvc.gradient_gesture", text="Draw Gradient", icon='IPO_LINEAR')
        common(op)
        op.shape = settings.gradient_shape

        box = layout.box()
        box.label(text="Between Vertices")
        row = box.row(align=True)
        for which, text in (('START', "Set Start"), ('END', "Set End"), ('CLEAR', "Clear")):
            row.operator("badvc.gradient_set_group", text=text).which = which
        row = box.row(align=True)
        row.label(text=f"Start: {len(get_group(obj, 'start'))} verts")
        row.label(text=f"End: {len(get_group(obj, 'end'))} verts")
        box.prop(settings, "gradient_method", expand=True)
        op = box.operator("badvc.gradient_between", text="Apply")
        common(op)
        op.method = settings.gradient_method
        box.label(text="Or select exactly 2 vertices in Edit Mode", icon='INFO')


class BADVC_PT_bake(_SubPanel, bpy.types.Panel):
    bl_label = "Bake"
    bl_idname = "BADVC_PT_bake"

    def draw(self, context):
        layout = self.layout
        layout.enabled = poll_color_mesh(context)
        settings = context.scene.badvc
        channels = effective_channels(context)

        row = layout.row(align=True)
        row.prop(settings, "bake_type", expand=True)
        kind = settings.bake_type

        if kind == 'NORMAL':
            row = layout.row(align=True)
            row.prop(settings, "bake_normal_space", expand=True)
            row = layout.row(align=True)
            row.prop(settings, "bake_normal_source", expand=True)
            if settings.bake_normal_source == 'PROXY':
                layout.prop(settings, "bake_proxy", text="Proxy")
                proxy = settings.bake_proxy
                if proxy is not None and proxy == context.active_object:
                    layout.label(text="Proxy must be a different object", icon='ERROR')
            elif settings.bake_normal_source == 'SPHERICAL':
                layout.prop(settings, "bake_center", text="Center")
            box = layout.box()
            box.label(text="Swizzle")
            for ch in "rgba":
                row = box.row(align=True)
                row.label(text=ch.upper())
                row.prop(settings, f"bake_swizzle_{ch}", text="")
            box.label(text="Only selected channels are written", icon='INFO')
        elif kind == 'AO':
            layout.prop(settings, "bake_ao_samples")
            layout.prop(settings, "bake_ao_distance")
            layout.prop(settings, "bake_ao_bias")
            layout.prop(settings, "bake_ao_include_selected")
        elif kind == 'RANDOM':
            row = layout.row(align=True)
            row.prop(settings, "bake_random_per", expand=True)
            layout.prop(settings, "bake_random_seed")
            row = layout.row(align=True)
            row.prop(settings, "bake_random_min", slider=True)
            row.prop(settings, "bake_random_max", slider=True)
            layout.prop(settings, "bake_random_per_channel")
        else:
            row = layout.row(align=True)
            row.prop(settings, "bake_pos_mode", expand=True)
            if settings.bake_pos_mode == 'AXIS':
                row = layout.row(align=True)
                row.prop(settings, "bake_pos_axis", expand=True)
            else:
                layout.prop(settings, "bake_pos_center", text="Center")
            row = layout.row(align=True)
            row.prop(settings, "bake_pos_space", expand=True)
            layout.prop(settings, "bake_pos_per_part")
            layout.prop(settings, "bake_pos_invert")

        row = layout.row()
        row.scale_y = 1.5
        if kind == 'NORMAL':
            op = row.operator("badvc.bake_normal", text="Bake", icon='RENDER_STILL')
            op.space = settings.bake_normal_space
            op.source = settings.bake_normal_source
            op.proxy = settings.bake_proxy.name if settings.bake_proxy is not None else ""
            op.center = settings.bake_center
            op.swizzle_r = settings.bake_swizzle_r
            op.swizzle_g = settings.bake_swizzle_g
            op.swizzle_b = settings.bake_swizzle_b
            op.swizzle_a = settings.bake_swizzle_a
        elif kind == 'AO':
            op = row.operator("badvc.bake_ao", text="Bake", icon='RENDER_STILL')
            op.samples = settings.bake_ao_samples
            op.distance = settings.bake_ao_distance
            op.bias = settings.bake_ao_bias
            op.include_selected = settings.bake_ao_include_selected
        elif kind == 'RANDOM':
            op = row.operator("badvc.bake_random", text="Bake", icon='RENDER_STILL')
            op.per = settings.bake_random_per
            op.seed = settings.bake_random_seed
            op.min_value = settings.bake_random_min
            op.max_value = settings.bake_random_max
            op.per_channel = settings.bake_random_per_channel
        else:
            op = row.operator("badvc.bake_position", text="Bake", icon='RENDER_STILL')
            op.mode = settings.bake_pos_mode
            op.axis = settings.bake_pos_axis
            op.center = settings.bake_pos_center
            op.space = settings.bake_pos_space
            op.per_part = settings.bake_pos_per_part
            op.invert = settings.bake_pos_invert
        op.channels = channels
        op.scope = settings.scope


class BADVC_PT_channel_values(_SubPanel, bpy.types.Panel):
    bl_label = "Channel Values"
    bl_idname = "BADVC_PT_channel_values"

    def draw(self, context):
        layout = self.layout
        layout.enabled = poll_color_mesh(context)
        settings = context.scene.badvc
        layout.operator("badvc.sample_channels", text="Sample", icon='EYEDROPPER')
        for i, ch in enumerate("RGBA"):
            row = layout.row(align=True)
            row.prop(settings, "channel_values", index=i, text=ch, slider=True)
            op = row.operator("badvc.set_channel_value", text="Set")
            op.channel = ch
            op.value = settings.channel_values[i]
            op.scope = settings.scope


class BADVC_PT_adjust(_SubPanel, bpy.types.Panel):
    bl_label = "Adjust"
    bl_idname = "BADVC_PT_adjust"

    def draw(self, context):
        layout = self.layout
        layout.enabled = poll_color_mesh(context)
        settings = context.scene.badvc
        grid = layout.grid_flow(row_major=True, columns=2, align=True)
        for idname, text in (("badvc.levels", "Levels"),
                             ("badvc.brightness_contrast", "Brightness / Contrast"),
                             ("badvc.posterize", "Posterize"),
                             ("badvc.clamp_values", "Clamp")):
            op = grid.operator(idname, text=text)
            op.channels = effective_channels(context)
            op.scope = settings.scope
        layout.label(text="Tweak values in Adjust Last Operation (F9)", icon='INFO')


class BADVC_PT_transfer(_SubPanel, bpy.types.Panel):
    bl_label = "Channel Transfer"
    bl_idname = "BADVC_PT_transfer"

    def draw(self, context):
        layout = self.layout
        layout.enabled = poll_color_mesh(context)
        settings = context.scene.badvc
        mesh = context.active_object.data

        layout.label(text="Within Attribute")
        row = layout.row(align=True)
        row.prop(settings, "transfer_src_channel", text="")
        row.label(text="", icon='FORWARD')
        row.prop(settings, "transfer_dst_channel", text="")
        row = layout.row(align=True)
        op = row.operator("badvc.channel_copy", text="Copy")
        op.src = settings.transfer_src_channel
        op.dst = settings.transfer_dst_channel
        op.scope = settings.scope
        op = row.operator("badvc.channel_swap", text="Swap")
        op.a = settings.transfer_src_channel
        op.b = settings.transfer_dst_channel
        op.scope = settings.scope

        layout.separator()
        layout.label(text="From Attribute")
        layout.prop_search(settings, "transfer_source", mesh, "color_attributes", text="Source")
        layout.prop(settings, "transfer_mode", expand=True)
        if settings.transfer_mode == 'CHANNEL':
            row = layout.row(align=True)
            row.prop(settings, "transfer_src_channel", text="")
            row.label(text="", icon='FORWARD')
            row.prop(settings, "transfer_dst_channel", text="")
        else:
            layout.label(text="Channels: " + (", ".join(sorted(effective_channels(context))) or "none"))

        active = mesh.color_attributes.active_color
        src = settings.transfer_source
        if not src or src not in mesh.color_attributes:
            layout.label(text="Pick a source attribute", icon='INFO')
        elif active is not None and src == active.name:
            layout.label(text="Source is the active attribute", icon='ERROR')
        row = layout.row(align=True)
        for text, operation in (("Copy", 'COPY'), ("Swap", 'SWAP')):
            op = row.operator("badvc.attribute_transfer", text=text)
            op.source = src
            op.operation = operation
            op.mode = settings.transfer_mode
            op.src_channel = settings.transfer_src_channel
            op.dst_channel = settings.transfer_dst_channel
            op.channels = effective_channels(context)
            op.scope = settings.scope


class BADVC_PT_attribute(_SubPanel, bpy.types.Panel):
    bl_label = "Color Attribute"
    bl_idname = "BADVC_PT_attribute"

    def draw(self, context):
        layout = self.layout
        mesh = context.active_object.data
        layout.template_list(
            "MESH_UL_color_attributes", "", mesh, "color_attributes",
            mesh.color_attributes, "active_color_index", rows=3,
        )
        layout.operator("geometry.color_attribute_add", text="Add Color Attribute", icon='ADD')

        attr = mesh.color_attributes.active_color
        if attr is not None:
            box = layout.box()
            box.label(text=f"Name: {attr.name}")
            box.label(text=f"Domain: {attr.domain}")
            box.label(text=f"Type: {attr.data_type}")


classes = (
    BADVC_PT_main,
    BADVC_PT_paint,
    BADVC_PT_gradient,
    BADVC_PT_bake,
    BADVC_PT_channel_values,
    BADVC_PT_adjust,
    BADVC_PT_transfer,
    BADVC_PT_attribute,
)
