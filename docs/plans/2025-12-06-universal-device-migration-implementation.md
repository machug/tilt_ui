# Universal Device Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate legacy `tilts` table to universal `devices` table, eliminate dual-table synchronization bugs, and create single API surface for all hydrometer device types.

**Architecture:** Single-table architecture where `devices` is the source of truth. All device types (Tilt, iSpindel, GravityMon, future) stored in one table with `device_type` differentiation. Legacy `tilts` table and `/api/tilts/*` endpoints completely removed. Reading handler simplified to single-table logic.

**Tech Stack:** SQLAlchemy (async), FastAPI, SQLite, Svelte 5, TypeScript

**Related Documents:**
- Design: `docs/plans/2025-12-06-universal-device-migration-design.md`
- Current PR: #73 (Multi-Device Support)

---

## Pre-Implementation Checklist

Before starting implementation:
- [ ] Current PR #73 is merged or closed
- [ ] Working on clean branch from master
- [ ] All existing tests passing
- [ ] Database backup taken (if using production data)

---

## Phase 1: Database Migration & Core Models

### Task 1: Create Migration Function

**Files:**
- Modify: `backend/database.py` (after existing migrations)

**Step 1: Add migration function before `init_db()`**

Add this function after the existing migration functions, before `async def init_db()`:

```python
def _migrate_tilts_to_devices_final(conn):
    """Final migration: Consolidate Tilt table into Device table.

    This migration:
    1. Copies all Tilt records to Device table (if not already there)
    2. Updates foreign keys: tilt_id -> device_id in readings and calibration_points
    3. Drops the legacy tilts table

    Idempotent: Can run multiple times safely.
    """
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    # Check if tilts table exists
    if "tilts" not in inspector.get_table_names():
        print("Migration: tilts table already migrated")
        return

    print("Migration: Starting Tilt -> Device consolidation")

    # Step 1: Migrate Tilt data to Device table
    # Uses INSERT OR IGNORE to handle devices that already exist (from PR #73)
    result = conn.execute(text("""
        INSERT OR IGNORE INTO devices (
            id, device_type, name, display_name, beer_name, original_gravity,
            native_gravity_unit, native_temp_unit, calibration_type,
            mac, color, last_seen, paired, paired_at, created_at
        )
        SELECT
            id,
            'tilt' as device_type,
            color as name,
            NULL as display_name,
            beer_name,
            original_gravity,
            'sg' as native_gravity_unit,
            'F' as native_temp_unit,
            'linear' as calibration_type,
            mac,
            color,
            last_seen,
            paired,
            paired_at,
            CURRENT_TIMESTAMP as created_at
        FROM tilts
    """))
    migrated_count = result.rowcount
    print(f"Migration: Copied {migrated_count} Tilt records to Device table")

    # Step 2: Update foreign keys in readings table
    # Check if column needs renaming
    readings_columns = [c["name"] for c in inspector.get_columns("readings")]
    if "tilt_id" in readings_columns:
        # SQLite doesn't support RENAME COLUMN directly in old versions
        # We need to check SQLite version and use appropriate method
        version_result = conn.execute(text("SELECT sqlite_version()"))
        sqlite_version = version_result.scalar()
        major, minor, _ = sqlite_version.split('.')

        if int(major) >= 3 and int(minor) >= 25:
            # SQLite 3.25+ supports ALTER TABLE RENAME COLUMN
            conn.execute(text("ALTER TABLE readings RENAME COLUMN tilt_id TO device_id"))
            print("Migration: Renamed readings.tilt_id to device_id")
        else:
            # Older SQLite: recreate table
            print("Migration: Recreating readings table with device_id column")
            conn.execute(text("""
                CREATE TABLE readings_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id VARCHAR(100),
                    timestamp DATETIME NOT NULL,
                    sg_raw FLOAT,
                    sg_calibrated FLOAT,
                    temp_raw FLOAT,
                    temp_calibrated FLOAT,
                    rssi INTEGER,
                    status VARCHAR(20),
                    sg_filtered FLOAT,
                    temp_filtered FLOAT,
                    confidence FLOAT,
                    sg_rate FLOAT,
                    temp_rate FLOAT,
                    is_anomaly BOOLEAN,
                    anomaly_score FLOAT,
                    anomaly_reasons TEXT,
                    FOREIGN KEY(device_id) REFERENCES devices(id)
                )
            """))
            conn.execute(text("INSERT INTO readings_new SELECT * FROM readings"))
            conn.execute(text("DROP TABLE readings"))
            conn.execute(text("ALTER TABLE readings_new RENAME TO readings"))
            print("Migration: Recreated readings table with device_id")

    # Step 3: Update foreign keys in calibration_points table
    calibration_columns = [c["name"] for c in inspector.get_columns("calibration_points")]
    if "tilt_id" in calibration_columns:
        version_result = conn.execute(text("SELECT sqlite_version()"))
        sqlite_version = version_result.scalar()
        major, minor, _ = sqlite_version.split('.')

        if int(major) >= 3 and int(minor) >= 25:
            conn.execute(text("ALTER TABLE calibration_points RENAME COLUMN tilt_id TO device_id"))
            print("Migration: Renamed calibration_points.tilt_id to device_id")
        else:
            print("Migration: Recreating calibration_points table with device_id column")
            conn.execute(text("""
                CREATE TABLE calibration_points_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id VARCHAR(100) NOT NULL,
                    type VARCHAR(20) NOT NULL,
                    raw_value FLOAT NOT NULL,
                    reference_value FLOAT NOT NULL,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY(device_id) REFERENCES devices(id) ON DELETE CASCADE
                )
            """))
            conn.execute(text("INSERT INTO calibration_points_new SELECT * FROM calibration_points"))
            conn.execute(text("DROP TABLE calibration_points"))
            conn.execute(text("ALTER TABLE calibration_points_new RENAME TO calibration_points"))
            print("Migration: Recreated calibration_points table with device_id")

    # Step 4: Drop tilts table
    conn.execute(text("DROP TABLE tilts"))
    print("Migration: Dropped tilts table - migration complete!")
```

**Step 2: Call migration from init_db()**

Find the `async def init_db()` function and add the migration call in the appropriate location. Add it after `_migrate_tilts_to_devices` and before `_migrate_add_cooler_entity`:

```python
async def init_db():
    async with engine.begin() as conn:
        # ... existing migrations ...

        # Step 4: Data migrations
        await conn.run_sync(_migrate_tilts_to_devices)
        await conn.run_sync(_migrate_mark_outliers_invalid)
        await conn.run_sync(_migrate_fix_temp_outlier_detection)
        await conn.run_sync(_migrate_tilts_to_devices_final)  # ← ADD THIS LINE

    # Add cooler support (runs outside conn.begin() context since it has its own)
    await _migrate_add_cooler_entity()
    # ... rest of init_db ...
```

**Step 3: Test migration on empty database**

```bash
# Backup current database
cp data/fermentation.db data/fermentation.db.backup

# Delete database to test fresh migration
rm data/fermentation.db

# Run app to trigger migrations
python -m backend.main &
sleep 3
pkill -f "python -m backend.main"

# Check migration ran successfully
sqlite3 data/fermentation.db "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
# Expected: devices table exists, tilts table does NOT exist
```

**Step 4: Test migration on database with Tilt data**

```bash
# Restore backup
mv data/fermentation.db.backup data/fermentation.db

# Run migration
python -m backend.main &
sleep 3
pkill -f "python -m backend.main"

# Verify data migrated
sqlite3 data/fermentation.db "SELECT COUNT(*) FROM devices WHERE device_type='tilt';"
# Expected: Count matches original Tilt count

sqlite3 data/fermentation.db "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
# Expected: tilts table does NOT exist
```

**Step 5: Commit**

```bash
git add backend/database.py
git commit -m "feat: add final Tilt->Device migration function

- Migrates all Tilt records to Device table
- Updates foreign keys (tilt_id -> device_id)
- Drops legacy tilts table
- Handles both old and new SQLite versions
- Idempotent migration (safe to run multiple times)"
```

---

### Task 2: Update Models - Remove Tilt Model

**Files:**
- Modify: `backend/models.py`

**Step 1: Remove Tilt SQLAlchemy model**

Find and delete the entire `Tilt` class (around line 37-53):

```python
# DELETE THIS ENTIRE CLASS:
class Tilt(Base):
    __tablename__ = "tilts"
    # ... entire class definition ...
```

**Step 2: Remove Tilt Pydantic schemas**

Find and delete these Pydantic schema classes (around line 506-563):

```python
# DELETE THESE CLASSES:
class TiltBase(BaseModel):
    # ...

class TiltCreate(TiltBase):
    # ...

class TiltUpdate(BaseModel):
    # ...

class TiltResponse(TiltBase):
    # ...
```

**KEEP `TiltReading`** - This is the scanner output format, not a DB model (around line 548).

**Step 3: Update CalibrationPoint model**

Find the `CalibrationPoint` class and update the foreign key:

```python
class CalibrationPoint(Base):
    """Calibration point for device (was: tilt)."""
    __tablename__ = "calibration_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # OLD: tilt_id: Mapped[str] = mapped_column(String(50), ForeignKey("tilts.id"), nullable=False)
    # NEW:
    device_id: Mapped[str] = mapped_column(String(100), ForeignKey("devices.id"), nullable=False)

    type: Mapped[str] = mapped_column(String(20), nullable=False)  # 'sg' or 'temp'
    raw_value: Mapped[float] = mapped_column(Float, nullable=False)
    reference_value: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # OLD: tilt: Mapped["Tilt"] = relationship(back_populates="calibration_points")
    # NEW:
    device: Mapped["Device"] = relationship(back_populates="calibration_points")
```

**Step 4: Update Reading model**

Find the `Reading` class and update the foreign key:

```python
class Reading(Base):
    """Hydrometer reading (from any device type)."""
    __tablename__ = "readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # OLD: tilt_id: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey("tilts.id"))
    # NEW:
    device_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("devices.id"))

    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    # ... rest of fields unchanged ...

    # OLD: tilt: Mapped[Optional["Tilt"]] = relationship(back_populates="readings")
    # NEW:
    device: Mapped[Optional["Device"]] = relationship(back_populates="readings")
```

**Step 5: Update Device model relationships**

Find the `Device` class and add the relationships if not already present:

```python
class Device(Base):
    """Universal hydrometer device registry."""
    __tablename__ = "devices"

    # ... existing fields ...

    # Relationships
    readings: Mapped[list["Reading"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    calibration_points: Mapped[list["CalibrationPoint"]] = relationship(back_populates="device", cascade="all, delete-orphan")
```

**Step 6: Verify no Tilt references remain**

```bash
grep -n "class Tilt" backend/models.py
# Expected: Only "TiltReading" should appear, not "class Tilt"

grep -n "tilt_id" backend/models.py
# Expected: No matches (all changed to device_id)
```

**Step 7: Commit**

```bash
git add backend/models.py
git commit -m "refactor: remove Tilt model, update foreign keys to device_id

- Remove Tilt SQLAlchemy model (migrated to Device)
- Remove TiltBase, TiltCreate, TiltUpdate, TiltResponse schemas
- Keep TiltReading (scanner output format)
- Update CalibrationPoint.tilt_id -> device_id
- Update Reading.tilt_id -> device_id
- Add relationships to Device model"
```

---

### Task 3: Simplify Reading Handler

**Files:**
- Modify: `backend/main.py`

**Step 1: Remove Tilt import**

Find the import line (around line 19):

```python
# OLD:
from .models import Device, Reading, Tilt, serialize_datetime_to_utc

# NEW:
from .models import Device, Reading, serialize_datetime_to_utc
```

**Step 2: Simplify handle_tilt_reading function**

Find the `handle_tilt_reading` function (around line 73) and replace with simplified version:

```python
async def handle_tilt_reading(reading: TiltReading):
    """Process Tilt BLE reading and store if paired.

    Simplified: Only manages Device table (no dual-table sync).
    """
    async with async_session_factory() as session:
        # Get or create Device record (single source of truth)
        device = await session.get(Device, reading.id)
        if not device:
            # Create new Tilt device
            device = Device(
                id=reading.id,
                device_type='tilt',
                name=reading.color,
                native_temp_unit='F',
                native_gravity_unit='sg',
                calibration_type='linear',
                paired=False,  # New devices start unpaired
            )
            session.add(device)

        # Update device metadata from reading
        timestamp = datetime.now(timezone.utc)
        device.last_seen = timestamp
        device.color = reading.color
        device.mac = reading.mac

        # Convert Tilt's Fahrenheit to Celsius immediately
        temp_raw_c = (reading.temp_f - 32) * 5.0 / 9.0

        # Apply calibration in Celsius
        sg_calibrated, temp_calibrated_c = await calibration_service.calibrate_reading(
            session, reading.id, reading.sg, temp_raw_c
        )

        # Validate reading for outliers (physical impossibility check)
        # Valid SG range: 0.500-1.200 (beer is typically 1.000-1.120)
        # Valid temp range: 0-100°C (freezing to boiling)
        status = "valid"
        if not (0.500 <= sg_calibrated <= 1.200) or not (0.0 <= temp_calibrated_c <= 100.0):
            status = "invalid"

        # Only store readings if device is paired
        if device.paired:
            # Process through ML pipeline if available
            ml_outputs = {}
            if ml_pipeline_manager:
                try:
                    ml_outputs = await ml_pipeline_manager.process_reading(
                        device_id=reading.id,
                        sg=sg_calibrated,
                        temp=temp_calibrated_c,
                        timestamp=timestamp,
                    )
                except Exception as e:
                    logger.error(f"ML pipeline failed for {reading.id}: {e}")

            # Create reading record
            db_reading = Reading(
                device_id=reading.id,
                timestamp=timestamp,
                sg_raw=reading.sg,
                sg_calibrated=sg_calibrated,
                temp_raw=temp_raw_c,
                temp_calibrated=temp_calibrated_c,
                rssi=reading.rssi,
                status=status,
                # ML outputs
                sg_filtered=ml_outputs.get("sg_filtered"),
                temp_filtered=ml_outputs.get("temp_filtered"),
                confidence=ml_outputs.get("confidence"),
                sg_rate=ml_outputs.get("sg_rate"),
                temp_rate=ml_outputs.get("temp_rate"),
                is_anomaly=ml_outputs.get("is_anomaly", False),
                anomaly_score=ml_outputs.get("anomaly_score"),
                anomaly_reasons=json.dumps(ml_outputs.get("anomaly_reasons", [])) if ml_outputs.get("anomaly_reasons") else None,
            )
            session.add(db_reading)

        await session.commit()

        # Update in-memory latest_readings cache
        latest_readings[reading.id] = {
            "device_id": reading.id,
            "color": reading.color,
            "sg": sg_calibrated,
            "temp": temp_calibrated_c,
            "timestamp": serialize_datetime_to_utc(timestamp),
            "paired": device.paired,
            "mac": reading.mac,
        }

        # Broadcast to WebSocket clients
        await manager.broadcast(latest_readings[reading.id])
```

**Step 3: Remove device_utils import**

Find the import (around line 30):

```python
# DELETE THIS LINE:
from .device_utils import create_tilt_device_record  # noqa: E402
```

**Step 4: Verify changes**

```bash
grep -n "from.*Tilt" backend/main.py
# Expected: No matches (Tilt import removed)

grep -n "create_tilt_device_record" backend/main.py
# Expected: No matches (function call removed)

grep -n "device_type='tilt'" backend/main.py
# Expected: One match in handle_tilt_reading
```

**Step 5: Commit**

```bash
git add backend/main.py
git commit -m "refactor: simplify reading handler to single-table logic

- Remove Tilt model import and dual-table sync
- Create/update only Device table (single source of truth)
- Remove device_utils.create_tilt_device_record usage
- Eliminates data consistency bugs from dual-table management"
```

---

## Phase 2: Universal Device Endpoints

### Task 4: Add Universal Pairing Endpoints

**Files:**
- Modify: `backend/routers/devices.py`

**Step 1: Add required imports**

At the top of `devices.py`, ensure these imports exist:

```python
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Device, serialize_datetime_to_utc
from ..state import latest_readings
from ..websocket import manager
```

**Step 2: Add pair_device endpoint**

Add this endpoint after the existing device CRUD endpoints (around line 200):

```python
@router.post("/{device_id}/pair", response_model=DeviceResponse)
async def pair_device(device_id: str, db: AsyncSession = Depends(get_db)):
    """Pair any device type to enable reading storage.

    Works for Tilt, iSpindel, GravityMon, and future device types.
    """
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    device.paired = True
    device.paired_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(device)

    # Update in-memory cache (if device has readings)
    if device_id in latest_readings:
        latest_readings[device_id]["paired"] = True
        await manager.broadcast(latest_readings[device_id])

    return DeviceResponse.from_orm_with_calibration(device)
```

**Step 3: Add unpair_device endpoint**

Add immediately after `pair_device`:

```python
@router.post("/{device_id}/unpair", response_model=DeviceResponse)
async def unpair_device(device_id: str, db: AsyncSession = Depends(get_db)):
    """Unpair device to stop reading storage.

    Works for all device types.
    """
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    device.paired = False
    device.paired_at = None
    await db.commit()
    await db.refresh(device)

    # Update in-memory cache (if device has readings)
    if device_id in latest_readings:
        latest_readings[device_id]["paired"] = False
        await manager.broadcast(latest_readings[device_id])

    return DeviceResponse.from_orm_with_calibration(device)
```

**Step 4: Test pairing endpoints**

Create a simple test file to verify endpoints work:

```bash
# Start server
uvicorn backend.main:app --reload &

# Wait for startup
sleep 3

# Test pairing (replace DEVICE_ID with actual device ID from your DB)
curl -X POST http://localhost:8080/api/devices/BLUE/pair

# Expected: 200 OK with device JSON, paired=true

# Test unpairing
curl -X POST http://localhost:8080/api/devices/BLUE/unpair

# Expected: 200 OK with device JSON, paired=false

# Stop server
pkill -f uvicorn
```

**Step 5: Commit**

```bash
git add backend/routers/devices.py
git commit -m "feat: add universal pairing endpoints to devices router

- POST /api/devices/{id}/pair - works for all device types
- POST /api/devices/{id}/unpair - works for all device types
- Updates in-memory cache and broadcasts via WebSocket
- Replaces legacy /api/tilts/{id}/pair endpoints"
```

---

### Task 5: Add Calibration Endpoints to Devices Router

**Files:**
- Modify: `backend/routers/devices.py`

**Step 1: Add CalibrationPoint imports**

At the top of `devices.py`, add to imports:

```python
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from ..models import Device, CalibrationPoint, serialize_datetime_to_utc
```

Also import the Pydantic schemas (if not already imported):

```python
# Should be in models.py around line 600
from ..models import CalibrationPointCreate, CalibrationPointResponse
```

**Step 2: Add get calibration endpoint**

Add after the pairing endpoints:

```python
@router.get("/{device_id}/calibration", response_model=list[CalibrationPointResponse])
async def get_device_calibration(device_id: str, db: AsyncSession = Depends(get_db)):
    """Get calibration points for any device type."""
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    result = await db.execute(
        select(CalibrationPoint)
        .where(CalibrationPoint.device_id == device_id)
        .order_by(CalibrationPoint.type, CalibrationPoint.raw_value)
    )
    return result.scalars().all()
```

**Step 3: Add create calibration point endpoint**

```python
@router.post("/{device_id}/calibration", response_model=CalibrationPointResponse)
async def add_device_calibration_point(
    device_id: str,
    point: CalibrationPointCreate,
    db: AsyncSession = Depends(get_db)
):
    """Add calibration point for any device type."""
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    calibration_point = CalibrationPoint(
        device_id=device_id,
        **point.model_dump()
    )
    db.add(calibration_point)
    await db.commit()
    await db.refresh(calibration_point)

    return calibration_point
```

**Step 4: Add delete calibration endpoint**

```python
@router.delete("/{device_id}/calibration/{type}")
async def clear_device_calibration(
    device_id: str,
    type: str,
    db: AsyncSession = Depends(get_db)
):
    """Clear calibration points for a specific type (sg or temp)."""
    if type not in ["sg", "temp"]:
        raise HTTPException(status_code=400, detail="Type must be 'sg' or 'temp'")

    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    await db.execute(
        delete(CalibrationPoint)
        .where(CalibrationPoint.device_id == device_id)
        .where(CalibrationPoint.type == type)
    )
    await db.commit()

    return {"message": f"Cleared {type} calibration for device {device_id}"}
```

**Step 5: Add get readings endpoint**

```python
from sqlalchemy import desc

@router.get("/{device_id}/readings", response_model=list[ReadingResponse])
async def get_device_readings(
    device_id: str,
    limit: int = Query(default=100, le=1000),
    db: AsyncSession = Depends(get_db)
):
    """Get recent readings for any device type."""
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    result = await db.execute(
        select(Reading)
        .where(Reading.device_id == device_id)
        .order_by(desc(Reading.timestamp))
        .limit(limit)
    )
    return result.scalars().all()
```

**Step 6: Verify imports are complete**

Check that these models are imported:

```python
from ..models import (
    Device,
    CalibrationPoint,
    Reading,
    CalibrationPointCreate,
    CalibrationPointResponse,
    ReadingResponse,
    serialize_datetime_to_utc
)
```

**Step 7: Commit**

```bash
git add backend/routers/devices.py
git commit -m "feat: add calibration and readings endpoints to devices router

- GET /api/devices/{id}/calibration - list points
- POST /api/devices/{id}/calibration - add point
- DELETE /api/devices/{id}/calibration/{type} - clear type
- GET /api/devices/{id}/readings - get device readings
- All endpoints work for any device type (universal)"
```

---

### Task 6: Remove Tilts Router

**Files:**
- Delete: `backend/routers/tilts.py`
- Modify: `backend/main.py`

**Step 1: Remove tilts router registration from main.py**

Find the router imports (around line 21):

```python
# OLD:
from .routers import alerts, ambient, batches, config, control, devices, ha, ingest, maintenance, recipes, system, tilts

# NEW:
from .routers import alerts, ambient, batches, config, control, devices, ha, ingest, maintenance, recipes, system
```

Find the router registration (around line 69):

```python
# DELETE THIS LINE:
app.include_router(tilts.router)
```

**Step 2: Delete tilts router file**

```bash
rm backend/routers/tilts.py
```

**Step 3: Verify tilts router removed**

```bash
ls backend/routers/tilts.py
# Expected: No such file

grep -r "tilts.router" backend/
# Expected: No matches

grep -r "from.*tilts import" backend/
# Expected: No matches
```

**Step 4: Test server starts without errors**

```bash
uvicorn backend.main:app --reload &
sleep 3

# Check for startup errors
curl http://localhost:8080/docs
# Expected: 200 OK, Swagger UI loads

pkill -f uvicorn
```

**Step 5: Commit**

```bash
git add backend/routers/tilts.py backend/main.py
git commit -m "refactor: remove legacy tilts router

- Delete backend/routers/tilts.py entirely (~350 lines)
- Remove tilts router registration from main.py
- All functionality migrated to /api/devices/* endpoints"
```

---

### Task 7: Delete Legacy Helper File

**Files:**
- Delete: `backend/device_utils.py`

**Step 1: Verify no references remain**

```bash
grep -r "device_utils" backend/
# Expected: No matches (already removed from main.py in Task 3)

grep -r "create_tilt_device_record" backend/
# Expected: No matches
```

**Step 2: Delete file**

```bash
rm backend/device_utils.py
```

**Step 3: Commit**

```bash
git add backend/device_utils.py
git commit -m "refactor: remove legacy device_utils helper

- Delete backend/device_utils.py (~50 lines)
- Logic absorbed into Device model and reading handler"
```

---

## Phase 3: Security Fix

### Task 8: Fix Command Injection Vulnerability

**Files:**
- Modify: `backend/routers/system.py`

**Step 1: Replace shutil.which with absolute paths**

Find the imports (around line 5):

```python
# OLD:
import shutil
import socket
import subprocess

# NEW:
import socket
import subprocess
from pathlib import Path
```

**Step 2: Define secure command paths**

Add constants at the top of the file (around line 20, after imports):

```python
# System command paths - hardcoded for security (prevents PATH manipulation attacks)
TIMEDATECTL_PATH = "/usr/bin/timedatectl"
SUDO_PATH = "/usr/bin/sudo"
```

**Step 3: Update get_timezone function**

Find `get_timezone()` (around line 154) and replace:

```python
@router.get("/timezone")
async def get_timezone():
    """Get current timezone."""
    # Validate timedatectl exists
    if not Path(TIMEDATECTL_PATH).exists():
        logger.error(f"timedatectl not found at {TIMEDATECTL_PATH}")
        return {"timezone": "UTC"}

    try:
        result = subprocess.run(
            [TIMEDATECTL_PATH, "show", "--property=Timezone", "--value"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            tz = result.stdout.strip()
            logger.debug(f"Returning timezone from timedatectl: {tz}")
            return {"timezone": tz}

        # Fallback to /etc/timezone
        tz_file = Path("/etc/timezone")
        if tz_file.exists():
            tz = tz_file.read_text().strip()
            logger.debug(f"Returning timezone from /etc/timezone: {tz}")
            return {"timezone": tz}
    except Exception as e:
        logger.error(f"Error getting timezone: {e}")

    logger.warning("Falling back to UTC timezone")
    return {"timezone": "UTC"}
```

**Step 4: Update set_timezone function**

Find `set_timezone()` (around line 183) and replace:

```python
@router.put("/timezone")
async def set_timezone(update: TimezoneUpdate, request: Request):
    """Set system timezone."""
    if not is_local_request(request):
        raise HTTPException(
            status_code=403,
            detail="System controls only available from local network",
        )

    # Validate timezone exists
    tz_path = Path(f"/usr/share/zoneinfo/{update.timezone}")
    if not tz_path.exists():
        raise HTTPException(status_code=400, detail=f"Unknown timezone: {update.timezone}")

    # Validate required binaries exist
    if not Path(SUDO_PATH).exists():
        raise HTTPException(status_code=500, detail="sudo not found")
    if not Path(TIMEDATECTL_PATH).exists():
        raise HTTPException(status_code=500, detail="timedatectl not found")

    try:
        subprocess.run(
            [SUDO_PATH, TIMEDATECTL_PATH, "set-timezone", update.timezone],
            check=True,
            timeout=10,
        )
        return {"timezone": update.timezone}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Failed to set timezone: {e}")
```

**Step 5: Remove debug logging**

Remove or reduce verbose debug logs (lines 166-169, 175):

```python
# Remove these lines:
logger.debug(f"timedatectl returncode: {result.returncode}, stdout: '{result.stdout.strip()}', stderr: '{result.stderr.strip()}'")
logger.debug(f"Returning timezone from timedatectl: {tz}")
logger.debug(f"Returning timezone from /etc/timezone: {tz}")

# Or change to debug level only (keep if useful for troubleshooting)
```

**Step 6: Test security fix**

```bash
# Test that timezone endpoints still work
uvicorn backend.main:app --reload &
sleep 3

curl http://localhost:8080/api/system/timezone
# Expected: {"timezone": "America/New_York"} or similar

pkill -f uvicorn

# Verify no shutil.which usage
grep "shutil.which" backend/routers/system.py
# Expected: No matches
```

**Step 7: Commit**

```bash
git add backend/routers/system.py
git commit -m "security: fix command injection vulnerability in system.py

- Replace shutil.which() with hardcoded absolute paths
- Prevents PATH manipulation attacks
- Validate binaries exist before execution
- Add proper error handling for missing binaries
- Remove verbose debug logging"
```

---

## Phase 4: Frontend Updates

### Task 9: Update Frontend API Client

**Files:**
- Modify: `frontend/src/lib/api/devices.ts`

**Step 1: Update pairing functions**

Find `pairDevice` and `unpairDevice` functions (around line 30):

```typescript
// OLD:
export async function pairDevice(deviceId: string): Promise<DeviceResponse> {
	// Use legacy /api/tilts endpoint for pairing (still works for all devices)
	return fetchApi(`/api/tilts/${deviceId}/pair`, {
		method: 'POST'
	});
}

export async function unpairDevice(deviceId: string): Promise<DeviceResponse> {
	// Use legacy /api/tilts endpoint for unpairing (still works for all devices)
	return fetchApi(`/api/tilts/${deviceId}/unpair`, {
		method: 'POST'
	});
}

// NEW:
export async function pairDevice(deviceId: string): Promise<DeviceResponse> {
	return fetchApi(`/api/devices/${deviceId}/pair`, {
		method: 'POST'
	});
}

export async function unpairDevice(deviceId: string): Promise<DeviceResponse> {
	return fetchApi(`/api/devices/${deviceId}/unpair`, {
		method: 'POST'
	});
}
```

**Step 2: Verify changes**

```bash
grep "/api/tilts" frontend/src/lib/api/devices.ts
# Expected: No matches
```

**Step 3: Build frontend to check for errors**

```bash
cd frontend
npm run build
cd ..
```

**Step 4: Commit**

```bash
git add frontend/src/lib/api/devices.ts
git commit -m "refactor: update pairing API calls to use /api/devices

- Change pairDevice to use /api/devices/{id}/pair
- Change unpairDevice to use /api/devices/{id}/unpair
- Remove references to legacy /api/tilts endpoints"
```

---

### Task 10: Update Calibration Page

**Files:**
- Modify: `frontend/src/routes/calibration/+page.svelte`

**Step 1: Update device fetch endpoint**

Find the device fetching code (around line 30):

```typescript
// OLD:
const response = await fetch('/api/tilts');

// NEW:
const response = await fetch('/api/devices?paired_only=true');
```

**Step 2: Update calibration fetch endpoint**

Find calibration point fetching (around line 50):

```typescript
// OLD:
const response = await fetch(`/api/tilts/${selectedTiltId}/calibration`);

// NEW:
const response = await fetch(`/api/devices/${selectedDeviceId}/calibration`);
```

**Step 3: Update add calibration endpoint**

Find calibration point creation (around line 80):

```typescript
// OLD:
const response = await fetch(`/api/tilts/${selectedTiltId}/calibration`, {
	method: 'POST',
	headers: { 'Content-Type': 'application/json' },
	body: JSON.stringify(point)
});

// NEW:
const response = await fetch(`/api/devices/${selectedDeviceId}/calibration`, {
	method: 'POST',
	headers: { 'Content-Type': 'application/json' },
	body: JSON.stringify(point)
});
```

**Step 4: Update clear calibration endpoint**

Find calibration clearing (around line 100):

```typescript
// OLD:
const response = await fetch(`/api/tilts/${selectedTiltId}/calibration/${type}`, {
	method: 'DELETE'
});

// NEW:
const response = await fetch(`/api/devices/${selectedDeviceId}/calibration/${type}`, {
	method: 'DELETE'
});
```

**Step 5: Update UI labels (optional but recommended)**

Find UI labels and update:

```svelte
<!-- OLD: -->
<label>Select Tilt:</label>

<!-- NEW: -->
<label>Select Device:</label>
```

**Step 6: Verify no /api/tilts references remain**

```bash
grep "/api/tilts" frontend/src/routes/calibration/+page.svelte
# Expected: No matches
```

**Step 7: Build and test**

```bash
cd frontend
npm run build
cd ..
```

**Step 8: Commit**

```bash
git add frontend/src/routes/calibration/+page.svelte
git commit -m "refactor: update calibration page to use /api/devices

- Update all API calls from /api/tilts to /api/devices
- Change UI label from 'Select Tilt' to 'Select Device'
- Works for all device types (Tilt, iSpindel, GravityMon)"
```

---

### Task 11: Remove Legacy Frontend Store

**Files:**
- Delete: `frontend/src/lib/stores/tilts.svelte.ts` (if exists)

**Step 1: Check if file exists and is used**

```bash
ls frontend/src/lib/stores/tilts.svelte.ts
# If file doesn't exist, skip this task

# If it exists, check for usage:
grep -r "tilts.svelte" frontend/src/
```

**Step 2: If file exists and is not used, delete it**

```bash
rm frontend/src/lib/stores/tilts.svelte.ts
```

**Step 3: If file is used, refactor to use devices store instead**

Replace imports:
```typescript
// OLD:
import { tiltsStore } from '$lib/stores/tilts.svelte';

// NEW:
import { deviceCache } from '$lib/state';
```

**Step 4: Commit (if file was deleted)**

```bash
git add frontend/src/lib/stores/tilts.svelte.ts
git commit -m "refactor: remove legacy tilts store

- Delete frontend/src/lib/stores/tilts.svelte.ts
- All functionality available via deviceCache store"
```

---

## Phase 5: Testing & Validation

### Task 12: Update Backend Tests

**Files:**
- Modify: `backend/tests/test_pairing_endpoints.py`
- Modify: `backend/tests/test_models.py`
- Delete: `backend/tests/test_tilts_api.py` (if exists)

**Step 1: Update test_pairing_endpoints.py**

Replace all `Tilt` model references with `Device`:

```python
# OLD imports:
from backend.models import Tilt, Device, Batch

# NEW imports:
from backend.models import Device, Batch

# Update test fixtures - remove Tilt creation, use Device only
# OLD:
tilt = Tilt(id="test-tilt", color="RED", paired=False)
device = Device(id="test-tilt", device_type="tilt", name="RED", paired=False)
test_db.add_all([tilt, device])

# NEW:
device = Device(id="test-tilt", device_type="tilt", name="RED", paired=False)
test_db.add(device)
```

Update test API calls:

```python
# OLD:
response = await client.post("/api/tilts/test-tilt/pair")

# NEW:
response = await client.post("/api/devices/test-tilt/pair")
```

**Step 2: Update test_models.py**

Remove Tilt model tests:

```python
# DELETE tests like:
def test_tilt_creation():
    # ...

def test_tilt_response_serialization():
    # ...
```

Keep Device model tests, update if needed.

**Step 3: Delete test_tilts_api.py if it exists**

```bash
rm backend/tests/test_tilts_api.py
```

**Step 4: Run tests**

```bash
pytest backend/tests/ -v
```

**Step 5: Fix any failing tests**

Common issues:
- Tilt model references → Change to Device
- /api/tilts/ endpoints → Change to /api/devices/
- tilt_id foreign keys → Change to device_id

**Step 6: Commit**

```bash
git add backend/tests/
git commit -m "test: update tests for universal device architecture

- Update test_pairing_endpoints to use Device model
- Remove Tilt model from test fixtures
- Update API endpoint paths to /api/devices
- Remove legacy test_tilts_api.py
- All tests passing"
```

---

### Task 13: Manual Testing Checklist

**No files to modify - validation only**

**Step 1: Test fresh installation**

```bash
# Backup current database
cp data/fermentation.db data/fermentation.db.pre-test

# Delete database
rm data/fermentation.db

# Start server
uvicorn backend.main:app --reload &
sleep 5

# Check migration ran successfully
sqlite3 data/fermentation.db "SELECT name FROM sqlite_master WHERE type='table';"
# Expected: devices table exists, tilts table does NOT exist

# Stop server
pkill -f uvicorn
```

**Step 2: Test existing installation migration**

```bash
# Restore database with old schema (if you have one)
# cp data/fermentation.db.with-tilts data/fermentation.db

# Start server to trigger migration
uvicorn backend.main:app --reload &
sleep 5

# Verify migration
sqlite3 data/fermentation.db "SELECT COUNT(*) FROM devices WHERE device_type='tilt';"
# Expected: Count > 0

sqlite3 data/fermentation.db "SELECT name FROM sqlite_master WHERE type='table';"
# Expected: tilts table does NOT exist

pkill -f uvicorn
```

**Step 3: Test device pairing**

```bash
# Start server and frontend
uvicorn backend.main:app --reload &
cd frontend && npm run dev &
sleep 5

# Open browser to http://localhost:5173/devices
# Manual checks:
# □ Device cards display for all device types
# □ Pair button works
# □ Unpair button works
# □ Status updates immediately
# □ No console errors

# Stop servers
pkill -f uvicorn
pkill -f vite
```

**Step 4: Test calibration page**

```bash
# Start servers
uvicorn backend.main:app --reload &
cd frontend && npm run dev &
sleep 5

# Open browser to http://localhost:5173/calibration
# Manual checks:
# □ "Select Device" dropdown shows all paired devices
# □ Can add calibration points
# □ Can view calibration points
# □ Can clear calibration
# □ Works for Tilt devices
# □ No console errors

pkill -f uvicorn
pkill -f vite
```

**Step 5: Test live readings**

```bash
# With real Tilt hardware broadcasting
uvicorn backend.main:app --reload &
cd frontend && npm run dev &
sleep 5

# Open browser to http://localhost:5173
# Manual checks:
# □ Tilt readings appear on dashboard
# □ Device can be paired from Devices page
# □ Paired device stores readings
# □ Unpaired device shows on dashboard but doesn't store
# □ WebSocket updates work

pkill -f uvicorn
pkill -f vite
```

**Step 6: Document test results**

Create test report in commit message or PR description.

---

### Task 14: Final Integration Test on Raspberry Pi

**Files to modify: None (deployment test only)**

**Step 1: Build frontend**

```bash
cd frontend
npm run build
cd ..
```

**Step 2: Commit all changes**

```bash
git add .
git commit -m "build: production build for deployment test"
```

**Step 3: Push to repository**

```bash
git push origin fix/universal-device-migration
```

**Step 4: Deploy to Raspberry Pi**

```bash
sshpass -p 'tilt' ssh -o StrictHostKeyChecking=no pi@192.168.4.218 \
  "cd /opt/brewsignal && git fetch origin && git reset --hard origin/fix/universal-device-migration && sudo systemctl restart brewsignal"
```

**Step 5: Verify deployment**

```bash
# Check service status
sshpass -p 'tilt' ssh -o StrictHostKeyChecking=no pi@192.168.4.218 "sudo systemctl status brewsignal"

# View logs
sshpass -p 'tilt' ssh -o StrictHostKeyChecking=no pi@192.168.4.218 "sudo journalctl -u brewsignal -n 100 --no-pager"

# Look for migration success message:
# "Migration: Dropped tilts table - migration complete!"
```

**Step 6: Test production application**

```bash
# Open browser to http://192.168.4.218:8080

# Manual checks:
# □ Dashboard loads
# □ Devices page shows all devices
# □ Pairing/unpairing works
# □ Calibration page works
# □ Live readings appear
# □ Temperature control works
# □ No errors in browser console
```

**Step 7: Monitor for issues**

```bash
# Watch logs for errors
sshpass -p 'tilt' ssh -o StrictHostKeyChecking=no pi@192.168.4.218 "sudo journalctl -u brewsignal -f"

# Leave running for 10-15 minutes to verify stability
```

---

## Completion Checklist

**Migration:**
- [ ] Database migration runs successfully on empty DB
- [ ] Database migration runs successfully on existing DB
- [ ] All Tilt data migrated to Device table
- [ ] Foreign keys updated (readings, calibration_points)
- [ ] Legacy tilts table dropped

**Backend:**
- [ ] Tilt model removed from models.py
- [ ] Reading handler simplified (single table)
- [ ] Universal pairing endpoints work
- [ ] Calibration endpoints work for all devices
- [ ] Legacy tilts router deleted
- [ ] Security vulnerability fixed
- [ ] All backend tests passing

**Frontend:**
- [ ] Pairing API calls updated
- [ ] Calibration page updated
- [ ] Frontend builds without errors
- [ ] No /api/tilts references remain

**Testing:**
- [ ] Manual testing checklist complete
- [ ] Deployed to Raspberry Pi
- [ ] Production testing complete
- [ ] No errors in logs

**Documentation:**
- [ ] Design document exists
- [ ] Implementation plan exists
- [ ] Changes documented in commit messages

---

## Rollback Plan

If critical issues found in production:

**Step 1: Restore database backup**

```bash
sshpass -p 'tilt' ssh -o StrictHostKeyChecking=no pi@192.168.4.218 \
  "cp /opt/brewsignal/data/fermentation.db.backup /opt/brewsignal/data/fermentation.db"
```

**Step 2: Revert to master branch**

```bash
sshpass -p 'tilt' ssh -o StrictHostKeyChecking=no pi@192.168.4.218 \
  "cd /opt/brewsignal && git reset --hard origin/master && sudo systemctl restart brewsignal"
```

**Step 3: Verify rollback**

```bash
# Check that old schema is back
sshpass -p 'tilt' ssh -o StrictHostKeyChecking=no pi@192.168.4.218 \
  "sqlite3 /opt/brewsignal/data/fermentation.db 'SELECT name FROM sqlite_master WHERE type=\"table\";'"

# Expected: tilts table exists again
```

---

## Post-Implementation

After successful deployment:

1. **Create PR** with all changes
2. **Update PR #73** - Close with note about superseding with clean migration
3. **Tag release** - `v2.0.0-universal-devices`
4. **Monitor production** for 48 hours
5. **Delete backup database** after confidence period

**Success metrics:**
- Zero data loss
- All device types working
- No pairing/synchronization bugs
- ~500 lines of code removed
- Cleaner, more maintainable architecture
