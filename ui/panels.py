"""Sidebar panel. Read-only except for explicit user actions."""

import bpy

from ..ops._common import poll_color_mesh


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
        layout.template_list(
            "MESH_UL_color_attributes", "", mesh, "color_attributes",
            mesh.color_attributes, "active_color_index", rows=3,
        )
        layout.operator("geometry.color_attribute_add", text="Add Color Attribute", icon='ADD')

        attr = mesh.color_attributes.active_color
        if attr is None:
            layout.label(text="No active color attribute", icon='ERROR')
        else:
            box = layout.box()
            box.label(text=f"Name: {attr.name}")
            box.label(text=f"Domain: {attr.domain}")
            box.label(text=f"Type: {attr.data_type}")

        settings = context.scene.badvc
        col = layout.column()
        col.prop(settings, "target_channels", expand=True)
        col.prop(settings, "scope", expand=True)


class _SubPanel:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "BadVC"
    bl_parent_id = "BADVC_PT_main"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'


class BADVC_PT_fill(_SubPanel, bpy.types.Panel):
    bl_label = "Fill / Invert"
    bl_idname = "BADVC_PT_fill"

    def draw(self, context):
        layout = self.layout
        layout.enabled = poll_color_mesh(context)
        settings = context.scene.badvc
        layout.prop(settings, "color", text="")
        layout.operator("badvc.fill", text="Fill", icon='BRUSH_DATA')
        row = layout.row(align=True)
        for text, value in (("Fill 0", 0.0), ("Fill 1", 1.0)):
            op = row.operator("badvc.fill_value", text=text)
            op.value = value
            op.channels = settings.target_channels
            op.scope = settings.scope
        layout.operator("badvc.invert", text="Invert Channels")
        op = layout.operator("badvc.invert", text="Invert Color")
        op.channels = {'R', 'G', 'B'}
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


classes = (BADVC_PT_main, BADVC_PT_fill, BADVC_PT_channel_values)
