"""Typed, fail-closed contract errors."""


class EngineError(Exception):
    """Base for input, capability, and replay contract failures."""


class InvalidEvent(EngineError, ValueError):
    """An event violates a schema, identity, or ordering invariant."""


class UnsupportedData(EngineError, ValueError):
    """A data type, resolution, or capability is not available."""


class StaleData(EngineError, ValueError):
    """An observation is not eligible for the requested decision time."""
