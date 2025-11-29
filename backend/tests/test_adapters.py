# backend/tests/test_adapters.py
"""Tests for device format adapters."""

from datetime import datetime, timezone

import pytest
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
