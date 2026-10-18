"""GPU brush cursor: a circle of the brush radius (in region pixels) drawn at the mouse position."""

import traceback

import bpy
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader

MODE_COLORS = {
    'MIX': (1.0, 1.0, 1.0, 0.9),
    'ADD': (0.3, 1.0, 0.3, 0.9),
    'SUB': (1.0, 0.3, 0.3, 0.9),
    'BLUR': (0.3, 0.7, 1.0, 0.9),
}

_shader = [None]


def circle_points(center, radius: float, segments: int = 64) -> np.ndarray:
    """Closed polyline (segments + 1, 2) float32."""
    ang = np.linspace(0.0, 2.0 * np.pi, segments + 1, dtype=np.float32)
    c = np.asarray(center, dtype=np.float32)
    return c + float(radius) * np.stack([np.cos(ang), np.sin(ang)], axis=1)


def draw_cursor(state: dict) -> None:
    """POST_PIXEL callback. `state`: pos (x, y) or None, radius, mode, strength, failed. Silent after a failure."""
    if state['failed'] or state['pos'] is None:
        return
    try:
        if _shader[0] is None:
            _shader[0] = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
        shader = _shader[0]
        region = bpy.context.region
        color = MODE_COLORS.get(state['mode'], MODE_COLORS['MIX'])
        strips = [(circle_points(state['pos'], state['radius']), color, 2.0)]
        # Inner circle hints the strength; centre dot marks the exact dab position.
        inner = max(state['radius'] * (1.0 - state['strength']), 1.0)
        strips.append((circle_points(state['pos'], inner, 48), (color[0], color[1], color[2], 0.35), 1.0))
        strips.append((circle_points(state['pos'], 1.5, 8), color, 2.0))
        gpu.state.blend_set('ALPHA')
        shader.bind()
        shader.uniform_float('viewportSize', (region.width, region.height))
        for pts, col, width in strips:
            shader.uniform_float('color', col)
            shader.uniform_float('lineWidth', width)
            batch_for_shader(shader, 'LINE_STRIP', {"pos": pts}).draw(shader)
    except Exception:
        state['failed'] = True
        print("[BadVC] Brush cursor draw error:")
        traceback.print_exc()
    finally:
        gpu.state.blend_set('NONE')


def add_handler(state: dict):
    """Register the cursor draw handler; returns the handle."""
    return bpy.types.SpaceView3D.draw_handler_add(draw_cursor, (state,), 'WINDOW', 'POST_PIXEL')


def remove_handler(handle) -> None:
    """Remove a handle returned by add_handler (errors ignored)."""
    if handle is None:
        return
    try:
        bpy.types.SpaceView3D.draw_handler_remove(handle, 'WINDOW')
    except Exception:
        pass
