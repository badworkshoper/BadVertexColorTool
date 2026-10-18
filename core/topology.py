"""Mesh topology helpers: vertex <-> corner mapping (more later: adjacency, loose parts, geodesic)."""

import numpy as np


def loop_vertex_indices(mesh) -> np.ndarray:
    """Vertex index of every loop (corner), int32 (L,)."""
    out = np.empty(len(mesh.loops), dtype=np.int32)
    if len(out):
        mesh.loops.foreach_get('vertex_index', out)
    return out


def corner_to_point(arr: np.ndarray, mesh) -> np.ndarray:
    """(L, 4) corner values -> (V, 4): mean over the corners of each vertex (loose vertices -> 0)."""
    arr = np.asarray(arr, dtype=np.float32)
    n_verts = len(mesh.vertices)
    lv = loop_vertex_indices(mesh)
    counts = np.bincount(lv, minlength=n_verts).astype(np.float64)
    out = np.zeros((n_verts, arr.shape[1]), dtype=np.float32)
    safe = np.maximum(counts, 1.0)
    for c in range(arr.shape[1]):  # loop over channels only (<= 4), not elements
        sums = np.bincount(lv, weights=arr[:, c], minlength=n_verts)
        out[:, c] = sums / safe
    return out


def point_to_corner(arr: np.ndarray, mesh) -> np.ndarray:
    """(V, 4) vertex values -> (L, 4): gather by loop vertex index."""
    return np.asarray(arr, dtype=np.float32)[loop_vertex_indices(mesh)]


def convert_domain(arr: np.ndarray, mesh, src_domain: str, dst_domain: str) -> np.ndarray:
    """Convert per-element values between 'POINT' and 'CORNER' (no-op if equal)."""
    if src_domain == dst_domain:
        return arr
    if src_domain == 'CORNER' and dst_domain == 'POINT':
        return corner_to_point(arr, mesh)
    if src_domain == 'POINT' and dst_domain == 'CORNER':
        return point_to_corner(arr, mesh)
    raise ValueError(f"Unsupported domain conversion {src_domain} -> {dst_domain}")


def edge_vertex_pairs(mesh) -> np.ndarray:
    """(E, 2) int32 vertex indices of every edge."""
    out = np.empty(len(mesh.edges) * 2, dtype=np.int32)
    if len(out):
        mesh.edges.foreach_get('vertices', out)
    return out.reshape(-1, 2)


def vertex_neighbor_mean(values: np.ndarray, edges: np.ndarray, n_verts: int) -> np.ndarray:
    """(V, C) -> (V, C): mean of edge-connected neighbours; vertices without neighbours keep their value."""
    values = np.asarray(values, dtype=np.float32)
    out = values.copy()
    if len(edges) == 0:
        return out
    a, b = edges[:, 0], edges[:, 1]
    deg = (np.bincount(a, minlength=n_verts) + np.bincount(b, minlength=n_verts)).astype(np.float64)
    has = deg > 0
    safe = np.maximum(deg, 1.0)
    for c in range(values.shape[1]):  # loop over channels only (<= 4), not elements
        v = values[:, c].astype(np.float64)
        sums = np.bincount(a, weights=v[b], minlength=n_verts) + np.bincount(b, weights=v[a], minlength=n_verts)
        out[has, c] = (sums / safe)[has]
    return out
