"""Data cleanup service for managing database retention.

Removes old readings based on configurable retention period.
Default: 30 days for normal readings.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select

from .database import async_session_factory
from .models import Reading, serialize_datetime_to_utc

logger = logging.getLogger(__name__)


async def cleanup_old_readings(retention_days: int = 30) -> int:
    """Delete readings older than retention_days.

    Returns the number of deleted rows.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    async with async_session_factory() as session:
        # Get count first for logging
        count_result = await session.execute(
            select(func.count()).select_from(Reading).where(Reading.timestamp < cutoff)
        )
        count = count_result.scalar() or 0

        if count > 0:
            await session.execute(
                delete(Reading).where(Reading.timestamp < cutoff)
            )
            await session.commit()
            logger.info("Deleted %d readings older than %d days", count, retention_days)

        return count


async def get_reading_stats() -> dict:
    """Get statistics about stored readings."""
    async with async_session_factory() as session:
        # Total count
        total_result = await session.execute(
            select(func.count()).select_from(Reading)
        )
        total = total_result.scalar() or 0

        # Oldest reading
        oldest_result = await session.execute(
            select(func.min(Reading.timestamp))
        )
        oldest = oldest_result.scalar()

        # Newest reading
        newest_result = await session.execute(
            select(func.max(Reading.timestamp))
        )
        newest = newest_result.scalar()

        return {
            "total_readings": total,
            "oldest_reading": serialize_datetime_to_utc(oldest) if oldest else None,
            "newest_reading": serialize_datetime_to_utc(newest) if newest else None,
        }


class CleanupService:
    """Background service that periodically cleans up old data."""

    def __init__(self, retention_days: int = 30, interval_hours: int = 1):
        self.retention_days = retention_days
        self.interval_seconds = interval_hours * 3600
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self):
        """Start the cleanup service."""
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info(
            "Cleanup service started (retention: %d days, interval: %dh)",
            self.retention_days,
            self.interval_seconds // 3600,
        )

    async def stop(self):
        """Stop the cleanup service."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Cleanup service stopped")

    async def _run(self):
        """Main loop that runs cleanup periodically."""
        # Run initial cleanup after a short delay
        await asyncio.sleep(60)  # Wait 1 minute after startup

        while self._running:
            try:
                await cleanup_old_readings(self.retention_days)
            except Exception as e:
                logger.exception("Cleanup error: %s", e)

            await asyncio.sleep(self.interval_seconds)
