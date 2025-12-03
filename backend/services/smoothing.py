"""Smoothing service for sensor readings using moving average."""

from collections import deque
import time
from typing import Dict, Tuple

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Reading


class SmoothingService:
    """Apply moving average smoothing to sensor readings."""

    def __init__(self):
        # In-memory buffer of recent readings per device
        # Format: {device_id: deque([(sg, temp), ...], maxlen=N)}
        self._buffers: Dict[str, deque] = {}
        # Track last access time for each buffer to enable cleanup
        # Format: {device_id: timestamp}
        self._buffer_access_times: Dict[str, float] = {}

    async def smooth_reading(
        self,
        session: AsyncSession,
        device_id: str,
        sg: float,
        temp: float,
        window_size: int,
    ) -> Tuple[float, float]:
        """Apply moving average smoothing to a reading.

        Args:
            session: Database session to fetch recent readings if needed
            device_id: Device identifier
            sg: Current specific gravity reading
            temp: Current temperature reading
            window_size: Number of samples to average (including current)

        Returns:
            Tuple of (smoothed_sg, smoothed_temp)
        """
        if window_size <= 1:
            # No smoothing needed
            return sg, temp

        # Initialize buffer for this device if needed
        if device_id not in self._buffers:
            # Fetch recent valid readings to populate buffer
            result = await session.execute(
                select(Reading.sg_calibrated, Reading.temp_calibrated)
                .where(
                    Reading.device_id == device_id,
                    Reading.status == "valid",
                )
                .order_by(desc(Reading.timestamp))
                .limit(window_size - 1)
            )
            recent = result.all()

            # Create buffer with maxlen (will auto-evict oldest)
            self._buffers[device_id] = deque(maxlen=window_size)

            # Add recent readings in chronological order (oldest first)
            for row in reversed(recent):
                if row.sg_calibrated is not None and row.temp_calibrated is not None:
                    self._buffers[device_id].append((row.sg_calibrated, row.temp_calibrated))

        # Add current reading to buffer
        self._buffers[device_id].append((sg, temp))
        # Update last access time
        self._buffer_access_times[device_id] = time.monotonic()

        # Calculate moving average
        buffer = self._buffers[device_id]
        if len(buffer) == 0:
            return sg, temp

        avg_sg = sum(reading[0] for reading in buffer) / len(buffer)
        avg_temp = sum(reading[1] for reading in buffer) / len(buffer)

        return avg_sg, avg_temp

    def clear_buffer(self, device_id: str):
        """Clear the smoothing buffer for a device.

        Call this when:
        - A device is unpaired
        - A batch is completed
        - Smoothing config is changed
        """
        if device_id in self._buffers:
            del self._buffers[device_id]
        if device_id in self._buffer_access_times:
            del self._buffer_access_times[device_id]

    def cleanup_inactive_buffers(self, max_age_seconds: int = 3600):
        """Remove buffers for devices that haven't been used recently.

        Args:
            max_age_seconds: Maximum age in seconds before a buffer is considered stale (default: 1 hour)

        This prevents memory growth from inactive/deleted devices.
        Call this periodically (e.g., from a background task or on app startup).
        """
        now = time.monotonic()
        inactive_devices = [
            device_id
            for device_id, last_access in self._buffer_access_times.items()
            if now - last_access > max_age_seconds
        ]

        for device_id in inactive_devices:
            del self._buffers[device_id]
            del self._buffer_access_times[device_id]

        if inactive_devices:
            import logging
            logging.info(f"Cleaned up {len(inactive_devices)} inactive smoothing buffers")


# Global singleton instance
smoothing_service = SmoothingService()
