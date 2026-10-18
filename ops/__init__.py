"""Operators package."""

from . import channel_transfer, channel_value, fill, filters, invert, levels

classes = (*fill.classes, *invert.classes, *channel_value.classes,
           *channel_transfer.classes, *filters.classes, *levels.classes)
