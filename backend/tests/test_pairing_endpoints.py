"""Tests for Tilt pairing/unpairing API endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Tilt, Device, Batch


@pytest.mark.asyncio
async def test_pair_tilt_endpoint(client: AsyncClient, test_db: AsyncSession):
    """Test that pairing endpoint sets paired=True."""
    # Create a tilt
    tilt = Tilt(id="tilt-red", color="RED", beer_name="Test Beer", paired=False)
    test_db.add(tilt)
    await test_db.commit()

    # Pair the tilt
    response = await client.post("/api/tilts/tilt-red/pair")
    assert response.status_code == 200
    data = response.json()
    assert data["paired"] is True

    # Verify via GET
    response = await client.get("/api/tilts/tilt-red")
    assert response.status_code == 200
    assert response.json()["paired"] is True


@pytest.mark.asyncio
async def test_unpair_tilt_endpoint(client: AsyncClient, test_db: AsyncSession):
    """Test that unpairing endpoint sets paired=False."""
    # Create a tilt that is paired
    tilt = Tilt(id="tilt-green", color="GREEN", beer_name="Test Beer", paired=True)
    test_db.add(tilt)
    await test_db.commit()

    # Unpair the tilt
    response = await client.post("/api/tilts/tilt-green/unpair")
    assert response.status_code == 200
    data = response.json()
    assert data["paired"] is False

    # Verify via GET
    response = await client.get("/api/tilts/tilt-green")
    assert response.status_code == 200
    assert response.json()["paired"] is False


@pytest.mark.asyncio
async def test_pair_tilt_not_found(client: AsyncClient):
    """Test pairing non-existent tilt returns 404."""
    response = await client.post("/api/tilts/nonexistent/pair")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_unpair_tilt_not_found(client: AsyncClient):
    """Test unpairing non-existent tilt returns 404."""
    response = await client.post("/api/tilts/nonexistent/unpair")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_pair_tilt_with_active_batch(client: AsyncClient, test_db: AsyncSession):
    """Test pairing a tilt that is assigned to an active batch."""
    # Create a tilt
    tilt = Tilt(
        id="tilt-orange",
        color="ORANGE",
        beer_name="Test Beer",
        paired=False
    )
    test_db.add(tilt)

    # Create a device for this tilt
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

    # Should be able to pair the tilt even with an active batch
    response = await client.post("/api/tilts/tilt-orange/pair")
    assert response.status_code == 200
    data = response.json()
    assert data["paired"] is True
    assert data["paired_at"] is not None


@pytest.mark.asyncio
async def test_unpair_tilt_mid_batch(client: AsyncClient, test_db: AsyncSession):
    """Test unpairing a tilt that is in the middle of an active batch."""
    # Create a paired tilt
    tilt = Tilt(
        id="tilt-purple",
        color="PURPLE",
        beer_name="Test Beer",
        paired=True
    )
    test_db.add(tilt)

    # Create a device for this tilt
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
    response = await client.post("/api/tilts/tilt-purple/unpair")
    assert response.status_code == 200
    data = response.json()
    assert data["paired"] is False
    assert data["paired_at"] is None

    # Verify batch is still active (unpairing doesn't affect batch status)
    await test_db.refresh(batch)
    assert batch.status == "fermenting"
