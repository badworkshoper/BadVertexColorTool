"""Read/write color attributes as numpy (N, 4) float32 arrays.

BYTE_COLOR uses `color_srgb` (raw byte/255), FLOAT_COLOR uses `color`.
Writes touch ONLY the attribute passed in. Mesh must be in OBJECT mode
(see core.mode.ensure_object_mode).
"""

import numpy as np

_COLOR_TYPES = ('BYTE_COLOR', 'FLOAT_COLOR')
_COLOR_DOMAINS = ('POINT', 'CORNER')


def get_active_color_attribute(mesh):
    """Return the active color attribute or None."""
    return mesh.color_attributes.active_color


def validate_color_attribute(mesh, attr) -> str | None:
    """Return None if attr is usable, otherwise an error message."""
    if attr is None:
        return "No active color attribute"
    if attr.data_type not in _COLOR_TYPES:
        return f"Attribute '{attr.name}' is not a color attribute ({attr.data_type})"
    if attr.domain not in _COLOR_DOMAINS:
        return f"Attribute '{attr.name}' has unsupported domain {attr.domain} (need POINT or CORNER)"
    return None


def _prop_name(attr) -> str:
    return 'color_srgb' if attr.data_type == 'BYTE_COLOR' else 'color'


def attribute_size(mesh, attr) -> int:
    """Number of elements in the attribute domain."""
    if attr.domain == 'POINT':
        return len(mesh.vertices)
    if attr.domain == 'CORNER':
        return len(mesh.loops)
    raise ValueError(f"Unsupported domain {attr.domain}")


def read_colors(mesh, attr) -> np.ndarray:
    """Return raw 0..1 colors as float32 array (N, 4)."""
    n = attribute_size(mesh, attr)
    buf = np.empty(n * 4, dtype=np.float32)
    if n:
        attr.data.foreach_get(_prop_name(attr), buf)
    return buf.reshape(n, 4)


def write_colors(mesh, attr, arr: np.ndarray) -> None:
    """Write (N, 4) colors (clamped to 0..1) into attr only."""
    n = attribute_size(mesh, attr)
    arr = np.asarray(arr)
    if arr.shape != (n, 4):
        raise ValueError(f"Expected array of shape ({n}, 4), got {arr.shape}")
    buf = np.ascontiguousarray(np.clip(arr, 0.0, 1.0), dtype=np.float32).reshape(-1)
    if n:
        attr.data.foreach_set(_prop_name(attr), buf)
    mesh.update()
