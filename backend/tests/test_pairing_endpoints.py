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


@pytest.mark.asyncio
async def test_pair_tilt_creates_device_record(client: AsyncClient, test_db: AsyncSession):
    """Test that pairing a Tilt creates a Device record if missing."""
    # Create Tilt without Device record
    tilt = Tilt(id="RED", color="RED", paired=False)
    test_db.add(tilt)
    await test_db.commit()

    # Verify Device doesn't exist yet
    device = await test_db.get(Device, "RED")
    assert device is None

    # Pair the tilt
    response = await client.post("/api/tilts/RED/pair")
    assert response.status_code == 200

    # Verify Device record was created with correct attributes
    device = await test_db.get(Device, "RED")
    assert device is not None
    assert device.paired is True
    assert device.paired_at is not None
    assert device.device_type == "tilt"
    assert device.name == "RED"
    assert device.color == "RED"

    # Verify Tilt was also updated
    await test_db.refresh(tilt)
    assert tilt.paired is True
    assert tilt.paired_at is not None


@pytest.mark.asyncio
async def test_unpair_tilt_creates_device_record(client: AsyncClient, test_db: AsyncSession):
    """Test that unpairing a Tilt creates a Device record if missing."""
    # Create paired Tilt without Device record
    tilt = Tilt(id="BLUE", color="BLUE", paired=True)
    test_db.add(tilt)
    await test_db.commit()

    # Verify Device doesn't exist yet
    device = await test_db.get(Device, "BLUE")
    assert device is None

    # Unpair the tilt
    response = await client.post("/api/tilts/BLUE/unpair")
    assert response.status_code == 200

    # Verify Device record was created with correct attributes
    device = await test_db.get(Device, "BLUE")
    assert device is not None
    assert device.paired is False
    assert device.paired_at is None
    assert device.device_type == "tilt"
    assert device.name == "BLUE"
    assert device.color == "BLUE"

    # Verify Tilt was also updated
    await test_db.refresh(tilt)
    assert tilt.paired is False
    assert tilt.paired_at is None


@pytest.mark.asyncio
async def test_pair_tilt_updates_both_tables(client: AsyncClient, test_db: AsyncSession):
    """Test that pairing updates both Tilt and Device tables."""
    # Create both Tilt and Device records (unpaired)
    tilt = Tilt(id="GREEN", color="GREEN", paired=False)
    device = Device(
        id="GREEN",
        device_type="tilt",
        name="GREEN",
        color="GREEN",
        paired=False
    )
    test_db.add(tilt)
    test_db.add(device)
    await test_db.commit()

    # Pair the tilt
    response = await client.post("/api/tilts/GREEN/pair")
    assert response.status_code == 200

    # Verify both tables were updated
    await test_db.refresh(tilt)
    await test_db.refresh(device)

    assert tilt.paired is True
    assert tilt.paired_at is not None
    assert device.paired is True
    assert device.paired_at is not None

    # Verify timestamps match
    assert tilt.paired_at == device.paired_at


@pytest.mark.asyncio
async def test_unpair_tilt_updates_both_tables(client: AsyncClient, test_db: AsyncSession):
    """Test that unpairing updates both Tilt and Device tables."""
    # Create both Tilt and Device records (paired)
    tilt = Tilt(id="YELLOW", color="YELLOW", paired=True)
    device = Device(
        id="YELLOW",
        device_type="tilt",
        name="YELLOW",
        color="YELLOW",
        paired=True
    )
    test_db.add(tilt)
    test_db.add(device)
    await test_db.commit()

    # Unpair the tilt
    response = await client.post("/api/tilts/YELLOW/unpair")
    assert response.status_code == 200

    # Verify both tables were updated
    await test_db.refresh(tilt)
    await test_db.refresh(device)

    assert tilt.paired is False
    assert tilt.paired_at is None
    assert device.paired is False
    assert device.paired_at is None
