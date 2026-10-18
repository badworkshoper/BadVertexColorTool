"""Operators package."""

from . import channel_value, fill, invert

classes = (*fill.classes, *invert.classes, *channel_value.classes)
