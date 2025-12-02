import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from backend.main import handle_tilt_reading
from backend.scanner import TiltReading

@pytest.mark.asyncio
async def test_unpaired_tilt_does_not_store_reading():
    """Test that readings from unpaired Tilts are not stored."""
    reading = TiltReading(
        color="RED",
        mac="AA:BB:CC:DD:EE:FF",
        sg=1.050,
        temp_f=68.0,
        rssi=-45,
        timestamp=datetime.now(timezone.utc)
    )

    # Mock database session
    with patch('backend.main.async_session_factory') as mock_factory:
        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__.return_value = mock_session

        # Simulate unpaired tilt
        mock_tilt = MagicMock()
        mock_tilt.paired = False
        mock_tilt.beer_name = "Untitled"
        mock_tilt.original_gravity = None
        mock_session.get.return_value = mock_tilt

        # Mock calibration service and batch linker
        with patch('backend.main.calibration_service.calibrate_reading',
                   return_value=(1.050, 68.0)):
            with patch('backend.main.link_reading_to_batch', return_value=None):
                await handle_tilt_reading(reading)

        # Verify that a Reading object was NOT added to session
        # (Note: The Tilt object itself might be added if it's new, but we check that no Reading was added)
        from backend.models import Reading
        reading_adds = [call for call in mock_session.add.call_args_list
                       if call[0] and isinstance(call[0][0], Reading)]
        assert len(reading_adds) == 0, "Expected no Reading objects to be added for unpaired tilt"

@pytest.mark.asyncio
async def test_paired_tilt_stores_reading():
    """Test that readings from paired Tilts are stored."""
    reading = TiltReading(
        color="BLUE",
        mac="BB:CC:DD:EE:FF:AA",
        sg=1.048,
        temp_f=66.0,
        rssi=-50,
        timestamp=datetime.now(timezone.utc)
    )

    with patch('backend.main.async_session_factory') as mock_factory:
        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__.return_value = mock_session

        # Simulate paired tilt
        mock_tilt = MagicMock()
        mock_tilt.paired = True
        mock_tilt.beer_name = "IPA"
        mock_tilt.original_gravity = 1.055
        mock_session.get.return_value = mock_tilt

        with patch('backend.main.calibration_service.calibrate_reading',
                   return_value=(1.048, 66.0)):
            with patch('backend.main.link_reading_to_batch', return_value=None):
                await handle_tilt_reading(reading)

        # Verify that a Reading object WAS added to session
        from backend.models import Reading
        reading_adds = [call for call in mock_session.add.call_args_list
                       if call[0] and isinstance(call[0][0], Reading)]
        assert len(reading_adds) == 1, "Expected exactly one Reading object to be added for paired tilt"
        assert reading_adds[0][0][0].tilt_id == "BLUE"
