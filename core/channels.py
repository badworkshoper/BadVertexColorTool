"""Channel enum helpers. Pure numpy, no bpy dependency."""

import numpy as np

CHANNEL_ITEMS: list[tuple[str, str, str]] = [
    ('R', "R", "Red channel"),
    ('G', "G", "Green channel"),
    ('B', "B", "Blue channel"),
    ('A', "A", "Alpha channel"),
]

CHANNEL_INDEX: dict[str, int] = {'R': 0, 'G': 1, 'B': 2, 'A': 3}


def channels_to_indices(channels: set[str]) -> list[int]:
    """Return sorted channel indices for a set like {'R', 'A'}."""
    return sorted(CHANNEL_INDEX[c] for c in channels)


def channel_mask(channels: set[str]) -> np.ndarray:
    """Return bool array of shape (4,) with True for the given channels."""
    mask = np.zeros(4, dtype=bool)
    mask[channels_to_indices(channels)] = True
    return mask
