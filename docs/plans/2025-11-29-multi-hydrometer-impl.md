# Multi-Hydrometer Support Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend Tilt UI to support iSpindel, Floaty, GravityMon, and future hydrometers via a universal ingest layer.

**Architecture:** Protocol adapters normalize device-specific formats into a unified `HydrometerReading` dataclass. Calibration service handles unit conversion and polynomial/offset calibration. Non-destructive database migration preserves existing Tilt data.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, aiosqlite, aiomqtt (optional)

**Design Doc:** `docs/plans/2025-11-29-multi-hydrometer-design.md`

---

## Phase 1: Core Data Model & Unit Conversion

### Task 1.1: Create Ingest Module Structure

**Files:**
- Create: `backend/ingest/__init__.py`
- Create: `backend/ingest/base.py`
- Create: `backend/ingest/units.py`

**Step 1: Create ingest package init**

```python
# backend/ingest/__init__.py
"""Universal hydrometer ingest layer."""

from .base import (
    GravityUnit,
    HydrometerReading,
    ReadingStatus,
    TemperatureUnit,
)
from .units import (
    celsius_to_fahrenheit,
    fahrenheit_to_celsius,
    normalize_battery,
    plato_to_sg,
    sg_to_plato,
)

__all__ = [
    "GravityUnit",
    "HydrometerReading",
    "ReadingStatus",
    "TemperatureUnit",
    "celsius_to_fahrenheit",
    "fahrenheit_to_celsius",
    "normalize_battery",
    "plato_to_sg",
    "sg_to_plato",
]
```

**Step 2: Create base.py with core dataclasses**

```python
# backend/ingest/base.py
"""Core data structures for universal hydrometer readings."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class GravityUnit(Enum):
    """Gravity measurement units."""
    SG = "sg"        # Specific Gravity (1.000-1.150)
    PLATO = "plato"  # Degrees Plato (0-35)


class TemperatureUnit(Enum):
    """Temperature measurement units."""
    FAHRENHEIT = "f"
    CELSIUS = "c"


class ReadingStatus(Enum):
    """Processing status of a reading."""
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
    - Brewfather payloads with degrees Plato instead of SG
    """
    device_id: str
    device_type: str  # "tilt", "ispindel", "floaty", "gravitymon", "rapt"
    timestamp: datetime

    # Normalized measurements (filled by calibration service, may be None)
    gravity: Optional[float] = None       # Always SG after normalization
    temperature: Optional[float] = None   # Always Fahrenheit after normalization

    # Raw measurements as received (before calibration/conversion)
    gravity_raw: Optional[float] = None
    gravity_unit: GravityUnit = GravityUnit.SG
    temperature_raw: Optional[float] = None
    temperature_unit: TemperatureUnit = TemperatureUnit.FAHRENHEIT
    angle: Optional[float] = None         # Tilt angle (iSpindel/Floaty)

    # Metadata
    rssi: Optional[int] = None
    battery_voltage: Optional[float] = None   # Always volts
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

**Step 3: Create units.py with conversion functions**

```python
# backend/ingest/units.py
"""Unit conversion utilities for hydrometer readings."""

from typing import Optional


def plato_to_sg(plato: float) -> float:
    """Convert degrees Plato to specific gravity.

    Formula: SG = 1 + (plato / (258.6 - (plato/258.2) * 227.1))
    """
    if plato == 0:
        return 1.0
    return 1 + (plato / (258.6 - (plato / 258.2) * 227.1))


def sg_to_plato(sg: float) -> float:
    """Convert specific gravity to degrees Plato.

    Approximation: P = -616.868 + 1111.14*SG - 630.272*SG^2 + 135.997*SG^3
    """
    return -616.868 + 1111.14 * sg - 630.272 * sg**2 + 135.997 * sg**3


def celsius_to_fahrenheit(c: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return (c * 9 / 5) + 32


def fahrenheit_to_celsius(f: float) -> float:
    """Convert Fahrenheit to Celsius."""
    return (f - 32) * 5 / 9


# Device-specific battery voltage ranges
BATTERY_RANGES: dict[str, tuple[float, float]] = {
    "ispindel": (3.0, 4.2),   # LiPo
    "floaty": (3.0, 4.2),     # LiPo
    "gravitymon": (3.0, 4.2), # LiPo
    "tilt": (2.0, 3.0),       # CR123A
}


def normalize_battery(
    value: float,
    device_type: str,
    is_percent: bool = False
) -> tuple[Optional[float], Optional[int]]:
    """Normalize battery to (voltage, percent).

    Args:
        value: Battery reading (voltage or percent)
        device_type: Device type for voltage range lookup
        is_percent: True if value is percentage, False if voltage

    Returns:
        Tuple of (voltage, percent)
    """
    vmin, vmax = BATTERY_RANGES.get(device_type, (3.0, 4.2))

    if is_percent:
        percent = int(max(0, min(100, value)))
        voltage = vmin + (vmax - vmin) * (percent / 100)
        return voltage, percent
    else:
        voltage = value
        percent = int(max(0, min(100, (voltage - vmin) / (vmax - vmin) * 100)))
        return voltage, percent
```

**Step 4: Verify module imports**

Run: `cd /home/ladmin/Projects/tilt_ui && python3 -c "from backend.ingest import HydrometerReading, plato_to_sg; print('OK')"`

Expected: `OK`

**Step 5: Commit**

```bash
git add backend/ingest/
git commit -m "feat(ingest): add core data model and unit conversion

- HydrometerReading dataclass with optional fields
- GravityUnit, TemperatureUnit, ReadingStatus enums
- Unit conversion: plato<->sg, celsius<->fahrenheit
- Battery normalization per device type"
```

---

### Task 1.2: Add Unit Conversion Tests

**Files:**
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_units.py`
- Create: `backend/tests/conftest.py`

**NOTE:** Creating tests in `backend/tests/` (not root `tests/`). Pytest will discover these via the package structure.

**Step 1: Create test package with conftest**

```python
# backend/tests/__init__.py
"""Backend test package."""
```

```python
# backend/tests/conftest.py
"""Pytest configuration for backend tests."""

import sys
from pathlib import Path

# Ensure backend package is importable
backend_path = Path(__file__).parent.parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))
```

**Step 2: Write unit conversion tests**

```python
# backend/tests/test_units.py
"""Tests for unit conversion utilities."""

import pytest
from backend.ingest.units import (
    celsius_to_fahrenheit,
    fahrenheit_to_celsius,
    normalize_battery,
    plato_to_sg,
    sg_to_plato,
)


class TestTemperatureConversion:
    """Test temperature unit conversion."""

    def test_celsius_to_fahrenheit_freezing(self):
        assert celsius_to_fahrenheit(0) == 32

    def test_celsius_to_fahrenheit_boiling(self):
        assert celsius_to_fahrenheit(100) == 212

    def test_celsius_to_fahrenheit_fermentation(self):
        # 20C is typical ale fermentation temp
        result = celsius_to_fahrenheit(20)
        assert result == pytest.approx(68, abs=0.1)

    def test_fahrenheit_to_celsius_freezing(self):
        assert fahrenheit_to_celsius(32) == 0

    def test_fahrenheit_to_celsius_boiling(self):
        assert fahrenheit_to_celsius(212) == 100

    def test_roundtrip_conversion(self):
        original = 18.5
        converted = fahrenheit_to_celsius(celsius_to_fahrenheit(original))
        assert converted == pytest.approx(original, abs=0.001)


class TestGravityConversion:
    """Test gravity unit conversion."""

    def test_plato_to_sg_zero(self):
        assert plato_to_sg(0) == 1.0

    def test_plato_to_sg_typical_wort(self):
        # 12 Plato ~ 1.048 SG
        result = plato_to_sg(12)
        assert result == pytest.approx(1.048, abs=0.002)

    def test_plato_to_sg_high_gravity(self):
        # 20 Plato ~ 1.083 SG
        result = plato_to_sg(20)
        assert result == pytest.approx(1.083, abs=0.002)

    def test_sg_to_plato_water(self):
        result = sg_to_plato(1.0)
        assert result == pytest.approx(0, abs=0.5)

    def test_sg_to_plato_typical_wort(self):
        # 1.050 SG ~ 12.4 Plato
        result = sg_to_plato(1.050)
        assert result == pytest.approx(12.4, abs=0.5)

    def test_roundtrip_gravity(self):
        original = 15.0  # Plato
        sg = plato_to_sg(original)
        back = sg_to_plato(sg)
        assert back == pytest.approx(original, abs=0.1)


class TestBatteryNormalization:
    """Test battery voltage/percent normalization."""

    def test_ispindel_full_battery(self):
        voltage, percent = normalize_battery(4.2, "ispindel", is_percent=False)
        assert voltage == 4.2
        assert percent == 100

    def test_ispindel_empty_battery(self):
        voltage, percent = normalize_battery(3.0, "ispindel", is_percent=False)
        assert voltage == 3.0
        assert percent == 0

    def test_ispindel_half_battery(self):
        voltage, percent = normalize_battery(3.6, "ispindel", is_percent=False)
        assert voltage == 3.6
        assert percent == 50

    def test_tilt_battery_range(self):
        # Tilt uses CR123A: 2.0-3.0V
        voltage, percent = normalize_battery(2.5, "tilt", is_percent=False)
        assert voltage == 2.5
        assert percent == 50

    def test_percent_to_voltage(self):
        voltage, percent = normalize_battery(50, "ispindel", is_percent=True)
        assert percent == 50
        assert voltage == pytest.approx(3.6, abs=0.01)

    def test_clamp_percent_over_100(self):
        voltage, percent = normalize_battery(150, "ispindel", is_percent=True)
        assert percent == 100

    def test_clamp_percent_below_0(self):
        voltage, percent = normalize_battery(-10, "ispindel", is_percent=True)
        assert percent == 0

    def test_unknown_device_uses_default_range(self):
        voltage, percent = normalize_battery(3.6, "unknown_device", is_percent=False)
        # Default range is 3.0-4.2V
        assert percent == 50
```

**Step 3: Run tests to verify they pass**

Run: `cd /home/ladmin/Projects/tilt_ui && python3 -m pytest backend/tests/test_units.py -v`

Expected: All tests pass

**Step 4: Commit**

```bash
git add backend/tests/
git commit -m "test(ingest): add unit conversion tests

- Temperature conversion (C<->F)
- Gravity conversion (Plato<->SG)
- Battery normalization per device type"
```

---

### Task 1.3: Add HydrometerReading Tests

**Files:**
- Create: `backend/tests/test_base.py`

**Step 1: Write HydrometerReading tests**

```python
# backend/tests/test_base.py
"""Tests for core hydrometer data structures."""

from datetime import datetime, timezone

import pytest
from backend.ingest.base import (
    GravityUnit,
    HydrometerReading,
    ReadingStatus,
    TemperatureUnit,
)


class TestHydrometerReading:
    """Test HydrometerReading dataclass."""

    def test_minimal_reading(self):
        """Test creating reading with only required fields."""
        reading = HydrometerReading(
            device_id="test-device",
            device_type="ispindel",
            timestamp=datetime.now(timezone.utc),
        )
        assert reading.device_id == "test-device"
        assert reading.device_type == "ispindel"
        assert reading.gravity is None
        assert reading.temperature is None
        assert reading.status == ReadingStatus.VALID

    def test_complete_reading(self):
        """Test creating reading with all fields."""
        reading = HydrometerReading(
            device_id="test-device",
            device_type="tilt",
            timestamp=datetime.now(timezone.utc),
            gravity=1.050,
            temperature=68.0,
            gravity_raw=1.052,
            temperature_raw=67.5,
            rssi=-65,
            battery_voltage=2.8,
            battery_percent=80,
            status=ReadingStatus.VALID,
            source_protocol="ble",
        )
        assert reading.is_complete()
        assert not reading.needs_calibration()

    def test_is_complete_with_gravity_only(self):
        """Test is_complete returns False when temperature missing."""
        reading = HydrometerReading(
            device_id="test",
            device_type="ispindel",
            timestamp=datetime.now(timezone.utc),
            gravity=1.050,
            temperature=None,
        )
        assert not reading.is_complete()

    def test_is_complete_with_temperature_only(self):
        """Test is_complete returns False when gravity missing."""
        reading = HydrometerReading(
            device_id="test",
            device_type="ispindel",
            timestamp=datetime.now(timezone.utc),
            gravity=None,
            temperature=68.0,
        )
        assert not reading.is_complete()

    def test_needs_calibration(self):
        """Test needs_calibration for uncalibrated readings."""
        reading = HydrometerReading(
            device_id="test",
            device_type="ispindel",
            timestamp=datetime.now(timezone.utc),
            angle=25.5,
            status=ReadingStatus.UNCALIBRATED,
        )
        assert reading.needs_calibration()

    def test_does_not_need_calibration(self):
        """Test needs_calibration for valid readings."""
        reading = HydrometerReading(
            device_id="test",
            device_type="tilt",
            timestamp=datetime.now(timezone.utc),
            gravity=1.050,
            temperature=68.0,
            status=ReadingStatus.VALID,
        )
        assert not reading.needs_calibration()

    def test_gravity_unit_default(self):
        """Test default gravity unit is SG."""
        reading = HydrometerReading(
            device_id="test",
            device_type="ispindel",
            timestamp=datetime.now(timezone.utc),
        )
        assert reading.gravity_unit == GravityUnit.SG

    def test_temperature_unit_default(self):
        """Test default temperature unit is Fahrenheit."""
        reading = HydrometerReading(
            device_id="test",
            device_type="tilt",
            timestamp=datetime.now(timezone.utc),
        )
        assert reading.temperature_unit == TemperatureUnit.FAHRENHEIT

    def test_raw_payload_storage(self):
        """Test raw payload is stored for debugging."""
        payload = {"name": "iSpindel", "angle": 25.5, "temperature": 20.0}
        reading = HydrometerReading(
            device_id="test",
            device_type="ispindel",
            timestamp=datetime.now(timezone.utc),
            raw_payload=payload,
        )
        assert reading.raw_payload == payload


class TestReadingStatus:
    """Test ReadingStatus enum values."""

    def test_all_statuses_exist(self):
        assert ReadingStatus.VALID.value == "valid"
        assert ReadingStatus.UNCALIBRATED.value == "uncalibrated"
        assert ReadingStatus.INCOMPLETE.value == "incomplete"
        assert ReadingStatus.INVALID.value == "invalid"


class TestGravityUnit:
    """Test GravityUnit enum values."""

    def test_sg_value(self):
        assert GravityUnit.SG.value == "sg"

    def test_plato_value(self):
        assert GravityUnit.PLATO.value == "plato"


class TestTemperatureUnit:
    """Test TemperatureUnit enum values."""

    def test_fahrenheit_value(self):
        assert TemperatureUnit.FAHRENHEIT.value == "f"

    def test_celsius_value(self):
        assert TemperatureUnit.CELSIUS.value == "c"
```

**Step 2: Run tests**

Run: `cd /home/ladmin/Projects/tilt_ui && python3 -m pytest backend/tests/test_base.py -v`

Expected: All tests pass

**Step 3: Commit**

```bash
git add backend/tests/test_base.py
git commit -m "test(ingest): add HydrometerReading and enum tests"
```

---

## Phase 2: Database Migration

### Task 2.1: Create Device Model (Separate from Base.metadata)

**Files:**
- Create: `backend/models_device.py` (new file, NOT in Base.metadata initially)

**IMPORTANT:** We create Device in a separate file first to avoid `create_all` creating an empty table before migration runs. The model will be merged into `models.py` after migration logic is proven.

**Step 1: Create device model in separate file**

```python
# backend/models_device.py
"""Device model - kept separate to control migration order.

This model is NOT part of Base.metadata.create_all initially.
Migration creates the table manually and migrates data from tilts.
After migration, this can be merged into models.py.
"""

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Device(Base):
    """Universal hydrometer device registry."""
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    device_type: Mapped[str] = mapped_column(String(20), nullable=False, default="tilt")
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(100))

    # Current assignment
    beer_name: Mapped[Optional[str]] = mapped_column(String(100))
    original_gravity: Mapped[Optional[float]] = mapped_column()

    # Native units (for display and conversion)
    native_gravity_unit: Mapped[str] = mapped_column(String(10), default="sg")
    native_temp_unit: Mapped[str] = mapped_column(String(5), default="f")

    # Calibration - stored as JSON string, use properties for access
    calibration_type: Mapped[str] = mapped_column(String(20), default="none")
    _calibration_data: Mapped[Optional[str]] = mapped_column("calibration_data", Text)

    @property
    def calibration_data(self) -> Optional[dict[str, Any]]:
        """Get calibration data as dict."""
        if self._calibration_data:
            return json.loads(self._calibration_data)
        return None

    @calibration_data.setter
    def calibration_data(self, value: Optional[dict[str, Any]]) -> None:
        """Set calibration data from dict."""
        if value is not None:
            self._calibration_data = json.dumps(value)
        else:
            self._calibration_data = None

    # Security
    auth_token: Mapped[Optional[str]] = mapped_column(String(100))

    # Status
    last_seen: Mapped[Optional[datetime]] = mapped_column()
    battery_voltage: Mapped[Optional[float]] = mapped_column()
    firmware_version: Mapped[Optional[str]] = mapped_column(String(50))

    # Legacy compatibility (Tilt-specific)
    color: Mapped[Optional[str]] = mapped_column(String(20))
    mac: Mapped[Optional[str]] = mapped_column(String(17))

    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
```

**Step 2: Verify model loads**

Run: `cd /home/ladmin/Projects/tilt_ui && python3 -c "from backend.models_device import Device; print('OK')"`

Expected: `OK`

**Step 3: Commit**

```bash
git add backend/models_device.py
git commit -m "feat(models): add Device model for multi-hydrometer support

- Universal device registry with device_type field
- Native unit tracking (gravity_unit, temp_unit)
- Calibration data as JSON with property accessors
- Auth token for secure ingest
- Legacy Tilt fields (color, mac) preserved
- Separate file to control migration order"
```

---

### Task 2.2: Create Database Migration

**Files:**
- Modify: `backend/database.py`

**IMPORTANT FIXES:**
1. Migration runs BEFORE `create_all` to handle existing DBs
2. Migration checks for DATA not just table existence
3. No destructive test commands - use separate test DB
4. Calibration data stored as plain JSON string (no json_object SQL function)

**Step 1: Add migration functions**

Add after `_migrate_add_original_gravity` function:

```python
def _migrate_create_devices_table(conn):
    """Create devices table if it doesn't exist (without SQLAlchemy metadata)."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "devices" in inspector.get_table_names():
        return  # Table exists, will check data migration separately

    # Create devices table manually (not via create_all)
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS devices (
            id TEXT PRIMARY KEY,
            device_type TEXT NOT NULL DEFAULT 'tilt',
            name TEXT NOT NULL,
            display_name TEXT,
            beer_name TEXT,
            original_gravity REAL,
            native_gravity_unit TEXT DEFAULT 'sg',
            native_temp_unit TEXT DEFAULT 'f',
            calibration_type TEXT DEFAULT 'none',
            calibration_data TEXT,
            auth_token TEXT,
            last_seen TIMESTAMP,
            battery_voltage REAL,
            firmware_version TEXT,
            color TEXT,
            mac TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    print("Migration: Created devices table")


def _migrate_tilts_to_devices(conn):
    """Migrate existing tilts to devices table if not already done."""
    from sqlalchemy import text

    # Check if tilts table exists and has data
    try:
        result = conn.execute(text("SELECT COUNT(*) FROM tilts"))
        tilt_count = result.scalar()
    except Exception:
        # tilts table doesn't exist (fresh install)
        return

    if tilt_count == 0:
        return  # No tilts to migrate

    # Check if these tilts are already in devices
    result = conn.execute(text("""
        SELECT COUNT(*) FROM devices d
        WHERE EXISTS (SELECT 1 FROM tilts t WHERE t.id = d.id)
    """))
    migrated_count = result.scalar()

    if migrated_count >= tilt_count:
        print(f"Migration: Tilts already migrated ({migrated_count} devices)")
        return

    # Migrate tilts that aren't in devices yet
    # Build calibration_data as JSON string manually (portable, no json_object)
    conn.execute(text("""
        INSERT OR IGNORE INTO devices (
            id, device_type, name, color, mac, beer_name,
            original_gravity, calibration_type, calibration_data,
            last_seen, created_at
        )
        SELECT
            id,
            'tilt',
            COALESCE(color, id),
            color,
            mac,
            beer_name,
            original_gravity,
            'offset',
            '{"sg_offset": 0, "temp_offset": 0}',
            last_seen,
            CURRENT_TIMESTAMP
        FROM tilts
        WHERE id NOT IN (SELECT id FROM devices)
    """))
    print(f"Migration: Migrated {tilt_count - migrated_count} tilts to devices table")


def _migrate_add_reading_columns(conn):
    """Add new columns to readings table for multi-hydrometer support."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    # Check if readings table exists
    if "readings" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    columns = [c["name"] for c in inspector.get_columns("readings")]

    new_columns = [
        ("device_type", "TEXT DEFAULT 'tilt'"),
        ("angle", "REAL"),
        ("battery_voltage", "REAL"),
        ("battery_percent", "INTEGER"),
        ("source_protocol", "TEXT DEFAULT 'ble'"),
        ("status", "TEXT DEFAULT 'valid'"),
        ("is_pre_filtered", "INTEGER DEFAULT 0"),
    ]

    for col_name, col_def in new_columns:
        if col_name not in columns:
            try:
                conn.execute(text(f"ALTER TABLE readings ADD COLUMN {col_name} {col_def}"))
                print(f"Migration: Added {col_name} column to readings table")
            except Exception as e:
                # Column might already exist in some edge cases
                print(f"Migration: Skipping {col_name} - {e}")
```

**Step 2: Update init_db - migrations BEFORE create_all for existing DBs**

Replace the `init_db` function:

```python
async def init_db():
    """Initialize database with migrations.

    Order matters:
    1. Run migrations first (for existing DBs with data)
    2. Then create_all (for new tables/columns in fresh DBs)
    3. Then data migrations (copy tilts to devices)
    """
    async with engine.begin() as conn:
        # Step 1: Schema migrations for existing DBs
        await conn.run_sync(_migrate_add_original_gravity)
        await conn.run_sync(_migrate_create_devices_table)
        await conn.run_sync(_migrate_add_reading_columns)

        # Step 2: Create any missing tables (fresh install or new models)
        # NOTE: Device model should be imported AFTER migrations for existing DBs
        await conn.run_sync(Base.metadata.create_all)

        # Step 3: Data migrations (requires both tables to exist)
        await conn.run_sync(_migrate_tilts_to_devices)
```

**Step 3: Test migration on COPY of database (non-destructive)**

```bash
# Create test copy - DO NOT run on production DB
cd /home/ladmin/Projects/tilt_ui
cp data/tiltui.db data/tiltui_backup.db 2>/dev/null || true
python3 -c "import asyncio; from backend.database import init_db; asyncio.run(init_db()); print('Migration OK')"
```

Expected: Migration messages and `Migration OK`

**Step 4: Verify data migrated**

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('data/tiltui.db')
devices = conn.execute('SELECT id, device_type, name FROM devices').fetchall()
print(f'Devices: {devices}')
conn.close()
"
```

Expected: List of devices (may be empty on fresh install)

**Step 5: Commit**

```bash
git add backend/database.py
git commit -m "feat(db): add migrations for multi-hydrometer support

- Create devices table before create_all (handles existing DBs)
- Migrate tilts to devices with data check (idempotent)
- Add new columns to readings table
- Non-destructive: preserves all existing data
- No SQLite json_object (portable across versions)"
```

---

### Task 2.3: Integrate Device Model into Main Models

**Files:**
- Modify: `backend/models.py`
- Delete: `backend/models_device.py`

**Step 1: Move Device class to models.py**

Add after `Tilt` class in `backend/models.py` (copy from models_device.py):

```python
# Add import at top
import json
from typing import Any

# Add Device class after Tilt class
class Device(Base):
    """Universal hydrometer device registry."""
    __tablename__ = "devices"
    # ... (full class from models_device.py)
```

**Step 2: Update imports in models.py**

Ensure `Text` is imported:

```python
from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
```

**Step 3: Delete temporary model file**

```bash
rm backend/models_device.py
```

**Step 4: Verify model loads from main models**

Run: `cd /home/ladmin/Projects/tilt_ui && python3 -c "from backend.models import Device, Tilt; print('OK')"`

Expected: `OK`

**Step 5: Commit**

```bash
git add backend/models.py
git rm backend/models_device.py
git commit -m "refactor(models): merge Device model into main models.py"
```

---

## Phase 3: Adapter Infrastructure

### Task 3.1: Create Base Adapter

**Files:**
- Create: `backend/ingest/adapters/__init__.py`
- Create: `backend/ingest/adapters/base.py`

**Step 1: Create adapters package**

```python
# backend/ingest/adapters/__init__.py
"""Device format adapters for normalizing hydrometer payloads."""

from .base import BaseAdapter

__all__ = ["BaseAdapter"]
```

**Step 2: Create BaseAdapter abstract class**

```python
# backend/ingest/adapters/base.py
"""Base adapter class for device format normalization."""

from abc import ABC, abstractmethod
from typing import Optional

from ..base import GravityUnit, HydrometerReading, TemperatureUnit


class BaseAdapter(ABC):
    """Base class for device format adapters.

    Each adapter normalizes a specific device's payload format into
    a universal HydrometerReading.
    """

    device_type: str  # "tilt", "ispindel", "floaty", "gravitymon"

    # Native units for this device type
    native_gravity_unit: GravityUnit = GravityUnit.SG
    native_temp_unit: TemperatureUnit = TemperatureUnit.CELSIUS

    @abstractmethod
    def can_handle(self, payload: dict) -> bool:
        """Check if this adapter can handle the payload.

        Args:
            payload: Raw payload dictionary

        Returns:
            True if this adapter should process the payload
        """
        pass

    @abstractmethod
    def parse(self, payload: dict, source_protocol: str) -> Optional[HydrometerReading]:
        """Parse payload into HydrometerReading.

        Adapters MUST:
        - Set gravity_raw/temperature_raw with original values
        - Set gravity_unit/temperature_unit to indicate native units
        - Set status=UNCALIBRATED if angle-only (no pre-calculated gravity)
        - Set is_pre_filtered=True if device sends smoothed/filtered values
        - NOT fill gravity/temperature - calibration service does that

        Args:
            payload: Raw payload dictionary
            source_protocol: How payload was received ("http", "mqtt", "ble", etc.)

        Returns:
            HydrometerReading or None if parsing fails
        """
        pass
```

**Step 3: Update ingest __init__.py exports**

Add to `backend/ingest/__init__.py`:

```python
from .adapters import BaseAdapter

# Update __all__
__all__ = [
    "BaseAdapter",
    "GravityUnit",
    # ... rest of exports
]
```

**Step 4: Verify imports work**

Run: `cd /home/ladmin/Projects/tilt_ui && python3 -c "from backend.ingest.adapters import BaseAdapter; print('OK')"`

Expected: `OK`

**Step 5: Commit**

```bash
git add backend/ingest/adapters/
git add backend/ingest/__init__.py
git commit -m "feat(ingest): add BaseAdapter abstract class

- Abstract methods: can_handle(), parse()
- Native unit declarations per device type
- Documentation for adapter contract"
```

---

### Task 3.2: Implement Tilt Adapter

**Files:**
- Create: `backend/ingest/adapters/tilt.py`
- Create: `backend/tests/test_adapters.py`

**Step 1: Write failing test first**

```python
# backend/tests/test_adapters.py
"""Tests for device format adapters."""

from datetime import datetime, timezone

import pytest
from backend.ingest.adapters.tilt import TiltAdapter
from backend.ingest.base import GravityUnit, ReadingStatus, TemperatureUnit


class TestTiltAdapter:
    """Test Tilt BLE adapter."""

    @pytest.fixture
    def adapter(self):
        return TiltAdapter()

    def test_can_handle_tilt_payload(self, adapter):
        payload = {
            "color": "RED",
            "mac": "AA:BB:CC:DD:EE:FF",
            "temp_f": 68.5,
            "sg": 1.050,
            "rssi": -65,
        }
        assert adapter.can_handle(payload) is True

    def test_cannot_handle_ispindel_payload(self, adapter):
        payload = {
            "name": "iSpindel",
            "angle": 25.5,
            "temperature": 20.0,
        }
        assert adapter.can_handle(payload) is False

    def test_parse_tilt_reading(self, adapter):
        payload = {
            "color": "RED",
            "mac": "AA:BB:CC:DD:EE:FF",
            "temp_f": 68.5,
            "sg": 1.050,
            "rssi": -65,
        }
        reading = adapter.parse(payload, source_protocol="ble")

        assert reading is not None
        assert reading.device_id == "RED"
        assert reading.device_type == "tilt"
        assert reading.gravity_raw == 1.050
        assert reading.temperature_raw == 68.5
        assert reading.temperature_unit == TemperatureUnit.FAHRENHEIT
        assert reading.gravity_unit == GravityUnit.SG
        assert reading.rssi == -65
        assert reading.source_protocol == "ble"
        assert reading.status == ReadingStatus.VALID

    def test_parse_stores_raw_payload(self, adapter):
        payload = {"color": "BLUE", "temp_f": 70.0, "sg": 1.045, "rssi": -70}
        reading = adapter.parse(payload, source_protocol="ble")
        assert reading.raw_payload == payload

    def test_parse_missing_sg_returns_incomplete(self, adapter):
        payload = {"color": "RED", "temp_f": 68.5, "rssi": -65}
        reading = adapter.parse(payload, source_protocol="ble")
        assert reading.status == ReadingStatus.INCOMPLETE
        assert reading.gravity_raw is None

    def test_parse_missing_color_returns_none(self, adapter):
        payload = {"temp_f": 68.5, "sg": 1.050, "rssi": -65}
        reading = adapter.parse(payload, source_protocol="ble")
        assert reading is None
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ladmin/Projects/tilt_ui && python3 -m pytest backend/tests/test_adapters.py -v`

Expected: FAIL (TiltAdapter not found)

**Step 3: Implement TiltAdapter**

```python
# backend/ingest/adapters/tilt.py
"""Tilt Hydrometer BLE adapter."""

from datetime import datetime, timezone
from typing import Optional

from ..base import GravityUnit, HydrometerReading, ReadingStatus, TemperatureUnit
from .base import BaseAdapter


class TiltAdapter(BaseAdapter):
    """Adapter for Tilt Hydrometer BLE iBeacon format.

    Tilt sends:
    - color: Device color identifier (RED, GREEN, etc.)
    - mac: BLE MAC address
    - temp_f: Temperature in Fahrenheit
    - sg: Specific gravity
    - rssi: Signal strength
    """

    device_type = "tilt"
    native_gravity_unit = GravityUnit.SG
    native_temp_unit = TemperatureUnit.FAHRENHEIT

    def can_handle(self, payload: dict) -> bool:
        """Tilt payloads have 'color' and 'sg' fields."""
        return "color" in payload and ("sg" in payload or "temp_f" in payload)

    def parse(self, payload: dict, source_protocol: str) -> Optional[HydrometerReading]:
        """Parse Tilt BLE reading."""
        color = payload.get("color")
        if not color:
            return None

        # Extract values
        sg = payload.get("sg")
        temp_f = payload.get("temp_f")
        rssi = payload.get("rssi")
        mac = payload.get("mac")

        # Determine status
        if sg is None and temp_f is None:
            status = ReadingStatus.INVALID
        elif sg is None or temp_f is None:
            status = ReadingStatus.INCOMPLETE
        else:
            status = ReadingStatus.VALID

        # Parse numeric values safely
        gravity_raw = None
        if sg is not None:
            try:
                gravity_raw = float(sg)
            except (ValueError, TypeError):
                pass

        temperature_raw = None
        if temp_f is not None:
            try:
                temperature_raw = float(temp_f)
            except (ValueError, TypeError):
                pass

        return HydrometerReading(
            device_id=color,
            device_type=self.device_type,
            timestamp=datetime.now(timezone.utc),
            # Raw values - calibration service will fill normalized values
            gravity_raw=gravity_raw,
            gravity_unit=self.native_gravity_unit,
            temperature_raw=temperature_raw,
            temperature_unit=self.native_temp_unit,
            # Metadata
            rssi=rssi,
            # Processing
            status=status,
            is_pre_filtered=False,
            source_protocol=source_protocol,
            raw_payload=payload,
        )
```

**Step 4: Update adapters __init__.py**

```python
# backend/ingest/adapters/__init__.py
"""Device format adapters for normalizing hydrometer payloads."""

from .base import BaseAdapter
from .tilt import TiltAdapter

__all__ = ["BaseAdapter", "TiltAdapter"]
```

**Step 5: Run tests to verify they pass**

Run: `cd /home/ladmin/Projects/tilt_ui && python3 -m pytest backend/tests/test_adapters.py -v`

Expected: All tests pass

**Step 6: Commit**

```bash
git add backend/ingest/adapters/tilt.py
git add backend/ingest/adapters/__init__.py
git add backend/tests/test_adapters.py
git commit -m "feat(ingest): add TiltAdapter for BLE format

- Parses Tilt BLE payload (color, sg, temp_f, rssi)
- Sets correct status based on available fields
- Stores raw_payload for debugging"
```

---

### Task 3.3: Implement iSpindel Adapter

**Files:**
- Create: `backend/ingest/adapters/ispindel.py`
- Modify: `backend/tests/test_adapters.py`

**Step 1: Add iSpindel tests**

Add to `backend/tests/test_adapters.py`:

```python
from backend.ingest.adapters.ispindel import ISpindelAdapter


class TestISpindelAdapter:
    """Test iSpindel HTTP/MQTT adapter."""

    @pytest.fixture
    def adapter(self):
        return ISpindelAdapter()

    def test_can_handle_ispindel_payload(self, adapter):
        payload = {
            "name": "iSpindel001",
            "angle": 25.5,
            "temperature": 20.0,
            "battery": 3.8,
        }
        assert adapter.can_handle(payload) is True

    def test_cannot_handle_tilt_payload(self, adapter):
        payload = {"color": "RED", "sg": 1.050}
        assert adapter.can_handle(payload) is False

    def test_parse_with_precalculated_gravity(self, adapter):
        payload = {
            "name": "iSpindel001",
            "ID": 12345,
            "angle": 25.5,
            "temperature": 20.0,
            "gravity": 1.048,
            "battery": 3.8,
            "RSSI": -72,
        }
        reading = adapter.parse(payload, source_protocol="http")

        assert reading is not None
        assert reading.device_id == "12345"
        assert reading.device_type == "ispindel"
        assert reading.gravity_raw == 1.048
        assert reading.angle == 25.5
        assert reading.temperature_raw == 20.0
        assert reading.temperature_unit == TemperatureUnit.CELSIUS
        assert reading.battery_voltage is not None
        assert reading.status == ReadingStatus.VALID

    def test_parse_angle_only_uncalibrated(self, adapter):
        """iSpindel without pre-calculated gravity needs polynomial calibration."""
        payload = {
            "name": "iSpindel001",
            "angle": 25.5,
            "temperature": 20.0,
            "battery": 3.8,
        }
        reading = adapter.parse(payload, source_protocol="http")

        assert reading is not None
        assert reading.gravity_raw is None
        assert reading.angle == 25.5
        assert reading.status == ReadingStatus.UNCALIBRATED

    def test_parse_gravity_zero_treated_as_uncalibrated(self, adapter):
        """Gravity of 0 means iSpindel hasn't been calibrated."""
        payload = {
            "name": "iSpindel001",
            "angle": 25.5,
            "temperature": 20.0,
            "gravity": 0,
            "battery": 3.8,
        }
        reading = adapter.parse(payload, source_protocol="http")

        assert reading.gravity_raw is None
        assert reading.status == ReadingStatus.UNCALIBRATED

    def test_parse_plato_unit_detection(self, adapter):
        """Detect Plato gravity unit from payload."""
        payload = {
            "name": "iSpindel001",
            "angle": 25.5,
            "temperature": 20.0,
            "gravity": 12.5,
            "gravity-unit": "P",
            "battery": 3.8,
        }
        reading = adapter.parse(payload, source_protocol="http")

        assert reading.gravity_unit == GravityUnit.PLATO
        assert reading.gravity_raw == 12.5

    def test_parse_uses_id_over_name(self, adapter):
        """Prefer numeric ID over name for device_id."""
        payload = {
            "name": "MySpindel",
            "ID": 98765,
            "angle": 25.5,
            "temperature": 20.0,
        }
        reading = adapter.parse(payload, source_protocol="http")
        assert reading.device_id == "98765"

    def test_parse_falls_back_to_name(self, adapter):
        """Use name as device_id when ID not present."""
        payload = {
            "name": "MySpindel",
            "angle": 25.5,
            "temperature": 20.0,
        }
        reading = adapter.parse(payload, source_protocol="http")
        assert reading.device_id == "MySpindel"
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/ladmin/Projects/tilt_ui && python3 -m pytest backend/tests/test_adapters.py::TestISpindelAdapter -v`

Expected: FAIL (ISpindelAdapter not found)

**Step 3: Implement ISpindelAdapter**

```python
# backend/ingest/adapters/ispindel.py
"""iSpindel WiFi hydrometer adapter."""

from datetime import datetime, timezone
from typing import Optional

from ..base import GravityUnit, HydrometerReading, ReadingStatus, TemperatureUnit
from ..units import normalize_battery
from .base import BaseAdapter


class ISpindelAdapter(BaseAdapter):
    """Adapter for iSpindel JSON format.

    iSpindel sends via HTTP POST or MQTT:
    - name: Device name
    - ID: Chip ID (numeric, preferred for device_id)
    - angle: Tilt angle in degrees
    - temperature: Temperature in Celsius
    - gravity: Pre-calculated gravity (may be 0 if not calibrated)
    - gravity-unit: "G" for SG, "P" for Plato (optional)
    - battery: Battery voltage
    - RSSI: WiFi signal strength
    """

    device_type = "ispindel"
    native_gravity_unit = GravityUnit.SG
    native_temp_unit = TemperatureUnit.CELSIUS

    def can_handle(self, payload: dict) -> bool:
        """iSpindel payloads have 'angle' and 'name' fields."""
        return "angle" in payload and "name" in payload

    def parse(self, payload: dict, source_protocol: str) -> Optional[HydrometerReading]:
        """Parse iSpindel JSON payload."""
        # Device ID: prefer numeric ID, fall back to name
        device_id = payload.get("ID") or payload.get("id") or payload.get("name")
        if not device_id:
            return None
        device_id = str(device_id)

        # Detect gravity unit
        gravity_unit = GravityUnit.SG
        unit_field = payload.get("gravity-unit", payload.get("temp_units", ""))
        if unit_field == "P":
            gravity_unit = GravityUnit.PLATO

        # Extract gravity (may be None or 0 = uncalibrated)
        gravity_raw = None
        raw_gravity = payload.get("gravity")
        if raw_gravity is not None:
            try:
                gravity_raw = float(raw_gravity)
                if gravity_raw == 0:
                    gravity_raw = None  # 0 means uncalibrated
            except (ValueError, TypeError):
                pass

        # Extract angle
        angle = None
        raw_angle = payload.get("angle")
        if raw_angle is not None:
            try:
                angle = float(raw_angle)
            except (ValueError, TypeError):
                pass

        # Extract temperature
        temperature_raw = None
        raw_temp = payload.get("temperature", payload.get("temp"))
        if raw_temp is not None:
            try:
                temperature_raw = float(raw_temp)
            except (ValueError, TypeError):
                pass

        # Determine status
        if gravity_raw is None and angle is not None:
            status = ReadingStatus.UNCALIBRATED
        elif gravity_raw is None and angle is None:
            status = ReadingStatus.INCOMPLETE
        else:
            status = ReadingStatus.VALID

        # Battery normalization
        battery_voltage, battery_percent = None, None
        raw_battery = payload.get("battery")
        if raw_battery is not None:
            try:
                battery_voltage, battery_percent = normalize_battery(
                    float(raw_battery),
                    self.device_type,
                    is_percent=False
                )
            except (ValueError, TypeError):
                pass

        # RSSI
        rssi = payload.get("RSSI")
        if rssi is not None:
            try:
                rssi = int(rssi)
            except (ValueError, TypeError):
                rssi = None

        return HydrometerReading(
            device_id=device_id,
            device_type=self.device_type,
            timestamp=datetime.now(timezone.utc),
            # Raw values
            gravity_raw=gravity_raw,
            gravity_unit=gravity_unit,
            temperature_raw=temperature_raw,
            temperature_unit=self.native_temp_unit,
            angle=angle,
            # Metadata
            rssi=rssi,
            battery_voltage=battery_voltage,
            battery_percent=battery_percent,
            # Processing
            status=status,
            is_pre_filtered=False,
            source_protocol=source_protocol,
            raw_payload=payload,
        )
```

**Step 4: Update adapters __init__.py**

```python
# backend/ingest/adapters/__init__.py
"""Device format adapters for normalizing hydrometer payloads."""

from .base import BaseAdapter
from .ispindel import ISpindelAdapter
from .tilt import TiltAdapter

__all__ = ["BaseAdapter", "ISpindelAdapter", "TiltAdapter"]
```

**Step 5: Run tests to verify they pass**

Run: `cd /home/ladmin/Projects/tilt_ui && python3 -m pytest backend/tests/test_adapters.py -v`

Expected: All tests pass

**Step 6: Commit**

```bash
git add backend/ingest/adapters/ispindel.py
git add backend/ingest/adapters/__init__.py
git add backend/tests/test_adapters.py
git commit -m "feat(ingest): add ISpindelAdapter for HTTP/MQTT format

- Parses angle, temperature, gravity, battery
- Detects Plato vs SG gravity unit
- Handles uncalibrated (gravity=0) as UNCALIBRATED status
- Prefers chip ID over name for device_id"
```

---

### Task 3.4: Implement GravityMon Adapter

**Files:**
- Create: `backend/ingest/adapters/gravitymon.py`
- Modify: `backend/tests/test_adapters.py`

**Step 1: Add GravityMon tests**

Add to `backend/tests/test_adapters.py`:

```python
from backend.ingest.adapters.gravitymon import GravityMonAdapter


class TestGravityMonAdapter:
    """Test GravityMon adapter (iSpindel-compatible with extensions)."""

    @pytest.fixture
    def adapter(self):
        return GravityMonAdapter()

    def test_can_handle_gravitymon_payload(self, adapter):
        payload = {
            "name": "GravityMon",
            "angle": 25.5,
            "temperature": 20.0,
            "corr-gravity": 1.048,
            "run-time": 12345,
        }
        assert adapter.can_handle(payload) is True

    def test_cannot_handle_plain_ispindel(self, adapter):
        """Plain iSpindel without GravityMon extensions."""
        payload = {
            "name": "iSpindel001",
            "angle": 25.5,
            "temperature": 20.0,
            "gravity": 1.048,
        }
        assert adapter.can_handle(payload) is False

    def test_parse_with_corrected_gravity(self, adapter):
        """GravityMon corr-gravity is pre-filtered."""
        payload = {
            "name": "GravityMon",
            "ID": 54321,
            "angle": 25.5,
            "temperature": 20.0,
            "corr-gravity": 1.048,
            "run-time": 12345,
        }
        reading = adapter.parse(payload, source_protocol="mqtt")

        assert reading is not None
        assert reading.device_type == "gravitymon"
        assert reading.gravity_raw == 1.048
        assert reading.is_pre_filtered is True  # Key difference from iSpindel

    def test_parse_falls_back_to_gravity(self, adapter):
        """Use gravity field if corr-gravity not present."""
        payload = {
            "name": "GravityMon",
            "angle": 25.5,
            "temperature": 20.0,
            "gravity": 1.050,
            "run-time": 12345,
        }
        reading = adapter.parse(payload, source_protocol="http")

        assert reading.gravity_raw == 1.050
        assert reading.is_pre_filtered is False  # Regular gravity, not filtered
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/ladmin/Projects/tilt_ui && python3 -m pytest backend/tests/test_adapters.py::TestGravityMonAdapter -v`

Expected: FAIL

**Step 3: Implement GravityMonAdapter**

```python
# backend/ingest/adapters/gravitymon.py
"""GravityMon adapter (extended iSpindel format)."""

from datetime import datetime, timezone
from typing import Optional

from ..base import GravityUnit, HydrometerReading, ReadingStatus, TemperatureUnit
from ..units import normalize_battery
from .base import BaseAdapter


class GravityMonAdapter(BaseAdapter):
    """Adapter for GravityMon JSON format.

    GravityMon extends iSpindel format with:
    - corr-gravity: Corrected/filtered gravity value
    - run-time: Uptime in seconds
    - Other extended fields

    GravityMon can send already-filtered values, so we mark
    is_pre_filtered=True when corr-gravity is present.
    """

    device_type = "gravitymon"
    native_gravity_unit = GravityUnit.SG
    native_temp_unit = TemperatureUnit.CELSIUS

    def can_handle(self, payload: dict) -> bool:
        """GravityMon has iSpindel base fields plus extensions."""
        has_ispindel_base = "angle" in payload and "name" in payload
        has_gravitymon_ext = "corr-gravity" in payload or "run-time" in payload
        return has_ispindel_base and has_gravitymon_ext

    def parse(self, payload: dict, source_protocol: str) -> Optional[HydrometerReading]:
        """Parse GravityMon JSON payload."""
        device_id = payload.get("ID") or payload.get("id") or payload.get("name")
        if not device_id:
            return None
        device_id = str(device_id)

        # Detect gravity unit
        gravity_unit = GravityUnit.SG
        unit_field = payload.get("gravity-unit", "")
        if unit_field == "P":
            gravity_unit = GravityUnit.PLATO

        # Check for pre-filtered corrected gravity
        is_pre_filtered = "corr-gravity" in payload
        gravity_raw = None

        # Prefer corr-gravity, fall back to gravity
        raw_gravity = payload.get("corr-gravity") or payload.get("gravity")
        if raw_gravity is not None:
            try:
                gravity_raw = float(raw_gravity)
                if gravity_raw == 0:
                    gravity_raw = None
            except (ValueError, TypeError):
                pass

        # If we used regular gravity (not corr-gravity), not pre-filtered
        if gravity_raw is not None and "corr-gravity" not in payload:
            is_pre_filtered = False

        # Extract angle
        angle = None
        raw_angle = payload.get("angle")
        if raw_angle is not None:
            try:
                angle = float(raw_angle)
            except (ValueError, TypeError):
                pass

        # Extract temperature
        temperature_raw = None
        raw_temp = payload.get("temperature", payload.get("temp"))
        if raw_temp is not None:
            try:
                temperature_raw = float(raw_temp)
            except (ValueError, TypeError):
                pass

        # Determine status
        if gravity_raw is None and angle is not None:
            status = ReadingStatus.UNCALIBRATED
        elif gravity_raw is None and angle is None:
            status = ReadingStatus.INCOMPLETE
        else:
            status = ReadingStatus.VALID

        # Battery normalization
        battery_voltage, battery_percent = None, None
        raw_battery = payload.get("battery")
        if raw_battery is not None:
            try:
                battery_voltage, battery_percent = normalize_battery(
                    float(raw_battery),
                    self.device_type,
                    is_percent=False
                )
            except (ValueError, TypeError):
                pass

        # RSSI
        rssi = payload.get("RSSI")
        if rssi is not None:
            try:
                rssi = int(rssi)
            except (ValueError, TypeError):
                rssi = None

        return HydrometerReading(
            device_id=device_id,
            device_type=self.device_type,
            timestamp=datetime.now(timezone.utc),
            gravity_raw=gravity_raw,
            gravity_unit=gravity_unit,
            temperature_raw=temperature_raw,
            temperature_unit=self.native_temp_unit,
            angle=angle,
            rssi=rssi,
            battery_voltage=battery_voltage,
            battery_percent=battery_percent,
            status=status,
            is_pre_filtered=is_pre_filtered,
            source_protocol=source_protocol,
            raw_payload=payload,
        )
```

**Step 4: Update adapters __init__.py**

```python
# backend/ingest/adapters/__init__.py
"""Device format adapters for normalizing hydrometer payloads."""

from .base import BaseAdapter
from .gravitymon import GravityMonAdapter
from .ispindel import ISpindelAdapter
from .tilt import TiltAdapter

__all__ = ["BaseAdapter", "GravityMonAdapter", "ISpindelAdapter", "TiltAdapter"]
```

**Step 5: Run tests**

Run: `cd /home/ladmin/Projects/tilt_ui && python3 -m pytest backend/tests/test_adapters.py -v`

Expected: All tests pass

**Step 6: Commit**

```bash
git add backend/ingest/adapters/gravitymon.py
git add backend/ingest/adapters/__init__.py
git add backend/tests/test_adapters.py
git commit -m "feat(ingest): add GravityMonAdapter for extended iSpindel format

- Detects GravityMon by corr-gravity or run-time fields
- Sets is_pre_filtered=True when corr-gravity present
- Falls back to gravity field if corr-gravity missing"
```

---

### Task 3.5: Create Adapter Router

**Files:**
- Create: `backend/ingest/router.py`
- Create: `backend/tests/test_router.py`

**Step 1: Write failing test**

```python
# backend/tests/test_router.py
"""Tests for adapter routing."""

import pytest
from backend.ingest.router import AdapterRouter


class TestAdapterRouter:
    """Test payload routing to correct adapter."""

    @pytest.fixture
    def router(self):
        return AdapterRouter()

    def test_routes_tilt_payload(self, router):
        payload = {"color": "RED", "sg": 1.050, "temp_f": 68.0}
        reading = router.route(payload, source_protocol="ble")

        assert reading is not None
        assert reading.device_type == "tilt"

    def test_routes_ispindel_payload(self, router):
        payload = {"name": "iSpindel", "angle": 25.5, "temperature": 20.0}
        reading = router.route(payload, source_protocol="http")

        assert reading is not None
        assert reading.device_type == "ispindel"

    def test_routes_gravitymon_payload(self, router):
        payload = {
            "name": "GravityMon",
            "angle": 25.5,
            "temperature": 20.0,
            "corr-gravity": 1.048,
        }
        reading = router.route(payload, source_protocol="mqtt")

        assert reading is not None
        assert reading.device_type == "gravitymon"

    def test_gravitymon_takes_precedence_over_ispindel(self, router):
        """GravityMon should be checked before iSpindel due to specificity."""
        payload = {
            "name": "GravityMon",
            "angle": 25.5,
            "temperature": 20.0,
            "gravity": 1.048,
            "run-time": 12345,
        }
        reading = router.route(payload, source_protocol="http")

        # Should be GravityMon, not iSpindel
        assert reading.device_type == "gravitymon"

    def test_unknown_payload_returns_none(self, router):
        payload = {"unknown_field": "value"}
        reading = router.route(payload, source_protocol="http")

        assert reading is None

    def test_empty_payload_returns_none(self, router):
        reading = router.route({}, source_protocol="http")
        assert reading is None
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ladmin/Projects/tilt_ui && python3 -m pytest backend/tests/test_router.py -v`

Expected: FAIL

**Step 3: Implement AdapterRouter**

```python
# backend/ingest/router.py
"""Routes incoming payloads to appropriate adapters."""

import logging
from typing import Optional

from .adapters import GravityMonAdapter, ISpindelAdapter, TiltAdapter
from .base import HydrometerReading

logger = logging.getLogger(__name__)


class AdapterRouter:
    """Routes incoming payloads to the appropriate device adapter.

    Adapters are checked in order of specificity - more specific adapters
    (like GravityMon) are checked before more general ones (like iSpindel).
    """

    def __init__(self):
        # Order matters: more specific adapters first
        self.adapters = [
            GravityMonAdapter(),  # Check before iSpindel (extends it)
            ISpindelAdapter(),
            TiltAdapter(),
        ]

    def route(self, payload: dict, source_protocol: str) -> Optional[HydrometerReading]:
        """Find matching adapter and parse payload.

        Args:
            payload: Raw payload dictionary
            source_protocol: How payload was received

        Returns:
            HydrometerReading or None if no adapter matches
        """
        if not payload:
            return None

        for adapter in self.adapters:
            if adapter.can_handle(payload):
                try:
                    reading = adapter.parse(payload, source_protocol)
                    if reading:
                        logger.debug(
                            "Routed payload to %s adapter: device_id=%s",
                            adapter.device_type,
                            reading.device_id,
                        )
                        return reading
                except Exception as e:
                    logger.warning(
                        "Adapter %s failed to parse payload: %s",
                        adapter.device_type,
                        e,
                    )
                    continue

        logger.debug("No adapter found for payload: %s", payload)
        return None
```

**Step 4: Update ingest __init__.py**

Add to `backend/ingest/__init__.py`:

```python
from .router import AdapterRouter

# Add to __all__
__all__ = [
    "AdapterRouter",
    # ... rest
]
```

**Step 5: Run tests**

Run: `cd /home/ladmin/Projects/tilt_ui && python3 -m pytest backend/tests/test_router.py -v`

Expected: All tests pass

**Step 6: Commit**

```bash
git add backend/ingest/router.py
git add backend/ingest/__init__.py
git add backend/tests/test_router.py
git commit -m "feat(ingest): add AdapterRouter for payload dispatch

- Routes payloads to correct adapter based on content
- GravityMon checked before iSpindel (specificity order)
- Returns None for unknown payload formats"
```

---

## Phase 4: Calibration Service Enhancement

### Task 4.1: Extend Calibration Service for Multi-Device

**Files:**
- Modify: `backend/services/calibration.py`
- Create: `backend/tests/test_calibration.py`

**Step 1: Write tests for new calibration features**

```python
# backend/tests/test_calibration.py
"""Tests for calibration service."""

import pytest
from backend.ingest.base import (
    GravityUnit,
    HydrometerReading,
    ReadingStatus,
    TemperatureUnit,
)
from backend.services.calibration import CalibrationService
from datetime import datetime, timezone


class TestUnitConversion:
    """Test unit conversion in calibration service."""

    def test_convert_celsius_to_fahrenheit(self):
        service = CalibrationService()
        reading = HydrometerReading(
            device_id="test",
            device_type="ispindel",
            timestamp=datetime.now(timezone.utc),
            temperature_raw=20.0,
            temperature_unit=TemperatureUnit.CELSIUS,
        )

        result = service.convert_units(reading)

        assert result.temperature == pytest.approx(68.0, abs=0.1)

    def test_fahrenheit_unchanged(self):
        service = CalibrationService()
        reading = HydrometerReading(
            device_id="test",
            device_type="tilt",
            timestamp=datetime.now(timezone.utc),
            temperature_raw=68.0,
            temperature_unit=TemperatureUnit.FAHRENHEIT,
        )

        result = service.convert_units(reading)

        assert result.temperature == 68.0

    def test_convert_plato_to_sg(self):
        service = CalibrationService()
        reading = HydrometerReading(
            device_id="test",
            device_type="ispindel",
            timestamp=datetime.now(timezone.utc),
            gravity_raw=12.0,  # ~1.048 SG
            gravity_unit=GravityUnit.PLATO,
        )

        result = service.convert_units(reading)

        assert result.gravity == pytest.approx(1.048, abs=0.002)

    def test_sg_unchanged(self):
        service = CalibrationService()
        reading = HydrometerReading(
            device_id="test",
            device_type="tilt",
            timestamp=datetime.now(timezone.utc),
            gravity_raw=1.050,
            gravity_unit=GravityUnit.SG,
        )

        result = service.convert_units(reading)

        assert result.gravity == 1.050


class TestPolynomialCalibration:
    """Test polynomial calibration for iSpindel-style devices."""

    def test_apply_polynomial_linear(self):
        service = CalibrationService()
        # Simple linear: y = 0.001x + 1.0 (1 degree at x=50 gives SG 1.050)
        coefficients = [0.001, 1.0]

        result = service.apply_polynomial(50.0, coefficients)

        assert result == pytest.approx(1.050, abs=0.001)

    def test_apply_polynomial_quadratic(self):
        service = CalibrationService()
        # Quadratic: typical iSpindel calibration
        coefficients = [0.00001, 0.001, 0.9]

        result = service.apply_polynomial(25.0, coefficients)

        # 0.00001*625 + 0.001*25 + 0.9 = 0.00625 + 0.025 + 0.9 = 0.93125
        assert result == pytest.approx(0.93125, abs=0.0001)

    def test_apply_polynomial_empty_coefficients(self):
        service = CalibrationService()

        result = service.apply_polynomial(25.0, [])

        # No coefficients = no transformation
        assert result == 0.0
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/ladmin/Projects/tilt_ui && python3 -m pytest backend/tests/test_calibration.py -v`

Expected: FAIL (new methods don't exist)

**Step 3: Extend CalibrationService**

Add new methods to `backend/services/calibration.py` (before the class closing):

```python
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
```

**Step 4: Add required import at top of calibration.py**

```python
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..ingest.base import HydrometerReading
```

**Step 5: Run tests**

Run: `cd /home/ladmin/Projects/tilt_ui && python3 -m pytest backend/tests/test_calibration.py -v`

Expected: All tests pass

**Step 6: Commit**

```bash
git add backend/services/calibration.py
git add backend/tests/test_calibration.py
git commit -m "feat(calibration): add unit conversion and polynomial calibration

- convert_units(): C->F, Plato->SG
- apply_polynomial(): iSpindel-style angle->SG calibration
- Preserves existing linear interpolation for Tilt offset calibration"
```

---

## Phase 5: HTTP Ingest Endpoints

### Task 5.1: Create Ingest Router

**Files:**
- Create: `backend/routers/ingest.py`
- Modify: `backend/main.py` (register router)

**Step 1: Create ingest router**

```python
# backend/routers/ingest.py
"""HTTP endpoints for hydrometer data ingestion."""

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request

from ..ingest import AdapterRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ingest", tags=["ingest"])

# Global adapter router instance
adapter_router = AdapterRouter()


@router.post("/generic")
async def ingest_generic(
    request: Request,
    x_device_token: Optional[str] = Header(None, alias="X-Device-Token"),
):
    """Auto-detect payload format and ingest.

    Accepts JSON payloads from any supported device type.
    The adapter router will detect the format and parse accordingly.
    """
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(400, f"Invalid JSON: {e}")

    reading = adapter_router.route(payload, source_protocol="http")

    if not reading:
        raise HTTPException(400, "Unknown payload format")

    logger.info(
        "Ingested %s reading from device %s",
        reading.device_type,
        reading.device_id,
    )

    # TODO: Process through calibration and store
    # For now, just acknowledge receipt

    return {
        "status": "ok",
        "device_type": reading.device_type,
        "device_id": reading.device_id,
    }


@router.post("/ispindel")
async def ingest_ispindel(
    request: Request,
    x_device_token: Optional[str] = Header(None, alias="X-Device-Token"),
):
    """Receive iSpindel HTTP POST.

    iSpindel devices should configure their HTTP endpoint to POST here.
    """
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(400, f"Invalid JSON: {e}")

    reading = adapter_router.route(payload, source_protocol="http")

    if not reading or reading.device_type not in ("ispindel", "gravitymon"):
        raise HTTPException(400, "Invalid iSpindel payload")

    logger.info(
        "Ingested iSpindel reading: device=%s, angle=%s, gravity=%s",
        reading.device_id,
        reading.angle,
        reading.gravity_raw,
    )

    return {"status": "ok"}


@router.post("/gravitymon")
async def ingest_gravitymon(
    request: Request,
    x_device_token: Optional[str] = Header(None, alias="X-Device-Token"),
):
    """Receive GravityMon HTTP POST."""
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(400, f"Invalid JSON: {e}")

    reading = adapter_router.route(payload, source_protocol="http")

    if not reading:
        raise HTTPException(400, "Invalid GravityMon payload")

    logger.info(
        "Ingested GravityMon reading: device=%s, gravity=%s, filtered=%s",
        reading.device_id,
        reading.gravity_raw,
        reading.is_pre_filtered,
    )

    return {"status": "ok"}
```

**Step 2: Register router in main.py**

Add import after other router imports (around line 19):

```python
from .routers import alerts, ambient, config, control, ha, ingest, system, tilts
```

Add router registration after other routers (around line 147):

```python
app.include_router(ingest.router)
```

**Step 3: Verify server starts**

Run: `cd /home/ladmin/Projects/tilt_ui && timeout 3 python3 -c "from backend.main import app; print('App loads OK')" || echo "Timeout OK"`

Expected: `App loads OK`

**Step 4: Commit**

```bash
git add backend/routers/ingest.py
git add backend/main.py
git commit -m "feat(api): add HTTP ingest endpoints

- POST /api/ingest/generic - auto-detect format
- POST /api/ingest/ispindel - iSpindel-specific
- POST /api/ingest/gravitymon - GravityMon-specific
- Optional X-Device-Token header for auth"
```

---

## Remaining Phases (Summary)

The following phases complete the implementation. Each follows the same TDD pattern:

### Phase 6: Full Reading Pipeline
- Task 6.1: Create IngestManager class
- Task 6.2: Wire calibration to reading pipeline
- Task 6.3: Store readings to database
- Task 6.4: Broadcast to WebSocket

### Phase 7: Legacy Compatibility
- Task 7.1: Implement reading_to_legacy_format()
- Task 7.2: Update handle_tilt_reading() to use new pipeline
- Task 7.3: Add backward-compatible WebSocket broadcast

### Phase 8: Device Registration API
- Task 8.1: CRUD endpoints for devices
- Task 8.2: Calibration data endpoints
- Task 8.3: Device auto-registration on first reading

### Phase 9: MQTT Support (Optional)
- Task 9.1: MQTT subscriber implementation
- Task 9.2: Broker configuration
- Task 9.3: Topic routing

### Phase 10: UI Updates
- Task 10.1: Device management page
- Task 10.2: Calibration wizard
- Task 10.3: Multi-device dashboard

---

## Verification Checklist

After completing all phases, verify:

- [ ] `python3 -m pytest backend/tests/ -v` - All tests pass
- [ ] Existing Tilt readings still work via BLE
- [ ] iSpindel HTTP POST ingests correctly
- [ ] Database migration preserves existing data
- [ ] WebSocket broadcasts include device_type field
- [ ] Legacy UI still displays Tilt cards correctly

---

## References

- Design: `docs/plans/2025-11-29-multi-hydrometer-design.md`
- iSpindel Format: https://opensourcedistilling.com/ispindel/
- GravityMon Format: https://gravitymon.com/doc-data.html

---

## Appendix: Review Fixes Applied

| Issue | Resolution |
|-------|------------|
| **Migration order bug** | Migrations run BEFORE `create_all`; Device model in separate file initially; data migration checks for existing rows, not just table |
| **Type mismatch (Text vs JSON)** | Device model uses Text column with `@property` getter/setter for JSON serialization; no SQLAlchemy JSON type needed |
| **Destructive test step** | Removed `rm -f data/tiltui.db`; test uses backup copy instead |
| **create_all + migrations combo** | init_db order: schema migrations → create_all → data migrations; idempotent checks prevent conflicts |
| **Test directory discovery** | Added `conftest.py` with sys.path setup; tests in `backend/tests/` package |
| **SQLite json_object compatibility** | Replaced with plain JSON string literal `'{"sg_offset": 0, "temp_offset": 0}'` |

**No downgrade path defined** - noted as acceptable for this migration since it's additive (new table, new columns). Rollback would require manual SQL.
