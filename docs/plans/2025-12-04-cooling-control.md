# Cooling Control Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add cooling control support to complement existing heating system, enabling full temperature management (heating + cooling) for fermentation batches.

**Architecture:** Mirror existing heater implementation with parallel state tracking for coolers, enforce mutual exclusion to prevent simultaneous operation, use shared hysteresis for symmetric control thresholds.

**Tech Stack:** Python/FastAPI (backend), SQLAlchemy (ORM), SvelteKit/TypeScript (frontend), Home Assistant API integration

**Design Document:** `docs/plans/2025-12-04-cooling-control-design.md`

**GitHub Issue:** [#58](https://github.com/machug/brewsignal/issues/58)

---

## Task 1: Database Schema - Add cooler_entity_id Column

**Files:**
- Modify: `backend/models.py:343-346`
- Modify: `backend/database.py` (add migration function)

**Step 1: Add cooler_entity_id field to Batch model**

In `backend/models.py`, locate the temperature control section around line 343-346:

```python
# Temperature control - per-batch heater assignment
heater_entity_id: Mapped[Optional[str]] = mapped_column(String(100))
cooler_entity_id: Mapped[Optional[str]] = mapped_column(String(100))  # ADD THIS LINE
temp_target: Mapped[Optional[float]] = mapped_column()  # Override target temp for this batch
temp_hysteresis: Mapped[Optional[float]] = mapped_column()  # Override hysteresis for this batch
```

**Step 2: Create migration function**

In `backend/database.py`, add this migration function before `init_db()`:

```python
async def _migrate_add_cooler_entity():
    """Add cooler_entity_id column to batches table."""
    async with engine.begin() as conn:
        # Check if column exists
        result = await conn.execute(text("PRAGMA table_info(batches)"))
        columns = {row[1] for row in result}

        if "cooler_entity_id" not in columns:
            await conn.execute(text(
                "ALTER TABLE batches ADD COLUMN cooler_entity_id VARCHAR(100)"
            ))
            logger.info("Added cooler_entity_id column to batches table")
```

**Step 3: Call migration from init_db()**

In `backend/database.py`, locate the `init_db()` function and add the migration call in the appropriate order (after other batch-related migrations):

```python
async def init_db():
    """Initialize database and run migrations."""
    # ... existing migrations ...

    # Add cooler support
    await _migrate_add_cooler_entity()

    # ... rest of init_db ...
```

**Step 4: Test migration**

```bash
# Delete test database
rm data/fermentation.db

# Start backend to trigger migration
uvicorn backend.main:app --reload
```

Expected output in logs:
```
INFO:backend.database:Added cooler_entity_id column to batches table
```

**Step 5: Verify column exists**

```bash
sqlite3 data/fermentation.db "PRAGMA table_info(batches);" | grep cooler_entity_id
```

Expected output shows cooler_entity_id column.

**Step 6: Commit**

```bash
git add backend/models.py backend/database.py
git commit -m "feat(db): add cooler_entity_id to batches table

Add cooler entity field to support cooling control alongside heating.
Migration adds nullable column for backward compatibility.

Related to #58"
```

---

## Task 2: Backend State Tracking - Add Cooler State Dictionaries

**Files:**
- Modify: `backend/temp_controller.py:22-28`

**Step 1: Add cooler state tracking dict**

In `backend/temp_controller.py`, locate the state tracking section around line 22-28, after `_batch_heater_states`:

```python
# Track per-batch heater states to avoid redundant API calls
# Keys are batch_id, values are {"state": "on"/"off", "last_change": datetime}
_batch_heater_states: dict[int, dict] = {}

# Track per-batch cooler states (same structure as heater states)
_batch_cooler_states: dict[int, dict] = {}

# Track per-batch manual overrides
# Keys are batch_id, values are {"state": "on"/"off", "until": datetime or None}
_batch_overrides: dict[int, dict] = {}
```

**Step 2: Update cleanup_batch_state function**

In `backend/temp_controller.py`, locate `cleanup_batch_state()` around line 33-40 and add cooler cleanup:

```python
def cleanup_batch_state(batch_id: int) -> None:
    """Clean up runtime state for a batch (called when batch leaves fermenting status)."""
    if batch_id in _batch_heater_states:
        logger.debug(f"Cleaning up heater state for batch {batch_id}")
        del _batch_heater_states[batch_id]
    if batch_id in _batch_cooler_states:
        logger.debug(f"Cleaning up cooler state for batch {batch_id}")
        del _batch_cooler_states[batch_id]
    if batch_id in _batch_overrides:
        logger.debug(f"Cleaning up override for batch {batch_id}")
        del _batch_overrides[batch_id]
```

**Step 3: Commit**

```bash
git add backend/temp_controller.py
git commit -m "feat(control): add cooler state tracking

Add parallel state dictionary for cooler tracking.
Update cleanup to handle cooler states.

Related to #58"
```

---

## Task 3: Backend Control Logic - Add set_cooler_state_for_batch Function

**Files:**
- Modify: `backend/temp_controller.py:191-240`

**Step 1: Create set_cooler_state_for_batch function**

In `backend/temp_controller.py`, after `set_heater_state_for_batch()` (around line 240), add:

```python
async def set_cooler_state_for_batch(
    ha_client,
    entity_id: str,
    state: str,
    db,
    batch_id: int,
    wort_temp: float,
    ambient_temp: Optional[float],
    target_temp: float,
    device_id: Optional[str],
    force: bool = False
) -> bool:
    """Turn cooler on or off for a specific batch and log the event."""
    global _batch_cooler_states

    # Get batch's cooler state tracking
    batch_state = _batch_cooler_states.get(batch_id, {})
    last_state = batch_state.get("state")
    last_change = batch_state.get("last_change")

    # Check minimum cycle time (skip for forced changes like overrides)
    if not force and last_change is not None:
        elapsed = datetime.now(timezone.utc) - last_change
        if elapsed < timedelta(minutes=MIN_CYCLE_MINUTES):
            remaining = MIN_CYCLE_MINUTES - (elapsed.total_seconds() / 60)
            logger.debug(f"Batch {batch_id}: Skipping cooler change to '{state}' - min cycle time not met ({remaining:.1f} min remaining)")
            return False

    logger.debug(f"Batch {batch_id}: Attempting to set cooler to '{state}' (entity: {entity_id})")

    if state == "on":
        success = await ha_client.call_service("switch", "turn_on", entity_id)
        action = "cool_on"
    else:
        success = await ha_client.call_service("switch", "turn_off", entity_id)
        action = "cool_off"

    if success:
        _batch_cooler_states[batch_id] = {
            "state": state,
            "last_change": datetime.now(timezone.utc),
            "entity_id": entity_id,
        }
        logger.info(f"Batch {batch_id}: Cooler state changed: {last_state} -> {state}")
        await log_control_event(db, action, wort_temp, ambient_temp, target_temp, device_id, batch_id)
    else:
        logger.error(f"Batch {batch_id}: Failed to set cooler to '{state}' via HA (entity: {entity_id})")

    return success
```

**Step 2: Commit**

```bash
git add backend/temp_controller.py
git commit -m "feat(control): add set_cooler_state_for_batch function

Mirror heater state management for cooler.
Includes min cycle time protection and event logging.

Related to #58"
```

---

## Task 4: Backend Control Logic - Implement Dual-Device Control with Mutual Exclusion

**Files:**
- Modify: `backend/temp_controller.py:242-346`

**Step 1: Rename control_batch_heater to control_batch_temperature**

In `backend/temp_controller.py`, locate `control_batch_heater()` function (around line 242) and rename it to `control_batch_temperature`. Update the docstring:

```python
async def control_batch_temperature(
    ha_client,
    batch: Batch,
    db,
    global_target: float,
    global_hysteresis: float,
    ambient_temp: Optional[float],
) -> None:
    """Control both heating and cooling for a single batch."""
    batch_id = batch.id
    device_id = batch.device_id
    heater_entity = batch.heater_entity_id
    cooler_entity = batch.cooler_entity_id  # ADD THIS LINE

    if not heater_entity and not cooler_entity:  # MODIFY THIS LINE
        return

    # ... rest of function ...
```

**Step 2: Add cooler state syncing**

After the heater state sync section (around line 274-288), add cooler state sync:

```python
    # Sync cached cooler state with actual HA state
    if cooler_entity:
        actual_cooler_state = await ha_client.get_state(cooler_entity)
        if actual_cooler_state:
            ha_cooler_state = actual_cooler_state.get("state", "").lower()
            if ha_cooler_state in ("on", "off"):
                if batch_id in _batch_cooler_states:
                    if _batch_cooler_states[batch_id].get("state") != ha_cooler_state:
                        logger.debug(f"Batch {batch_id}: Syncing cooler cache: {_batch_cooler_states[batch_id].get('state')} -> {ha_cooler_state} (from HA)")
                    # Only update the state, preserve the existing last_change timestamp
                    _batch_cooler_states[batch_id]["state"] = ha_cooler_state
                else:
                    # Initialize state tracking for new batch (no last_change yet)
                    _batch_cooler_states[batch_id] = {"state": ha_cooler_state}
            elif ha_cooler_state == "unavailable":
                logger.warning(f"Batch {batch_id}: Cooler entity {cooler_entity} is unavailable in HA")

    current_heater_state = _batch_heater_states.get(batch_id, {}).get("state")
    current_cooler_state = _batch_cooler_states.get(batch_id, {}).get("state")
```

**Step 3: Update override handling for both devices**

Replace the override section (around line 292-308) with:

```python
    # Check for manual overrides for this batch
    if batch_id in _batch_overrides:
        override = _batch_overrides[batch_id]

        # Handle heater override
        heater_override = override.get("heater")
        if heater_override:
            override_until = heater_override.get("until")
            if override_until and datetime.now(timezone.utc) > override_until:
                # Override expired
                logger.info(f"Batch {batch_id}: Heater override expired, returning to auto mode")
                del _batch_overrides[batch_id]["heater"]
            else:
                # Override active
                desired_state = heater_override.get("state")
                if heater_entity and current_heater_state != desired_state:
                    await set_heater_state_for_batch(
                        ha_client, heater_entity, desired_state, db, batch_id,
                        wort_temp, ambient_temp, target_temp, device_id, force=True
                    )

        # Handle cooler override
        cooler_override = override.get("cooler")
        if cooler_override:
            override_until = cooler_override.get("until")
            if override_until and datetime.now(timezone.utc) > override_until:
                # Override expired
                logger.info(f"Batch {batch_id}: Cooler override expired, returning to auto mode")
                del _batch_overrides[batch_id]["cooler"]
            else:
                # Override active
                desired_state = cooler_override.get("state")
                if cooler_entity and current_cooler_state != desired_state:
                    await set_cooler_state_for_batch(
                        ha_client, cooler_entity, desired_state, db, batch_id,
                        wort_temp, ambient_temp, target_temp, device_id, force=True
                    )

        # If either override is active, skip automatic control
        if heater_override or cooler_override:
            return
```

**Step 4: Replace automatic control logic with dual-device logic**

Replace the automatic control section (around line 310-345) with:

```python
    # Calculate thresholds (symmetric hysteresis)
    heat_on_threshold = round(target_temp - hysteresis, 1)
    cool_on_threshold = round(target_temp + hysteresis, 1)

    logger.debug(
        f"Batch {batch_id}: Control check: wort={wort_temp:.2f}F, target={target_temp:.2f}F, "
        f"hysteresis={hysteresis:.2f}F, heat_on<={heat_on_threshold:.2f}F, "
        f"cool_on>={cool_on_threshold:.2f}F, heater={current_heater_state}, cooler={current_cooler_state}"
    )

    # Automatic control logic with mutual exclusion
    if wort_temp <= heat_on_threshold:
        # Need heating
        if heater_entity and current_heater_state != "on":
            logger.info(f"Batch {batch_id}: Wort temp {wort_temp:.1f}F at/below threshold {heat_on_threshold:.1f}F, turning heater ON")
            await set_heater_state_for_batch(
                ha_client, heater_entity, "on", db, batch_id,
                wort_temp, ambient_temp, target_temp, device_id
            )
        # Ensure cooler is OFF (mutual exclusion)
        if cooler_entity and current_cooler_state == "on":
            logger.info(f"Batch {batch_id}: Turning cooler OFF (heater needs to run)")
            await set_cooler_state_for_batch(
                ha_client, cooler_entity, "off", db, batch_id,
                wort_temp, ambient_temp, target_temp, device_id
            )

    elif wort_temp >= cool_on_threshold:
        # Need cooling
        if cooler_entity and current_cooler_state != "on":
            logger.info(f"Batch {batch_id}: Wort temp {wort_temp:.1f}F at/above threshold {cool_on_threshold:.1f}F, turning cooler ON")
            await set_cooler_state_for_batch(
                ha_client, cooler_entity, "on", db, batch_id,
                wort_temp, ambient_temp, target_temp, device_id
            )
        # Ensure heater is OFF (mutual exclusion)
        if heater_entity and current_heater_state == "on":
            logger.info(f"Batch {batch_id}: Turning heater OFF (cooler needs to run)")
            await set_heater_state_for_batch(
                ha_client, heater_entity, "off", db, batch_id,
                wort_temp, ambient_temp, target_temp, device_id
            )

    else:
        # Within deadband - maintain current states
        logger.debug(
            f"Batch {batch_id}: Within hysteresis band ({heat_on_threshold:.1f}F-{cool_on_threshold:.1f}F), "
            f"maintaining states: heater={current_heater_state}, cooler={current_cooler_state}"
        )
```

**Step 5: Update function call in temperature_control_loop**

In `backend/temp_controller.py`, locate the `temperature_control_loop()` function (around line 348-434) and update the function call and query:

Change the query to include cooler entities:
```python
# Get all active batches with heater OR cooler entities configured
result = await db.execute(
    select(Batch).where(
        Batch.status == "fermenting",
        Batch.device_id.isnot(None),
        (Batch.heater_entity_id.isnot(None)) | (Batch.cooler_entity_id.isnot(None)),
    )
)
```

Change the function call:
```python
# Control each batch's temperature concurrently for better performance
if batches:
    await asyncio.gather(*[
        control_batch_temperature(  # CHANGED FROM control_batch_heater
            ha_client, batch, db, global_target, global_hysteresis, ambient_temp
        )
        for batch in batches
    ], return_exceptions=True)
```

**Step 6: Add cooler state cleanup at end of loop**

In the cleanup section (around line 420-429), add cooler cleanup:

```python
# Cleanup old batch entries from in-memory state dictionaries
active_batch_ids = {b.id for b in batches}
for batch_id in list(_batch_heater_states.keys()):
    if batch_id not in active_batch_ids:
        logger.debug(f"Cleaning up heater state for inactive batch {batch_id}")
        del _batch_heater_states[batch_id]
for batch_id in list(_batch_cooler_states.keys()):
    if batch_id not in active_batch_ids:
        logger.debug(f"Cleaning up cooler state for inactive batch {batch_id}")
        del _batch_cooler_states[batch_id]
for batch_id in list(_batch_overrides.keys()):
    if batch_id not in active_batch_ids:
        logger.debug(f"Cleaning up override for inactive batch {batch_id}")
        del _batch_overrides[batch_id]
```

**Step 7: Test control logic manually**

```bash
# Start backend
uvicorn backend.main:app --reload

# Monitor logs for control loop activity
tail -f backend.log
```

Expected: Control loop runs without errors, processes batches.

**Step 8: Commit**

```bash
git add backend/temp_controller.py
git commit -m "feat(control): implement dual-device control with mutual exclusion

- Rename control_batch_heater to control_batch_temperature
- Add cooler state syncing with HA
- Implement mutual exclusion logic (heater blocks cooler, vice versa)
- Support independent overrides for both devices
- Add cooler state cleanup

Related to #58"
```

---

## Task 5: Backend API - Update Control Status Functions

**Files:**
- Modify: `backend/temp_controller.py:450-472`

**Step 1: Update get_batch_control_status function**

In `backend/temp_controller.py`, locate `get_batch_control_status()` (around line 450-472) and update to include cooler state:

```python
def get_batch_control_status(batch_id: int) -> dict:
    """Get temperature control status for a specific batch.

    Returns state_available=True if runtime state exists for this batch,
    False if state was cleaned up (e.g., batch completed/archived).
    """
    batch_heater_state = _batch_heater_states.get(batch_id)
    batch_cooler_state = _batch_cooler_states.get(batch_id)
    override = _batch_overrides.get(batch_id)

    # state_available indicates whether runtime state exists for this batch
    # False means state was cleaned up (batch no longer fermenting) or never existed
    state_available = batch_heater_state is not None or batch_cooler_state is not None

    return {
        "batch_id": batch_id,
        "heater_state": batch_heater_state.get("state") if batch_heater_state else None,
        "heater_entity": batch_heater_state.get("entity_id") if batch_heater_state else None,
        "cooler_state": batch_cooler_state.get("state") if batch_cooler_state else None,
        "cooler_entity": batch_cooler_state.get("entity_id") if batch_cooler_state else None,
        "override_active": override is not None and (override.get("heater") is not None or override.get("cooler") is not None),
        "override_state": None,  # Deprecated, kept for backward compatibility
        "override_until": None,  # Deprecated, kept for backward compatibility
        "state_available": state_available,
    }
```

**Step 2: Update set_manual_override function**

In `backend/temp_controller.py`, locate `set_manual_override()` (around line 474-509) and update to support device_type parameter:

```python
def set_manual_override(
    state: Optional[str],
    duration_minutes: int = 60,
    batch_id: Optional[int] = None,
    device_type: str = "heater"
) -> bool:
    """Set manual override for heater or cooler control.

    Args:
        state: "on", "off", or None to cancel override
        duration_minutes: How long override lasts (default 60 min)
        batch_id: Batch ID for override (required)
        device_type: "heater" or "cooler"

    Returns:
        True if override was set/cleared successfully
    """
    global _batch_overrides

    if batch_id is None:
        logger.warning("Batch ID required for override in multi-batch mode.")
        return False

    if device_type not in ("heater", "cooler"):
        logger.warning(f"Invalid device_type: {device_type}. Must be 'heater' or 'cooler'.")
        return False

    # Initialize override dict for batch if needed
    if batch_id not in _batch_overrides:
        _batch_overrides[batch_id] = {}

    if state is None:
        # Cancel override for device_type
        if device_type in _batch_overrides[batch_id]:
            del _batch_overrides[batch_id][device_type]
        if not _batch_overrides[batch_id]:
            del _batch_overrides[batch_id]
        logger.info(f"Batch {batch_id}: {device_type} override cancelled, returning to auto mode")
        _trigger_immediate_check()
        return True

    if state not in ("on", "off"):
        return False

    _batch_overrides[batch_id][device_type] = {
        "state": state,
        "until": datetime.now(timezone.utc) + timedelta(minutes=duration_minutes) if duration_minutes > 0 else None,
    }
    logger.info(f"Batch {batch_id}: {device_type} override set: {state} for {duration_minutes} minutes")
    _trigger_immediate_check()
    return True
```

**Step 3: Update sync_cached_heater_state to support cooler**

In `backend/temp_controller.py`, locate `sync_cached_heater_state()` (around line 512-516) and update:

```python
def sync_cached_state(state: Optional[str], batch_id: Optional[int] = None, device_type: str = "heater") -> None:
    """Keep the in-memory device state in sync with external changes (e.g., manual HA toggles)."""
    global _batch_heater_states, _batch_cooler_states

    if state in ("on", "off", None) and batch_id is not None:
        if device_type == "heater":
            _batch_heater_states.setdefault(batch_id, {})["state"] = state
        elif device_type == "cooler":
            _batch_cooler_states.setdefault(batch_id, {})["state"] = state
```

**Step 4: Commit**

```bash
git add backend/temp_controller.py
git commit -m "feat(control): update status functions for dual-device support

- Update get_batch_control_status to include cooler state
- Add device_type parameter to set_manual_override
- Rename sync_cached_heater_state to sync_cached_state, support cooler
- Maintain backward compatibility

Related to #58"
```

---

## Task 6: Backend API - Update Response Models

**Files:**
- Modify: `backend/routers/control.py:42-54`

**Step 1: Update BatchControlStatusResponse model**

In `backend/routers/control.py`, locate `BatchControlStatusResponse` (around line 42-54) and add cooler fields:

```python
class BatchControlStatusResponse(BaseModel):
    batch_id: int
    enabled: bool
    # Heater fields
    heater_state: Optional[str]
    heater_entity: Optional[str]
    # Cooler fields (NEW)
    cooler_state: Optional[str]
    cooler_entity: Optional[str]
    # Shared/override fields
    override_active: bool
    override_state: Optional[str]
    override_until: Optional[str]
    target_temp: Optional[float]
    hysteresis: Optional[float]
    wort_temp: Optional[float]
    state_available: bool  # True if runtime state exists, False if cleaned up (batch completed/archived)
```

**Step 2: Update OverrideRequest model**

In `backend/routers/control.py`, locate `OverrideRequest` (around line 56-60) and add device_type field:

```python
class OverrideRequest(BaseModel):
    device_type: str = "heater"  # "heater" or "cooler"
    state: Optional[str] = None  # "on", "off", or null to cancel
    duration_minutes: int = 60
    batch_id: Optional[int] = None  # Required for batch-specific override
```

**Step 3: Commit**

```bash
git add backend/routers/control.py
git commit -m "feat(api): update control response models for cooling support

- Add cooler_state and cooler_entity to BatchControlStatusResponse
- Add device_type to OverrideRequest for independent device control

Related to #58"
```

---

## Task 7: Backend API - Add Cooler Entities Endpoint

**Files:**
- Modify: `backend/routers/control.py:97-129`

**Step 1: Add get_cooler_entities endpoint**

In `backend/routers/control.py`, after `get_heater_entities()` (around line 129), add:

```python
@router.get("/cooler-entities", response_model=list[HeaterEntityResponse])
async def get_cooler_entities(db: AsyncSession = Depends(get_db)):
    """Get available cooler entities from Home Assistant.

    Returns switch.* and input_boolean.* entities that can be used as coolers.
    Same implementation as heater entities (coolers are also switches).
    """
    ha_enabled = await get_config_value(db, "ha_enabled")
    if not ha_enabled:
        return []

    # Get or initialize HA client
    ha_client = get_ha_client()
    if not ha_client:
        ha_url = await get_config_value(db, "ha_url")
        ha_token = await get_config_value(db, "ha_token")
        if ha_url and ha_token:
            ha_client = init_ha_client(ha_url, ha_token)

    if not ha_client:
        return []

    # Fetch switch and input_boolean entities
    entities = await ha_client.get_entities_by_domain(["switch", "input_boolean"])

    return [
        HeaterEntityResponse(
            entity_id=e["entity_id"],
            friendly_name=e["friendly_name"],
            state=e["state"]
        )
        for e in entities
    ]
```

**Step 2: Test endpoint**

```bash
# Start backend
uvicorn backend.main:app --reload

# Test endpoint (requires HA configured)
curl http://localhost:8080/api/control/cooler-entities
```

Expected: JSON array of switch entities.

**Step 3: Commit**

```bash
git add backend/routers/control.py
git commit -m "feat(api): add GET /api/control/cooler-entities endpoint

Return available cooler entities from Home Assistant.
Same implementation as heater entities (both use switches).

Related to #58"
```

---

## Task 8: Backend API - Update Batch Status Endpoint

**Files:**
- Modify: `backend/routers/control.py:154-186`

**Step 1: Update get_batch_status endpoint**

In `backend/routers/control.py`, locate `get_batch_status()` (around line 154-186) and update to include cooler data:

```python
@router.get("/batch/{batch_id}/status", response_model=BatchControlStatusResponse)
async def get_batch_status(batch_id: int, db: AsyncSession = Depends(get_db)):
    """Get temperature control status for a specific batch."""
    from fastapi import HTTPException

    batch = await db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")

    temp_control_enabled = await get_config_value(db, "temp_control_enabled") or False
    global_target = await get_config_value(db, "temp_target") or 68.0
    global_hysteresis = await get_config_value(db, "temp_hysteresis") or 1.0

    # Get batch-specific status
    batch_status = get_batch_control_status(batch_id)

    # Get temperature from batch's device
    wort_temp = get_device_temp(batch.device_id) if batch.device_id else None

    return BatchControlStatusResponse(
        batch_id=batch_id,
        enabled=temp_control_enabled and (batch.heater_entity_id is not None or batch.cooler_entity_id is not None),
        heater_state=batch_status["heater_state"],
        heater_entity=batch.heater_entity_id,
        cooler_state=batch_status["cooler_state"],
        cooler_entity=batch.cooler_entity_id,
        override_active=batch_status["override_active"],
        override_state=batch_status["override_state"],
        override_until=batch_status["override_until"],
        target_temp=batch.temp_target if batch.temp_target is not None else global_target,
        hysteresis=batch.temp_hysteresis if batch.temp_hysteresis is not None else global_hysteresis,
        wort_temp=wort_temp,
        state_available=batch_status["state_available"],
    )
```

**Step 2: Commit**

```bash
git add backend/routers/control.py
git commit -m "feat(api): update batch status endpoint with cooler data

Include cooler_state and cooler_entity in batch status response.

Related to #58"
```

---

## Task 9: Backend API - Update Override Endpoint

**Files:**
- Modify: `backend/routers/control.py:207-288`

**Step 1: Update set_override endpoint**

In `backend/routers/control.py`, locate `set_override()` (around line 207-288) and update to support device_type:

```python
@router.post("/override", response_model=OverrideResponse)
async def set_override(request: OverrideRequest, db: AsyncSession = Depends(get_db)):
    """Set or cancel manual heater or cooler override.

    - device_type: "heater" or "cooler"
    - state: "on" to force device on, "off" to force device off, null to cancel override
    - duration_minutes: how long override lasts (default 60 min, 0 = indefinite)
    - batch_id: required for batch-specific override
    """
    temp_control_enabled = await get_config_value(db, "temp_control_enabled")

    # Validate device_type
    if request.device_type not in ("heater", "cooler"):
        return OverrideResponse(
            success=False,
            message="device_type must be 'heater' or 'cooler'",
            override_state=None,
            override_until=None,
            batch_id=request.batch_id
        )

    # Require batch_id for override (multi-batch mode) - validate early
    if request.batch_id is None:
        return OverrideResponse(
            success=False,
            message="batch_id is required for override",
            override_state=None,
            override_until=None,
            batch_id=None
        )

    # Verify batch exists and has device configured - validate early before other checks
    batch = await db.get(Batch, request.batch_id)
    if not batch:
        return OverrideResponse(
            success=False,
            message=f"Batch {request.batch_id} not found",
            override_state=None,
            override_until=None,
            batch_id=request.batch_id
        )

    if not temp_control_enabled:
        return OverrideResponse(
            success=False,
            message="Temperature control is not enabled",
            override_state=None,
            override_until=None,
            batch_id=request.batch_id
        )

    if request.state is not None and request.state not in ("on", "off"):
        return OverrideResponse(
            success=False,
            message="State must be 'on', 'off', or null",
            override_state=None,
            override_until=None,
            batch_id=request.batch_id
        )

    # Check device entity is configured
    entity_id = batch.heater_entity_id if request.device_type == "heater" else batch.cooler_entity_id
    if not entity_id:
        return OverrideResponse(
            success=False,
            message=f"Batch {request.batch_id} has no {request.device_type} entity configured",
            override_state=None,
            override_until=None,
            batch_id=request.batch_id
        )

    success = set_manual_override(
        request.state,
        request.duration_minutes,
        batch_id=request.batch_id,
        device_type=request.device_type
    )

    if success:
        batch_status = get_batch_control_status(request.batch_id)
        if request.state is None:
            message = f"{request.device_type.capitalize()} override cancelled for batch {request.batch_id}, returning to automatic control"
        else:
            duration_msg = f"for {request.duration_minutes} minutes" if request.duration_minutes > 0 else "indefinitely"
            message = f"{request.device_type.capitalize()} override for batch {request.batch_id} set to {request.state} {duration_msg}"

        return OverrideResponse(
            success=True,
            message=message,
            override_state=request.state,
            override_until=batch_status.get("override_until"),
            batch_id=request.batch_id
        )
    else:
        return OverrideResponse(
            success=False,
            message="Failed to set override",
            override_state=None,
            override_until=None,
            batch_id=request.batch_id
        )
```

**Step 2: Commit**

```bash
git add backend/routers/control.py
git commit -m "feat(api): update override endpoint for dual-device support

- Add device_type validation
- Check appropriate entity based on device_type
- Pass device_type to set_manual_override

Related to #58"
```

---

## Task 10: Backend API - Update Heater State Sync Calls

**Files:**
- Modify: `backend/routers/control.py:291-373, 375-451`

**Step 1: Update get_heater_state to use new sync function**

In `backend/routers/control.py`, locate the `sync_cached_heater_state` call in `get_heater_state()` (around line 356) and update:

```python
# Keep controller cache aligned with the actual HA state
if batch_id:
    from ..temp_controller import sync_cached_state
    sync_cached_state(heater_state, batch_id=batch_id, device_type="heater")
```

**Step 2: Update toggle_heater to use new sync function**

In `backend/routers/control.py`, locate the `sync_cached_heater_state` call in `toggle_heater()` (around line 437) and update:

```python
# Keep controller cache aligned with manual toggles
if request.batch_id:
    from ..temp_controller import sync_cached_state
    sync_cached_state(request.state, batch_id=request.batch_id, device_type="heater")
```

**Step 3: Update imports at top of file**

In `backend/routers/control.py`, locate the imports from temp_controller (around line 14-21) and update:

```python
from ..temp_controller import (
    get_control_status,
    get_batch_control_status,
    set_manual_override,
    get_latest_tilt_temp,
    get_device_temp,
    sync_cached_state,  # Changed from sync_cached_heater_state
)
```

**Step 4: Commit**

```bash
git add backend/routers/control.py
git commit -m "refactor(api): update to use renamed sync_cached_state function

Update imports and function calls to use device_type parameter.

Related to #58"
```

---

## Task 11: Frontend Types - Update API Types

**Files:**
- Modify: `frontend/src/lib/api.ts`

**Step 1: Update BatchControlStatus type**

In `frontend/src/lib/api.ts`, locate `BatchControlStatus` interface and add cooler fields:

```typescript
export interface BatchControlStatus {
	batch_id: number;
	enabled: boolean;
	// Heater fields
	heater_state: string | null;
	heater_entity: string | null;
	// Cooler fields
	cooler_state: string | null;
	cooler_entity: string | null;
	// Shared/override fields
	override_active: boolean;
	override_state: string | null;
	override_until: string | null;
	target_temp: number | null;
	hysteresis: number | null;
	wort_temp: number | null;
	state_available: boolean;
}
```

**Step 2: Add HeaterEntity type (if not exists)**

In `frontend/src/lib/api.ts`, add:

```typescript
export interface HeaterEntity {
	entity_id: string;
	friendly_name: string;
	state: string | null;
}
```

**Step 3: Add cooler API functions**

In `frontend/src/lib/api.ts`, add after heater entity functions:

```typescript
export async function fetchCoolerEntities(): Promise<HeaterEntity[]> {
	const response = await fetch(`${API_BASE}/control/cooler-entities`);
	if (!response.ok) throw new Error('Failed to fetch cooler entities');
	return response.json();
}
```

**Step 4: Update override function to support device_type**

In `frontend/src/lib/api.ts`, locate `setBatchHeaterOverride` and update signature:

```typescript
export async function setBatchDeviceOverride(
	batchId: number,
	state: 'on' | 'off' | null,
	deviceType: 'heater' | 'cooler' = 'heater',
	durationMinutes: number = 60
): Promise<void> {
	const response = await fetch(`${API_BASE}/control/override`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			device_type: deviceType,
			state,
			batch_id: batchId,
			duration_minutes: durationMinutes
		})
	});
	if (!response.ok) throw new Error('Failed to set override');
}

// Keep backward compatibility
export async function setBatchHeaterOverride(
	batchId: number,
	state: 'on' | 'off' | null,
	durationMinutes: number = 60
): Promise<void> {
	return setBatchDeviceOverride(batchId, state, 'heater', durationMinutes);
}
```

**Step 5: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(frontend): update API types for cooling support

- Add cooler fields to BatchControlStatus
- Add fetchCoolerEntities function
- Add setBatchDeviceOverride with device_type parameter
- Maintain backward compatibility with setBatchHeaterOverride

Related to #58"
```

---

## Task 12: Frontend UI - Update Batch Form with Cooler Selection

**Files:**
- Modify: `frontend/src/lib/components/BatchForm.svelte`

**Step 1: Add cooler state and entity fetching**

In `frontend/src/lib/components/BatchForm.svelte`, locate the state declarations and heater entity fetching (around line 10-30):

```typescript
let heaterEntities = $state<HeaterEntity[]>([]);
let coolerEntities = $state<HeaterEntity[]>([]);  // ADD THIS
let loadingEntities = $state(false);

// ... existing code ...

async function loadHeaterEntities() {
	loadingEntities = true;
	try {
		heaterEntities = await fetchHeaterEntities();
	} catch (e) {
		console.error('Failed to load heater entities:', e);
	} finally {
		loadingEntities = false;
	}
}

async function loadCoolerEntities() {  // ADD THIS FUNCTION
	loadingEntities = true;
	try {
		coolerEntities = await fetchCoolerEntities();
	} catch (e) {
		console.error('Failed to load cooler entities:', e);
	} finally {
		loadingEntities = false;
	}
}

onMount(() => {
	loadHeaterEntities();
	loadCoolerEntities();  // ADD THIS CALL
});
```

**Step 2: Add cooler entity selection field**

In the form template, after the heater entity selection (locate "Heater Entity" field), add:

```svelte
<!-- Heater Entity (existing field) -->
<label>
	Heater Entity (optional)
	<select bind:value={data.heater_entity_id}>
		<option value={null}>No heater control</option>
		{#each heaterEntities as entity}
			<option value={entity.entity_id}>{entity.friendly_name}</option>
		{/each}
	</select>
</label>

<!-- Cooler Entity (NEW) -->
<label>
	Cooler Entity (optional)
	<select bind:value={data.cooler_entity_id}>
		<option value={null}>No cooling control</option>
		{#each coolerEntities as entity}
			<option value={entity.entity_id}>{entity.friendly_name}</option>
		{/each}
	</select>
</label>
```

**Step 3: Ensure data object includes cooler_entity_id**

In the component props/data initialization, ensure `cooler_entity_id` is included:

```typescript
let data = $state({
	name: batch?.name || '',
	device_id: batch?.device_id || null,
	recipe_id: batch?.recipe_id || null,
	heater_entity_id: batch?.heater_entity_id || null,
	cooler_entity_id: batch?.cooler_entity_id || null,  // ADD THIS
	temp_target: batch?.temp_target || null,
	temp_hysteresis: batch?.temp_hysteresis || null,
	// ... other fields ...
});
```

**Step 4: Update imports**

Add `fetchCoolerEntities` to imports at top of file:

```typescript
import { fetchHeaterEntities, fetchCoolerEntities, type HeaterEntity } from '$lib/api';
```

**Step 5: Test form**

```bash
cd frontend
npm run dev
```

Navigate to batch creation/edit form and verify cooler dropdown appears.

**Step 6: Commit**

```bash
git add frontend/src/lib/components/BatchForm.svelte
git commit -m "feat(ui): add cooler entity selection to batch form

- Add cooler entities state and fetching
- Add cooler entity dropdown field
- Initialize cooler_entity_id in form data

Related to #58"
```

---

## Task 13: Frontend UI - Update Batch Detail Page with Cooler Status

**Files:**
- Modify: `frontend/src/routes/batches/[id]/+page.svelte`

**Step 1: Update control status display**

In `frontend/src/routes/batches/[id]/+page.svelte`, locate the heater control status display section and update to show both devices:

```svelte
{#if hasHeaterControl || hasCoolerControl}
	<div class="control-status-card">
		<h3>Temperature Control</h3>

		{#if controlStatus}
			<div class="device-states">
				{#if batch.heater_entity_id}
					<div class="device-status heater">
						<span class="label">Heater:</span>
						<span class="state" class:active={controlStatus.heater_state === 'on'}>
							{controlStatus.heater_state?.toUpperCase() || 'OFF'}
						</span>
					</div>
				{/if}

				{#if batch.cooler_entity_id}
					<div class="device-status cooler">
						<span class="label">Cooler:</span>
						<span class="state" class:active={controlStatus.cooler_state === 'on'}>
							{controlStatus.cooler_state?.toUpperCase() || 'OFF'}
						</span>
					</div>
				{/if}
			</div>

			<!-- Override controls -->
			<div class="override-controls">
				{#if batch.heater_entity_id}
					<div class="device-controls">
						<span class="device-label">Heater:</span>
						<button onclick={() => handleOverride('heater', 'on')} disabled={heaterLoading}>
							Force ON
						</button>
						<button onclick={() => handleOverride('heater', 'off')} disabled={heaterLoading}>
							Force OFF
						</button>
					</div>
				{/if}

				{#if batch.cooler_entity_id}
					<div class="device-controls">
						<span class="device-label">Cooler:</span>
						<button onclick={() => handleOverride('cooler', 'on')} disabled={heaterLoading}>
							Force ON
						</button>
						<button onclick={() => handleOverride('cooler', 'off')} disabled={heaterLoading}>
							Force OFF
						</button>
					</div>
				{/if}

				<button onclick={() => handleOverride('both', null)} disabled={heaterLoading}>
					Auto Mode
				</button>
			</div>
		{/if}
	</div>
{/if}
```

**Step 2: Update hasHeaterControl derived value**

Locate `hasHeaterControl` and add `hasCoolerControl`:

```typescript
let hasHeaterControl = $derived(
	configState.config.ha_enabled &&
	configState.config.temp_control_enabled &&
	batch?.heater_entity_id
);

let hasCoolerControl = $derived(
	configState.config.ha_enabled &&
	configState.config.temp_control_enabled &&
	batch?.cooler_entity_id
);
```

**Step 3: Update handleOverride function**

Locate `handleOverride` function and update to support both device types:

```typescript
async function handleOverride(deviceType: 'heater' | 'cooler' | 'both', state: 'on' | 'off' | null) {
	if (!batch || heaterLoading) return;
	heaterLoading = true;
	try {
		if (deviceType === 'both') {
			// Cancel overrides for both devices
			if (batch.heater_entity_id) {
				await setBatchDeviceOverride(batch.id, null, 'heater');
			}
			if (batch.cooler_entity_id) {
				await setBatchDeviceOverride(batch.id, null, 'cooler');
			}
		} else {
			await setBatchDeviceOverride(batch.id, state, deviceType);
		}
		// Reload control status
		controlStatus = await fetchBatchControlStatus(batch.id);
	} catch (e) {
		console.error('Failed to set override:', e);
	} finally {
		heaterLoading = false;
	}
}
```

**Step 4: Update imports**

Add `setBatchDeviceOverride` to imports:

```typescript
import {
	fetchBatch,
	fetchBatchProgress,
	updateBatch,
	deleteBatch,
	fetchBatchControlStatus,
	setBatchDeviceOverride  // ADD THIS
} from '$lib/api';
```

**Step 5: Test UI**

```bash
cd frontend
npm run dev
```

Navigate to batch detail page with heater/cooler configured and verify controls appear.

**Step 6: Commit**

```bash
git add frontend/src/routes/batches/[id]/+page.svelte
git commit -m "feat(ui): add cooler status and controls to batch detail page

- Display both heater and cooler states
- Add override controls for each device
- Add 'Auto Mode' button to cancel all overrides
- Update handleOverride to support device_type

Related to #58"
```

---

## Task 14: Documentation - Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Update Temperature Control section**

In `CLAUDE.md`, locate the "Temperature Control" section (around line 80-90) and update:

```markdown
### Temperature Control

**Per-Batch Control:** Each batch can have independent temperature control with its own heater and/or cooler entity, target, and hysteresis.

**Architecture:**

- `temp_controller.py` runs background loop (every 60s)
- Fetches fermenting batches with heater/cooler entities
- Compares current temp (from latest_readings state) to target
- Sends Home Assistant API calls to control switch entities
- Supports manual override (Force ON/OFF) per device per batch
- Enforces mutual exclusion (heater and cooler never run simultaneously)

**Control Logic (Symmetric Hysteresis):**

- Turn heater ON if: `current_temp <= (target - hysteresis)`
- Turn heater OFF if: `current_temp >= (target + hysteresis)`
- Turn cooler ON if: `current_temp >= (target + hysteresis)`
- Turn cooler OFF if: `current_temp <= (target - hysteresis)`
- Within deadband: maintain current states (prevent oscillation)
- Mutual exclusion: Turning heater ON ensures cooler is OFF (and vice versa)

**Operational Modes:**
- Heating-only: `heater_entity_id` set, `cooler_entity_id` NULL
- Cooling-only: `cooler_entity_id` set, `heater_entity_id` NULL
- Dual-mode: Both entities set (full temperature regulation)

**Min Cycle Time:** 5 minutes for both heater and cooler to prevent equipment damage and compressor short-cycling.
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with cooling control details

- Document cooling control architecture
- Explain mutual exclusion logic
- Document operational modes
- Update control logic with symmetric hysteresis

Related to #58"
```

---

## Task 15: Testing - Manual Integration Test

**Files:**
- None (manual testing)

**Step 1: Setup test batch with dual-mode control**

1. Start backend: `uvicorn backend.main:app --reload`
2. Start frontend: `cd frontend && npm run dev`
3. Navigate to batch creation page
4. Create test batch with both heater and cooler entities selected
5. Set batch status to "fermenting"

**Step 2: Verify control loop operation**

Monitor backend logs:
```bash
tail -f backend.log | grep "Batch.*Control check"
```

Expected: Control loop processes batch, shows thresholds and states.

**Step 3: Test manual overrides**

1. Navigate to batch detail page
2. Click "Force Heater ON"
3. Verify cooler turns OFF (mutual exclusion)
4. Click "Force Cooler ON"
5. Verify heater turns OFF (mutual exclusion)
6. Click "Auto Mode"
7. Verify both return to automatic control

**Step 4: Test min cycle time**

1. Set override to force heater ON
2. Immediately try to cancel (set to OFF)
3. Verify min cycle time prevents rapid switching (check logs)

**Step 5: Verify Home Assistant integration**

1. Check HA entities are being controlled
2. Manually toggle switches in HA
3. Verify backend syncs state correctly (check logs)

**Step 6: Document test results**

Create test summary in commit message or separate test report.

**Step 7: Commit**

```bash
git add .
git commit -m "test: manual integration testing complete

Verified:
- Dual-mode control (heater + cooler)
- Mutual exclusion enforcement
- Manual overrides for both devices
- Min cycle time protection
- HA state syncing

Related to #58"
```

---

## Task 16: Build and Deploy

**Files:**
- None (deployment task)

**Step 1: Build frontend**

```bash
cd frontend
npm run build
```

Expected: Build succeeds, outputs to `backend/static/`

**Step 2: Commit build artifacts**

```bash
cd ..
git add backend/static/
git commit -m "build: compile frontend for cooling control feature

Related to #58"
```

**Step 3: Create pull request**

```bash
# Push feature branch
git push -u origin feature/cooling-control

# Create PR
gh pr create --title "Add Cooling Control Support" --body "Implements cooling control alongside heating for full temperature management.

## Changes
- Add cooler_entity_id to batches table
- Implement dual-device control with mutual exclusion
- Add cooler state tracking and min cycle time protection
- Update API endpoints for cooler entities and override
- Add cooler selection and controls to frontend UI
- Update documentation

## Testing
- Manual integration testing completed
- Verified mutual exclusion logic
- Tested override controls for both devices

Closes #58"
```

**Step 4: Merge and deploy**

After PR approval:

```bash
# Merge to main
gh pr merge --squash

# Switch back to main and pull
git checkout master
git pull origin master

# Deploy to Raspberry Pi
sshpass -p 'tilt' ssh -o StrictHostKeyChecking=no pi@192.168.4.117 \
  "cd /opt/brewsignal && git fetch origin && git reset --hard origin/master && sudo systemctl restart brewsignal"

# Verify deployment
sshpass -p 'tilt' ssh -o StrictHostKeyChecking=no pi@192.168.4.117 "sudo journalctl -u brewsignal -n 50 --no-pager"
```

Expected: Service restarts successfully, migration runs, no errors.

**Step 5: Verify production deployment**

1. Navigate to `http://192.168.4.117:8080`
2. Create/edit batch with cooler entity
3. Verify control loop operates correctly
4. Monitor for any errors in logs

---

## Task 17: Cleanup and Close

**Files:**
- None (cleanup task)

**Step 1: Remove worktree**

```bash
# From main repo directory
git worktree remove .worktrees/feature/cooling-control
```

**Step 2: Delete feature branch**

```bash
git branch -d feature/cooling-control
git push origin --delete feature/cooling-control
```

**Step 3: Close GitHub issue**

```bash
gh issue close 58 --comment "Implemented in PR #<number>. Cooling control now available for fermentation temperature management."
```

**Step 4: Update project documentation if needed**

Add any additional notes to README or user-facing docs about cooling control feature.

---

## Success Criteria

- [ ] Database migration adds `cooler_entity_id` column
- [ ] Backend control loop supports dual-device operation
- [ ] Mutual exclusion prevents heater and cooler from running simultaneously
- [ ] Min cycle time protection works for both devices
- [ ] API endpoints return cooler status and accept cooler overrides
- [ ] Frontend displays cooler selection and controls
- [ ] Manual overrides work for both devices independently
- [ ] "Auto Mode" button cancels all overrides
- [ ] Existing heating-only batches work unchanged
- [ ] Deployment to Raspberry Pi succeeds
- [ ] Production testing confirms feature works correctly

---

## Notes

- All code follows existing patterns (mirroring heater implementation)
- Backward compatibility maintained (cooler fields nullable)
- DRY principle applied (reuse HA client, similar logic)
- YAGNI respected (no features beyond requirements)
- Commits are frequent and focused on single tasks
- Each step is 2-5 minutes of work for efficient TDD flow
