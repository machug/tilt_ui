"""Base adapter class for device format normalization."""

from abc import ABC, abstractmethod
from typing import Optional

from ..base import GravityUnit, HydrometerReading, TemperatureUnit


class BaseAdapter(ABC):
    """Base class for device format adapters.

    Each adapter normalizes a specific device's payload format into
    a universal HydrometerReading.
    """

    device_type: str  # "tilt", "ispindel", "floaty", "gravitymon"

    # Native units for this device type
    native_gravity_unit: GravityUnit = GravityUnit.SG
    native_temp_unit: TemperatureUnit = TemperatureUnit.CELSIUS

    @abstractmethod
    def can_handle(self, payload: dict) -> bool:
        """Check if this adapter can handle the payload.

        Args:
            payload: Raw payload dictionary

        Returns:
            True if this adapter should process the payload
        """
        pass

    @abstractmethod
    def parse(self, payload: dict, source_protocol: str) -> Optional[HydrometerReading]:
        """Parse payload into HydrometerReading.

        Adapters MUST:
        - Set gravity_raw/temperature_raw with original values
        - Set gravity_unit/temperature_unit to indicate native units
        - Set status=UNCALIBRATED if angle-only (no pre-calculated gravity)
        - Set is_pre_filtered=True if device sends smoothed/filtered values
        - NOT fill gravity/temperature - calibration service does that

        Args:
            payload: Raw payload dictionary
            source_protocol: How payload was received ("http", "mqtt", "ble", etc.)

        Returns:
            HydrometerReading or None if parsing fails
        """
        pass
