"""Sidebar panel. Read-only except for explicit user actions."""

import bpy

from ..ops._common import effective_channels, poll_color_mesh


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
    BADVC_PT_channel_values,
    BADVC_PT_adjust,
    BADVC_PT_transfer,
    BADVC_PT_attribute,
)
