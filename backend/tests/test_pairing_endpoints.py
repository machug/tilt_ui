"""Tests for device pairing/unpairing API endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Device, Batch


@pytest.mark.asyncio
async def test_pair_device_endpoint(client: AsyncClient, test_db: AsyncSession):
    """Test that pairing endpoint sets paired=True."""
    # Create a device
    device = Device(id="tilt-red", device_type="tilt", name="RED", color="RED", paired=False)
    test_db.add(device)
    await test_db.commit()

    # Pair the device
    response = await client.post("/api/devices/tilt-red/pair")
    assert response.status_code == 200
    data = response.json()
    assert data["paired"] is True

    # Verify via GET
    response = await client.get("/api/devices/tilt-red")
    assert response.status_code == 200
    assert response.json()["paired"] is True


@pytest.mark.asyncio
async def test_unpair_device_endpoint(client: AsyncClient, test_db: AsyncSession):
    """Test that unpairing endpoint sets paired=False."""
    # Create a device that is paired
    device = Device(id="tilt-green", device_type="tilt", name="GREEN", color="GREEN", paired=True)
    test_db.add(device)
    await test_db.commit()

    # Unpair the device
    response = await client.post("/api/devices/tilt-green/unpair")
    assert response.status_code == 200
    data = response.json()
    assert data["paired"] is False

    # Verify via GET
    response = await client.get("/api/devices/tilt-green")
    assert response.status_code == 200
    assert response.json()["paired"] is False


@pytest.mark.asyncio
async def test_pair_device_not_found(client: AsyncClient):
    """Test pairing non-existent device returns 404."""
    response = await client.post("/api/devices/nonexistent/pair")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_unpair_device_not_found(client: AsyncClient):
    """Test unpairing non-existent device returns 404."""
    response = await client.post("/api/devices/nonexistent/unpair")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_pair_device_with_active_batch(client: AsyncClient, test_db: AsyncSession):
    """Test pairing a device that is assigned to an active batch."""
    # Create a device
    device = Device(
        id="tilt-orange",
        device_type="tilt",
        name="Orange Tilt",
        color="ORANGE",
        paired=False
    )
    test_db.add(device)

    # Create an active batch assigned to this device
    batch = Batch(
        device_id="tilt-orange",
        status="fermenting",
        name="Test Batch"
    )
    test_db.add(batch)
    await test_db.commit()

    # Should be able to pair the device even with an active batch
    response = await client.post("/api/devices/tilt-orange/pair")
    assert response.status_code == 200
    data = response.json()
    assert data["paired"] is True
    assert data["paired_at"] is not None


@pytest.mark.asyncio
async def test_unpair_device_mid_batch(client: AsyncClient, test_db: AsyncSession):
    """Test unpairing a device that is in the middle of an active batch."""
    # Create a paired device
    device = Device(
        id="tilt-purple",
        device_type="tilt",
        name="Purple Tilt",
        color="PURPLE",
        paired=True
    )
    test_db.add(device)

    # Create an active batch assigned to this device
    batch = Batch(
        device_id="tilt-purple",
        status="fermenting",
        name="Active Fermentation"
    )
    test_db.add(batch)
    await test_db.commit()

    # Should be able to unpair (this will stop readings from being logged)
    response = await client.post("/api/devices/tilt-purple/unpair")
    assert response.status_code == 200
    data = response.json()
    assert data["paired"] is False
    assert data["paired_at"] is None

    # Verify batch is still active (unpairing doesn't affect batch status)
    await test_db.refresh(batch)
    assert batch.status == "fermenting"


