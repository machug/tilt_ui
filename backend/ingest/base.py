"""Core data structures for universal hydrometer readings."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class GravityUnit(Enum):
    """Gravity measurement units."""
    SG = "sg"        # Specific Gravity (1.000-1.150)
    PLATO = "plato"  # Degrees Plato (0-35)


class TemperatureUnit(Enum):
    """Temperature measurement units."""
    FAHRENHEIT = "f"
    CELSIUS = "c"


class ReadingStatus(Enum):
    """Processing status of a reading."""
    VALID = "valid"              # All fields present and calibrated
    UNCALIBRATED = "uncalibrated"  # Needs calibration (angle-only)
    INCOMPLETE = "incomplete"    # Missing required fields
    INVALID = "invalid"          # Failed validation


@dataclass
class HydrometerReading:
    """Universal reading from any hydrometer type.

    All measurement fields are Optional to handle:
    - Angle-only iSpindel before polynomial calibration
    - Degraded BLE reads with partial data
    - Brewfather payloads with degrees Plato instead of SG
    """
    device_id: str
    device_type: str  # "tilt", "ispindel", "floaty", "gravitymon", "rapt"
    timestamp: datetime

    # Normalized measurements (filled by calibration service, may be None)
    gravity: Optional[float] = None       # Always SG after normalization
    temperature: Optional[float] = None   # Always Fahrenheit after normalization

    # Raw measurements as received (before calibration/conversion)
    gravity_raw: Optional[float] = None
    gravity_unit: GravityUnit = GravityUnit.SG
    temperature_raw: Optional[float] = None
    temperature_unit: TemperatureUnit = TemperatureUnit.FAHRENHEIT
    angle: Optional[float] = None         # Tilt angle (iSpindel/Floaty)

    # Metadata
    rssi: Optional[int] = None
    battery_voltage: Optional[float] = None   # Always volts
    battery_percent: Optional[int] = None     # 0-100 if device provides it

    # Processing metadata
    status: ReadingStatus = ReadingStatus.VALID
    is_pre_filtered: bool = False         # True if device sent filtered/smoothed data
    source_protocol: str = "unknown"      # "ble", "http", "mqtt", "websocket", "influxdb"
    raw_payload: Optional[dict] = None    # Original payload for debugging

    def is_complete(self) -> bool:
        """Check if reading has all required fields for storage."""
        return self.gravity is not None and self.temperature is not None

    def needs_calibration(self) -> bool:
        """Check if reading needs calibration processing."""
        return self.status == ReadingStatus.UNCALIBRATED
