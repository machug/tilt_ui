"""Unit conversion utilities for hydrometer readings."""

from typing import Optional


def plato_to_sg(plato: float) -> float:
    """Convert degrees Plato to specific gravity.

    Formula: SG = 1 + (plato / (258.6 - (plato/258.2) * 227.1))
    """
    if plato == 0:
        return 1.0
    return 1 + (plato / (258.6 - (plato / 258.2) * 227.1))


def sg_to_plato(sg: float) -> float:
    """Convert specific gravity to degrees Plato.

    Approximation: P = -616.868 + 1111.14*SG - 630.272*SG^2 + 135.997*SG^3
    """
    return -616.868 + 1111.14 * sg - 630.272 * sg**2 + 135.997 * sg**3


def sg_to_brix(sg: float) -> float:
    """Convert specific gravity to degrees Brix.

    For wort/beer fermentation, Brix is approximately equal to Plato.
    The difference between Brix and Plato is negligible for brewing purposes.
    """
    return sg_to_plato(sg)


def celsius_to_fahrenheit(c: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return (c * 9 / 5) + 32


def fahrenheit_to_celsius(f: float) -> float:
    """Convert Fahrenheit to Celsius."""
    return (f - 32) * 5 / 9


# Device-specific battery voltage ranges
BATTERY_RANGES: dict[str, tuple[float, float]] = {
    "ispindel": (3.0, 4.2),   # LiPo
    "floaty": (3.0, 4.2),     # LiPo
    "gravitymon": (3.0, 4.2), # LiPo
    "tilt": (2.0, 3.0),       # CR123A
}


def normalize_battery(
    value: float,
    device_type: str,
    is_percent: bool = False
) -> tuple[Optional[float], Optional[int]]:
    """Normalize battery to (voltage, percent).

    Args:
        value: Battery reading (voltage or percent)
        device_type: Device type for voltage range lookup
        is_percent: True if value is percentage, False if voltage

    Returns:
        Tuple of (voltage, percent)
    """
    vmin, vmax = BATTERY_RANGES.get(device_type, (3.0, 4.2))

    if is_percent:
        percent = int(max(0, min(100, value)))
        voltage = vmin + (vmax - vmin) * (percent / 100)
        return voltage, percent
    else:
        voltage = value
        percent = int(max(0, min(100, (voltage - vmin) / (vmax - vmin) * 100)))
        return voltage, percent
