"""Zero-Dependency Multi-Threaded HTTP Backend Server for Project eMyrge."""

from typing import Any

__all__ = ["EmyrgeRuntime", "create_server", "main"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from emyrge.web import app
        return getattr(app, name)
    raise AttributeError(f"module 'emyrge.web' has no attribute {name!r}")
