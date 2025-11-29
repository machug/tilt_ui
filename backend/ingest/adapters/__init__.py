"""Device format adapters for normalizing hydrometer payloads."""

from .base import BaseAdapter
from .tilt import TiltAdapter

__all__ = ["BaseAdapter", "TiltAdapter"]
