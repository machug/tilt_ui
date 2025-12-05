"""Test ML schema changes."""
import pytest
from backend.models import Reading
from sqlalchemy import inspect


def test_reading_has_ml_columns():
    """Reading model has ML output columns."""
    inspector = inspect(Reading)
    column_names = [col.name for col in inspector.columns]

    # Kalman filtered values
    assert "sg_filtered" in column_names
    assert "temp_filtered" in column_names

    # Confidence and rates
    assert "confidence" in column_names
    assert "sg_rate" in column_names
    assert "temp_rate" in column_names

    # Anomaly detection
    assert "is_anomaly" in column_names
    assert "anomaly_score" in column_names
    assert "anomaly_reasons" in column_names
