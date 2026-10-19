"""BadVertexColorTool: safe and fast work with Vertex Colors (Color Attributes)."""

bl_info = {
    "name": "BadVertexColorTool",
    "author": "badworkshoper",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > BadVC",
    "description": "Fast and safe tools for Vertex Colors / Color Attributes",
    "category": "Paint",
}

import bpy

from . import brush, ops, preview, props
from .ui import panels

# Central registration list. Order matters: props before UI that uses them.
_modules = (props, ops, brush, preview, panels)


def _all_classes() -> list:
    result = []
    for mod in _modules:
        result.extend(mod.classes)
    return result


def register() -> None:
    for cls in _all_classes():
        bpy.utils.register_class(cls)
    bpy.types.Scene.badvc = bpy.props.PointerProperty(type=props.BADVC_PG_Settings)
    preview.register()


def unregister() -> None:
    preview.unregister()
    if hasattr(bpy.types.Scene, "badvc"):
        del bpy.types.Scene.badvc
    for cls in reversed(_all_classes()):
        bpy.utils.unregister_class(cls)
