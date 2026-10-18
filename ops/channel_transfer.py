"""F04: copy / swap channels within an attribute and between color attributes."""

import bpy
import numpy as np
from bpy.props import EnumProperty, StringProperty

from ..core.attributes import (
    get_active_color_attribute,
    read_colors,
    validate_color_attribute,
    write_colors,
)
from ..core.channels import CHANNEL_INDEX, CHANNEL_ITEMS, channels_to_indices
from ..core.mode import ensure_object_mode
from ..core.selection import get_selection_mask
from ..core.topology import convert_domain
from ._common import init_from_settings, poll_color_mesh, run_color_op
from .fill import SCOPE_ITEMS

_LOSSY_MSG = "Domains differ: swap is lossy (corner values averaged)"


class BADVC_OT_channel_copy(bpy.types.Operator):
    """Copy one channel into another within the active color attribute"""
    bl_idname = "badvc.channel_copy"
    bl_label = "Copy Channel"
    bl_options = {'REGISTER', 'UNDO'}

    src: EnumProperty(name="From", items=CHANNEL_ITEMS, default='R')
    dst: EnumProperty(name="To", items=CHANNEL_ITEMS, default='G')
    scope: EnumProperty(name="Scope", items=SCOPE_ITEMS, default='SELECTED')

    @classmethod
    def poll(cls, context):
        return poll_color_mesh(context)

    def invoke(self, context, event):
        init_from_settings(self, context, ('src', 'dst', 'scope'))
        return self.execute(context)

    def execute(self, context):
        if self.src == self.dst:
            self.report({'WARNING'}, "Source and destination channels are the same")
            return {'CANCELLED'}
        s, d = CHANNEL_INDEX[self.src], CHANNEL_INDEX[self.dst]

        def func(c):
            out = c.copy()
            out[:, d] = c[:, s]
            return out

        return run_color_op(self, context, func, {self.dst}, self.scope)


class BADVC_OT_channel_swap(bpy.types.Operator):
    """Swap two channels within the active color attribute"""
    bl_idname = "badvc.channel_swap"
    bl_label = "Swap Channels"
    bl_options = {'REGISTER', 'UNDO'}

    a: EnumProperty(name="A", items=CHANNEL_ITEMS, default='R')
    b: EnumProperty(name="B", items=CHANNEL_ITEMS, default='G')
    scope: EnumProperty(name="Scope", items=SCOPE_ITEMS, default='SELECTED')

    @classmethod
    def poll(cls, context):
        return poll_color_mesh(context)

    def invoke(self, context, event):
        # Panel settings: transfer_src_channel / transfer_dst_channel
        settings = context.scene.badvc
        if not self.properties.is_property_set('a'):
            self.a = settings.transfer_src_channel
        if not self.properties.is_property_set('b'):
            self.b = settings.transfer_dst_channel
        init_from_settings(self, context, ('scope',))
        return self.execute(context)

    def execute(self, context):
        if self.a == self.b:
            self.report({'WARNING'}, "Both channels are the same")
            return {'CANCELLED'}
        ia, ib = CHANNEL_INDEX[self.a], CHANNEL_INDEX[self.b]

        def func(c):
            out = c.copy()
            out[:, [ia, ib]] = c[:, [ib, ia]]
            return out

        return run_color_op(self, context, func, {self.a, self.b}, self.scope)


def transfer_between_attributes(obj, source_name: str, operation: str, mode: str,
                                src_channel: str, dst_channel: str,
                                channels: set[str], scope: str) -> tuple[int, bool]:
    """Copy/swap values between the active (target) attribute and `source_name`.

    Returns (elements changed in target, lossy_swap). Raises ValueError on invalid input.
    COPY writes only the target; SWAP writes both (explicit user action).
    """
    with ensure_object_mode(obj) as orig_mode:
        mesh = obj.data
        # Re-fetch everything by name after the mode change (no stale references).
        target = get_active_color_attribute(mesh)
        error = validate_color_attribute(mesh, target)
        if error:
            raise ValueError(error)
        target_name = target.name
        if not source_name:
            raise ValueError("No source attribute selected")
        source = mesh.color_attributes.get(source_name)
        if source is None:
            raise ValueError(f"Source attribute '{source_name}' not found")
        if source.name == target_name:
            raise ValueError("Source and target attributes are the same")
        error = validate_color_attribute(mesh, source)
        if error:
            raise ValueError(error)

        if mode == 'CHANNEL':
            t_ch, s_ch = [CHANNEL_INDEX[dst_channel]], [CHANNEL_INDEX[src_channel]]
        else:
            t_ch = s_ch = channels_to_indices(channels)
        if not t_ch:
            return 0, False

        t_dom, s_dom = target.domain, source.domain
        t_col, s_col = read_colors(mesh, target), read_colors(mesh, source)
        t_idx = np.flatnonzero(get_selection_mask(obj, t_dom, scope, mode=orig_mode))
        if t_idx.size == 0:
            return 0, False

        new_t = t_col.copy()
        s_in_t = convert_domain(s_col, mesh, s_dom, t_dom)
        new_t[np.ix_(t_idx, t_ch)] = s_in_t[np.ix_(t_idx, s_ch)]

        new_s = None
        if operation == 'SWAP':
            s_idx = np.flatnonzero(get_selection_mask(obj, s_dom, scope, mode=orig_mode))
            t_in_s = convert_domain(t_col, mesh, t_dom, s_dom)
            new_s = s_col.copy()
            if s_idx.size:
                new_s[np.ix_(s_idx, s_ch)] = t_in_s[np.ix_(s_idx, t_ch)]

        # Both new arrays are computed from the original data before any write.
        write_colors(mesh, mesh.color_attributes[target_name], new_t)
        if new_s is not None:
            write_colors(mesh, mesh.color_attributes[source_name], new_s)
        return int(t_idx.size), operation == 'SWAP' and t_dom != s_dom


class BADVC_OT_attribute_transfer(bpy.types.Operator):
    """Copy or swap a channel (or the whole color) between another color attribute and the active one"""
    bl_idname = "badvc.attribute_transfer"
    bl_label = "Transfer From Attribute"
    bl_options = {'REGISTER', 'UNDO'}

    source: StringProperty(name="Source", description="Source color attribute name")
    operation: EnumProperty(name="Operation", items=[
        ('COPY', "Copy", "Copy from source into the active attribute (source unchanged)"),
        ('SWAP', "Swap", "Exchange values between the two attributes (both are written)"),
    ], default='COPY')
    mode: EnumProperty(name="Mode", items=[
        ('CHANNEL', "Channel", "Transfer one channel to another"),
        ('COLOR', "Color", "Transfer the selected channels, same channel to same channel"),
    ], default='CHANNEL')
    src_channel: EnumProperty(name="From", items=CHANNEL_ITEMS, default='R')
    dst_channel: EnumProperty(name="To", items=CHANNEL_ITEMS, default='G')
    channels: EnumProperty(name="Channels", items=CHANNEL_ITEMS, options={'ENUM_FLAG'},
                           default={'R', 'G', 'B', 'A'})
    scope: EnumProperty(name="Scope", items=SCOPE_ITEMS, default='SELECTED')

    @classmethod
    def poll(cls, context):
        return poll_color_mesh(context)

    def invoke(self, context, event):
        init_from_settings(self, context, ('source', 'mode', 'src_channel', 'dst_channel',
                                           'channels', 'scope'))
        return self.execute(context)

    def execute(self, context):
        try:
            count, lossy = transfer_between_attributes(
                context.active_object, self.source, self.operation, self.mode,
                self.src_channel, self.dst_channel, set(self.channels), self.scope)
        except ValueError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        if count == 0:
            no_channels = self.mode == 'COLOR' and not self.channels
            self.report({'WARNING'}, "No channels selected" if no_channels else "Nothing selected")
            return {'CANCELLED'}
        if lossy:
            self.report({'WARNING'}, _LOSSY_MSG)
        return {'FINISHED'}


classes = (BADVC_OT_channel_copy, BADVC_OT_channel_swap, BADVC_OT_attribute_transfer)
