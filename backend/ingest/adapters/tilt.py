# backend/ingest/adapters/tilt.py
"""Tilt Hydrometer BLE adapter."""

from datetime import datetime, timezone
from typing import Optional

from ..base import GravityUnit, HydrometerReading, ReadingStatus, TemperatureUnit
from .base import BaseAdapter


class TiltAdapter(BaseAdapter):
    """Adapter for Tilt Hydrometer BLE iBeacon format.

    Tilt sends:
    - color: Device color identifier (RED, GREEN, etc.)
    - mac: BLE MAC address
    - temp_f: Temperature in Fahrenheit
    - sg: Specific gravity
    - rssi: Signal strength
    """

    device_type = "tilt"
    native_gravity_unit = GravityUnit.SG
    native_temp_unit = TemperatureUnit.FAHRENHEIT

    def can_handle(self, payload: dict) -> bool:
        """Tilt payloads have 'color' and 'sg' fields."""
        return "color" in payload and ("sg" in payload or "temp_f" in payload)

    def parse(self, payload: dict, source_protocol: str) -> Optional[HydrometerReading]:
        """Parse Tilt BLE reading."""
        color = payload.get("color")
        if not color:
            return None

        # Extract values
        sg = payload.get("sg")
        temp_f = payload.get("temp_f")
        rssi = payload.get("rssi")
        _mac = payload.get("mac")  # Extracted but not used (available in raw_payload)

        # Determine status
        if sg is None and temp_f is None:
            status = ReadingStatus.INVALID
        elif sg is None or temp_f is None:
            status = ReadingStatus.INCOMPLETE
        else:
            status = ReadingStatus.VALID

        # Parse numeric values safely
        gravity_raw = None
        if sg is not None:
            try:
                gravity_raw = float(sg)
            except (ValueError, TypeError):
                pass

        temperature_raw = None
        if temp_f is not None:
            try:
                temperature_raw = float(temp_f)
            except (ValueError, TypeError):
                pass

        return HydrometerReading(
            device_id=color,
            device_type=self.device_type,
            timestamp=datetime.now(timezone.utc),
            # Raw values - calibration service will fill normalized values
            gravity_raw=gravity_raw,
            gravity_unit=self.native_gravity_unit,
            temperature_raw=temperature_raw,
            temperature_unit=self.native_temp_unit,
            # Metadata
            rssi=rssi,
            # Processing
            status=status,
            is_pre_filtered=False,
            source_protocol=source_protocol,
            raw_payload=payload,
        )
