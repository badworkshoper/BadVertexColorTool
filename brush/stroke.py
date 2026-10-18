"""Brush session cache and the dab application used by the modal operator (no modal logic, testable).

All distances are computed in WORLD space (cached world positions/normals), so non-uniform
object scale gives the same spherical brush as seen on screen. Ray casting is done in object
space on a BVHTree built once per session.
"""

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from mathutils.bvhtree import BVHTree

from ..core.selection import get_selection_mask
from ..core.topology import edge_vertex_pairs, loop_vertex_indices
from ..ops.gradient import vertex_positions
from . import core as bcore


@dataclass
class BrushParams:
    """Snapshot of the settings used by one stroke."""
    mode: str = 'MIX'
    target: tuple = (1.0, 1.0, 1.0, 1.0)
    channels_idx: tuple = (0, 1, 2, 3)
    strength: float = 0.5
    falloff: str = 'SMOOTH'
    front_only: bool = True


@dataclass
class BrushCache:
    """Per-session mesh cache (rebuilt only when the session starts)."""
    domain: str
    n_verts: int
    n_loops: int
    mw: np.ndarray                 # (4, 4) matrix_world
    mw_inv: np.ndarray             # (4, 4) inverse
    world_pos: np.ndarray          # (V, 3) float32
    world_nor: np.ndarray          # (V, 3) float32, normalised
    lv: np.ndarray                 # (L,) loop -> vertex
    neighbor_fn: Callable
    bvh: BVHTree
    mask: np.ndarray = field(default=None)  # (N,) bool, selection mask over the domain

    @property
    def n_elements(self) -> int:
        return self.n_verts if self.domain == 'POINT' else self.n_loops


def build_cache(obj, domain: str, mask: np.ndarray | None = None) -> BrushCache:
    """Cache geometry of `obj` (must be in OBJECT mode so mesh data is up to date)."""
    mesh = obj.data
    n_verts, n_loops = len(mesh.vertices), len(mesh.loops)
    mw = np.array(obj.matrix_world, dtype=np.float64)
    mw_inv = np.linalg.inv(mw)
    local = vertex_positions(mesh).astype(np.float64)
    world_pos = (local @ mw[:3, :3].T + mw[:3, 3]).astype(np.float32)

    nor = np.empty(n_verts * 3, dtype=np.float32)
    if n_verts:
        mesh.vertex_normals.foreach_get('vector', nor)
    nor = nor.reshape(-1, 3).astype(np.float64)
    nor_w = nor @ np.linalg.inv(mw[:3, :3])  # inverse-transpose for row vectors
    length = np.maximum(np.linalg.norm(nor_w, axis=1, keepdims=True), 1e-12)
    world_nor = (nor_w / length).astype(np.float32)

    mesh.calc_loop_triangles()
    tris = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int32)
    if len(tris):
        mesh.loop_triangles.foreach_get('vertices', tris)
    bvh = BVHTree.FromPolygons(local.tolist(), tris.reshape(-1, 3).tolist(), all_triangles=True)

    lv = loop_vertex_indices(mesh)
    neighbor_fn = bcore.make_neighbor_fn(edge_vertex_pairs(mesh), n_verts, domain, lv)
    n = n_verts if domain == 'POINT' else n_loops
    if mask is None:
        mask = np.ones(n, dtype=bool)
    return BrushCache(domain, n_verts, n_loops, mw, mw_inv, world_pos, world_nor, lv,
                      neighbor_fn, bvh, mask)


def refresh_mask(cache: BrushCache, obj, scope: str, mode: str) -> None:
    """Recompute the selection mask (`mode` = object mode at session start, see get_selection_mask)."""
    cache.mask = get_selection_mask(obj, cache.domain, scope, mode=mode)


def ray_cast_local(cache: BrushCache, origin_world, direction_world):
    """Cast a world-space ray against the cached mesh. Returns (hit_world (3,), normal_world (3,)) or None."""
    o = np.asarray(origin_world, dtype=np.float64)
    d = np.asarray(direction_world, dtype=np.float64)
    ol = cache.mw_inv[:3, :3] @ o + cache.mw_inv[:3, 3]
    dl = cache.mw_inv[:3, :3] @ d
    norm = np.linalg.norm(dl)
    if norm < 1e-12:
        return None
    hit = cache.bvh.ray_cast(tuple(ol), tuple(dl / norm))
    if hit is None or hit[0] is None:
        return None
    hw = cache.mw[:3, :3] @ np.array(hit[0], dtype=np.float64) + cache.mw[:3, 3]
    nw = np.array(hit[1], dtype=np.float64) @ np.linalg.inv(cache.mw[:3, :3])
    return hw, nw / max(np.linalg.norm(nw), 1e-12)


def stroke_at(cache: BrushCache, colors: np.ndarray, hit_world, radius_world: float,
              params: BrushParams, view_origin=None, view_dir=None) -> int:
    """Apply one dab centred at `hit_world` to the working `colors` (N, 4) in place.

    view_origin: camera position (perspective) or view_dir: camera direction (orthographic),
    both world space; only used when params.front_only. Returns the number of changed elements.
    """
    w_vert = bcore.dab_weights(cache.world_pos, hit_world, radius_world, params.falloff,
                               cache.world_nor, view_dir, params.front_only, view_origin)
    if not w_vert.any():
        return 0
    w_dom = bcore.vertex_to_domain_weights(w_vert, cache.domain, cache.lv)
    w_dom = w_dom * cache.mask * np.float32(params.strength)
    idx = bcore.apply_dab(colors, w_dom, params.mode, params.target, params.channels_idx,
                          cache.neighbor_fn)
    return int(idx.size)
