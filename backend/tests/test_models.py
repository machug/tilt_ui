"""Tests for paired field in Tilt and Device models."""

import pytest
from sqlalchemy import select
from datetime import datetime, timezone
import json

from backend.models import Tilt, Device, TiltResponse, serialize_datetime_to_utc, ReadingResponse, BatchResponse


@pytest.mark.asyncio
async def test_tilt_model_has_paired_field(test_db):
    """Test that Tilt model includes paired field with default False."""
    tilt = Tilt(
        id="tilt-red",
        color="RED",
        beer_name="Test Beer"
    )
    test_db.add(tilt)
    await test_db.commit()

    # Verify tilt was created with default paired=False
    result = await test_db.execute(select(Tilt).where(Tilt.id == "tilt-red"))
    saved_tilt = result.scalar_one()
    assert hasattr(saved_tilt, 'paired')
    assert saved_tilt.paired is False


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


def test_tilt_response_includes_paired():
    """Test that TiltResponse schema includes paired field."""
    response = TiltResponse(
        id="tilt-red",
        color="RED",
        beer_name="Test Beer",
        mac="AA:BB:CC:DD:EE:FF",
        original_gravity=1.050,
        last_seen=datetime.now(timezone.utc),
        paired=True
    )
    assert response.paired is True


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


def test_tilt_response_serialization_includes_z_suffix():
    """Test TiltResponse serializes datetimes with Z suffix."""
    response = TiltResponse(
        id="tilt-red",
        color="RED",
        beer_name="Test Beer",
        mac="AA:BB:CC:DD:EE:FF",
        original_gravity=1.050,
        last_seen=datetime(2025, 12, 2, 22, 28, 45, 589178, tzinfo=timezone.utc),
        paired=True,
        paired_at=datetime(2025, 12, 2, 22, 26, 59, 374325, tzinfo=timezone.utc)
    )
    json_data = response.model_dump_json()
    assert '"last_seen":"2025-12-02T22:28:45.589178Z"' in json_data
    assert '"paired_at":"2025-12-02T22:26:59.374325Z"' in json_data


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


def test_tilt_response_with_none_datetimes():
    """Test TiltResponse handles None datetime values correctly."""
    response = TiltResponse(
        id="tilt-red",
        color="RED",
        beer_name="Test Beer",
        mac="AA:BB:CC:DD:EE:FF",
        original_gravity=None,
        last_seen=None,
        paired=False,
        paired_at=None
    )
    json_data = response.model_dump_json()
    parsed = json.loads(json_data)
    assert parsed["last_seen"] is None
    assert parsed["paired_at"] is None
