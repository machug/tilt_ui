"""Ingest Manager for processing hydrometer readings.

This is the central pipeline for ingesting readings from any device type:
1. Parse payload via AdapterRouter
2. Get or create Device record
3. Convert units to standard (SG, Fahrenheit)
4. Apply device calibration
5. Store Reading in database
6. Broadcast via WebSocket
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..ingest import AdapterRouter, HydrometerReading
from ..models import Device, Reading
from ..state import latest_readings
from ..websocket import manager as ws_manager
from .calibration import calibration_service

logger = logging.getLogger(__name__)


class IngestManager:
    """Manages the full ingest pipeline for all hydrometer types."""

    def __init__(self):
        self.adapter_router = AdapterRouter()

    async def ingest(
        self,
        db: AsyncSession,
        payload: dict,
        source_protocol: str = "http",
        auth_token: Optional[str] = None,
    ) -> Optional[Reading]:
        """Process a hydrometer payload through the full pipeline.

        Args:
            db: Database session
            payload: Raw payload from device
            source_protocol: Protocol used (http, mqtt, ble)
            auth_token: Optional auth token from request header

        Returns:
            Reading model if successful, None if parsing failed
        """
        # Step 1: Parse payload
        reading = self.adapter_router.route(payload, source_protocol=source_protocol)
        if not reading:
            logger.warning("Failed to parse payload: %s", payload)
            return None

        # Step 2: Get or create device
        device = await self._get_or_create_device(db, reading, auth_token)

        # Step 3: Validate auth token if device has one configured
        if not self._validate_auth(device, auth_token):
            logger.warning(
                "Auth token mismatch for device %s",
                reading.device_id,
            )
            return None

        # Step 4: Convert units to standard (SG, Fahrenheit)
        reading = calibration_service.convert_units(reading)

        # Step 5: Apply device calibration
        reading = await calibration_service.calibrate_device_reading(db, device, reading)

        # Step 6: Store reading in database
        db_reading = await self._store_reading(db, device, reading)

        # Step 7: Update device last_seen
        device.last_seen = reading.timestamp
        if reading.battery_voltage is not None:
            device.battery_voltage = reading.battery_voltage

        await db.commit()

        # Step 8: Broadcast via WebSocket
        await self._broadcast_reading(device, reading)

        logger.info(
            "Ingested %s reading: device=%s, sg=%.4f, temp=%.1f",
            reading.device_type,
            reading.device_id,
            reading.gravity or 0,
            reading.temperature or 0,
        )

        return db_reading

    async def _get_or_create_device(
        self,
        db: AsyncSession,
        reading: HydrometerReading,
        auth_token: Optional[str],
    ) -> Device:
        """Get existing device or create a new one from reading data."""
        # Build kwargs based on device type
        kwargs = {}

        if reading.device_type == "tilt":
            # Tilt-specific: extract color from device_id
            kwargs["color"] = reading.device_id
            kwargs["native_gravity_unit"] = "sg"
            kwargs["native_temp_unit"] = "f"

        elif reading.device_type in ("ispindel", "gravitymon"):
            kwargs["native_gravity_unit"] = str(reading.gravity_unit.value)
            kwargs["native_temp_unit"] = str(reading.temperature_unit.value)

        device = await calibration_service.get_or_create_device(
            db=db,
            device_id=reading.device_id,
            device_type=reading.device_type,
            name=reading.device_id,
            **kwargs,
        )

        return device

    def _validate_auth(self, device: Device, provided_token: Optional[str]) -> bool:
        """Validate auth token against device configuration.

        Returns True if:
        - Device has no auth_token configured (open)
        - Provided token matches device auth_token
        """
        if not device.auth_token:
            return True  # No auth required

        return device.auth_token == provided_token

    async def _store_reading(
        self,
        db: AsyncSession,
        device: Device,
        reading: HydrometerReading,
    ) -> Reading:
        """Store reading in database."""
        db_reading = Reading(
            device_id=device.id,
            device_type=reading.device_type,
            timestamp=reading.timestamp or datetime.now(timezone.utc),
            sg_raw=reading.gravity_raw,
            sg_calibrated=reading.gravity,
            temp_raw=reading.temperature_raw,
            temp_calibrated=reading.temperature,
            rssi=reading.rssi,
            battery_voltage=reading.battery_voltage,
            battery_percent=reading.battery_percent,
            angle=reading.angle,
            source_protocol=reading.source_protocol,
            status=reading.status.value,
            is_pre_filtered=reading.is_pre_filtered,
        )

        # Also set tilt_id for backwards compatibility if this is a Tilt
        if reading.device_type == "tilt":
            # Check if tilt exists in legacy table
            from sqlalchemy import select
            from ..models import Tilt
            result = await db.execute(select(Tilt).where(Tilt.id == reading.device_id))
            tilt = result.scalar_one_or_none()
            if tilt:
                db_reading.tilt_id = tilt.id

        db.add(db_reading)
        await db.flush()

        return db_reading

    def _build_reading_payload(
        self,
        device: Device,
        reading: HydrometerReading,
    ) -> dict:
        """Build WebSocket payload in legacy-compatible format.

        The payload format is compatible with existing UI consumers:
        - id: device identifier (required)
        - color: Tilt color or device name for non-Tilt
        - beer_name: current beer assignment
        - original_gravity: OG if set
        - sg/sg_raw: calibrated and raw gravity
        - temp/temp_raw: calibrated and raw temperature
        - rssi: signal strength
        - last_seen: ISO timestamp

        Additional fields for non-Tilt devices:
        - device_type: type of device
        - angle: tilt angle (iSpindel)
        - battery_voltage/battery_percent: battery status
        """
        timestamp = reading.timestamp or datetime.now(timezone.utc)

        payload = {
            # Core fields (legacy format)
            "id": device.id,
            "color": device.color or device.name,  # Use color for Tilt, name for others
            "beer_name": device.beer_name or "Untitled",
            "original_gravity": device.original_gravity,
            "sg": reading.gravity,
            "sg_raw": reading.gravity_raw,
            "temp": reading.temperature,
            "temp_raw": reading.temperature_raw,
            "rssi": reading.rssi,
            "last_seen": timestamp.isoformat(),
            # Extended fields for multi-hydrometer support
            "device_type": reading.device_type,
            "angle": reading.angle,
            "battery_voltage": reading.battery_voltage,
            "battery_percent": reading.battery_percent,
        }

        return payload

    async def _broadcast_reading(
        self,
        device: Device,
        reading: HydrometerReading,
    ) -> None:
        """Broadcast reading update via WebSocket and update latest_readings cache."""
        try:
            payload = self._build_reading_payload(device, reading)

            # Update the latest_readings cache
            # This ensures new WebSocket clients get current state
            latest_readings[device.id] = payload

            # Broadcast to all connected WebSocket clients
            await ws_manager.broadcast(payload)
        except Exception as e:
            logger.warning("Failed to broadcast reading: %s", e)


# Global ingest manager instance
ingest_manager = IngestManager()
