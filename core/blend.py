"""Pure numpy blend and level functions (inputs (M, 4) float32; clamping is done by write_colors)."""

import numpy as np


def clamp01(a: np.ndarray) -> np.ndarray:
    """Clamp values to 0..1."""
    return np.clip(a, 0.0, 1.0)


def mix(a: np.ndarray, b: np.ndarray, factor) -> np.ndarray:
    """Linear interpolation a -> b by factor (scalar or broadcastable array)."""
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    return (a + (b - a) * np.asarray(factor, dtype=np.float32)).astype(np.float32)


def _f32(x) -> np.ndarray:
    return np.asarray(x, dtype=np.float32)


def add(a: np.ndarray, b: np.ndarray, factor) -> np.ndarray:
    """a + b * factor."""
    return (_f32(a) + _f32(b) * _f32(factor)).astype(np.float32)


def sub(a: np.ndarray, b: np.ndarray, factor) -> np.ndarray:
    """a - b * factor."""
    return (_f32(a) - _f32(b) * _f32(factor)).astype(np.float32)


def levels(a: np.ndarray, in_black: float, in_white: float, gamma: float,
           out_black: float, out_white: float) -> np.ndarray:
    """Photoshop-like levels: input range -> gamma -> output range."""
    a = _f32(a)
    x = np.clip((a - in_black) / max(in_white - in_black, 1e-6), 0.0, 1.0)
    x = x ** (1.0 / max(gamma, 1e-6))
    return (out_black + x * (out_white - out_black)).astype(np.float32)


def brightness_contrast(a: np.ndarray, brightness: float, contrast: float) -> np.ndarray:
    """(a - 0.5) * (1 + contrast) + 0.5 + brightness."""
    return ((_f32(a) - 0.5) * (1.0 + contrast) + 0.5 + brightness).astype(np.float32)


def posterize(a: np.ndarray, steps: int) -> np.ndarray:
    """Quantize to `steps` levels (steps >= 2)."""
    n = max(int(steps), 2) - 1
    return (np.round(np.clip(_f32(a), 0.0, 1.0) * n) / n).astype(np.float32)


def clamp(a: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Clamp values to [lo, hi]."""
    return np.clip(_f32(a), lo, hi).astype(np.float32)
