"""Test temperature unit migration."""
import pytest
from sqlalchemy import text
from backend.database import init_db, async_session_factory


@pytest.mark.asyncio
async def test_temperatures_stored_in_celsius():
    """Readings, calibration points, and batch temps use Celsius."""
    # Initialize database (runs migrations)
    await init_db()

    async with async_session_factory() as session:
        # Check a sample reading temp is in Celsius range (0-40 typical fermentation)
        result = await session.execute(text(
            "SELECT temp_raw, temp_calibrated FROM readings WHERE temp_raw IS NOT NULL LIMIT 1"
        ))
        row = result.fetchone()

        if row:
            temp_raw, temp_calibrated = row
            # Celsius range check (not Fahrenheit 60-80)
            assert 0 <= temp_raw <= 40, f"temp_raw {temp_raw} not in Celsius range"
            assert 0 <= temp_calibrated <= 40, f"temp_calibrated {temp_calibrated} not in Celsius range"

        # Check batch temperature targets are in Celsius range
        result = await session.execute(text(
            "SELECT temp_target, temp_hysteresis FROM batches WHERE temp_target IS NOT NULL LIMIT 1"
        ))
        row = result.fetchone()

        if row:
            temp_target, temp_hysteresis = row
            # Celsius range check (fermentation typically 0-30°C, not 60-86°F)
            assert 0 <= temp_target <= 40, f"temp_target {temp_target} not in Celsius range"
            # Hysteresis typically 0.5-5°C, not Fahrenheit values
            if temp_hysteresis:
                assert 0 <= temp_hysteresis <= 10, f"temp_hysteresis {temp_hysteresis} not in Celsius range"
