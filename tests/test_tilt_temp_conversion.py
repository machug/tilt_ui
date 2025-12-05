"""Test Tilt temperature conversion at boundary."""
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch
from backend.main import handle_tilt_reading
from backend.scanner import TiltReading


@pytest.mark.asyncio
@patch('backend.main.link_reading_to_batch', new_callable=AsyncMock)
@patch('backend.main.manager')
@patch('backend.main.calibration_service')
async def test_tilt_reading_converts_fahrenheit_to_celsius(mock_calib, mock_ws, mock_link):
    """Tilt readings convert F→C immediately."""
    # Mock calibration to pass through
    mock_calib.calibrate_reading = AsyncMock(return_value=(1.050, 20.0))

    # Mock manager.broadcast to be async
    mock_ws.broadcast = AsyncMock()

    # Mock link_reading_to_batch
    mock_link.return_value = None

    # Tilt reading in Fahrenheit
    reading = TiltReading(
        color="RED",
        mac="AA:BB:CC:DD:EE:FF",
        temp_f=68.0,  # 68°F = 20°C
        sg=1.050,
        rssi=-60,
        timestamp=datetime.now(timezone.utc)
    )

    await handle_tilt_reading(reading)

    # Verify calibration was called with Celsius
    args = mock_calib.calibrate_reading.call_args[0]
    temp_c = args[3]  # Fourth argument is temperature

    # 68°F should be 20°C
    assert abs(temp_c - 20.0) < 0.1, f"Expected 20°C, got {temp_c}"
