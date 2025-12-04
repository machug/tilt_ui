"""Shared test fixtures for Tilt UI tests."""

import pytest
from datetime import datetime, timezone


@pytest.fixture
def sample_readings():
    """Generate sample Tilt readings with realistic noise."""
    return [
        {"sg": 1.050, "temp": 68.0, "rssi": -60, "dt_hours": 0.0},
        {"sg": 1.049, "temp": 68.2, "rssi": -55, "dt_hours": 1.0},
        {"sg": 1.048, "temp": 68.1, "rssi": -70, "dt_hours": 2.0},
        {"sg": 1.055, "temp": 67.8, "rssi": -85, "dt_hours": 3.0},  # Anomaly - SG jump
        {"sg": 1.046, "temp": 68.0, "rssi": -58, "dt_hours": 4.0},
        {"sg": 1.045, "temp": 68.3, "rssi": -62, "dt_hours": 5.0},
    ]


@pytest.fixture
def fermentation_data():
    """Generate realistic 7-day fermentation curve data."""
    import numpy as np

    # Exponential decay: SG(t) = FG + (OG - FG) * exp(-k * t)
    og = 1.055
    fg = 1.012
    k = 0.02  # decay rate

    hours = np.arange(0, 168, 4)  # Every 4 hours for 7 days
    sg_clean = fg + (og - fg) * np.exp(-k * hours)

    # Add realistic noise
    np.random.seed(42)
    noise = np.random.normal(0, 0.001, len(hours))
    sg_noisy = sg_clean + noise

    return {
        "hours": hours.tolist(),
        "sg": sg_noisy.tolist(),
        "og": og,
        "fg": fg,
        "k": k,
    }
