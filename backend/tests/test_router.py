"""Tests for adapter routing."""

import pytest
from backend.ingest.router import AdapterRouter


class TestAdapterRouter:
    """Test payload routing to correct adapter."""

    @pytest.fixture
    def router(self):
        return AdapterRouter()

    def test_routes_tilt_payload(self, router):
        payload = {"color": "RED", "sg": 1.050, "temp_f": 68.0}
        reading = router.route(payload, source_protocol="ble")

        assert reading is not None
        assert reading.device_type == "tilt"

    def test_routes_ispindel_payload(self, router):
        payload = {"name": "iSpindel", "angle": 25.5, "temperature": 20.0}
        reading = router.route(payload, source_protocol="http")

        assert reading is not None
        assert reading.device_type == "ispindel"

    def test_routes_gravitymon_payload(self, router):
        payload = {
            "name": "GravityMon",
            "angle": 25.5,
            "temperature": 20.0,
            "corr-gravity": 1.048,
        }
        reading = router.route(payload, source_protocol="mqtt")

        assert reading is not None
        assert reading.device_type == "gravitymon"

    def test_gravitymon_takes_precedence_over_ispindel(self, router):
        """GravityMon should be checked before iSpindel due to specificity."""
        payload = {
            "name": "GravityMon",
            "angle": 25.5,
            "temperature": 20.0,
            "gravity": 1.048,
            "run-time": 12345,
        }
        reading = router.route(payload, source_protocol="http")

        # Should be GravityMon, not iSpindel
        assert reading.device_type == "gravitymon"

    def test_unknown_payload_returns_none(self, router):
        payload = {"unknown_field": "value"}
        reading = router.route(payload, source_protocol="http")

        assert reading is None

    def test_empty_payload_returns_none(self, router):
        reading = router.route({}, source_protocol="http")
        assert reading is None
