# backend/ingest/adapters/ispindel.py
"""iSpindel WiFi hydrometer adapter."""

from datetime import datetime, timezone
from typing import Optional

from ..base import GravityUnit, HydrometerReading, ReadingStatus, TemperatureUnit
from ..units import normalize_battery
from .base import BaseAdapter


class ISpindelAdapter(BaseAdapter):
    """Adapter for iSpindel JSON format.

    iSpindel sends via HTTP POST or MQTT:
    - name: Device name
    - ID: Chip ID (numeric, preferred for device_id)
    - angle: Tilt angle in degrees
    - temperature: Temperature in Celsius
    - gravity: Pre-calculated gravity (may be 0 if not calibrated)
    - gravity-unit: "G" for SG, "P" for Plato (optional)
    - battery: Battery voltage
    - RSSI: WiFi signal strength
    """

    device_type = "ispindel"
    native_gravity_unit = GravityUnit.SG
    native_temp_unit = TemperatureUnit.CELSIUS

    def can_handle(self, payload: dict) -> bool:
        """iSpindel payloads have 'angle' and 'name' fields."""
        return "angle" in payload and "name" in payload

    def parse(self, payload: dict, source_protocol: str) -> Optional[HydrometerReading]:
        """Parse iSpindel JSON payload."""
        # Device ID: prefer numeric ID, fall back to name
        device_id = payload.get("ID") or payload.get("id") or payload.get("name")
        if not device_id:
            return None
        device_id = str(device_id)

        # Detect gravity unit
        gravity_unit = GravityUnit.SG
        unit_field = payload.get("gravity-unit", payload.get("temp_units", ""))
        if unit_field == "P":
            gravity_unit = GravityUnit.PLATO

        # Extract gravity (may be None or 0 = uncalibrated)
        gravity_raw = None
        raw_gravity = payload.get("gravity")
        if raw_gravity is not None:
            try:
                gravity_raw = float(raw_gravity)
                if gravity_raw == 0:
                    gravity_raw = None  # 0 means uncalibrated
            except (ValueError, TypeError):
                pass

        # Extract angle
        angle = None
        raw_angle = payload.get("angle")
        if raw_angle is not None:
            try:
                angle = float(raw_angle)
            except (ValueError, TypeError):
                pass

        # Extract temperature
        temperature_raw = None
        raw_temp = payload.get("temperature", payload.get("temp"))
        if raw_temp is not None:
            try:
                temperature_raw = float(raw_temp)
            except (ValueError, TypeError):
                pass

        # Determine status
        if gravity_raw is None and angle is not None:
            status = ReadingStatus.UNCALIBRATED
        elif gravity_raw is None and angle is None:
            status = ReadingStatus.INCOMPLETE
        else:
            status = ReadingStatus.VALID

        # Battery normalization
        battery_voltage, battery_percent = None, None
        raw_battery = payload.get("battery")
        if raw_battery is not None:
            try:
                battery_voltage, battery_percent = normalize_battery(
                    float(raw_battery),
                    self.device_type,
                    is_percent=False
                )
            except (ValueError, TypeError):
                pass

        # RSSI
        rssi = payload.get("RSSI")
        if rssi is not None:
            try:
                rssi = int(rssi)
            except (ValueError, TypeError):
                rssi = None

        return HydrometerReading(
            device_id=device_id,
            device_type=self.device_type,
            timestamp=datetime.now(timezone.utc),
            # Raw values
            gravity_raw=gravity_raw,
            gravity_unit=gravity_unit,
            temperature_raw=temperature_raw,
            temperature_unit=self.native_temp_unit,
            angle=angle,
            # Metadata
            rssi=rssi,
            battery_voltage=battery_voltage,
            battery_percent=battery_percent,
            # Processing
            status=status,
            is_pre_filtered=False,
            source_protocol=source_protocol,
            raw_payload=payload,
        )
