# Cooling Control Design

**Date:** 2025-12-04
**Feature:** Add cooling control support for fermentation temperature management
**GitHub Issue:** [#58](https://github.com/machug/brewsignal/issues/58)
**Status:** Design approved, ready for implementation

---

## Overview

Add cooling control capability to complement the existing heating system, enabling full temperature management (heating and cooling) for fermentation batches using separate Home Assistant switch entities.

### Current State (Heating Only)

The system currently supports heating-only temperature control:
- Per-batch heater assignment (`Batch.heater_entity_id`)
- Automatic control with hysteresis-based thresholds
- Manual override support (60-minute default expiration)
- Min cycle time protection (5 minutes)
- Home Assistant switch integration
- Runtime state tracking in `_batch_heater_states`

**Key Files:**
- `backend/temp_controller.py` - Control loop logic
- `backend/models.py:343-346` - Batch heater fields
- `backend/routers/control.py` - Control API endpoints

### Design Goals

1. **Mirror existing heater architecture** - Symmetric implementation for cooling
2. **Mutual exclusion** - Never run heater and cooler simultaneously
3. **Backward compatibility** - Existing heating-only setups continue working unchanged
4. **Per-batch independence** - Each batch has independent heater/cooler control
5. **Shared hysteresis** - Single deadband value for both heating and cooling

---

## Database Schema

### Batch Model Changes

Add cooling field to `Batch` model (backend/models.py):

```python
# Temperature control - per-batch assignments
heater_entity_id: Mapped[Optional[str]] = mapped_column(String(100))
cooler_entity_id: Mapped[Optional[str]] = mapped_column(String(100))  # NEW
temp_target: Mapped[Optional[float]] = mapped_column()
temp_hysteresis: Mapped[Optional[float]] = mapped_column()  # Shared for heat/cool
```

### Migration Strategy

1. Add `cooler_entity_id` column to batches table (nullable)
2. No data migration needed (defaults to NULL = heating-only mode)
3. Existing batches continue working unchanged

### Operational Modes

Three modes per batch based on entity configuration:

| Mode | heater_entity_id | cooler_entity_id | Behavior |
|------|-----------------|------------------|----------|
| **Heating-only** | Set | NULL | Existing behavior, no changes |
| **Cooling-only** | NULL | Set | Only cooling control active |
| **Dual-mode** | Set | Set | Full temp regulation with mutual exclusion |

---

## Control Logic

### Threshold Calculation (Symmetric Hysteresis)

Using shared `temp_hysteresis` value:

```python
heat_on_threshold = target_temp - hysteresis
cool_on_threshold = target_temp + hysteresis
```

**Example:** Target = 68°F, Hysteresis = 1°F
- Heat ON when: temp ≤ 67°F
- Cool ON when: temp ≥ 69°F
- Deadband: 67°F < temp < 69°F (maintain current states)

### Control Flow with Mutual Exclusion

```python
async def control_batch_temperature(
    ha_client, batch, db, global_target, global_hysteresis, ambient_temp
):
    """Control both heating and cooling for a batch."""

    heater_entity = batch.heater_entity_id
    cooler_entity = batch.cooler_entity_id

    # Get current states
    heater_state = _batch_heater_states.get(batch_id, {}).get("state")
    cooler_state = _batch_cooler_states.get(batch_id, {}).get("state")

    # Calculate thresholds
    heat_on_threshold = target - hysteresis
    cool_on_threshold = target + hysteresis

    # Control logic with mutual exclusion
    if wort_temp <= heat_on_threshold and heater_entity:
        # Need heating
        await set_heater_state("on", ...)
        if cooler_entity and cooler_state == "on":
            await set_cooler_state("off", ...)  # Ensure cooler OFF

    elif wort_temp >= cool_on_threshold and cooler_entity:
        # Need cooling
        await set_cooler_state("on", ...)
        if heater_entity and heater_state == "on":
            await set_heater_state("off", ...)  # Ensure heater OFF

    else:
        # Within deadband - maintain current states
        pass
```

### State Tracking

Add parallel state tracking for coolers (backend/temp_controller.py):

```python
# Add alongside existing _batch_heater_states
_batch_cooler_states: dict[int, dict] = {}

# Structure (same as heater states):
{
    batch_id: {
        "state": "on" | "off",
        "last_change": datetime,
        "entity_id": "switch.fermentation_fridge"
    }
}
```

### Min Cycle Time Protection

Apply same 5-minute minimum cycle time to **both** devices:
- Prevents rapid switching (heater burnout prevention)
- Prevents compressor short-cycling (critical for refrigeration)
- Tracked independently per device type
- Check enforced in `set_heater_state_for_batch()` and `set_cooler_state_for_batch()`

---

## API Changes

### Response Models

**Update existing BatchControlStatusResponse:**

```python
class BatchControlStatusResponse(BaseModel):
    batch_id: int
    enabled: bool

    # Heater fields (existing)
    heater_state: Optional[str]
    heater_entity: Optional[str]

    # Cooler fields (NEW)
    cooler_state: Optional[str]
    cooler_entity: Optional[str]

    # Shared fields
    override_active: bool
    override_state: Optional[str]
    override_until: Optional[str]
    target_temp: Optional[float]
    hysteresis: Optional[float]
    wort_temp: Optional[float]
    state_available: bool
```

### New Endpoints

```python
# Get available cooler entities
GET /api/control/cooler-entities
Response: list[HeaterEntityResponse]  # Same structure as heater entities

# Get cooler state (similar to heater endpoint)
GET /api/control/cooler?batch_id={id}
Response: HeaterStateResponse with cooler data
```

### Updated Endpoints

**Existing endpoint includes cooler status:**

```python
GET /api/control/batch/{id}/status
Response: BatchControlStatusResponse  # Now includes cooler_state, cooler_entity
```

### Override System

**Support independent overrides for both devices:**

```python
class OverrideRequest(BaseModel):
    device_type: str  # "heater" or "cooler"
    state: Optional[str]  # "on", "off", or null
    duration_minutes: int = 60
    batch_id: int  # Required

# Override state tracking (extend existing _batch_overrides):
_batch_overrides: dict[int, dict] = {
    batch_id: {
        "heater": {"state": "on", "until": datetime},  # Optional
        "cooler": {"state": "off", "until": datetime}  # Optional
    }
}
```

**Override patterns:**

```python
# Force heater on (auto turns cooler off via mutual exclusion)
POST /api/control/override {"device_type": "heater", "state": "on", "batch_id": 1}

# Force cooler on (auto turns heater off via mutual exclusion)
POST /api/control/override {"device_type": "cooler", "state": "on", "batch_id": 1}

# Force heater off (cooler remains in auto mode)
POST /api/control/override {"device_type": "heater", "state": "off", "batch_id": 1}

# Force cooler off (heater remains in auto mode)
POST /api/control/override {"device_type": "cooler", "state": "off", "batch_id": 1}

# Force BOTH off (maintenance mode - no temp control)
POST /api/control/override {"device_type": "heater", "state": "off", "batch_id": 1}
POST /api/control/override {"device_type": "cooler", "state": "off", "batch_id": 1}

# Return to auto mode
POST /api/control/override {"device_type": "heater", "state": null, "batch_id": 1}
POST /api/control/override {"device_type": "cooler", "state": null, "batch_id": 1}
```

### Control Events

**Add new action types to ControlEvent model:**
- Existing: `heat_on`, `heat_off`
- New: `cool_on`, `cool_off`

All existing fields (wort_temp, target_temp, ambient_temp, batch_id) work as-is.

---

## Frontend Changes

### Batch Configuration UI

**Add cooler entity selection** (mirrors heater selection):

```svelte
<!-- In BatchForm.svelte and batch detail page -->
<label>
  Cooler Entity (optional)
  <select bind:value={batch.cooler_entity_id}>
    <option value={null}>No cooling control</option>
    {#each coolerEntities as entity}
      <option value={entity.entity_id}>{entity.friendly_name}</option>
    {/each}
  </select>
</label>
```

### Control Status Display

```svelte
{#if hasHeaterControl || hasCoolerControl}
  <div class="control-status">
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
{/if}
```

### Manual Override Controls

```svelte
<!-- Override buttons for both devices -->
<div class="override-controls">
  {#if batch.heater_entity_id}
    <button onclick={() => handleOverride('heater', 'on')}>Force Heat ON</button>
    <button onclick={() => handleOverride('heater', 'off')}>Force Heat OFF</button>
  {/if}

  {#if batch.cooler_entity_id}
    <button onclick={() => handleOverride('cooler', 'on')}>Force Cool ON</button>
    <button onclick={() => handleOverride('cooler', 'off')}>Force Cool OFF</button>
  {/if}

  <button onclick={() => handleOverride('both', null)}>Auto Mode</button>
</div>
```

### Visual Indicators

- **Status badges** showing heater/cooler state (ON/OFF/AUTO)
- **Mutual exclusion indicator** when one device blocks the other
- **Temperature chart annotations** for cooling/heating events from ControlEvent log

---

## Technical Considerations

### 1. Mutual Exclusion Enforcement

**Critical safety requirement:** Never run heater and cooler simultaneously.

**Implementation:**
- Check before every state change
- Explicit turn-off of opposing device when activating
- Log warnings if both try to activate
- Override system respects mutual exclusion

### 2. Min Cycle Time

**5-minute minimum for both devices:**
- Heater: Prevents element burnout
- Cooler: Prevents compressor short-cycling (critical!)

**Tracking:**
- Independent `last_change` timestamps per device
- Enforced in `set_heater_state_for_batch()` and `set_cooler_state_for_batch()`
- Skip changes if min cycle time not met (with debug logging)

### 3. Override Handling

**Manual overrides respect mutual exclusion:**
- Forcing heater ON → auto forces cooler OFF
- Forcing cooler ON → auto forces heater OFF
- Forcing device OFF → other device remains in auto mode
- Clear messaging in API responses about mutual exclusion

### 4. Backward Compatibility

**No breaking changes:**
- `cooler_entity_id` is nullable
- Existing heating-only setups work unchanged
- Control loop checks for entity presence before control logic
- API responses include new fields (optional, clients can ignore)

### 5. Home Assistant Integration

**Reuse existing patterns:**
- Same service calls: `switch.turn_on`, `switch.turn_off`
- Support both `switch.*` and `input_boolean.*` entities
- State syncing with HA to handle manual toggles
- Entity availability checking before control actions

### 6. State Cleanup

**Clean up runtime state when batches complete:**

```python
# In temperature_control_loop(), after processing batches:
active_batch_ids = {b.id for b in batches}

# Clean up heater states (existing)
for batch_id in list(_batch_heater_states.keys()):
    if batch_id not in active_batch_ids:
        del _batch_heater_states[batch_id]

# Clean up cooler states (NEW)
for batch_id in list(_batch_cooler_states.keys()):
    if batch_id not in active_batch_ids:
        del _batch_cooler_states[batch_id]

# Clean up overrides (existing, handles both heater and cooler)
for batch_id in list(_batch_overrides.keys()):
    if batch_id not in active_batch_ids:
        del _batch_overrides[batch_id]
```

---

## Example Use Cases

### Scenario 1: Ale Fermentation (Heating Only)
**Configuration:**
- Target: 68°F, Hysteresis: 1°F
- Heater: `switch.fermentation_heater`
- Cooler: NULL

**Behavior:** Existing heating control, no changes. Heater turns on below 67°F, off above 69°F.

### Scenario 2: Lager Fermentation (Cooling Only)
**Configuration:**
- Target: 50°F, Hysteresis: 1°F
- Heater: NULL
- Cooler: `switch.fermentation_fridge`

**Behavior:** Cooling control only. Cooler turns on above 51°F, off below 49°F.

### Scenario 3: Year-Round Control (Heating + Cooling)
**Configuration:**
- Target: 68°F, Hysteresis: 1°F
- Heater: `switch.fermentation_heater`
- Cooler: `switch.fermentation_fridge`

**Behavior:**
- Below 67°F: Heater ON, cooler OFF
- Above 69°F: Cooler ON, heater OFF
- 67°F - 69°F: Both maintain current state (deadband)
- Mutual exclusion enforced automatically

### Scenario 4: Cold Crash (Manual Override)
**Setup:** Active ale fermentation at 68°F with dual-mode control

**Steps:**
1. User force-sets cooler override to ON
2. User manually updates `temp_target` to 35°F
3. Cooler runs continuously, heater blocked by mutual exclusion
4. After 3 days, user cancels override, returns to auto mode

---

## Migration Path

### Database Migration

```python
# In backend/database.py
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

# Call from init_db() in correct migration order
```

### Deployment Steps

1. Deploy backend with migration
2. Migration adds `cooler_entity_id` column (nullable)
3. Deploy frontend with cooler UI
4. Users can optionally configure cooler entities
5. Existing batches continue with heating-only mode

---

## Testing Plan

### Unit Tests
- [ ] Mutual exclusion logic (heater blocks cooler, vice versa)
- [ ] Threshold calculations with symmetric hysteresis
- [ ] Min cycle time enforcement for both devices
- [ ] Override handling with mutual exclusion
- [ ] State cleanup when batches complete

### Integration Tests
- [ ] Heating-only mode (backward compatibility)
- [ ] Cooling-only mode
- [ ] Dual-mode (heater + cooler)
- [ ] Manual overrides for both devices
- [ ] HA entity availability handling
- [ ] WebSocket broadcasts for control events

### Manual Testing
- [ ] Configure batch with cooler entity
- [ ] Verify mutual exclusion in logs
- [ ] Test override controls via UI
- [ ] Verify min cycle time prevents rapid switching
- [ ] Test cold crash workflow (manual override + temp change)

---

## Files to Modify

### Backend
- `backend/models.py` - Add `cooler_entity_id` to Batch model
- `backend/database.py` - Add migration for cooler column
- `backend/temp_controller.py` - Add cooler state tracking and control logic
- `backend/routers/control.py` - Add cooler endpoints and update response models

### Frontend
- `frontend/src/lib/api.ts` - Add cooler API types and functions
- `frontend/src/routes/batches/[id]/+page.svelte` - Add cooler status display and controls
- `frontend/src/lib/components/BatchForm.svelte` - Add cooler entity selection
- `frontend/src/lib/stores/config.svelte` - Update types for cooler support

### Documentation
- `CLAUDE.md` - Update temperature control section with cooling details

---

## Future Enhancements

### Automated Fermentation Scheduling (Issue #60)
- Monitor SG readings vs target FG
- Auto-trigger cold crash after diacetyl rest
- Stage timeline visualization
- Builds on this cooling control foundation

### Notifications
- Alert when cold crash completes
- Warn if temp control fails
- Notify on stage transitions (with automated scheduling)

### Advanced Control Modes
- PID control for more precise temperature regulation
- Separate hysteresis for heating vs cooling (if users request)
- Ambient temperature compensation

---

## Success Criteria

- [ ] Existing heating-only batches work unchanged
- [ ] New batches can configure cooler entities
- [ ] Dual-mode batches never run heater and cooler simultaneously
- [ ] Min cycle time protection works for both devices
- [ ] Manual overrides respect mutual exclusion
- [ ] UI clearly shows heater and cooler status
- [ ] Control events log both heating and cooling actions
- [ ] No breaking changes to existing API clients

---

## Priority

**Medium-High** - Significantly expands temperature control capabilities for year-round brewing.

## Related Issues

- **Implements:** [#58 - Add Cooling Control Support](https://github.com/machug/brewsignal/issues/58)
- **Enables:** [#60 - Automated Fermentation Scheduling](https://github.com/machug/brewsignal/issues/60)
