"""Sidebar panel. Read-only except for explicit user actions."""

import bpy


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


classes = (BADVC_PT_main,)
