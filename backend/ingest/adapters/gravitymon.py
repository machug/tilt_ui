# backend/ingest/adapters/gravitymon.py
"""GravityMon adapter (extended iSpindel format)."""

from datetime import datetime, timezone
from typing import Optional

from ..base import GravityUnit, HydrometerReading, ReadingStatus, TemperatureUnit
from ..units import normalize_battery
from .base import BaseAdapter


class GravityMonAdapter(BaseAdapter):
    """Adapter for GravityMon JSON format.

    GravityMon extends iSpindel format with:
    - corr-gravity: Corrected/filtered gravity value
    - run-time: Uptime in seconds
    - Other extended fields

    GravityMon can send already-filtered values, so we mark
    is_pre_filtered=True when corr-gravity is present.
    """

    device_type = "gravitymon"
    native_gravity_unit = GravityUnit.SG
    native_temp_unit = TemperatureUnit.CELSIUS

    def can_handle(self, payload: dict) -> bool:
        """GravityMon has iSpindel base fields plus extensions."""
        has_ispindel_base = "angle" in payload and "name" in payload
        has_gravitymon_ext = "corr-gravity" in payload or "run-time" in payload
        return has_ispindel_base and has_gravitymon_ext

    def parse(self, payload: dict, source_protocol: str) -> Optional[HydrometerReading]:
        """Parse GravityMon JSON payload."""
        device_id = payload.get("ID") or payload.get("id") or payload.get("name")
        if not device_id:
            return None
        device_id = str(device_id)

        # Detect gravity unit
        gravity_unit = GravityUnit.SG
        unit_field = payload.get("gravity-unit", "")
        if unit_field == "P":
            gravity_unit = GravityUnit.PLATO

        # Check for pre-filtered corrected gravity
        is_pre_filtered = "corr-gravity" in payload
        gravity_raw = None

        # Prefer corr-gravity, fall back to gravity
        raw_gravity = payload.get("corr-gravity") or payload.get("gravity")
        if raw_gravity is not None:
            try:
                gravity_raw = float(raw_gravity)
                if gravity_raw == 0:
                    gravity_raw = None
            except (ValueError, TypeError):
                pass

        # If we used regular gravity (not corr-gravity), not pre-filtered
        if gravity_raw is not None and "corr-gravity" not in payload:
            is_pre_filtered = False

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
            gravity_raw=gravity_raw,
            gravity_unit=gravity_unit,
            temperature_raw=temperature_raw,
            temperature_unit=self.native_temp_unit,
            angle=angle,
            rssi=rssi,
            battery_voltage=battery_voltage,
            battery_percent=battery_percent,
            status=status,
            is_pre_filtered=is_pre_filtered,
            source_protocol=source_protocol,
            raw_payload=payload,
        )
