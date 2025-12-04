"""Mark historical outlier readings as invalid.

This migration finds existing readings with physically impossible values
and marks them as invalid so they're filtered from charts.

Valid ranges:
- SG: 0.500-1.200 (beer is typically 1.000-1.120)
- Temp: 32-212°F (freezing to boiling)
"""

import asyncio
import logging

from sqlalchemy import select

from backend.database import async_session_factory
from backend.models import Reading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def mark_outliers():
    """Mark historical outliers as invalid."""
    async with async_session_factory() as session:
        # Find and mark SG outliers
        sg_result = await session.execute(
            select(Reading).where(
                Reading.status == "valid",
                (Reading.sg_calibrated < 0.500) | (Reading.sg_calibrated > 1.200)
            )
        )
        sg_outliers = sg_result.scalars().all()

        logger.info(f"Found {len(sg_outliers)} SG outliers")

        if sg_outliers:
            for reading in sg_outliers:
                logger.info(
                    f"Marking SG outlier: device={reading.device_id}, "
                    f"timestamp={reading.timestamp}, sg={reading.sg_calibrated:.4f}"
                )
                reading.status = "invalid"

        # Find and mark temperature outliers
        temp_result = await session.execute(
            select(Reading).where(
                Reading.status == "valid",
                (Reading.temp_calibrated < 32.0) | (Reading.temp_calibrated > 212.0)
            )
        )
        temp_outliers = temp_result.scalars().all()

        logger.info(f"Found {len(temp_outliers)} temperature outliers")

        if temp_outliers:
            for reading in temp_outliers:
                logger.info(
                    f"Marking temp outlier: device={reading.device_id}, "
                    f"timestamp={reading.timestamp}, temp={reading.temp_calibrated:.1f}°F"
                )
                reading.status = "invalid"

        await session.commit()

        total = len(sg_outliers) + len(temp_outliers)
        logger.info(f"Marked {total} total outliers as invalid")

        return total


if __name__ == "__main__":
    total = asyncio.run(mark_outliers())
    print(f"\n✅ Migration complete: {total} outliers marked as invalid")
