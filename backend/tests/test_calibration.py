"""Tests for calibration service."""

import pytest
from backend.ingest.base import (
    GravityUnit,
    HydrometerReading,
    TemperatureUnit,
)
from backend.services.calibration import CalibrationService
from datetime import datetime, timezone


class TestUnitConversion:
    """Test unit conversion in calibration service."""

    def test_convert_celsius_to_fahrenheit(self):
        service = CalibrationService()
        reading = HydrometerReading(
            device_id="test",
            device_type="ispindel",
            timestamp=datetime.now(timezone.utc),
            temperature_raw=20.0,
            temperature_unit=TemperatureUnit.CELSIUS,
        )

        result = service.convert_units(reading)

        assert result.temperature == pytest.approx(68.0, abs=0.1)

    def test_fahrenheit_unchanged(self):
        service = CalibrationService()
        reading = HydrometerReading(
            device_id="test",
            device_type="tilt",
            timestamp=datetime.now(timezone.utc),
            temperature_raw=68.0,
            temperature_unit=TemperatureUnit.FAHRENHEIT,
        )

        result = service.convert_units(reading)

        assert result.temperature == 68.0

    def test_convert_plato_to_sg(self):
        service = CalibrationService()
        reading = HydrometerReading(
            device_id="test",
            device_type="ispindel",
            timestamp=datetime.now(timezone.utc),
            gravity_raw=12.0,  # ~1.048 SG
            gravity_unit=GravityUnit.PLATO,
        )

        result = service.convert_units(reading)

        assert result.gravity == pytest.approx(1.048, abs=0.002)

    def test_sg_unchanged(self):
        service = CalibrationService()
        reading = HydrometerReading(
            device_id="test",
            device_type="tilt",
            timestamp=datetime.now(timezone.utc),
            gravity_raw=1.050,
            gravity_unit=GravityUnit.SG,
        )

        result = service.convert_units(reading)

        assert result.gravity == 1.050


class TestPolynomialCalibration:
    """Test polynomial calibration for iSpindel-style devices."""

    def test_apply_polynomial_linear(self):
        service = CalibrationService()
        # Simple linear: y = 0.001x + 1.0 (1 degree at x=50 gives SG 1.050)
        coefficients = [0.001, 1.0]

        result = service.apply_polynomial(50.0, coefficients)

        assert result == pytest.approx(1.050, abs=0.001)

    def test_apply_polynomial_quadratic(self):
        service = CalibrationService()
        # Quadratic: typical iSpindel calibration
        coefficients = [0.00001, 0.001, 0.9]

        result = service.apply_polynomial(25.0, coefficients)

        # 0.00001*625 + 0.001*25 + 0.9 = 0.00625 + 0.025 + 0.9 = 0.93125
        assert result == pytest.approx(0.93125, abs=0.0001)

    def test_apply_polynomial_empty_coefficients(self):
        service = CalibrationService()

        result = service.apply_polynomial(25.0, [])

        # No coefficients = no transformation
        assert result == 0.0


class TestLinearCalibrationIngest:
    """Test linear calibration works through calibrate_device_reading."""

    @pytest.mark.asyncio
    async def test_linear_calibration_with_points_key(self):
        """Verify linear calibration uses 'points' key from API."""
        from unittest.mock import MagicMock

        service = CalibrationService()

        # Create a mock device with linear calibration using "points" key
        device = MagicMock()
        device.calibration_type = "linear"
        device.calibration_data = {
            "points": [[1.000, 1.002], [1.050, 1.048]]  # Raw -> Actual
        }

        # Create a reading with raw gravity
        reading = HydrometerReading(
            device_id="test",
            device_type="ispindel",
            timestamp=datetime.now(timezone.utc),
            gravity=1.025,  # Between the two points
        )

        # Apply calibration
        result = await service.calibrate_device_reading(
            db=None,  # Not used for linear calibration
            device=device,
            reading=reading,
        )

        # Linear interpolation: at 1.025, should be between 1.002 and 1.048
        # Slope = (1.048 - 1.002) / (1.050 - 1.000) = 0.046 / 0.050 = 0.92
        # Expected = 1.002 + (1.025 - 1.000) * 0.92 = 1.002 + 0.023 = 1.025
        assert result.gravity == pytest.approx(1.025, abs=0.001)
