"""Calibration service for applying SG and temperature corrections.

Uses linear interpolation between calibration points. With a single point,
applies a simple offset. With multiple points, interpolates or extrapolates
linearly based on the closest points.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import CalibrationPoint


def linear_interpolate(x: float, points: list[tuple[float, float]]) -> float:
    """Apply linear interpolation/extrapolation to calibrate a value.

    Args:
        x: The raw value to calibrate
        points: List of (raw_value, actual_value) calibration points

    Returns:
        The calibrated value

    Algorithm:
        - 0 points: return x unchanged
        - 1 point: apply offset (actual - raw) to x
        - 2+ points: find the two closest points bracketing x (or the two
          closest on one side for extrapolation) and interpolate linearly
    """
    if not points:
        return x

    # Sort points by raw value
    points = sorted(points, key=lambda p: p[0])

    if len(points) == 1:
        # Single point: apply offset
        raw, actual = points[0]
        offset = actual - raw
        return x + offset

    # Find bracketing points for interpolation
    # or edge points for extrapolation
    lower = None
    upper = None

    for raw, actual in points:
        if raw <= x:
            lower = (raw, actual)
        if raw >= x and upper is None:
            upper = (raw, actual)

    # Handle extrapolation cases
    if lower is None:
        # x is below all points, extrapolate from first two
        lower = points[0]
        upper = points[1]
    elif upper is None:
        # x is above all points, extrapolate from last two
        lower = points[-2]
        upper = points[-1]

    # Linear interpolation: y = y1 + (x - x1) * (y2 - y1) / (x2 - x1)
    x1, y1 = lower
    x2, y2 = upper

    if x2 == x1:
        # Avoid division by zero if points have same raw value
        return y1

    slope = (y2 - y1) / (x2 - x1)
    return y1 + (x - x1) * slope


class CalibrationService:
    """Service for calibrating Tilt readings."""

    def __init__(self):
        # Cache calibration points per tilt_id
        # Format: {tilt_id: {"sg": [(raw, actual), ...], "temp": [(raw, actual), ...]}}
        self._cache: dict[str, dict[str, list[tuple[float, float]]]] = {}

    async def load_calibration(self, db: AsyncSession, tilt_id: str) -> None:
        """Load calibration points for a Tilt from the database into cache."""
        result = await db.execute(
            select(CalibrationPoint).where(CalibrationPoint.tilt_id == tilt_id)
        )
        points = result.scalars().all()

        self._cache[tilt_id] = {"sg": [], "temp": []}
        for point in points:
            self._cache[tilt_id][point.type].append((point.raw_value, point.actual_value))

    def invalidate_cache(self, tilt_id: Optional[str] = None) -> None:
        """Invalidate cached calibration points.

        Args:
            tilt_id: If provided, only invalidate that Tilt's cache.
                    If None, clear entire cache.
        """
        if tilt_id:
            self._cache.pop(tilt_id, None)
        else:
            self._cache.clear()

    async def calibrate_sg(
        self, db: AsyncSession, tilt_id: str, raw_sg: float
    ) -> float:
        """Apply SG calibration to a raw reading.

        Args:
            db: Database session
            tilt_id: The Tilt identifier
            raw_sg: Raw specific gravity reading

        Returns:
            Calibrated specific gravity
        """
        if tilt_id not in self._cache:
            await self.load_calibration(db, tilt_id)

        points = self._cache.get(tilt_id, {}).get("sg", [])
        return linear_interpolate(raw_sg, points)

    async def calibrate_temp(
        self, db: AsyncSession, tilt_id: str, raw_temp: float
    ) -> float:
        """Apply temperature calibration to a raw reading.

        Args:
            db: Database session
            tilt_id: The Tilt identifier
            raw_temp: Raw temperature reading (in Fahrenheit)

        Returns:
            Calibrated temperature (in Fahrenheit)
        """
        if tilt_id not in self._cache:
            await self.load_calibration(db, tilt_id)

        points = self._cache.get(tilt_id, {}).get("temp", [])
        return linear_interpolate(raw_temp, points)

    async def calibrate_reading(
        self, db: AsyncSession, tilt_id: str, raw_sg: float, raw_temp: float
    ) -> tuple[float, float]:
        """Calibrate both SG and temperature for a reading.

        Args:
            db: Database session
            tilt_id: The Tilt identifier
            raw_sg: Raw specific gravity
            raw_temp: Raw temperature (Fahrenheit)

        Returns:
            Tuple of (calibrated_sg, calibrated_temp)
        """
        cal_sg = await self.calibrate_sg(db, tilt_id, raw_sg)
        cal_temp = await self.calibrate_temp(db, tilt_id, raw_temp)
        return cal_sg, cal_temp


# Global calibration service instance
calibration_service = CalibrationService()
