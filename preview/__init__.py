"""Preview overlays package. Never modifies mesh data."""

from . import isolate

classes = (*isolate.classes,)


def register() -> None:
    """Register WM props (handlers are installed only while a preview is ON)."""
    isolate.register_props()


def unregister() -> None:
    """Remove draw/app handlers and WM props; safe to call repeatedly."""
    isolate.shutdown()
    isolate.unregister_props()
