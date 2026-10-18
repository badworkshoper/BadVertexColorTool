"""Selection masks mapped to POINT / CORNER domains."""

import bpy
import numpy as np

from .topology import loop_vertex_indices as _loop_vertices


def vertex_selection(mesh) -> np.ndarray:
    """Bool (V,) of selected vertices."""
    out = np.zeros(len(mesh.vertices), dtype=bool)
    if len(out):
        mesh.vertices.foreach_get('select', out)
    return out


def face_selection(mesh) -> np.ndarray:
    """Bool (F,) of selected faces."""
    out = np.zeros(len(mesh.polygons), dtype=bool)
    if len(out):
        mesh.polygons.foreach_get('select', out)
    return out


def _face_sizes(mesh) -> np.ndarray:
    starts = np.empty(len(mesh.polygons), dtype=np.int32)
    if len(starts):
        mesh.polygons.foreach_get('loop_start', starts)
    return np.diff(np.append(starts, len(mesh.loops)))


def vert_to_corner(mask: np.ndarray, mesh) -> np.ndarray:
    """Map a vertex mask (V,) to corners (L,) by gathering over loop vertex index."""
    return mask[_loop_vertices(mesh)]


def face_to_corner(mask: np.ndarray, mesh) -> np.ndarray:
    """Map a face mask (F,) to corners (L,)."""
    return np.repeat(mask, _face_sizes(mesh))


def face_to_vert(mask: np.ndarray, mesh) -> np.ndarray:
    """Vertices belonging to any masked face."""
    out = np.zeros(len(mesh.vertices), dtype=bool)
    out[_loop_vertices(mesh)[face_to_corner(mask, mesh)]] = True
    return out


def get_selection_mask(obj, domain: str, scope: str, mode: str | None = None) -> np.ndarray:
    """Bool mask (N,) over the domain ('POINT'|'CORNER') for scope ('ALL'|'SELECTED').

    Object mode: whole mesh. Edit mode: vertex/face select mode decides.
    Vertex Paint: use_paint_mask (faces) / use_paint_mask_vertex (vertices);
    if neither is enabled the whole mesh is used.

    `mode` selects the branch ('OBJECT'|'EDIT'|'VERTEX_PAINT'); None -> obj.mode.
    Inside ensure_object_mode obj.mode is already 'OBJECT', so ALWAYS pass the
    original mode, otherwise SELECTED silently becomes the whole mesh:

        with ensure_object_mode(obj) as orig_mode:
            mask = get_selection_mask(obj, attr.domain, scope, mode=orig_mode)
    """
    if domain not in ('POINT', 'CORNER'):
        raise ValueError(f"Unsupported domain {domain}")
    mesh = obj.data
    n = len(mesh.vertices) if domain == 'POINT' else len(mesh.loops)
    all_true = np.ones(n, dtype=bool)
    if scope == 'ALL':
        return all_true
    if scope != 'SELECTED':
        raise ValueError(f"Unsupported scope {scope}")

    if mode is None:
        mode = obj.mode
    if mode == 'EDIT':
        if obj.mode == 'EDIT':  # in OBJECT mode data is already synced by mode_set
            obj.update_from_editmode()
        face_mode = bool(bpy.context.tool_settings.mesh_select_mode[2])
    elif mode == 'VERTEX_PAINT':
        if mesh.use_paint_mask:
            face_mode = True
        elif mesh.use_paint_mask_vertex:
            face_mode = False
        else:
            return all_true
    else:
        return all_true

    if face_mode:
        faces = face_selection(mesh)
        return face_to_vert(faces, mesh) if domain == 'POINT' else face_to_corner(faces, mesh)
    verts = vertex_selection(mesh)
    return verts if domain == 'POINT' else vert_to_corner(verts, mesh)
