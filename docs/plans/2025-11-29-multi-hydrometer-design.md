# Multi-Hydrometer Support Design

**Date:** 2025-11-29
**Status:** Draft (Revised after review)
**Prerequisite for:** ML Enhancements Plan (2025-11-29-ml-enhancements.md)

## Overview

Extend Tilt UI to support multiple hydrometer types beyond Tilt, creating a universal fermentation monitoring platform. This enables the ML enhancements (Kalman filter, anomaly detection, predictions) to work with any device.

### Supported Devices

| Device | Protocols | Data Format | Native Units | Calibration |
|--------|-----------|-------------|--------------|-------------|
| **Tilt** | BLE iBeacon | UUID-encoded temp/SG | SG, °F | Offset (SG/temp) |
| **iSpindel** | HTTP POST, MQTT | JSON with angle/gravity | SG or °P, °C | Polynomial (angle→SG) |
| **Floaty** | HTTP POST, MQTT, Brewfather | iSpindel-compatible JSON | SG or °P, °C | Polynomial |
| **GravityMon** | HTTP POST, MQTT, InfluxDB | Extended iSpindel JSON | SG or °P, °C | Polynomial |
| **RAPT Pill** | BLE (future) | Custom BLE format | TBD | TBD |

---

## 1. Unified Data Model

### HydrometerReading (Universal)

All measurement fields are **Optional** to handle incomplete payloads (angle-only, degraded BLE, missing calibration). Calibration and ML layers handle missing fields gracefully.

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum

class GravityUnit(Enum):
    SG = "sg"        # Specific Gravity (1.000-1.150)
    PLATO = "plato"  # Degrees Plato (0-35)

class TemperatureUnit(Enum):
    FAHRENHEIT = "f"
    CELSIUS = "c"

class ReadingStatus(Enum):
    VALID = "valid"              # All fields present and calibrated
    UNCALIBRATED = "uncalibrated"  # Needs calibration (angle-only)
    INCOMPLETE = "incomplete"    # Missing required fields
    INVALID = "invalid"          # Failed validation

@dataclass
class HydrometerReading:
    """Universal reading from any hydrometer type.

    All measurement fields are Optional to handle:
    - Angle-only iSpindel before polynomial calibration
    - Degraded BLE reads with partial data
    - Brewfather payloads with °P instead of SG
    """
    device_id: str               # Unique device identifier
    device_type: str             # "tilt", "ispindel", "floaty", "gravitymon", "rapt"
    timestamp: datetime

    # Normalized measurements (filled by calibration service, may be None)
    gravity: Optional[float] = None       # Always SG after normalization (1.000-1.150)
    temperature: Optional[float] = None   # Always °F after normalization

    # Raw measurements as received (before calibration/conversion)
    gravity_raw: Optional[float] = None
    gravity_unit: GravityUnit = GravityUnit.SG
    temperature_raw: Optional[float] = None
    temperature_unit: TemperatureUnit = TemperatureUnit.FAHRENHEIT
    angle: Optional[float] = None         # Tilt angle (iSpindel/Floaty)

    # Metadata
    rssi: Optional[int] = None
    battery_voltage: Optional[float] = None   # Always volts (converted from %)
    battery_percent: Optional[int] = None     # 0-100 if device provides it

    # Processing metadata
    status: ReadingStatus = ReadingStatus.VALID
    is_pre_filtered: bool = False         # True if device sent filtered/smoothed data
    source_protocol: str = "unknown"      # "ble", "http", "mqtt", "websocket", "influxdb"
    raw_payload: Optional[dict] = None    # Original payload for debugging

    def is_complete(self) -> bool:
        """Check if reading has all required fields for storage."""
        return self.gravity is not None and self.temperature is not None

    def needs_calibration(self) -> bool:
        """Check if reading needs calibration processing."""
        return self.status == ReadingStatus.UNCALIBRATED
```

### Device Registry (Database)

```python
class Device(Base):
    """Registered hydrometer device."""
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(primary_key=True)
    device_type: Mapped[str]              # "tilt", "ispindel", "floaty", "gravitymon"
    name: Mapped[str]                     # User-friendly name
    display_name: Mapped[Optional[str]]   # For UI (fallback to name)

    # Current assignment
    beer_name: Mapped[Optional[str]]
    original_gravity: Mapped[Optional[float]]

    # Native units (for display and conversion)
    native_gravity_unit: Mapped[str] = mapped_column(default="sg")  # "sg" or "plato"
    native_temp_unit: Mapped[str] = mapped_column(default="f")      # "f" or "c"

    # Calibration
    calibration_type: Mapped[str] = mapped_column(default="none")  # "none", "offset", "polynomial"
    calibration_data: Mapped[Optional[dict]] = mapped_column(JSON)

    # Security
    auth_token: Mapped[Optional[str]]     # Per-device shared secret (hashed)

    # Status
    last_seen: Mapped[Optional[datetime]]
    battery_voltage: Mapped[Optional[float]]
    firmware_version: Mapped[Optional[str]]

    # Legacy compatibility (Tilt-specific)
    color: Mapped[Optional[str]]          # Tilt color identifier
    mac: Mapped[Optional[str]]            # MAC address

    created_at: Mapped[datetime] = mapped_column(default=func.now())
```

---

## 2. Unit Normalization

Each adapter MUST normalize units before returning a reading. The calibration service then fills `gravity` and `temperature` with final normalized values.

### Conversion Functions

```python
# backend/ingest/units.py

def plato_to_sg(plato: float) -> float:
    """Convert degrees Plato to specific gravity."""
    # Standard formula: SG = 1 + (plato / (258.6 - (plato/258.2) * 227.1))
    return 1 + (plato / (258.6 - (plato / 258.2) * 227.1))

def sg_to_plato(sg: float) -> float:
    """Convert specific gravity to degrees Plato."""
    # Approximate: °P = -616.868 + 1111.14*SG - 630.272*SG^2 + 135.997*SG^3
    return -616.868 + 1111.14*sg - 630.272*sg**2 + 135.997*sg**3

def celsius_to_fahrenheit(c: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return (c * 9/5) + 32

def fahrenheit_to_celsius(f: float) -> float:
    """Convert Fahrenheit to Celsius."""
    return (f - 32) * 5/9

def normalize_battery(
    value: float,
    device_type: str,
    is_percent: bool = False
) -> tuple[Optional[float], Optional[int]]:
    """Normalize battery to (voltage, percent).

    Device-specific voltage ranges:
    - iSpindel: 3.0-4.2V (LiPo)
    - Tilt: 2.0-3.0V (CR123A)
    - Floaty: 3.0-4.2V (LiPo)
    """
    BATTERY_RANGES = {
        "ispindel": (3.0, 4.2),
        "floaty": (3.0, 4.2),
        "gravitymon": (3.0, 4.2),
        "tilt": (2.0, 3.0),
    }

    if is_percent:
        percent = int(value)
        # Estimate voltage from percent using device range
        vmin, vmax = BATTERY_RANGES.get(device_type, (3.0, 4.2))
        voltage = vmin + (vmax - vmin) * (percent / 100)
        return voltage, percent
    else:
        voltage = value
        vmin, vmax = BATTERY_RANGES.get(device_type, (3.0, 4.2))
        percent = int(max(0, min(100, (voltage - vmin) / (vmax - vmin) * 100)))
        return voltage, percent
```

---

## 3. Adapter Implementation Pattern

### Base Adapter

```python
from abc import ABC, abstractmethod
from typing import Optional
from .base import HydrometerReading, ReadingStatus

class BaseAdapter(ABC):
    """Base class for device format adapters."""

    device_type: str  # "tilt", "ispindel", etc.

    # Native units for this device type
    native_gravity_unit: GravityUnit = GravityUnit.SG
    native_temp_unit: TemperatureUnit = TemperatureUnit.CELSIUS

    @abstractmethod
    def can_handle(self, payload: dict) -> bool:
        """Check if this adapter can handle the payload."""
        pass

    @abstractmethod
    def parse(self, payload: dict, source_protocol: str) -> Optional[HydrometerReading]:
        """Parse payload into HydrometerReading.

        MUST:
        - Set gravity_raw/temperature_raw with original values
        - Set gravity_unit/temperature_unit to indicate native units
        - Set status=UNCALIBRATED if angle-only (no pre-calculated gravity)
        - Set is_pre_filtered=True if device sends smoothed/filtered values
        - NOT fill gravity/temperature - calibration service does that
        """
        pass
```

### iSpindel Adapter (Corrected)

```python
class ISpindelAdapter(BaseAdapter):
    """Adapter for iSpindel JSON format."""

    device_type = "ispindel"
    native_temp_unit = TemperatureUnit.CELSIUS

    def can_handle(self, payload: dict) -> bool:
        """iSpindel payloads have 'angle' field and device name."""
        return "angle" in payload and "name" in payload

    def parse(self, payload: dict, source_protocol: str) -> Optional[HydrometerReading]:
        device_id = payload.get("ID") or payload.get("id") or payload.get("name")
        if not device_id:
            return None

        # Detect gravity unit from payload
        gravity_unit = GravityUnit.SG
        if payload.get("gravity-unit") == "P" or payload.get("temp_units") == "P":
            gravity_unit = GravityUnit.PLATO

        # Extract raw values - DO NOT convert or fake
        gravity_raw = payload.get("gravity")
        if gravity_raw is not None:
            try:
                gravity_raw = float(gravity_raw)
                if gravity_raw == 0:
                    gravity_raw = None  # 0 means uncalibrated
            except (ValueError, TypeError):
                gravity_raw = None

        temp_raw = payload.get("temperature", payload.get("temp"))
        if temp_raw is not None:
            try:
                temp_raw = float(temp_raw)
            except (ValueError, TypeError):
                temp_raw = None

        angle = payload.get("angle")
        if angle is not None:
            try:
                angle = float(angle)
            except (ValueError, TypeError):
                angle = None

        # Determine status
        if gravity_raw is None and angle is not None:
            status = ReadingStatus.UNCALIBRATED
        elif gravity_raw is None and angle is None:
            status = ReadingStatus.INCOMPLETE
        else:
            status = ReadingStatus.VALID

        # Battery normalization
        battery_raw = payload.get("battery")
        battery_voltage, battery_percent = None, None
        if battery_raw is not None:
            battery_voltage, battery_percent = normalize_battery(
                float(battery_raw),
                self.device_type,
                is_percent=False  # iSpindel sends voltage
            )

        return HydrometerReading(
            device_id=str(device_id),
            device_type=self.device_type,
            timestamp=datetime.now(timezone.utc),
            # Normalized values - LEFT EMPTY, filled by calibration
            gravity=None,
            temperature=None,
            # Raw values with units
            gravity_raw=gravity_raw,
            gravity_unit=gravity_unit,
            temperature_raw=temp_raw,
            temperature_unit=TemperatureUnit.CELSIUS,
            angle=angle,
            # Metadata
            rssi=payload.get("RSSI"),
            battery_voltage=battery_voltage,
            battery_percent=battery_percent,
            # Processing
            status=status,
            is_pre_filtered=False,  # Raw iSpindel sends unfiltered
            source_protocol=source_protocol,
            raw_payload=payload,
        )
```

### GravityMon Adapter (Handles Pre-Filtered Data)

```python
class GravityMonAdapter(BaseAdapter):
    """Adapter for GravityMon JSON format (iSpindel-compatible with extensions)."""

    device_type = "gravitymon"
    native_temp_unit = TemperatureUnit.CELSIUS

    def can_handle(self, payload: dict) -> bool:
        """GravityMon has 'corr-gravity' or 'run-time' extensions."""
        has_ispindel_base = "angle" in payload and "name" in payload
        has_gravitymon_ext = "corr-gravity" in payload or "run-time" in payload
        return has_ispindel_base and has_gravitymon_ext

    def parse(self, payload: dict, source_protocol: str) -> Optional[HydrometerReading]:
        # Similar to iSpindel, but check for pre-filtered values
        device_id = payload.get("ID") or payload.get("id") or payload.get("name")
        if not device_id:
            return None

        # GravityMon can send corrected (filtered) gravity
        is_pre_filtered = "corr-gravity" in payload

        gravity_raw = payload.get("corr-gravity") or payload.get("gravity")
        if gravity_raw is not None:
            try:
                gravity_raw = float(gravity_raw)
                if gravity_raw == 0:
                    gravity_raw = None
            except (ValueError, TypeError):
                gravity_raw = None

        # ... rest similar to iSpindel adapter ...

        return HydrometerReading(
            # ... other fields ...
            is_pre_filtered=is_pre_filtered,  # Mark if device pre-filtered
            # ...
        )
```

---

## 4. Calibration Service (Safe Handling)

```python
# backend/services/calibration.py

class CalibrationService:
    """Unified calibration for all hydrometer types.

    Handles:
    - Unit conversion (°P→SG, °C→°F)
    - Polynomial calibration (angle→SG)
    - Offset calibration (SG/temp adjustment)
    - Missing value handling (no fake values)
    """

    async def process_reading(
        self,
        session: AsyncSession,
        reading: HydrometerReading
    ) -> HydrometerReading:
        """Process and calibrate a reading.

        Returns reading with normalized gravity/temperature filled,
        or status=INVALID if calibration fails.
        """
        device = await self.get_device(session, reading.device_id)

        # Step 1: Unit conversion for raw values
        reading = self._convert_units(reading)

        # Step 2: Apply device-specific calibration
        if device and device.calibration_data:
            reading = self._apply_calibration(reading, device)
        elif reading.status == ReadingStatus.UNCALIBRATED:
            # No calibration data and needs polynomial - cannot proceed
            reading.status = ReadingStatus.INVALID
            return reading

        # Step 3: Validate final values
        if not reading.is_complete():
            reading.status = ReadingStatus.INCOMPLETE

        return reading

    def _convert_units(self, reading: HydrometerReading) -> HydrometerReading:
        """Convert raw values to standard units (SG, °F)."""

        # Temperature: Convert to °F if needed
        if reading.temperature_raw is not None:
            if reading.temperature_unit == TemperatureUnit.CELSIUS:
                reading.temperature = celsius_to_fahrenheit(reading.temperature_raw)
            else:
                reading.temperature = reading.temperature_raw

        # Gravity: Convert to SG if needed
        if reading.gravity_raw is not None:
            if reading.gravity_unit == GravityUnit.PLATO:
                reading.gravity = plato_to_sg(reading.gravity_raw)
            else:
                reading.gravity = reading.gravity_raw

        return reading

    def _apply_calibration(
        self,
        reading: HydrometerReading,
        device: Device
    ) -> HydrometerReading:
        """Apply device-specific calibration."""

        cal_data = device.calibration_data
        cal_type = device.calibration_type

        if cal_type == "polynomial" and reading.angle is not None:
            # iSpindel-style: angle → SG using polynomial
            coefficients = cal_data.get("coefficients", [])
            if coefficients:
                reading.gravity = self._apply_polynomial(reading.angle, coefficients)
                reading.status = ReadingStatus.VALID

        elif cal_type == "offset":
            # Tilt-style: simple offset adjustment
            if reading.gravity is not None:
                reading.gravity += cal_data.get("sg_offset", 0)
            if reading.temperature is not None:
                reading.temperature += cal_data.get("temp_offset", 0)

        # Apply temp offset for polynomial devices too
        if reading.temperature is not None and "temp_offset" in cal_data:
            reading.temperature += cal_data.get("temp_offset", 0)

        return reading

    def _apply_polynomial(self, angle: float, coefficients: list[float]) -> float:
        """Apply polynomial calibration: SG = a*x^n + b*x^(n-1) + ... + c"""
        result = 0.0
        for i, coef in enumerate(reversed(coefficients)):
            result += coef * (angle ** i)
        return result
```

---

## 5. MQTT Broker Strategy (With Fallbacks)

```python
# backend/mqtt_broker.py
import subprocess
import asyncio
import shutil
from pathlib import Path
from typing import Optional
import tempfile
import os

class MQTTBrokerManager:
    """Manages MQTT broker - embedded or external."""

    def __init__(self, config: "MQTTConfig"):
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self._temp_dir: Optional[str] = None

    async def start(self) -> bool:
        """Start MQTT broker based on configuration.

        Returns True if broker is available, False if disabled/failed.
        """
        if not self.config.enabled:
            logger.info("MQTT disabled by configuration")
            return False

        if not self.config.use_embedded:
            # Using external broker - just verify connectivity
            return await self._verify_external_broker()

        # Try embedded broker
        if not self._mosquitto_available():
            logger.warning("Mosquitto not found, falling back to external broker")
            self.config.use_embedded = False
            return await self._verify_external_broker()

        return await self._start_embedded()

    def _mosquitto_available(self) -> bool:
        """Check if mosquitto binary is available."""
        return shutil.which("mosquitto") is not None

    async def _start_embedded(self) -> bool:
        """Start embedded Mosquitto broker."""
        try:
            # Use system temp directory (works on minimal images)
            self._temp_dir = tempfile.mkdtemp(prefix="tiltui_mqtt_")
            config_path = Path(self._temp_dir) / "mosquitto.conf"

            # Build config with optional auth
            config_lines = [
                f"listener {self.config.broker_port}",
                "persistence false",
            ]

            if self.config.username and self.config.password:
                password_file = Path(self._temp_dir) / "passwd"
                # Create password file using mosquitto_passwd
                subprocess.run(
                    ["mosquitto_passwd", "-b", "-c", str(password_file),
                     self.config.username, self.config.password],
                    check=True, capture_output=True
                )
                config_lines.extend([
                    "allow_anonymous false",
                    f"password_file {password_file}",
                ])
            else:
                config_lines.append("allow_anonymous true")

            config_path.write_text("\n".join(config_lines))

            self.process = subprocess.Popen(
                ["mosquitto", "-c", str(config_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            await asyncio.sleep(0.5)

            if self.process.poll() is not None:
                # Process exited - check stderr
                stderr = self.process.stderr.read().decode() if self.process.stderr else ""
                logger.error("Embedded MQTT broker failed to start: %s", stderr)
                return False

            logger.info("Embedded MQTT broker started on port %d", self.config.broker_port)
            return True

        except Exception as e:
            logger.error("Failed to start embedded MQTT broker: %s", e)
            return False

    async def _verify_external_broker(self) -> bool:
        """Verify connectivity to external MQTT broker."""
        try:
            import aiomqtt
            async with aiomqtt.Client(
                hostname=self.config.broker_host,
                port=self.config.broker_port,
                username=self.config.username,
                password=self.config.password,
            ) as client:
                logger.info("Connected to external MQTT broker at %s:%d",
                           self.config.broker_host, self.config.broker_port)
                return True
        except Exception as e:
            logger.error("Cannot connect to external MQTT broker: %s", e)
            return False

    async def stop(self):
        """Stop embedded broker and cleanup."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

        if self._temp_dir:
            import shutil
            shutil.rmtree(self._temp_dir, ignore_errors=True)
```

### Configuration

```python
# backend/config.py additions
@dataclass
class MQTTConfig:
    enabled: bool = True
    use_embedded: bool = True           # False = external only
    broker_host: str = "localhost"
    broker_port: int = 1883
    username: Optional[str] = None
    password: Optional[str] = None
    topics: list[str] = field(default_factory=lambda: [
        "ispindel/#",
        "gravitymon/#",
        "floaty/#",
        "tilt/#",
        "hydrometer/#",
    ])
```

---

## 6. Security: Ingest Authentication

```python
# backend/routers/ingest.py
from fastapi import APIRouter, Request, HTTPException, Header
from typing import Optional

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

async def verify_device_token(
    device_id: str,
    token: Optional[str],
    session: AsyncSession
) -> bool:
    """Verify per-device authentication token."""
    if not token:
        # Check if anonymous ingest is allowed
        config = await get_config(session)
        return config.allow_anonymous_ingest

    device = await session.get(Device, device_id)
    if not device or not device.auth_token:
        return False

    # Compare hashed tokens
    return verify_token_hash(token, device.auth_token)

@router.post("/generic")
async def ingest_generic(
    request: Request,
    x_device_token: Optional[str] = Header(None, alias="X-Device-Token"),
):
    """Auto-detect format and ingest with optional authentication."""
    payload = await request.json()
    reading = adapter_router.route(payload, source_protocol="http")

    if not reading:
        raise HTTPException(400, "Unknown payload format")

    async with async_session_factory() as session:
        # Verify authentication
        if not await verify_device_token(reading.device_id, x_device_token, session):
            raise HTTPException(401, "Invalid or missing device token")

        await ingest_manager.handle_reading(reading)
        return {"status": "ok", "device_type": reading.device_type}

# Device-specific endpoints (same auth pattern)
@router.post("/ispindel")
async def ingest_ispindel(
    request: Request,
    x_device_token: Optional[str] = Header(None, alias="X-Device-Token"),
):
    """Receive iSpindel HTTP POST."""
    # ... same auth pattern ...
```

---

## 7. Database Migrations (Non-Destructive)

### Migration Strategy

1. Create new `devices` table alongside existing `tilts`
2. Migrate data from `tilts` to `devices`
3. Add foreign key from `readings` to `devices`
4. Keep `tilts` as view for backward compatibility
5. Update code to use `devices`
6. Remove `tilts` table in future release

```python
# backend/migrations/versions/xxx_add_devices_table.py
"""Add devices table for multi-hydrometer support."""

from alembic import op
import sqlalchemy as sa

def upgrade():
    # Create new devices table
    op.create_table(
        'devices',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('device_type', sa.String(), nullable=False, server_default='tilt'),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('display_name', sa.String(), nullable=True),
        sa.Column('color', sa.String(), nullable=True),  # Tilt legacy
        sa.Column('mac', sa.String(), nullable=True),
        sa.Column('beer_name', sa.String(), nullable=True),
        sa.Column('original_gravity', sa.Float(), nullable=True),
        sa.Column('native_gravity_unit', sa.String(), server_default='sg'),
        sa.Column('native_temp_unit', sa.String(), server_default='f'),
        sa.Column('calibration_type', sa.String(), server_default='none'),
        sa.Column('calibration_data', sa.JSON(), nullable=True),
        sa.Column('auth_token', sa.String(), nullable=True),
        sa.Column('last_seen', sa.DateTime(), nullable=True),
        sa.Column('battery_voltage', sa.Float(), nullable=True),
        sa.Column('firmware_version', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # Migrate existing tilts to devices
    op.execute("""
        INSERT INTO devices (id, device_type, name, color, mac, beer_name,
                            original_gravity, calibration_type, calibration_data, last_seen)
        SELECT id, 'tilt', COALESCE(color, id), color, mac, beer_name,
               original_gravity, 'offset',
               json_object('sg_offset', COALESCE(sg_offset, 0),
                          'temp_offset', COALESCE(temp_offset, 0)),
               last_seen
        FROM tilts
    """)

    # Add new columns to readings
    op.add_column('readings', sa.Column('device_type', sa.String(), server_default='tilt'))
    op.add_column('readings', sa.Column('angle', sa.Float(), nullable=True))
    op.add_column('readings', sa.Column('battery_voltage', sa.Float(), nullable=True))
    op.add_column('readings', sa.Column('battery_percent', sa.Integer(), nullable=True))
    op.add_column('readings', sa.Column('source_protocol', sa.String(), server_default='ble'))
    op.add_column('readings', sa.Column('status', sa.String(), server_default='valid'))
    op.add_column('readings', sa.Column('is_pre_filtered', sa.Boolean(), server_default='false'))

    # Create view for backward compatibility
    op.execute("""
        CREATE VIEW tilts_compat AS
        SELECT id, color, mac, beer_name, original_gravity, last_seen,
               json_extract(calibration_data, '$.sg_offset') as sg_offset,
               json_extract(calibration_data, '$.temp_offset') as temp_offset
        FROM devices
        WHERE device_type = 'tilt'
    """)

def downgrade():
    op.execute("DROP VIEW IF EXISTS tilts_compat")
    op.drop_column('readings', 'is_pre_filtered')
    op.drop_column('readings', 'status')
    op.drop_column('readings', 'source_protocol')
    op.drop_column('readings', 'battery_percent')
    op.drop_column('readings', 'battery_voltage')
    op.drop_column('readings', 'angle')
    op.drop_column('readings', 'device_type')
    op.drop_table('devices')
```

---

## 8. Legacy Compatibility Layer

```python
# backend/compat.py
"""Backward compatibility helpers for Tilt-centric code."""

from typing import Optional
from .ingest.base import HydrometerReading
from .models import Device

async def reading_to_legacy_format(
    reading: HydrometerReading,
    device: Optional[Device] = None
) -> dict:
    """Convert universal reading to legacy TiltCard format.

    Uses device registry for color/name lookup instead of raw_payload.
    """
    # Get display info from device registry, not raw_payload
    color = None
    display_name = reading.device_id
    beer_name = None
    original_gravity = None

    if device:
        color = device.color  # Only Tilts have color
        display_name = device.display_name or device.name
        beer_name = device.beer_name
        original_gravity = device.original_gravity
    elif reading.device_type == "tilt":
        # Fallback for Tilt without device record
        color = reading.device_id  # Tilt ID is the color

    return {
        "id": reading.device_id,
        "color": color,
        "device_type": reading.device_type,
        "display_name": display_name,
        "beer_name": beer_name,
        "original_gravity": original_gravity,
        "sg": reading.gravity,
        "sg_raw": reading.gravity_raw,
        "temp": reading.temperature,
        "temp_raw": reading.temperature_raw,
        "rssi": reading.rssi,
        "last_seen": reading.timestamp.isoformat(),
        # Extended fields
        "battery_voltage": reading.battery_voltage,
        "battery_percent": reading.battery_percent,
        "angle": reading.angle,
        "is_pre_filtered": reading.is_pre_filtered,
        "status": reading.status.value,
    }
```

---

## 9. Ingest Manager (Handles Invalid Readings)

```python
# backend/ingest/manager.py

class IngestManager:
    """Central manager for all incoming readings."""

    async def handle_reading(self, reading: HydrometerReading):
        """Process incoming reading through calibration and storage."""

        async with async_session_factory() as session:
            # Get or create device
            device = await self._ensure_device(session, reading)

            # Apply calibration
            reading = await calibration_service.process_reading(session, reading)

            # Handle based on status
            if reading.status == ReadingStatus.INVALID:
                # Log but don't store - calibration failed and we won't fake data
                logger.warning(
                    "Dropping invalid reading from %s: missing calibration for angle-only data",
                    reading.device_id
                )
                # Optionally store in separate invalid_readings table for debugging
                await self._store_invalid_reading(session, reading)
                return

            if reading.status == ReadingStatus.INCOMPLETE:
                # Store partial data but flag it
                logger.info(
                    "Storing incomplete reading from %s: gravity=%s, temp=%s",
                    reading.device_id, reading.gravity, reading.temperature
                )

            # Store valid/incomplete reading
            await self._store_reading(session, reading, device)

            # Broadcast to WebSocket clients
            legacy_data = await reading_to_legacy_format(reading, device)
            await manager.broadcast(legacy_data)

            await session.commit()
```

---

## 10. Implementation Priority

### Phase 1: Core Abstraction
1. Create `ingest/` module with base classes
2. Implement `HydrometerReading` with optional fields
3. Implement unit conversion functions
4. Refactor existing Tilt scanner as `TiltAdapter`
5. Database migrations (non-destructive)
6. Backward compatibility layer

### Phase 2: HTTP Ingest + Auth
1. Implement `ISpindelAdapter` (no fake values)
2. Implement `GravityMonAdapter` (with pre-filtered flag)
3. Implement `BrewfatherAdapter`
4. Create HTTP POST endpoints with token auth
5. Device registration API

### Phase 3: MQTT Support
1. MQTT broker manager with fallbacks
2. MQTT subscriber for all device topics
3. Authentication (username/password + ACLs)
4. External broker configuration

### Phase 4: Calibration + UI
1. Polynomial calibration service
2. Device management page
3. Calibration wizard UI
4. Battery display normalization

---

## 11. Testing Strategy

### Unit Tests
- Adapter parsing for each device format
- Unit conversions (°P→SG, °C→°F)
- Calibration calculations (polynomial, offset)
- Invalid reading rejection (no fake values)
- Battery normalization per device type

### Integration Tests
- HTTP endpoint ingestion with/without auth
- MQTT message flow
- Embedded vs external broker fallback
- Database migration with existing data
- Legacy format compatibility

### Device Simulators
- Mock iSpindel (angle-only and pre-calibrated)
- Mock GravityMon (with pre-filtered data)
- Mock Floaty (MQTT and HTTP)
- Extend existing Tilt mock mode

---

## References

- [iSpindel Documentation](https://opensourcedistilling.com/ispindel/)
- [GravityMon Data Formats](https://gravitymon.com/doc-data.html)
- [Floaty Hydrometer](https://floatyhydrometer.com/)
- [Brewfather Custom Stream API](https://docs.brewfather.app/integrations/custom-stream)

---

## Appendix: Review Findings Addressed

| Finding | Resolution |
|---------|------------|
| Optional gravity/temperature | All measurement fields now `Optional`, `ReadingStatus` enum tracks completeness |
| Units underspecified | Added `GravityUnit`, `TemperatureUnit` enums, per-adapter normalization, device registry flags |
| Floaty MQTT missing | Updated device table to show MQTT/Brewfather protocols |
| GravityMon InfluxDB missing | Updated device table to show all protocols |
| Placeholder 1.000 gravity | Adapters set `gravity=None` and `status=UNCALIBRATED`, calibration fills or rejects |
| Mosquitto availability | `MQTTBrokerManager` with fallback to external, tempdir instead of /tmp |
| Destructive migration | Non-destructive migration with `tilts_compat` view for backward compatibility |
| Security absent | Per-device token auth via `X-Device-Token` header, MQTT credentials support |
| Legacy color lookup | `reading_to_legacy_format()` uses device registry, not `raw_payload` |
| Pre-filtered data | Added `is_pre_filtered` flag, GravityMon adapter sets it for `corr-gravity` |
| Battery semantics | Split into `battery_voltage` + `battery_percent`, per-device normalization |
| GravityMon URL wrong | Fixed to `doc-data.html` |
