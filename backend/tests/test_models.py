"""Tests for paired field in Tilt and Device models."""

import pytest
from sqlalchemy import select
from datetime import datetime, timezone

from backend.models import Tilt, Device, TiltResponse


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
