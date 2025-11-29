"""Tests for unit conversion utilities."""

import pytest
from backend.ingest.units import (
    celsius_to_fahrenheit,
    fahrenheit_to_celsius,
    normalize_battery,
    plato_to_sg,
    sg_to_plato,
)


class TestTemperatureConversion:
    """Test temperature unit conversion."""

    def test_celsius_to_fahrenheit_freezing(self):
        assert celsius_to_fahrenheit(0) == 32

    def test_celsius_to_fahrenheit_boiling(self):
        assert celsius_to_fahrenheit(100) == 212

    def test_celsius_to_fahrenheit_fermentation(self):
        # 20C is typical ale fermentation temp
        result = celsius_to_fahrenheit(20)
        assert result == pytest.approx(68, abs=0.1)

    def test_fahrenheit_to_celsius_freezing(self):
        assert fahrenheit_to_celsius(32) == 0

    def test_fahrenheit_to_celsius_boiling(self):
        assert fahrenheit_to_celsius(212) == 100

    def test_roundtrip_conversion(self):
        original = 18.5
        converted = fahrenheit_to_celsius(celsius_to_fahrenheit(original))
        assert converted == pytest.approx(original, abs=0.001)


class TestGravityConversion:
    """Test gravity unit conversion."""

    def test_plato_to_sg_zero(self):
        assert plato_to_sg(0) == 1.0

    def test_plato_to_sg_typical_wort(self):
        # 12 Plato ~ 1.048 SG
        result = plato_to_sg(12)
        assert result == pytest.approx(1.048, abs=0.002)

    def test_plato_to_sg_high_gravity(self):
        # 20 Plato ~ 1.083 SG
        result = plato_to_sg(20)
        assert result == pytest.approx(1.083, abs=0.002)

    def test_sg_to_plato_water(self):
        result = sg_to_plato(1.0)
        assert result == pytest.approx(0, abs=0.5)

    def test_sg_to_plato_typical_wort(self):
        # 1.050 SG ~ 12.4 Plato
        result = sg_to_plato(1.050)
        assert result == pytest.approx(12.4, abs=0.5)

    def test_roundtrip_gravity(self):
        original = 15.0  # Plato
        sg = plato_to_sg(original)
        back = sg_to_plato(sg)
        assert back == pytest.approx(original, abs=0.1)


class TestBatteryNormalization:
    """Test battery voltage/percent normalization."""

    def test_ispindel_full_battery(self):
        voltage, percent = normalize_battery(4.2, "ispindel", is_percent=False)
        assert voltage == 4.2
        assert percent == 100

    def test_ispindel_empty_battery(self):
        voltage, percent = normalize_battery(3.0, "ispindel", is_percent=False)
        assert voltage == 3.0
        assert percent == 0

    def test_ispindel_half_battery(self):
        voltage, percent = normalize_battery(3.6, "ispindel", is_percent=False)
        assert voltage == 3.6
        assert percent == 50

    def test_tilt_battery_range(self):
        # Tilt uses CR123A: 2.0-3.0V
        voltage, percent = normalize_battery(2.5, "tilt", is_percent=False)
        assert voltage == 2.5
        assert percent == 50

    def test_percent_to_voltage(self):
        voltage, percent = normalize_battery(50, "ispindel", is_percent=True)
        assert percent == 50
        assert voltage == pytest.approx(3.6, abs=0.01)

    def test_clamp_percent_over_100(self):
        voltage, percent = normalize_battery(150, "ispindel", is_percent=True)
        assert percent == 100

    def test_clamp_percent_below_0(self):
        voltage, percent = normalize_battery(-10, "ispindel", is_percent=True)
        assert percent == 0

    def test_unknown_device_uses_default_range(self):
        voltage, percent = normalize_battery(3.6, "unknown_device", is_percent=False)
        # Default range is 3.0-4.2V
        assert percent == 50
