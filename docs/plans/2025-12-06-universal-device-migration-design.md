# Universal Device Migration Design

**Date:** 2025-12-06
**Status:** Approved for Implementation
**Author:** Claude (with machug)
**Related PR:** #73 (Multi-Device Support)

## Executive Summary

This design consolidates the legacy `tilts` table into the universal `devices` table, creating a single source of truth for all hydrometer devices (Tilt, iSpindel, GravityMon, future devices). This migration eliminates dual-table synchronization bugs, simplifies the API surface, and provides a clean foundation for supporting additional device types.

## Problem Statement

PR #73 introduced multi-device support but revealed critical architectural issues:

1. **Non-Tilt devices cannot be paired** - Pairing endpoints require `Tilt` table records, but iSpindel/GravityMon only exist in `Device` table
2. **Data synchronization bugs** - Maintaining consistency between `Tilt` and `Device` tables is error-prone
3. **Code duplication** - Pairing logic duplicated across endpoints
4. **Security vulnerability** - System command paths use `shutil.which()` allowing PATH manipulation
5. **Technical debt** - Two tables, two API surfaces, two code paths for essentially the same entity

## Design Goals

1. **Single source of truth** - All devices in one table
2. **Universal API** - One set of endpoints works for all device types
3. **Type differentiation** - Device type determined by incoming payload structure
4. **Zero data loss** - All existing Tilt data preserved during migration
5. **Future-proof** - Easy to add new device types (RAPT pill, Plaato, etc.)
6. **Security** - Fix command injection vulnerability

## Architecture

### Database Schema Changes

#### Migration Strategy

All changes happen in one atomic migration function: `_migrate_tilts_to_devices_final()`

**Step 1: Migrate Tilt data to Device table**
```sql
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
FROM tilts;
```

**Step 2: Update foreign keys in dependent tables**

Rename `tilt_id` → `device_id`:
- `readings` table: `tilt_id` → `device_id`
- `calibration_points` table: `tilt_id` → `device_id`

**Step 3: Drop legacy table**
```sql
DROP TABLE tilts;
```

#### Updated Models

**Remove from `backend/models.py`:**
- `class Tilt(Base)` - SQLAlchemy ORM model
- `TiltBase`, `TiltCreate`, `TiltUpdate`, `TiltResponse` - Pydantic schemas

**Keep:**
- `TiltReading` - This is the scanner output format, not a DB model

**Update:**
```python
class CalibrationPoint(Base):
    # OLD: tilt_id: Mapped[str] = mapped_column(ForeignKey("tilts.id"))
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    device: Mapped["Device"] = relationship(back_populates="calibration_points")

class Reading(Base):
    # OLD: tilt_id: Mapped[Optional[str]] = mapped_column(ForeignKey("tilts.id"))
    device_id: Mapped[Optional[str]] = mapped_column(ForeignKey("devices.id"))
    device: Mapped[Optional["Device"]] = relationship(back_populates="readings")
```

### API Changes

#### Remove Legacy Endpoints

Delete entire `/api/tilts/*` router and all endpoints:
- `GET /api/tilts` - list tilts
- `GET /api/tilts/{id}` - get tilt details
- `PUT /api/tilts/{id}` - update tilt
- `POST /api/tilts/{id}/pair` - pair tilt
- `POST /api/tilts/{id}/unpair` - unpair tilt
- `GET /api/tilts/{id}/calibration` - get calibration points
- `POST /api/tilts/{id}/calibration` - add calibration point
- `DELETE /api/tilts/{id}/calibration/{type}` - clear calibration
- `GET /api/tilts/{id}/readings` - get tilt readings

#### Add Universal Endpoints

In `backend/routers/devices.py`:

**Pairing:**
```python
@router.post("/{device_id}/pair", response_model=DeviceResponse)
async def pair_device(device_id: str, db: AsyncSession = Depends(get_db)):
    """Pair any device type to enable reading storage."""
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    device.paired = True
    device.paired_at = datetime.now(timezone.utc)
    await db.commit()

    # Update in-memory cache
    if device_id in latest_readings:
        latest_readings[device_id]["paired"] = True
        await manager.broadcast(latest_readings[device_id])

    return DeviceResponse.from_orm_with_calibration(device)

@router.post("/{device_id}/unpair", response_model=DeviceResponse)
async def unpair_device(device_id: str, db: AsyncSession = Depends(get_db)):
    """Unpair device to stop reading storage."""
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    device.paired = False
    device.paired_at = None
    await db.commit()

    # Update in-memory cache
    if device_id in latest_readings:
        latest_readings[device_id]["paired"] = False
        await manager.broadcast(latest_readings[device_id])

    return DeviceResponse.from_orm_with_calibration(device)
```

**Calibration:**
```python
@router.get("/{device_id}/calibration", response_model=list[CalibrationPointResponse])
async def get_device_calibration(device_id: str, db: AsyncSession = Depends(get_db)):
    """Get calibration points for any device."""
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    result = await db.execute(
        select(CalibrationPoint)
        .where(CalibrationPoint.device_id == device_id)
        .order_by(CalibrationPoint.type, CalibrationPoint.raw_value)
    )
    return result.scalars().all()

@router.post("/{device_id}/calibration", response_model=CalibrationPointResponse)
async def add_device_calibration_point(
    device_id: str,
    point: CalibrationPointCreate,
    db: AsyncSession = Depends(get_db)
):
    """Add calibration point for any device."""
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    calibration_point = CalibrationPoint(device_id=device_id, **point.model_dump())
    db.add(calibration_point)
    await db.commit()
    await db.refresh(calibration_point)
    return calibration_point

@router.delete("/{device_id}/calibration/{type}")
async def clear_device_calibration(
    device_id: str,
    type: str,
    db: AsyncSession = Depends(get_db)
):
    """Clear calibration points for a specific type (sg or temp)."""
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

@router.get("/{device_id}/readings", response_model=list[ReadingResponse])
async def get_device_readings(
    device_id: str,
    limit: int = Query(default=100, le=1000),
    db: AsyncSession = Depends(get_db)
):
    """Get recent readings for any device."""
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

### Backend Code Changes

#### Reading Handler Simplification

**File:** `backend/main.py`

**Before (dual-table complexity):**
```python
async def handle_tilt_reading(reading: TiltReading):
    async with async_session_factory() as session:
        # Get or create Tilt record
        tilt = await session.get(Tilt, reading.id)
        if not tilt:
            tilt = Tilt(...)
            session.add(tilt)

        tilt.last_seen = timestamp
        tilt.mac = reading.mac

        # ALSO get or create Device record
        device = await session.get(Device, reading.id)
        if not device:
            device = create_tilt_device_record(...)
            session.add(device)

        # Keep both in sync
        device.last_seen = timestamp
        device.color = reading.color
        device.mac = reading.mac
        # BUT DON'T sync paired status (causes bugs!)

        # ... rest of reading processing ...
```

**After (single table):**
```python
async def handle_tilt_reading(reading: TiltReading):
    async with async_session_factory() as session:
        # Get or create Device record (single source of truth)
        device = await session.get(Device, reading.id)
        if not device:
            device = Device(
                id=reading.id,
                device_type='tilt',
                name=reading.color,
                native_temp_unit='F',
                native_gravity_unit='sg',
                calibration_type='linear',
                paired=False,
            )
            session.add(device)

        # Update device metadata
        device.last_seen = datetime.now(timezone.utc)
        device.color = reading.color
        device.mac = reading.mac

        # ... rest of reading processing (unchanged) ...
```

#### Security Fix

**File:** `backend/routers/system.py`

**Before (vulnerable):**
```python
timedatectl_path = shutil.which("timedatectl") or "/usr/bin/timedatectl"
sudo_path = shutil.which("sudo") or "/usr/bin/sudo"
```

**After (secure):**
```python
# System command paths - hardcoded for security (no PATH manipulation)
TIMEDATECTL_PATH = "/usr/bin/timedatectl"
SUDO_PATH = "/usr/bin/sudo"

@router.get("/timezone")
async def get_timezone():
    """Get current timezone."""
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
        # ... rest of logic ...
```

### Frontend Changes

#### API Client Updates

**File:** `frontend/src/lib/api/devices.ts`

```typescript
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

#### Calibration Page Updates

**File:** `frontend/src/routes/calibration/+page.svelte`

Replace all `/api/tilts` calls with `/api/devices`:

```typescript
// Fetch devices for calibration (was: fetch tilts)
const response = await fetch('/api/devices?paired_only=true');
const devices = await response.json();

// Get calibration points
const response = await fetch(`/api/devices/${selectedDeviceId}/calibration`);

// Add calibration point
await fetch(`/api/devices/${selectedDeviceId}/calibration`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(point)
});

// Clear calibration
await fetch(`/api/devices/${selectedDeviceId}/calibration/${type}`, {
    method: 'DELETE'
});
```

**UI Updates:**
- "Select Tilt" → "Select Device"
- Color badge shows for Tilt devices
- Type badge shows for other devices

#### Remove Legacy Code

**Delete files:**
- `frontend/src/lib/stores/tilts.svelte.ts` - No longer needed

### Files to Delete

**Backend:**
- `backend/routers/tilts.py` - Entire router (~350 lines)
- `backend/device_utils.py` - Helper absorbed into Device model (~50 lines)

**Frontend:**
- `frontend/src/lib/stores/tilts.svelte.ts` - Use devices store instead (~50 lines)

**Total code removed:** ~450 lines

### Files to Update

**Backend:**
- `backend/models.py` - Remove Tilt model and schemas
- `backend/database.py` - Add final migration function
- `backend/main.py` - Remove Tilt imports, simplify reading handler, remove tilts router
- `backend/routers/devices.py` - Add pairing and calibration endpoints
- `backend/routers/system.py` - Fix security vulnerability
- `backend/services/calibration.py` - Update to use device_id (minor change)

**Frontend:**
- `frontend/src/lib/api/devices.ts` - Update pairing functions
- `frontend/src/routes/calibration/+page.svelte` - Use /api/devices endpoints

**Tests:**
- `backend/tests/test_tilts_api.py` - Rewrite as test_devices_api.py
- `backend/tests/test_pairing_endpoints.py` - Update to use Device model
- `backend/tests/test_models.py` - Remove Tilt model tests

## Migration Safety

### Idempotency

Migration can run multiple times safely:
- Uses `INSERT OR IGNORE` for data migration
- Checks for column existence before renaming
- Checks for table existence before dropping

### Rollback Strategy

If migration fails:
1. Transaction rolls back automatically (SQLite ACID guarantees)
2. Database returns to pre-migration state
3. Error logged for debugging
4. Application fails to start (safe failure mode)

### Data Validation

Post-migration checks:
- Count devices == count original tilts
- All readings have valid device_id foreign keys
- All calibration points have valid device_id foreign keys
- No orphaned records

## Testing Strategy

### Automated Tests

**Migration tests:**
```python
async def test_migration_preserves_all_data():
    """Verify all Tilt data migrated to Device table."""
    # Create test Tilt records
    # Run migration
    # Verify all fields preserved in Device table
    # Verify foreign keys updated
    # Verify tilts table dropped

async def test_migration_is_idempotent():
    """Migration can run multiple times safely."""
    # Run migration twice
    # Verify no errors, no duplicate data
```

**Pairing tests:**
```python
async def test_pair_tilt_device():
    """Pairing works for Tilt devices."""

async def test_pair_ispindel_device():
    """Pairing works for iSpindel devices."""

async def test_pair_gravitymon_device():
    """Pairing works for GravityMon devices."""
```

**Calibration tests:**
```python
async def test_calibration_for_all_device_types():
    """Calibration endpoints work for all devices."""
```

### Manual Testing Checklist

**Fresh install:**
- [ ] Migration runs without errors on empty database
- [ ] Tilt readings appear on dashboard
- [ ] iSpindel readings appear on dashboard
- [ ] GravityMon readings appear on dashboard

**Existing installation:**
- [ ] Migration preserves all Tilt data
- [ ] Paired status maintained after migration
- [ ] Calibration points preserved
- [ ] Historical readings still accessible
- [ ] Charts render correctly

**Functionality:**
- [ ] Pairing/unpairing works from Devices page
- [ ] Calibration page works for all device types
- [ ] Temperature control works
- [ ] Batch tracking works
- [ ] WebSocket updates work

**Frontend:**
- [ ] No console errors
- [ ] Device cards render for all types
- [ ] Pairing buttons work
- [ ] Calibration page loads

## Implementation Phases

### Phase 1: Database Migration & Backend Core
1. Create migration function
2. Update models (remove Tilt, update foreign keys)
3. Simplify reading handler
4. Add universal pairing endpoints
5. Fix security vulnerability
6. Update tests

### Phase 2: API Migration
1. Add calibration endpoints to devices router
2. Add readings endpoint to devices router
3. Remove tilts router
4. Update main.py (remove tilts router registration)

### Phase 3: Frontend Updates
1. Update API client (devices.ts)
2. Update calibration page
3. Remove legacy stores
4. Update tests

### Phase 4: Cleanup & Validation
1. Delete legacy files
2. Run full test suite
3. Manual testing on deployed system
4. Performance validation

## Risks & Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|-----------|------------|
| Migration fails | High - app won't start | Low | Atomic transaction, rollback on error |
| Data loss during migration | High - historical data lost | Very Low | INSERT OR IGNORE, testing |
| Frontend breaks | Medium - UI unusable | Low | Comprehensive testing, gradual rollout |
| Security regression | High - system compromise | Very Low | Code review, absolute paths |
| Performance degradation | Medium - slow queries | Very Low | Same DB structure, just renamed |

## Success Criteria

1. ✅ All existing Tilt data migrated to Device table
2. ✅ Zero data loss (readings, calibration points, paired status)
3. ✅ Pairing works for Tilt, iSpindel, GravityMon
4. ✅ Calibration works for all device types
5. ✅ Security vulnerability fixed
6. ✅ No dual-table synchronization bugs possible
7. ✅ ~450 lines of code removed
8. ✅ All tests passing
9. ✅ Frontend works without errors

## Future Enhancements

With universal device architecture in place:

1. **Easy device addition** - Add RAPT pill, Plaato, Tilt Pro by:
   - Adding device type constant
   - Creating ingest endpoint for payload format
   - Device auto-created on first reading

2. **Device-specific features** - Store device-specific metadata in JSON field

3. **Multi-protocol support** - BLE, HTTP, MQTT, WebSocket all feed into same Device table

4. **Advanced calibration** - Per-device-type calibration algorithms

## Conclusion

This migration eliminates technical debt, fixes all PR #73 review issues, and creates a clean foundation for multi-device support. By consolidating to a single Device table, we eliminate synchronization bugs, simplify the codebase, and make it trivial to add new device types in the future.

The migration is safe (atomic, idempotent, tested), the API is cleaner (one endpoint per operation), and the code is smaller (~450 lines removed). This is the right architectural direction for the project.
