"""Operators package."""

from . import bake, channel_transfer, channel_value, fill, filters, gradient, invert, levels

classes = (*fill.classes, *invert.classes, *channel_value.classes,
           *channel_transfer.classes, *filters.classes, *levels.classes,
           *gradient.classes, *bake.classes)
