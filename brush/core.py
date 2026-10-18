"""Pure numpy brush math (no bpy): falloff, dab weights, dab application, stroke interpolation."""

from typing import Callable

import numpy as np

from ..core import blend

MODES = ('MIX', 'ADD', 'SUB', 'BLUR')
FALLOFFS = ('SMOOTH', 'LINEAR', 'SHARP', 'CONSTANT')


def falloff(name: str, d: np.ndarray, radius: float) -> np.ndarray:
    """Weight 0..1 for distances `d` (same units as radius). Zero outside the radius.

    With u = 1 - d/r: SMOOTH = 3u^2 - 2u^3, LINEAR = u, SHARP = u^2, CONSTANT = 1 inside.
    """
    d = np.asarray(d, dtype=np.float32)
    if radius <= 0.0:
        return np.zeros_like(d)
    u = 1.0 - d / np.float32(radius)
    inside = u > 0.0
    u = np.clip(u, 0.0, 1.0)
    if name == 'SMOOTH':
        w = u * u * (3.0 - 2.0 * u)
    elif name == 'LINEAR':
        w = u
    elif name == 'SHARP':
        w = u * u
    elif name == 'CONSTANT':
        w = np.ones_like(u)
    else:
        raise ValueError(f"Unknown falloff {name}")
    return np.where(inside, w, 0.0).astype(np.float32)


def dab_weights(positions: np.ndarray, hit, radius: float, falloff_name: str = 'SMOOTH',
                normals: np.ndarray | None = None, view_dir=None,
                front_only: bool = False, view_origin=None) -> np.ndarray:
    """Per-vertex weight (V,) of one dab: spherical influence around `hit`.

    positions/hit/radius share one space. `view_dir` is the direction FROM the camera TO
    the vertices: (3,) for orthographic or (V, 3) for perspective. Alternatively pass
    `view_origin` (camera position, perspective): the direction is then computed only for
    the vertices inside the sphere. With front_only, vertices whose normal does not face
    the camera (dot(normal, direction) >= 0) get 0.
    """
    positions = np.asarray(positions)
    n = len(positions)
    if n == 0 or radius <= 0.0:
        return np.zeros(n, dtype=np.float32)
    delta = positions - np.asarray(hit, dtype=positions.dtype)
    d = np.sqrt(np.einsum('ij,ij->i', delta, delta))
    w = falloff(falloff_name, d, radius)
    if front_only and normals is not None and (view_dir is not None or view_origin is not None):
        inside = np.flatnonzero(w)
        if inside.size:
            nrm = np.asarray(normals)[inside]
            if view_origin is not None:
                vd = positions[inside] - np.asarray(view_origin, dtype=positions.dtype)
                facing = np.einsum('ij,ij->i', nrm, vd)
            else:
                vd = np.asarray(view_dir, dtype=np.float32)
                facing = nrm @ vd if vd.ndim == 1 else np.einsum('ij,ij->i', nrm, vd[inside])
            w[inside[facing >= 0.0]] = 0.0
    return w


def vertex_to_domain_weights(w_vert: np.ndarray, domain: str, lv: np.ndarray) -> np.ndarray:
    """Vertex weights (V,) -> domain elements: identity for POINT, gather by loop vertex for CORNER."""
    return w_vert if domain == 'POINT' else w_vert[lv]


def effective_mode(mode: str, ctrl: bool = False, shift: bool = False) -> str:
    """Modifier logic: Shift -> BLUR; Ctrl swaps ADD <-> SUB (MIX/BLUR unchanged)."""
    if shift:
        return 'BLUR'
    if ctrl:
        return {'ADD': 'SUB', 'SUB': 'ADD'}.get(mode, mode)
    return mode


def make_neighbor_fn(edges: np.ndarray, n_verts: int, domain: str,
                     lv: np.ndarray | None = None) -> Callable:
    """Build neighbor_fn(colors, idx) -> (M, 4): edge-neighbour mean for domain rows `idx`.

    POINT: mean of the edge-connected vertices. CORNER: the per-vertex field (corner mean)
    is averaged over the neighbours of the corner's vertex (one blur_full iteration).
    Vertices without neighbours keep their own value. Only edges touching the needed
    vertices are processed, so a dab costs far less than a full-mesh blur.
    """
    edges = np.asarray(edges, dtype=np.int64).reshape(-1, 2)
    a, b = edges[:, 0], edges[:, 1]
    deg = (np.bincount(a, minlength=n_verts) + np.bincount(b, minlength=n_verts)).astype(np.float64)
    counts = None
    if domain == 'CORNER':
        counts = np.maximum(np.bincount(lv, minlength=n_verts).astype(np.float64), 1.0)

    def vertex_field(colors: np.ndarray) -> np.ndarray:
        if domain == 'POINT':
            return colors.astype(np.float64)
        out = np.empty((n_verts, 4), dtype=np.float64)
        for c in range(4):  # channels only
            out[:, c] = np.bincount(lv, weights=colors[:, c], minlength=n_verts) / counts
        return out

    def neighbor_fn(colors: np.ndarray, idx: np.ndarray) -> np.ndarray:
        field = vertex_field(colors)
        verts = idx if domain == 'POINT' else lv[idx]
        need = np.zeros(n_verts, dtype=bool)
        need[verts] = True
        ea, eb = need[a], need[b]  # edges contributing to a needed vertex
        out = field.copy()
        sums = np.zeros((n_verts, 4), dtype=np.float64)
        for c in range(4):  # channels only
            sums[:, c] = (np.bincount(a[ea], weights=field[b[ea], c], minlength=n_verts)
                          + np.bincount(b[eb], weights=field[a[eb], c], minlength=n_verts))
        has = need & (deg > 0)
        out[has] = sums[has] / deg[has, None]
        return out[verts].astype(np.float32)

    return neighbor_fn


def apply_dab(colors: np.ndarray, weights_dom: np.ndarray, mode: str, target,
              channels_idx, neighbor_fn: Callable | None = None) -> np.ndarray:
    """Apply one dab IN PLACE to `colors` (N, 4); returns indices of the elements with w > 0.

    weights_dom (N,) already contains strength/falloff/mask. Only rows with w > 0 and only
    `channels_idx` columns are written; results are clamped to 0..1.
    MIX lerp(c, target, w); ADD c + target*w; SUB c - target*w; BLUR lerp(c, neighbor_mean, w).
    """
    idx = np.flatnonzero(weights_dom > 0.0)
    ch = list(channels_idx)
    if idx.size == 0 or not ch:
        return idx
    rows = colors[idx]
    w = weights_dom[idx][:, None].astype(np.float32)
    if mode == 'BLUR':
        if neighbor_fn is None:
            raise ValueError("BLUR needs neighbor_fn")
        new = blend.mix(rows, neighbor_fn(colors, idx), w)
    else:
        t = np.broadcast_to(np.asarray(target, dtype=np.float32), rows.shape)
        if mode == 'MIX':
            new = blend.mix(rows, t, w)
        elif mode == 'ADD':
            new = blend.add(rows, t, w)
        elif mode == 'SUB':
            new = blend.sub(rows, t, w)
        else:
            raise ValueError(f"Unknown brush mode {mode}")
    new = blend.clamp01(new)
    colors[np.ix_(idx, ch)] = new[:, ch]
    return idx


def dab_path(p0, p1, spacing_px: float, carry: float = 0.0) -> tuple[np.ndarray, float]:
    """Dab positions (K, 2) along the segment p0 -> p1 and the new carry.

    `carry` = distance travelled since the last dab (0 right after a dab). The first new
    dab is `spacing - carry` from p0 and the rest follow every `spacing`, so consecutive
    segments (mouse events) continue the same even rhythm. p0 itself is never emitted.
    """
    p0 = np.asarray(p0, dtype=np.float64)
    p1 = np.asarray(p1, dtype=np.float64)
    spacing = max(float(spacing_px), 1e-3)
    seg = p1 - p0
    length = float(np.hypot(seg[0], seg[1]))
    first = spacing - carry
    if length < first or length <= 0.0:
        return np.empty((0, 2)), carry + length
    dist = np.arange(first, length + 1e-9, spacing)
    pts = p0 + seg * (dist / length)[:, None]
    return pts, float(length - dist[-1])
