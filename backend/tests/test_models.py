"""Tests for Device model and datetime serialization."""

import pytest
from sqlalchemy import select
from datetime import datetime, timezone
import json

from backend.models import Device, serialize_datetime_to_utc, ReadingResponse, BatchResponse


@pytest.mark.asyncio
async def test_device_model_has_paired_field(test_db):
    """Test that Device model includes paired field with default False."""
    device = Device(
        id="tilt-blue",
        device_type="tilt",
        name="Blue Tilt"
    )
    test_db.add(device)
    await test_db.commit()

    # Verify device was created with default paired=False
    result = await test_db.execute(select(Device).where(Device.id == "tilt-blue"))
    saved_device = result.scalar_one()
    assert hasattr(saved_device, 'paired')
    assert saved_device.paired is False


# Datetime serialization tests
def test_serialize_datetime_to_utc_with_naive_datetime():
    """Test serialization of naive datetime assumes UTC."""
    dt = datetime(2025, 12, 2, 22, 28, 45, 589178)
    result = serialize_datetime_to_utc(dt)
    assert result == "2025-12-02T22:28:45.589178Z"


def test_serialize_datetime_to_utc_with_utc_aware():
    """Test serialization of UTC-aware datetime."""
    dt = datetime(2025, 12, 2, 22, 28, 45, 589178, tzinfo=timezone.utc)
    result = serialize_datetime_to_utc(dt)
    assert result == "2025-12-02T22:28:45.589178Z"


def test_serialize_datetime_to_utc_handles_none():
    """Test serialization handles None gracefully."""
    assert serialize_datetime_to_utc(None) is None


def test_serialize_datetime_to_utc_with_zero_microseconds():
    """Test serialization includes .000000 for datetimes without microseconds."""
    dt = datetime(2025, 12, 2, 22, 28, 45, tzinfo=timezone.utc)
    result = serialize_datetime_to_utc(dt)
    assert result == "2025-12-02T22:28:45.000000Z"




def test_reading_response_serialization_includes_z_suffix():
    """Test ReadingResponse serializes timestamp with Z suffix."""
    response = ReadingResponse(
        id=1,
        timestamp=datetime(2025, 12, 2, 22, 28, 45, 589178, tzinfo=timezone.utc),
        sg_raw=1.050,
        sg_calibrated=1.051,
        temp_raw=68.0,
        temp_calibrated=68.5,
        rssi=-75,
        status="valid"
    )
    json_data = response.model_dump_json()
    assert '"timestamp":"2025-12-02T22:28:45.589178Z"' in json_data


def test_batch_response_serialization_includes_z_suffix():
    """Test BatchResponse serializes multiple datetime fields with Z suffix."""
    response = BatchResponse(
        id=1,
        status="fermenting",
        brew_date=datetime(2025, 12, 1, 10, 0, 0, tzinfo=timezone.utc),
        start_time=datetime(2025, 12, 1, 12, 0, 0, tzinfo=timezone.utc),
        created_at=datetime(2025, 12, 1, 9, 0, 0, tzinfo=timezone.utc)
    )
    json_data = response.model_dump_json()
    assert '"brew_date":"2025-12-01T10:00:00.000000Z"' in json_data
    assert '"start_time":"2025-12-01T12:00:00.000000Z"' in json_data
    assert '"created_at":"2025-12-01T09:00:00.000000Z"' in json_data


