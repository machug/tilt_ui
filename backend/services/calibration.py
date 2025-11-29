"""Calibration service for applying SG and temperature corrections.

Uses linear interpolation between calibration points. With a single point,
applies a simple offset. With multiple points, interpolates or extrapolates
linearly based on the closest points.

Supports multiple calibration types:
- offset: Simple additive offset (sg_offset, temp_offset)
- polynomial: Polynomial calibration from angle (iSpindel style)
- linear: Linear interpolation between multiple points (legacy Tilt)
- none: No calibration applied
"""

from typing import Any, Optional, TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import CalibrationPoint, Device

if TYPE_CHECKING:
    from ..ingest.base import HydrometerReading


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

    def convert_units(self, reading: "HydrometerReading") -> "HydrometerReading":
        """Convert raw values to standard units (SG, Fahrenheit).

        Args:
            reading: HydrometerReading with raw values

        Returns:
            Reading with gravity/temperature filled from unit conversion
        """
        from ..ingest.base import GravityUnit, TemperatureUnit
        from ..ingest.units import celsius_to_fahrenheit, plato_to_sg

        # Temperature: Convert to Fahrenheit if Celsius
        if reading.temperature_raw is not None:
            if reading.temperature_unit == TemperatureUnit.CELSIUS:
                reading.temperature = celsius_to_fahrenheit(reading.temperature_raw)
            else:
                reading.temperature = reading.temperature_raw

        # Gravity: Convert to SG if Plato
        if reading.gravity_raw is not None:
            if reading.gravity_unit == GravityUnit.PLATO:
                reading.gravity = plato_to_sg(reading.gravity_raw)
            else:
                reading.gravity = reading.gravity_raw

        return reading

    def apply_polynomial(self, angle: float, coefficients: list[float]) -> float:
        """Apply polynomial calibration: SG = a*x^n + b*x^(n-1) + ... + c

        Args:
            angle: Tilt angle in degrees
            coefficients: Polynomial coefficients [a, b, c, ...] highest degree first

        Returns:
            Calculated specific gravity
        """
        if not coefficients:
            return 0.0

        result = 0.0
        degree = len(coefficients) - 1
        for i, coef in enumerate(coefficients):
            power = degree - i
            result += coef * (angle ** power)

        return result

    async def calibrate_device_reading(
        self,
        db: AsyncSession,
        device: Device,
        reading: "HydrometerReading",
    ) -> "HydrometerReading":
        """Apply device-specific calibration to a reading.

        This is the universal calibration entry point that handles all device types
        and calibration methods.

        Args:
            db: Database session
            device: Device model with calibration_type and calibration_data
            reading: HydrometerReading with raw values (already unit-converted)

        Returns:
            Reading with calibrated gravity and temperature values
        """
        calibration_type = device.calibration_type or "none"
        calibration_data = device.calibration_data or {}

        # Apply gravity calibration based on type
        if reading.gravity is not None:
            if calibration_type == "offset":
                sg_offset = calibration_data.get("sg_offset", 0.0)
                reading.gravity = reading.gravity + sg_offset

            elif calibration_type == "polynomial":
                # iSpindel-style polynomial from angle
                if reading.angle is not None:
                    coefficients = calibration_data.get("coefficients", [])
                    if coefficients:
                        reading.gravity = self.apply_polynomial(reading.angle, coefficients)

            elif calibration_type == "linear":
                # Linear interpolation between points
                # API stores as "points", also support legacy "sg_points"
                sg_points = calibration_data.get("points") or calibration_data.get("sg_points", [])
                if sg_points:
                    points = [(p[0], p[1]) for p in sg_points]
                    reading.gravity = linear_interpolate(reading.gravity, points)

        # Apply temperature calibration (offset or linear for all types)
        if reading.temperature is not None:
            if calibration_type in ("offset", "polynomial"):
                temp_offset = calibration_data.get("temp_offset", 0.0)
                reading.temperature = reading.temperature + temp_offset

            elif calibration_type == "linear":
                temp_points = calibration_data.get("temp_points", [])
                if temp_points:
                    points = [(p[0], p[1]) for p in temp_points]
                    reading.temperature = linear_interpolate(reading.temperature, points)

        return reading

    async def get_or_create_device(
        self,
        db: AsyncSession,
        device_id: str,
        device_type: str,
        name: Optional[str] = None,
        **kwargs: Any,
    ) -> Device:
        """Get existing device or create a new one.

        Args:
            db: Database session
            device_id: Unique device identifier
            device_type: Type of device (tilt, ispindel, gravitymon, floaty)
            name: Display name for the device
            **kwargs: Additional device fields (color, mac, native_gravity_unit, etc.)

        Returns:
            Device model instance
        """
        result = await db.execute(select(Device).where(Device.id == device_id))
        device = result.scalar_one_or_none()

        if device is None:
            device = Device(
                id=device_id,
                device_type=device_type,
                name=name or device_id,
                calibration_type="none",
                **kwargs,
            )
            db.add(device)
            await db.flush()

        return device


# Global calibration service instance
calibration_service = CalibrationService()
