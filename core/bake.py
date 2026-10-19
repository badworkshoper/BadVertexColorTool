"""F09 bake math: normal encoding / swizzle, spherical and proxy normals, AO sample directions,
random tables, position normalisation. Pure numpy (no bpy)."""

from typing import Sequence

import numpy as np

SWIZZLE_ITEMS: list[tuple[str, str, str]] = [
    ('NONE', "None", "Channel is not written"),
    ('POS_X', "+X", "Normal X"),
    ('NEG_X', "-X", "Inverted normal X"),
    ('POS_Y', "+Y", "Normal Y"),
    ('NEG_Y', "-Y", "Inverted normal Y"),
    ('POS_Z', "+Z", "Normal Z"),
    ('NEG_Z', "-Z", "Inverted normal Z"),
]

_SWIZZLE_AXIS = {'POS_X': (0, 1.0), 'NEG_X': (0, -1.0), 'POS_Y': (1, 1.0),
                 'NEG_Y': (1, -1.0), 'POS_Z': (2, 1.0), 'NEG_Z': (2, -1.0)}


def swizzle_channels(swizzle: Sequence[str]) -> set[str]:
    """Channels ('R','G','B','A') whose swizzle (R, G, B, A order) is not NONE."""
    return {c for c, s in zip("RGBA", swizzle) if s != 'NONE'}


def normalize_rows(v: np.ndarray, fallback=(0.0, 0.0, 1.0)) -> np.ndarray:
    """Normalise (N, 3) vectors; (near) zero vectors become `fallback`."""
    v = np.asarray(v, dtype=np.float64).reshape(-1, 3)
    length = np.linalg.norm(v, axis=1, keepdims=True)
    ok = length > 1e-12
    return np.where(ok, v / np.where(ok, length, 1.0), np.asarray(fallback, dtype=np.float64))


def transform_normals(n: np.ndarray, matrix3: np.ndarray, inverse: bool = False) -> np.ndarray:
    """Transform row-vector normals by the normal matrix of `matrix3` (inverse transpose) and normalise.

    inverse=False: object -> world (n @ inv(M)); inverse=True: world -> object (n @ M).
    """
    m = np.asarray(matrix3, dtype=np.float64).reshape(3, 3)
    out = np.asarray(n, dtype=np.float64).reshape(-1, 3) @ (m if inverse else np.linalg.inv(m))
    return normalize_rows(out)


def encode_normals(n: np.ndarray, swizzle: Sequence[str]) -> np.ndarray:
    """(N, 3) unit normals -> (N, 4) float32 with (+-n[axis]) * 0.5 + 0.5 in channels whose swizzle != NONE.

    Channels with NONE hold 0.0 (callers must not write them).
    """
    n = np.asarray(n, dtype=np.float64).reshape(-1, 3)
    out = np.zeros((len(n), 4), dtype=np.float32)
    for c, s in enumerate(swizzle):  # <= 4 channels, not elements
        if s == 'NONE':
            continue
        axis, sign = _SWIZZLE_AXIS[s]
        out[:, c] = np.clip(sign * n[:, axis] * 0.5 + 0.5, 0.0, 1.0)
    return out


def spherical_normals(points: np.ndarray, center) -> np.ndarray:
    """normalize(p - center) for points (N, 3)."""
    return normalize_rows(np.asarray(points, dtype=np.float64).reshape(-1, 3) - np.asarray(center, dtype=np.float64))


def bbox_center(points: np.ndarray) -> np.ndarray:
    """Centre of the axis aligned bounding box of (N, 3) points (zeros if empty)."""
    p = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    return (p.min(axis=0) + p.max(axis=0)) * 0.5 if len(p) else np.zeros(3)


def interpolate_triangle_normals(points: np.ndarray, tri_pos: np.ndarray, tri_nor: np.ndarray,
                                 face_nor: np.ndarray) -> np.ndarray:
    """Smooth normals at `points` (N, 3) lying on triangles.

    tri_pos / tri_nor: (N, 3, 3) corner positions / unit normals of each point's triangle;
    barycentric interpolation of the corner normals; degenerate results fall back to face_nor (N, 3).
    """
    a, b, c = tri_pos[:, 0], tri_pos[:, 1], tri_pos[:, 2]
    v0, v1, v2 = b - a, c - a, points - a
    d00 = (v0 * v0).sum(1)
    d01 = (v0 * v1).sum(1)
    d11 = (v1 * v1).sum(1)
    d20 = (v2 * v0).sum(1)
    d21 = (v2 * v1).sum(1)
    den = d00 * d11 - d01 * d01
    ok = np.abs(den) > 1e-18
    safe = np.where(ok, den, 1.0)
    v = np.where(ok, (d11 * d20 - d01 * d21) / safe, 0.0)
    w = np.where(ok, (d00 * d21 - d01 * d20) / safe, 0.0)
    u = 1.0 - v - w
    n = u[:, None] * tri_nor[:, 0] + v[:, None] * tri_nor[:, 1] + w[:, None] * tri_nor[:, 2]
    length = np.linalg.norm(n, axis=1)
    n = np.where((length > 1e-9)[:, None], n, face_nor)
    return normalize_rows(n)


# --------------------------------------------------------------------------- AO

def hemisphere_samples(samples: int) -> np.ndarray:
    """(S, 3) deterministic cosine-weighted hemisphere directions around +Z (Fibonacci spiral)."""
    i = np.arange(samples, dtype=np.float64)
    u = (i + 0.5) / samples
    phi = i * np.pi * (3.0 - np.sqrt(5.0))
    r = np.sqrt(u)
    return np.stack([r * np.cos(phi), r * np.sin(phi), np.sqrt(1.0 - u)], axis=1)


def hemisphere_directions(normals: np.ndarray, samples: int, angles: np.ndarray) -> np.ndarray:
    """(M, S, 3) world directions: the sample set rotated by angles (M,) about +Z, then mapped to each normal's frame."""
    n = normalize_rows(normals)
    s = hemisphere_samples(samples)
    cs, sn = np.cos(angles)[:, None], np.sin(angles)[:, None]
    x = s[None, :, 0] * cs - s[None, :, 1] * sn
    y = s[None, :, 0] * sn + s[None, :, 1] * cs
    z = np.broadcast_to(s[None, :, 2], x.shape)
    helper = np.where((np.abs(n[:, 0]) > 0.9)[:, None], np.array([0.0, 1.0, 0.0]), np.array([1.0, 0.0, 0.0]))
    t = normalize_rows(np.cross(n, helper))
    b = np.cross(n, t)
    return (x[..., None] * t[:, None, :] + y[..., None] * b[:, None, :] + z[..., None] * n[:, None, :])


def occlusion_to_ao(hits: np.ndarray, samples: int) -> np.ndarray:
    """AO = 1 - hits / samples (1 = open)."""
    return 1.0 - np.asarray(hits, dtype=np.float64) / float(samples)


# --------------------------------------------------------------------------- random

def random_table(seed: int, count: int, per_channel: bool, lo: float, hi: float) -> np.ndarray:
    """(count, 4) float32 uniform values in [lo, hi]; same value in all 4 channels unless per_channel.

    Depends only on (seed, count), never on a mask.
    """
    lo, hi = (lo, hi) if lo <= hi else (hi, lo)
    rng = np.random.default_rng(seed)
    if per_channel:
        v = rng.uniform(lo, hi, size=(count, 4))
    else:
        v = np.repeat(rng.uniform(lo, hi, size=(count, 1)), 4, axis=1)
    return v.astype(np.float32)


def corner_values_to_vertices(values: np.ndarray, loop_vertex: np.ndarray, n_verts: int,
                              fill: float = 0.0) -> np.ndarray:
    """(L, C) per-corner values -> (V, C): mean over the corners of each vertex (vertices without corners -> fill)."""
    values = np.asarray(values, dtype=np.float64)
    counts = np.bincount(loop_vertex, minlength=n_verts).astype(np.float64)
    out = np.empty((n_verts, values.shape[1]), dtype=np.float64)
    for c in range(values.shape[1]):  # channels only
        out[:, c] = np.bincount(loop_vertex, weights=values[:, c], minlength=n_verts)
    has = counts > 0
    out[has] /= counts[has, None]
    out[~has] = fill
    return out.astype(np.float32)


# --------------------------------------------------------------------------- position

def part_bbox_centers(points: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """(K, 3) bbox centre of every label group of points (N, 3)."""
    p = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    k = int(labels.max()) + 1 if len(labels) else 0
    lo = np.full((k, 3), np.inf)
    hi = np.full((k, 3), -np.inf)
    np.minimum.at(lo, labels, p)
    np.maximum.at(hi, labels, p)
    return (lo + hi) * 0.5


def normalize_scalar(s: np.ndarray, mask: np.ndarray, labels: np.ndarray | None = None,
                     mode: str = 'MINMAX') -> np.ndarray:
    """t (N,) in 0..1 from scalars s (N,), statistics over masked elements only (unmasked -> 0).

    mode MINMAX: (s - min) / (max - min); MAX: s / max. Per group when labels (N,) are given,
    otherwise over all masked elements. Degenerate range -> 0.
    """
    s = np.asarray(s, dtype=np.float64)
    out = np.zeros(len(s), dtype=np.float64)
    if not mask.any():
        return out.astype(np.float32)
    lab = np.zeros(len(s), dtype=np.int64) if labels is None else np.asarray(labels, dtype=np.int64)
    k = int(lab[mask].max()) + 1
    hi = np.full(k, -np.inf)
    np.maximum.at(hi, lab[mask], s[mask])
    if mode == 'MAX':
        lo = np.zeros(k)
    else:
        lo = np.full(k, np.inf)
        np.minimum.at(lo, lab[mask], s[mask])
    rng = hi - lo
    ok = np.isfinite(rng) & (rng > 1e-12)
    m = np.flatnonzero(mask)
    g = lab[m]
    out[m] = np.where(ok[g], (s[m] - lo[g]) / np.where(ok[g], rng[g], 1.0), 0.0)
    return np.clip(out, 0.0, 1.0).astype(np.float32)
