"""Safe mode switching for data writes."""

from contextlib import contextmanager

import bpy


@contextmanager
def ensure_object_mode(obj=None):
    """Switch to OBJECT mode, yield the original mode string, restore it afterwards (even on error).

    Yields the mode before switching ('EDIT', 'VERTEX_PAINT', 'OBJECT', ...);
    'OBJECT' if there is no object. Pass it to get_selection_mask(..., mode=...).
    """
    ctx = bpy.context
    obj = obj or ctx.active_object
    if obj is None:
        yield 'OBJECT'
        return
    original = obj.mode
    if original == 'OBJECT':
        yield original
        return
    with ctx.temp_override(active_object=obj, object=obj):
        bpy.ops.object.mode_set(mode='OBJECT')
    try:
        yield original
    finally:
        with ctx.temp_override(active_object=obj, object=obj):
            bpy.ops.object.mode_set(mode=original)
