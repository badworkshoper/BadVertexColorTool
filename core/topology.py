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
