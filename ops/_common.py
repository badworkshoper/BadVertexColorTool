"""Shared helpers for color operators (no per-operator duplication)."""

from typing import Callable

import numpy as np

from ..core.attributes import (
    get_active_color_attribute,
    read_colors,
    validate_color_attribute,
    write_colors,
)
from ..core.channels import channels_to_indices
from ..core.mode import ensure_object_mode
from ..core.selection import get_selection_mask

_POLL_MODES = ('OBJECT', 'EDIT', 'VERTEX_PAINT')

# operator property name -> Scene.badvc property name
SETTINGS_MAP = {
    'channels': 'target_channels',
    'scope': 'scope',
    'color': 'color',
    'value': 'value',
    'src': 'transfer_src_channel',
    'dst': 'transfer_dst_channel',
    'src_channel': 'transfer_src_channel',
    'dst_channel': 'transfer_dst_channel',
    'source': 'transfer_source',
    'mode': 'transfer_mode',
}


def poll_color_mesh(context) -> bool:
    """Active object is a mesh with a valid active color attribute."""
    obj = context.active_object
    if obj is None or obj.type != 'MESH' or obj.mode not in _POLL_MODES:
        return False
    mesh = obj.data
    return validate_color_attribute(mesh, get_active_color_attribute(mesh)) is None


def init_from_settings(op, context, names) -> None:
    """Copy panel settings into operator props that were not set explicitly."""
    settings = context.scene.badvc
    for name in names:
        if op.properties.is_property_set(name):
            continue
        value = getattr(settings, SETTINGS_MAP.get(name, name))
        if name == 'color':
            value = tuple(value)
        setattr(op, name, value)


def apply_color_op(context, obj, func: Callable[[np.ndarray], np.ndarray],
                   channels: set[str], scope: str) -> int:
    """Apply func to masked rows, writing only the given channels. Returns rows changed.

    func receives (M, 4) float32 and returns (M, 4). Raises ValueError if the
    active color attribute is invalid.
    """
    with ensure_object_mode(obj) as orig_mode:
        mesh = obj.data
        attr = get_active_color_attribute(mesh)  # re-fetch after mode change
        error = validate_color_attribute(mesh, attr)
        if error:
            raise ValueError(error)
        ch = channels_to_indices(channels)
        if not ch:
            return 0
        colors = read_colors(mesh, attr)
        mask = get_selection_mask(obj, attr.domain, scope, mode=orig_mode)
        idx = np.flatnonzero(mask)
        if idx.size == 0:
            return 0
        new = np.asarray(func(colors[idx]), dtype=np.float32)
        out = colors.copy()
        out[np.ix_(idx, ch)] = new[:, ch]
        write_colors(mesh, attr, out)
        return int(idx.size)


def run_color_op(op, context, func, channels: set[str], scope: str) -> set:
    """Run apply_color_op and translate the result into an operator return value."""
    try:
        count = apply_color_op(context, context.active_object, func, channels, scope)
    except ValueError as e:
        op.report({'ERROR'}, str(e))
        return {'CANCELLED'}
    if count == 0:
        op.report({'WARNING'}, "Nothing selected" if channels else "No channels selected")
        return {'CANCELLED'}
    return {'FINISHED'}


def sample_mean(context, obj, scope: str):
    """Mean RGBA over masked elements, or None if nothing is masked. Does not write the mesh."""
    with ensure_object_mode(obj) as orig_mode:
        mesh = obj.data
        attr = get_active_color_attribute(mesh)
        error = validate_color_attribute(mesh, attr)
        if error:
            raise ValueError(error)
        colors = read_colors(mesh, attr)
        mask = get_selection_mask(obj, attr.domain, scope, mode=orig_mode)
        if not mask.any():
            return None
        return colors[mask].mean(axis=0)
