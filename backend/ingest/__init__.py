"""Universal hydrometer ingest layer."""

from .adapters import BaseAdapter
from .base import (
    GravityUnit,
    HydrometerReading,
    ReadingStatus,
    TemperatureUnit,
)
from .units import (
    celsius_to_fahrenheit,
    fahrenheit_to_celsius,
    normalize_battery,
    plato_to_sg,
    sg_to_plato,
)

__all__ = [
    "BaseAdapter",
    "GravityUnit",
    "HydrometerReading",
    "ReadingStatus",
    "TemperatureUnit",
    "celsius_to_fahrenheit",
    "fahrenheit_to_celsius",
    "normalize_battery",
    "plato_to_sg",
    "sg_to_plato",
]
