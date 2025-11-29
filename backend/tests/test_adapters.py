# backend/tests/test_adapters.py
"""Tests for device format adapters."""

from datetime import datetime, timezone

import pytest
from backend.ingest.adapters.gravitymon import GravityMonAdapter
from backend.ingest.adapters.ispindel import ISpindelAdapter
from backend.ingest.adapters.tilt import TiltAdapter
from backend.ingest.base import GravityUnit, ReadingStatus, TemperatureUnit


class TestTiltAdapter:
    """Test Tilt BLE adapter."""

    @pytest.fixture
    def adapter(self):
        return TiltAdapter()

    def test_can_handle_tilt_payload(self, adapter):
        payload = {
            "color": "RED",
            "mac": "AA:BB:CC:DD:EE:FF",
            "temp_f": 68.5,
            "sg": 1.050,
            "rssi": -65,
        }
        assert adapter.can_handle(payload) is True

    def test_cannot_handle_ispindel_payload(self, adapter):
        payload = {
            "name": "iSpindel",
            "angle": 25.5,
            "temperature": 20.0,
        }
        assert adapter.can_handle(payload) is False

    def test_parse_tilt_reading(self, adapter):
        payload = {
            "color": "RED",
            "mac": "AA:BB:CC:DD:EE:FF",
            "temp_f": 68.5,
            "sg": 1.050,
            "rssi": -65,
        }
        reading = adapter.parse(payload, source_protocol="ble")

        assert reading is not None
        assert reading.device_id == "RED"
        assert reading.device_type == "tilt"
        assert reading.gravity_raw == 1.050
        assert reading.temperature_raw == 68.5
        assert reading.temperature_unit == TemperatureUnit.FAHRENHEIT
        assert reading.gravity_unit == GravityUnit.SG
        assert reading.rssi == -65
        assert reading.source_protocol == "ble"
        assert reading.status == ReadingStatus.VALID

    def test_parse_stores_raw_payload(self, adapter):
        payload = {"color": "BLUE", "temp_f": 70.0, "sg": 1.045, "rssi": -70}
        reading = adapter.parse(payload, source_protocol="ble")
        assert reading.raw_payload == payload

    def test_parse_missing_sg_returns_incomplete(self, adapter):
        payload = {"color": "RED", "temp_f": 68.5, "rssi": -65}
        reading = adapter.parse(payload, source_protocol="ble")
        assert reading.status == ReadingStatus.INCOMPLETE
        assert reading.gravity_raw is None

    def test_parse_missing_color_returns_none(self, adapter):
        payload = {"temp_f": 68.5, "sg": 1.050, "rssi": -65}
        reading = adapter.parse(payload, source_protocol="ble")
        assert reading is None


class TestISpindelAdapter:
    """Test iSpindel HTTP/MQTT adapter."""

    @pytest.fixture
    def adapter(self):
        return ISpindelAdapter()

    def test_can_handle_ispindel_payload(self, adapter):
        payload = {
            "name": "iSpindel001",
            "angle": 25.5,
            "temperature": 20.0,
            "battery": 3.8,
        }
        assert adapter.can_handle(payload) is True

    def test_cannot_handle_tilt_payload(self, adapter):
        payload = {"color": "RED", "sg": 1.050}
        assert adapter.can_handle(payload) is False

    def test_parse_with_precalculated_gravity(self, adapter):
        payload = {
            "name": "iSpindel001",
            "ID": 12345,
            "angle": 25.5,
            "temperature": 20.0,
            "gravity": 1.048,
            "battery": 3.8,
            "RSSI": -72,
        }
        reading = adapter.parse(payload, source_protocol="http")

        assert reading is not None
        assert reading.device_id == "12345"
        assert reading.device_type == "ispindel"
        assert reading.gravity_raw == 1.048
        assert reading.angle == 25.5
        assert reading.temperature_raw == 20.0
        assert reading.temperature_unit == TemperatureUnit.CELSIUS
        assert reading.battery_voltage is not None
        assert reading.status == ReadingStatus.VALID

    def test_parse_angle_only_uncalibrated(self, adapter):
        """iSpindel without pre-calculated gravity needs polynomial calibration."""
        payload = {
            "name": "iSpindel001",
            "angle": 25.5,
            "temperature": 20.0,
            "battery": 3.8,
        }
        reading = adapter.parse(payload, source_protocol="http")

        assert reading is not None
        assert reading.gravity_raw is None
        assert reading.angle == 25.5
        assert reading.status == ReadingStatus.UNCALIBRATED

    def test_parse_gravity_zero_treated_as_uncalibrated(self, adapter):
        """Gravity of 0 means iSpindel hasn't been calibrated."""
        payload = {
            "name": "iSpindel001",
            "angle": 25.5,
            "temperature": 20.0,
            "gravity": 0,
            "battery": 3.8,
        }
        reading = adapter.parse(payload, source_protocol="http")

        assert reading.gravity_raw is None
        assert reading.status == ReadingStatus.UNCALIBRATED

    def test_parse_plato_unit_detection(self, adapter):
        """Detect Plato gravity unit from payload."""
        payload = {
            "name": "iSpindel001",
            "angle": 25.5,
            "temperature": 20.0,
            "gravity": 12.5,
            "gravity-unit": "P",
            "battery": 3.8,
        }
        reading = adapter.parse(payload, source_protocol="http")

        assert reading.gravity_unit == GravityUnit.PLATO
        assert reading.gravity_raw == 12.5

    def test_parse_uses_id_over_name(self, adapter):
        """Prefer numeric ID over name for device_id."""
        payload = {
            "name": "MySpindel",
            "ID": 98765,
            "angle": 25.5,
            "temperature": 20.0,
        }
        reading = adapter.parse(payload, source_protocol="http")
        assert reading.device_id == "98765"

    def test_parse_falls_back_to_name(self, adapter):
        """Use name as device_id when ID not present."""
        payload = {
            "name": "MySpindel",
            "angle": 25.5,
            "temperature": 20.0,
        }
        reading = adapter.parse(payload, source_protocol="http")
        assert reading.device_id == "MySpindel"


class TestGravityMonAdapter:
    """Test GravityMon adapter (iSpindel-compatible with extensions)."""

    @pytest.fixture
    def adapter(self):
        return GravityMonAdapter()

    def test_can_handle_gravitymon_payload(self, adapter):
        payload = {
            "name": "GravityMon",
            "angle": 25.5,
            "temperature": 20.0,
            "corr-gravity": 1.048,
            "run-time": 12345,
        }
        assert adapter.can_handle(payload) is True

    def test_cannot_handle_plain_ispindel(self, adapter):
        """Plain iSpindel without GravityMon extensions."""
        payload = {
            "name": "iSpindel001",
            "angle": 25.5,
            "temperature": 20.0,
            "gravity": 1.048,
        }
        assert adapter.can_handle(payload) is False

    def test_parse_with_corrected_gravity(self, adapter):
        """GravityMon corr-gravity is pre-filtered."""
        payload = {
            "name": "GravityMon",
            "ID": 54321,
            "angle": 25.5,
            "temperature": 20.0,
            "corr-gravity": 1.048,
            "run-time": 12345,
        }
        reading = adapter.parse(payload, source_protocol="mqtt")

        assert reading is not None
        assert reading.device_type == "gravitymon"
        assert reading.gravity_raw == 1.048
        assert reading.is_pre_filtered is True  # Key difference from iSpindel

    def test_parse_falls_back_to_gravity(self, adapter):
        """Use gravity field if corr-gravity not present."""
        payload = {
            "name": "GravityMon",
            "angle": 25.5,
            "temperature": 20.0,
            "gravity": 1.050,
            "run-time": 12345,
        }
        reading = adapter.parse(payload, source_protocol="http")

        assert reading.gravity_raw == 1.050
        assert reading.is_pre_filtered is False  # Regular gravity, not filtered
