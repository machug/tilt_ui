"""Tests for ML configuration."""

import pytest
from backend.ml.config import MLConfig


def test_default_config():
    """ML config has sensible defaults."""
    config = MLConfig()

    assert config.enable_kalman_filter is True
    assert config.enable_anomaly_detection is True
    assert config.enable_predictions is True
    assert config.enable_mpc is False  # Opt-in, requires HA setup
    assert config.enable_slm is False  # Opt-in, requires model download


def test_config_from_env(monkeypatch):
    """ML config can be overridden via environment."""
    monkeypatch.setenv("TILT_ML_ENABLE_KALMAN_FILTER", "false")
    monkeypatch.setenv("TILT_ML_ENABLE_SLM", "true")

    config = MLConfig()

    assert config.enable_kalman_filter is False
    assert config.enable_slm is True
