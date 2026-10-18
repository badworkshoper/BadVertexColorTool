"""Operators package."""

from . import channel_transfer, channel_value, fill, invert

classes = (*fill.classes, *invert.classes, *channel_value.classes,
           *channel_transfer.classes)
