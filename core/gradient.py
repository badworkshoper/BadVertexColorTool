"""Gradient math: easing, parameter `t` along an axis / segment / mesh edges, color values.

Pure numpy (no bpy), shared by F08a (axis, between vertices) and F08b (mouse gesture):
any source of `t` (N,) in 0..1 (NaN = "do not write") plus `ease` and `gradient_values`
gives a gradient. Only `geodesic_t` uses a Python loop (Dijkstra, see below).
"""

import heapq

import numpy as np

EASING_ITEMS: list[tuple[str, str, str]] = [
    ('LINEAR', "Linear", "Constant rate"),
    ('SMOOTH', "Smooth", "Smoothstep: slow start and end"),
    ('EASE_IN', "Ease In", "Slow start (t squared)"),
    ('EASE_OUT', "Ease Out", "Slow end"),
]


def ease(t, mode: str) -> np.ndarray:
    """Apply an easing curve to t (clamped to 0..1 first). NaN stays NaN."""
    t = np.clip(np.asarray(t, dtype=np.float32), 0.0, 1.0)
    if mode == 'LINEAR':
        return t
    if mode == 'SMOOTH':
        return t * t * (3.0 - 2.0 * t)
    if mode == 'EASE_IN':
        return t * t
    if mode == 'EASE_OUT':
        return 1.0 - (1.0 - t) * (1.0 - t)
    raise ValueError(f"Unknown easing {mode}")


def axis_t(points: np.ndarray, axis_vec, radial: bool = False, center=None) -> np.ndarray:
    """t (N,) for points (N, 3).

    Linear: projection on axis_vec normalised to min..max over the GIVEN points
    (pass only the masked ones). Radial: distance from center (default: bbox center
    of the points) divided by the max distance.
    """
    p = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    if len(p) == 0:
        return np.zeros(0, dtype=np.float32)
    if radial:
        c = (p.min(axis=0) + p.max(axis=0)) * 0.5 if center is None else np.asarray(center, dtype=np.float64)
        s = np.linalg.norm(p - c, axis=1)
        top = s.max()
        return (s / top if top > 1e-12 else np.zeros(len(p))).astype(np.float32)
    s = p @ np.asarray(axis_vec, dtype=np.float64)
    lo, hi = s.min(), s.max()
    return ((s - lo) / (hi - lo) if hi - lo > 1e-12 else np.zeros(len(p))).astype(np.float32)


def segment_t(points: np.ndarray, a, b) -> np.ndarray:
    """t (N,): projection of points on segment A->B, clamped to 0..1."""
    p = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    a = np.asarray(a, dtype=np.float64)
    ab = np.asarray(b, dtype=np.float64) - a
    denom = float(ab @ ab)
    if denom < 1e-18:
        return np.zeros(len(p), dtype=np.float32)
    return np.clip(((p - a) @ ab) / denom, 0.0, 1.0).astype(np.float32)


def radial_t(points: np.ndarray, a, b) -> np.ndarray:
    """t (N,): |p - A| / |B - A| clamped to 0..1 (sphere centred at A, radius up to B). Degenerate A == B -> 0."""
    p = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    a = np.asarray(a, dtype=np.float64)
    r = float(np.linalg.norm(np.asarray(b, dtype=np.float64) - a))
    if r < 1e-9:
        return np.zeros(len(p), dtype=np.float32)
    return np.clip(np.linalg.norm(p - a, axis=1) / r, 0.0, 1.0).astype(np.float32)


def _csr(n_verts: int, edges: np.ndarray, edge_len: np.ndarray):
    """Undirected adjacency in CSR form: (indptr, neighbours, weights)."""
    src = np.concatenate([edges[:, 0], edges[:, 1]])
    dst = np.concatenate([edges[:, 1], edges[:, 0]])
    w = np.concatenate([edge_len, edge_len]).astype(np.float64)
    order = np.argsort(src, kind='stable')
    indptr = np.zeros(n_verts + 1, dtype=np.int64)
    np.cumsum(np.bincount(src, minlength=n_verts), out=indptr[1:])
    return indptr.tolist(), dst[order].tolist(), w[order].tolist()


def _dijkstra(n_verts: int, indptr, nbr, wts, sources) -> np.ndarray:
    """Multi-source shortest distances (inf = unreachable).

    DOCUMENTED EXCEPTION to the "no Python loops" rule (ARCHITECTURE.md): Dijkstra is
    inherently sequential; adjacency is CSR and held in plain lists for speed.
    """
    dist = [float('inf')] * n_verts
    heap = []
    for s in sources:
        dist[s] = 0.0
        heap.append((0.0, s))
    heapq.heapify(heap)
    pop, push = heapq.heappop, heapq.heappush
    while heap:
        d, u = pop(heap)
        if d > dist[u]:
            continue
        for k in range(indptr[u], indptr[u + 1]):
            v = nbr[k]
            nd = d + wts[k]
            if nd < dist[v]:
                dist[v] = nd
                push(heap, (nd, v))
    return np.array(dist, dtype=np.float64)


def geodesic_t(n_verts: int, edges: np.ndarray, edge_len: np.ndarray,
               start_idx, end_idx) -> np.ndarray:
    """t (V,) = d_start / (d_start + d_end) over edge distances; unreachable vertices -> NaN.

    start_idx / end_idx: vertex index arrays (groups). Vertices in both groups get 0.5.
    """
    edges = np.asarray(edges, dtype=np.int64).reshape(-1, 2)
    start = np.unique(np.asarray(start_idx, dtype=np.int64))
    end = np.unique(np.asarray(end_idx, dtype=np.int64))
    if n_verts == 0 or len(start) == 0 or len(end) == 0:
        return np.full(n_verts, np.nan, dtype=np.float32)
    indptr, nbr, wts = _csr(n_verts, edges, np.asarray(edge_len))
    ds = _dijkstra(n_verts, indptr, nbr, wts, start.tolist())
    de = _dijkstra(n_verts, indptr, nbr, wts, end.tolist())
    ok = np.isfinite(ds) & np.isfinite(de)
    total = np.where(ok, ds + de, 1.0)
    t = np.where(total > 1e-12, ds / np.where(total > 1e-12, total, 1.0), 0.5)
    return np.where(ok, t, np.nan).astype(np.float32)


def geodesic_radial_t(n_verts: int, edges: np.ndarray, edge_len: np.ndarray,
                      start_idx, end_idx) -> np.ndarray:
    """t (V,) = clamp(d_start / R, 0, 1) over edge distances, R = mean d_start over the reachable end group.

    Unreachable vertices -> NaN; R ~ 0 or no reachable end vertex -> NaN for all.
    """
    edges = np.asarray(edges, dtype=np.int64).reshape(-1, 2)
    start = np.unique(np.asarray(start_idx, dtype=np.int64))
    end = np.unique(np.asarray(end_idx, dtype=np.int64))
    if n_verts == 0 or len(start) == 0 or len(end) == 0:
        return np.full(n_verts, np.nan, dtype=np.float32)
    indptr, nbr, wts = _csr(n_verts, edges, np.asarray(edge_len))
    ds = _dijkstra(n_verts, indptr, nbr, wts, start.tolist())
    d_end = ds[end]
    d_end = d_end[np.isfinite(d_end)]
    if len(d_end) == 0 or d_end.mean() < 1e-9:
        return np.full(n_verts, np.nan, dtype=np.float32)
    t = np.clip(ds / d_end.mean(), 0.0, 1.0)  # inf -> clipped to 1, masked below
    return np.where(np.isfinite(ds), t, np.nan).astype(np.float32)


def gradient_values(t, source: str, start_value: float, end_value: float,
                    color_a, color_b) -> np.ndarray:
    """(N, 4) values for t (N,): VALUE lerps start..end into all channels, COLOR lerps A..B."""
    t = np.asarray(t, dtype=np.float32).reshape(-1, 1)
    if source == 'VALUE':
        v = np.float32(start_value) + (np.float32(end_value) - np.float32(start_value)) * t
        return np.repeat(v, 4, axis=1).astype(np.float32)
    if source == 'COLOR':
        a = np.asarray(color_a, dtype=np.float32).reshape(1, 4)
        b = np.asarray(color_b, dtype=np.float32).reshape(1, 4)
        return (a + (b - a) * t).astype(np.float32)
    raise ValueError(f"Unknown source {source}")
