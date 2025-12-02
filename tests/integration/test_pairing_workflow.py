import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.database import init_db, async_session_factory
from backend.models import Tilt, Reading
from sqlalchemy import select, func

@pytest.mark.asyncio
async def test_full_pairing_workflow():
    """Test complete pairing workflow from detection to reading storage."""

    # Initialize test database
    await init_db()

    # Clean up any existing GREEN tilt from previous test runs
    async with async_session_factory() as session:
        existing_tilt = await session.get(Tilt, "GREEN")
        if existing_tilt:
            await session.delete(existing_tilt)
        # Also clean up any readings
        result = await session.execute(
            select(Reading).where(Reading.tilt_id == "GREEN")
        )
        for reading in result.scalars():
            await session.delete(reading)
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Step 1: Simulate device detection (unpaired by default)
        async with async_session_factory() as session:
            tilt = Tilt(
                id="GREEN",
                color="GREEN",
                beer_name="Untitled",
                paired=False
            )
            session.add(tilt)
            await session.commit()

        # Step 2: Verify device appears in list as unpaired
        response = await client.get("/api/tilts")
        assert response.status_code == 200
        tilts = response.json()
        green_tilt = next(t for t in tilts if t["id"] == "GREEN")
        assert green_tilt["paired"] is False

        # Step 3: Simulate reading - should NOT be stored
        from backend.scanner import TiltReading
        from backend.main import handle_tilt_reading
        from datetime import datetime, timezone

        reading = TiltReading(
            color="GREEN",
            mac="AA:BB:CC:DD:EE:FF",
            sg=1.050,
            temp_f=68.0,
            rssi=-45,
            timestamp=datetime.now(timezone.utc)
        )

        await handle_tilt_reading(reading)

        # Verify no reading was stored
        async with async_session_factory() as session:
            result = await session.execute(
                select(func.count()).select_from(Reading).where(Reading.tilt_id == "GREEN")
            )
            count = result.scalar()
            assert count == 0, "Reading should not be stored for unpaired device"

        # Step 4: Pair the device
        response = await client.post("/api/tilts/GREEN/pair")
        assert response.status_code == 200
        data = response.json()
        assert data["paired"] is True

        # Step 5: Simulate another reading - should BE stored
        reading2 = TiltReading(
            color="GREEN",
            mac="AA:BB:CC:DD:EE:FF",
            sg=1.048,
            temp_f=67.0,
            rssi=-47,
            timestamp=datetime.now(timezone.utc)
        )

        await handle_tilt_reading(reading2)

        # Verify reading WAS stored
        async with async_session_factory() as session:
            result = await session.execute(
                select(func.count()).select_from(Reading).where(Reading.tilt_id == "GREEN")
            )
            count = result.scalar()
            assert count == 1, "Reading should be stored for paired device"

        # Step 6: Unpair the device
        response = await client.post("/api/tilts/GREEN/unpair")
        assert response.status_code == 200
        data = response.json()
        assert data["paired"] is False

        # Step 7: Simulate third reading - should NOT be stored
        reading3 = TiltReading(
            color="GREEN",
            mac="AA:BB:CC:DD:EE:FF",
            sg=1.046,
            temp_f=66.0,
            rssi=-48,
            timestamp=datetime.now(timezone.utc)
        )

        await handle_tilt_reading(reading3)

        # Verify reading count unchanged (still 1)
        async with async_session_factory() as session:
            result = await session.execute(
                select(func.count()).select_from(Reading).where(Reading.tilt_id == "GREEN")
            )
            count = result.scalar()
            assert count == 1, "No additional reading should be stored after unpairing"
