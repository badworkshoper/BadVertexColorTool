"""Pure numpy blend functions (minimal in F00; extended in F05/F06)."""

import numpy as np


def clamp01(a: np.ndarray) -> np.ndarray:
    """Clamp values to 0..1."""
    return np.clip(a, 0.0, 1.0)


def mix(a: np.ndarray, b: np.ndarray, factor) -> np.ndarray:
    """Linear interpolation a -> b by factor (scalar or broadcastable array)."""
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    return (a + (b - a) * np.asarray(factor, dtype=np.float32)).astype(np.float32)
