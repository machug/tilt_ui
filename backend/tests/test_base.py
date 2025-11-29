# backend/tests/test_base.py
"""Tests for core hydrometer data structures."""

from datetime import datetime, timezone

import pytest
from backend.ingest.base import (
    GravityUnit,
    HydrometerReading,
    ReadingStatus,
    TemperatureUnit,
)


class TestHydrometerReading:
    """Test HydrometerReading dataclass."""

    def test_minimal_reading(self):
        """Test creating reading with only required fields."""
        reading = HydrometerReading(
            device_id="test-device",
            device_type="ispindel",
            timestamp=datetime.now(timezone.utc),
        )
        assert reading.device_id == "test-device"
        assert reading.device_type == "ispindel"
        assert reading.gravity is None
        assert reading.temperature is None
        assert reading.status == ReadingStatus.VALID

    def test_complete_reading(self):
        """Test creating reading with all fields."""
        reading = HydrometerReading(
            device_id="test-device",
            device_type="tilt",
            timestamp=datetime.now(timezone.utc),
            gravity=1.050,
            temperature=68.0,
            gravity_raw=1.052,
            temperature_raw=67.5,
            rssi=-65,
            battery_voltage=2.8,
            battery_percent=80,
            status=ReadingStatus.VALID,
            source_protocol="ble",
        )
        assert reading.is_complete()
        assert not reading.needs_calibration()

    def test_is_complete_with_gravity_only(self):
        """Test is_complete returns False when temperature missing."""
        reading = HydrometerReading(
            device_id="test",
            device_type="ispindel",
            timestamp=datetime.now(timezone.utc),
            gravity=1.050,
            temperature=None,
        )
        assert not reading.is_complete()

    def test_is_complete_with_temperature_only(self):
        """Test is_complete returns False when gravity missing."""
        reading = HydrometerReading(
            device_id="test",
            device_type="ispindel",
            timestamp=datetime.now(timezone.utc),
            gravity=None,
            temperature=68.0,
        )
        assert not reading.is_complete()

    def test_needs_calibration(self):
        """Test needs_calibration for uncalibrated readings."""
        reading = HydrometerReading(
            device_id="test",
            device_type="ispindel",
            timestamp=datetime.now(timezone.utc),
            angle=25.5,
            status=ReadingStatus.UNCALIBRATED,
        )
        assert reading.needs_calibration()

    def test_does_not_need_calibration(self):
        """Test needs_calibration for valid readings."""
        reading = HydrometerReading(
            device_id="test",
            device_type="tilt",
            timestamp=datetime.now(timezone.utc),
            gravity=1.050,
            temperature=68.0,
            status=ReadingStatus.VALID,
        )
        assert not reading.needs_calibration()

    def test_gravity_unit_default(self):
        """Test default gravity unit is SG."""
        reading = HydrometerReading(
            device_id="test",
            device_type="ispindel",
            timestamp=datetime.now(timezone.utc),
        )
        assert reading.gravity_unit == GravityUnit.SG

    def test_temperature_unit_default(self):
        """Test default temperature unit is Fahrenheit."""
        reading = HydrometerReading(
            device_id="test",
            device_type="tilt",
            timestamp=datetime.now(timezone.utc),
        )
        assert reading.temperature_unit == TemperatureUnit.FAHRENHEIT

    def test_raw_payload_storage(self):
        """Test raw payload is stored for debugging."""
        payload = {"name": "iSpindel", "angle": 25.5, "temperature": 20.0}
        reading = HydrometerReading(
            device_id="test",
            device_type="ispindel",
            timestamp=datetime.now(timezone.utc),
            raw_payload=payload,
        )
        assert reading.raw_payload == payload


class TestReadingStatus:
    """Test ReadingStatus enum values."""

    def test_all_statuses_exist(self):
        assert ReadingStatus.VALID.value == "valid"
        assert ReadingStatus.UNCALIBRATED.value == "uncalibrated"
        assert ReadingStatus.INCOMPLETE.value == "incomplete"
        assert ReadingStatus.INVALID.value == "invalid"


class TestGravityUnit:
    """Test GravityUnit enum values."""

    def test_sg_value(self):
        assert GravityUnit.SG.value == "sg"

    def test_plato_value(self):
        assert GravityUnit.PLATO.value == "plato"


class TestTemperatureUnit:
    """Test TemperatureUnit enum values."""

    def test_fahrenheit_value(self):
        assert TemperatureUnit.FAHRENHEIT.value == "f"

    def test_celsius_value(self):
        assert TemperatureUnit.CELSIUS.value == "c"
