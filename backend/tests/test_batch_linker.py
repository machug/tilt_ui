"""Tests for batch reading linker service."""

import pytest
from datetime import datetime, timezone

from backend.models import Batch, Device, Reading


@pytest.mark.asyncio
async def test_get_active_batch_for_device(test_db):
    """Should find active batch for device."""
    from backend.services.batch_linker import get_active_batch_for_device

    # Create device
    device = Device(id="tilt-red", device_type="tilt", name="Red")
    test_db.add(device)

    # Create active batch
    batch = Batch(
        device_id="tilt-red",
        status="fermenting",
        start_time=datetime.now(timezone.utc),
    )
    test_db.add(batch)
    await test_db.commit()

    # Find active batch
    active_batch = await get_active_batch_for_device(test_db, "tilt-red")

    assert active_batch is not None
    assert active_batch.id == batch.id


@pytest.mark.asyncio
async def test_no_active_batch_for_device(test_db):
    """Should return None when no active batch exists."""
    from backend.services.batch_linker import get_active_batch_for_device

    # Create device with no batches
    device = Device(id="tilt-blue", device_type="tilt", name="Blue")
    test_db.add(device)
    await test_db.commit()

    # Should return None
    active_batch = await get_active_batch_for_device(test_db, "tilt-blue")

    assert active_batch is None
