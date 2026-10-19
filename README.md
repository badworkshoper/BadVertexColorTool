# BadVertexColorTool

[Українська версія](README.uk.md)

Fast and safe tools for Vertex Colors (Color Attributes) in Blender: fill, invert, channel edits, filters, gradients, bake, an interactive brush and a single-channel preview. The add-on writes only to the active color attribute and only to the channels you pick.

## Requirements

- Blender 4.2 or newer.
- Color attributes on the Point (vertex) or Face Corner domain, Byte or Float type.

## Installation

- **Extension zip** (`bad_vertex_color_tool-<version>.zip`): Preferences > Get Extensions > top-right arrow menu > Install from Disk.
- **Legacy zip** (`BadVertexColorTool-<version>-legacy.zip`): Preferences > Add-ons > Install from Disk, then enable "BadVertexColorTool".

Find the tools in the 3D Viewport: Sidebar (N) > **BadVC** tab.

## Core concepts

- **Channels R G B A**: the row at the top of the panel chooses which channels every operation writes to. Other channels are never touched.
- **Scope**: *All* affects the whole mesh; *Selected* only selected elements.
  - Edit Mode: selected vertices or faces (depends on the select mode).
  - Vertex Paint: respects the Face / Vertex selection masks if enabled; with no mask the whole mesh is used.
  - Object Mode: the whole mesh.
- **Isolate** (R / G / B / A buttons): shows one channel of the active attribute as grayscale in the viewport. The mesh data is not changed. While a channel is isolated, edits go only to that channel. Click again (or the X button) to turn it off. The *Shading* option adds light shading to the preview.

## Panels

- **Channel Values**: *Sample* reads the average channel values of the affected elements into the sliders; *Set All* writes all four sliders at once; *Set* next to a slider writes only that channel.
- **Paint**
  - *Fill with Color* and *Fill with Value* (a single value into the chosen channels).
  - *Invert*.
  - Mode **Mix / Add / Sub / Blur** with a shared **Strength** (and Source for Mix/Add/Sub). *Apply* runs it once on the scope; *Brush* uses the same mode and strength interactively. Radius, Falloff, Spacing and Front Faces are brush settings.
- **Gradient** (collapsed by default): Source (values or colors), Easing, Linear / Radial shape.
  - *Axis*: X / Y / Z in Object or World space.
  - *Gesture*: *Draw Gradient*, then drag in the viewport.
  - *Between Vertices*: select exactly 2 vertices in Edit Mode, or set Start / End groups; Linear or Geodesic method.
- **Bake** (collapsed): Normal (Object / World space, with channel Swizzle +-X/Y/Z to R/G/B/A; sources: mesh normals, proxy object, spherical), AO, Random (per loose part / face / vertex), Position (axis or distance). The *Writes to* row shows exactly which channels will be written.
- **Adjust** (collapsed): Levels, Brightness / Contrast, Posterize, Clamp. Tweak the values afterwards in *Adjust Last Operation* (F9).
- **Channel Transfer** (collapsed): *Within Attribute* copies or swaps one channel with another; *From Attribute* copies or swaps a channel or the full color from another color attribute (domains and types may differ).
- **Color Attribute** (collapsed): add a color attribute and see the name, domain and type of the active one.

## Brush controls

Press **Brush** in the Paint panel (works in Vertex Paint and Object Mode).

| Key | Action |
|-----|--------|
| LMB drag | Paint (one undo step per stroke) |
| `[` / `]` | Decrease / increase radius |
| F | Resize radius interactively (LMB / F / Enter confirm, Esc cancel) |
| Shift+F | Change strength interactively |
| Shift (hold) | Blur instead of the current mode |
| Ctrl (hold) | Invert mode (Add becomes Sub, and so on) |
| Ctrl+Z | End the session and undo the last stroke |
| Esc / RMB / Enter / Ctrl+Tab | Exit the brush |

Mouse wheel and MMB navigate the viewport as usual.

## Gradient gesture controls

Press *Draw Gradient*, then drag LMB in the viewport from the start to the end point; release to apply. Hold **Shift** while dragging to snap the direction. **Esc** or **RMB** cancels. Very short drags are ignored.

## Tips and known limitations

- If a brush session started in Edit Mode and you press Ctrl+Z, the object stays in Object Mode.
- In Vertex Paint, Blender's own red brush circle is visible next to the add-on cursor.
- The *Front Faces* filter uses the vertex normal only (no occlusion test).
- Isolate in Edit Mode shows the last synchronized data; leave and re-enter Edit Mode to refresh.
- AO on objects with modifiers casts rays from the base mesh vertices.

## License

GPL-3.0-or-later.
