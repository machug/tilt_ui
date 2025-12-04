"""Background task for temperature control via Home Assistant."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from .database import async_session_factory
from .models import Batch, ControlEvent, AmbientReading, serialize_datetime_to_utc
from .routers.config import get_config_value
from .services.ha_client import get_ha_client, init_ha_client
from .websocket import manager as ws_manager

logger = logging.getLogger(__name__)

_controller_task: asyncio.Task | None = None
CONTROL_INTERVAL_SECONDS = 60
MIN_CYCLE_MINUTES = 5  # Minimum time between heater state changes

# Track per-batch heater states to avoid redundant API calls
# Keys are batch_id, values are {"state": "on"/"off", "last_change": datetime}
_batch_heater_states: dict[int, dict] = {}

# Track per-batch cooler states (same structure as heater states)
_batch_cooler_states: dict[int, dict] = {}

# Track per-batch manual overrides
# Keys are batch_id, values are {"state": "on"/"off", "until": datetime or None}
_batch_overrides: dict[int, dict] = {}

# Track HA config to detect changes


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
_last_ha_url: Optional[str] = None
_last_ha_token: Optional[str] = None

# Event to trigger immediate control check (for override)
_wake_event: asyncio.Event | None = None


async def _wait_or_wake(seconds: float) -> None:
    """Sleep for specified seconds, but wake early if _wake_event is set."""
    global _wake_event
    if _wake_event is None:
        await asyncio.sleep(seconds)
        return

    try:
        await asyncio.wait_for(_wake_event.wait(), timeout=seconds)
        _wake_event.clear()  # Reset for next wait
    except asyncio.TimeoutError:
        pass  # Normal timeout, continue


def _trigger_immediate_check() -> None:
    """Wake the control loop to run immediately."""
    global _wake_event
    if _wake_event is not None:
        _wake_event.set()


def get_device_temp(device_id: str) -> Optional[float]:
    """Get the latest wort temperature for a specific device.

    Returns temperature in Fahrenheit (calibrated if available).
    """
    from .state import latest_readings

    if not device_id or device_id not in latest_readings:
        return None

    reading = latest_readings[device_id]
    # Return calibrated temp, or raw temp if not available
    return reading.get("temp") or reading.get("temp_raw")


def get_latest_tilt_temp() -> Optional[float]:
    """Get the latest wort temperature from any active Tilt.

    Returns temperature in Fahrenheit (calibrated if available).
    """
    # Import here to avoid circular imports
    from .state import latest_readings

    if not latest_readings:
        return None

    # Get the most recently seen Tilt
    latest = None
    latest_time = None

    for reading in latest_readings.values():
        last_seen_str = reading.get("last_seen")
        if last_seen_str:
            try:
                last_seen = datetime.fromisoformat(last_seen_str.replace("Z", "+00:00"))
                if latest_time is None or last_seen > latest_time:
                    latest_time = last_seen
                    latest = reading
            except (ValueError, TypeError):
                continue

    if latest:
        # Return calibrated temp, or raw temp if not available
        return latest.get("temp") or latest.get("temp_raw")

    return None


def get_latest_tilt_id() -> Optional[str]:
    """Get the ID of the most recently active Tilt."""
    from .state import latest_readings

    if not latest_readings:
        return None

    latest_id = None
    latest_time = None

    for tilt_id, reading in latest_readings.items():
        last_seen_str = reading.get("last_seen")
        if last_seen_str:
            try:
                last_seen = datetime.fromisoformat(last_seen_str.replace("Z", "+00:00"))
                if latest_time is None or last_seen > latest_time:
                    latest_time = last_seen
                    latest_id = tilt_id
            except (ValueError, TypeError):
                continue

    return latest_id


async def get_latest_ambient_temp(db) -> Optional[float]:
    """Get the most recent ambient temperature reading."""
    from sqlalchemy import desc

    result = await db.execute(
        select(AmbientReading.temperature)
        .where(AmbientReading.temperature.isnot(None))
        .order_by(desc(AmbientReading.timestamp))
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row


async def log_control_event(
    db,
    action: str,
    wort_temp: Optional[float],
    ambient_temp: Optional[float],
    target_temp: Optional[float],
    tilt_id: Optional[str],
    batch_id: Optional[int] = None,
) -> None:
    """Log a control event to the database."""
    event = ControlEvent(
        action=action,
        wort_temp=wort_temp,
        ambient_temp=ambient_temp,
        target_temp=target_temp,
        tilt_id=tilt_id,
        batch_id=batch_id,
    )
    db.add(event)
    await db.commit()

    # Broadcast event via WebSocket
    await ws_manager.broadcast_json({
        "type": "control_event",
        "action": action,
        "wort_temp": wort_temp,
        "ambient_temp": ambient_temp,
        "target_temp": target_temp,
        "batch_id": batch_id,
        "timestamp": serialize_datetime_to_utc(datetime.now(timezone.utc))
    })

    batch_info = f", batch_id={batch_id}" if batch_id else ""
    logger.info(f"Control event: {action} (wort={wort_temp}, target={target_temp}{batch_info})")


async def set_heater_state_for_batch(
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
    """Turn heater on or off for a specific batch and log the event."""
    global _batch_heater_states

    # Get batch's heater state tracking
    batch_state = _batch_heater_states.get(batch_id, {})
    last_state = batch_state.get("state")
    last_change = batch_state.get("last_change")

    # Check minimum cycle time (skip for forced changes like overrides)
    if not force and last_change is not None:
        elapsed = datetime.now(timezone.utc) - last_change
        if elapsed < timedelta(minutes=MIN_CYCLE_MINUTES):
            remaining = MIN_CYCLE_MINUTES - (elapsed.total_seconds() / 60)
            logger.debug(f"Batch {batch_id}: Skipping heater change to '{state}' - min cycle time not met ({remaining:.1f} min remaining)")
            return False

    logger.debug(f"Batch {batch_id}: Attempting to set heater to '{state}' (entity: {entity_id})")

    if state == "on":
        success = await ha_client.call_service("switch", "turn_on", entity_id)
        action = "heat_on"
    else:
        success = await ha_client.call_service("switch", "turn_off", entity_id)
        action = "heat_off"

    if success:
        _batch_heater_states[batch_id] = {
            "state": state,
            "last_change": datetime.now(timezone.utc),
            "entity_id": entity_id,
        }
        logger.info(f"Batch {batch_id}: Heater state changed: {last_state} -> {state}")
        await log_control_event(db, action, wort_temp, ambient_temp, target_temp, device_id, batch_id)
    else:
        logger.error(f"Batch {batch_id}: Failed to set heater to '{state}' via HA (entity: {entity_id})")

    return success


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
    cooler_entity = batch.cooler_entity_id

    if not heater_entity and not cooler_entity:
        return

    # Get temperature from batch's linked device
    wort_temp = get_device_temp(device_id) if device_id else None
    if wort_temp is None:
        logger.debug(f"Batch {batch_id}: No temperature available from device {device_id}")
        return

    # Use batch-specific settings or fall back to global
    target_temp = batch.temp_target if batch.temp_target is not None else global_target
    hysteresis = batch.temp_hysteresis if batch.temp_hysteresis is not None else global_hysteresis

    # Sync cached heater state with actual HA state
    # NOTE: This sync happens before checking minimum cycle time. If the heater state
    # was changed externally (e.g., manual toggle in HA), this sync updates our cache
    # but does NOT reset the last_change timestamp. This means external changes won't
    # bypass the MIN_CYCLE_MINUTES protection, which is intentional to prevent rapid
    # cycling even when users manually toggle the heater.
    if heater_entity:
        actual_heater_state = await ha_client.get_state(heater_entity)
        if actual_heater_state:
            ha_heater_state = actual_heater_state.get("state", "").lower()
            if ha_heater_state in ("on", "off"):
                if batch_id in _batch_heater_states:
                    if _batch_heater_states[batch_id].get("state") != ha_heater_state:
                        logger.debug(f"Batch {batch_id}: Syncing heater cache: {_batch_heater_states[batch_id].get('state')} -> {ha_heater_state} (from HA)")
                    # Only update the state, preserve the existing last_change timestamp
                    _batch_heater_states[batch_id]["state"] = ha_heater_state
                else:
                    # Initialize state tracking for new batch (no last_change yet)
                    _batch_heater_states[batch_id] = {"state": ha_heater_state}
            elif ha_heater_state == "unavailable":
                logger.warning(f"Batch {batch_id}: Heater entity {heater_entity} is unavailable in HA")
                return  # Early return - cannot control unavailable entity

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
                return  # Early return - cannot control unavailable entity

    current_heater_state = _batch_heater_states.get(batch_id, {}).get("state")
    current_cooler_state = _batch_cooler_states.get(batch_id, {}).get("state")

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

    # Calculate thresholds (symmetric hysteresis)
    heat_on_threshold = round(target_temp - hysteresis, 1)
    cool_on_threshold = round(target_temp + hysteresis, 1)

    logger.debug(
        f"Batch {batch_id}: Control check: wort={wort_temp:.2f}F, target={target_temp:.2f}F, "
        f"hysteresis={hysteresis:.2f}F, heat_on<={heat_on_threshold:.2f}F, "
        f"cool_on>={cool_on_threshold:.2f}F, heater={current_heater_state}, cooler={current_cooler_state}"
    )

    # Automatic control logic with mutual exclusion
    # CRITICAL: Turn OFF opposite device FIRST, then turn ON current device
    # This prevents both devices from being ON simultaneously
    if wort_temp <= heat_on_threshold:
        # Need heating - FIRST ensure cooler is OFF
        if cooler_entity and current_cooler_state == "on":
            logger.info(f"Batch {batch_id}: Turning cooler OFF (heater needs to run)")
            await set_cooler_state_for_batch(
                ha_client, cooler_entity, "off", db, batch_id,
                wort_temp, ambient_temp, target_temp, device_id
            )
            # Refresh state after change
            current_cooler_state = _batch_cooler_states.get(batch_id, {}).get("state")

        # THEN turn heater ON (only if cooler is confirmed off)
        if heater_entity and current_heater_state != "on":
            logger.info(f"Batch {batch_id}: Wort temp {wort_temp:.1f}F at/below threshold {heat_on_threshold:.1f}F, turning heater ON")
            await set_heater_state_for_batch(
                ha_client, heater_entity, "on", db, batch_id,
                wort_temp, ambient_temp, target_temp, device_id
            )
            # Refresh state after change
            current_heater_state = _batch_heater_states.get(batch_id, {}).get("state")

    elif wort_temp >= cool_on_threshold:
        # Need cooling - FIRST ensure heater is OFF
        if heater_entity and current_heater_state == "on":
            logger.info(f"Batch {batch_id}: Turning heater OFF (cooler needs to run)")
            await set_heater_state_for_batch(
                ha_client, heater_entity, "off", db, batch_id,
                wort_temp, ambient_temp, target_temp, device_id
            )
            # Refresh state after change
            current_heater_state = _batch_heater_states.get(batch_id, {}).get("state")

        # THEN turn cooler ON (only if heater is confirmed off)
        if cooler_entity and current_cooler_state != "on":
            logger.info(f"Batch {batch_id}: Wort temp {wort_temp:.1f}F at/above threshold {cool_on_threshold:.1f}F, turning cooler ON")
            await set_cooler_state_for_batch(
                ha_client, cooler_entity, "on", db, batch_id,
                wort_temp, ambient_temp, target_temp, device_id
            )
            # Refresh state after change
            current_cooler_state = _batch_cooler_states.get(batch_id, {}).get("state")

    else:
        # Within deadband - maintain current states
        logger.debug(
            f"Batch {batch_id}: Within hysteresis band ({heat_on_threshold:.1f}F-{cool_on_threshold:.1f}F), "
            f"maintaining states: heater={current_heater_state}, cooler={current_cooler_state}"
        )


async def temperature_control_loop() -> None:
    """Main temperature control loop - handles multiple batches with their own heaters."""
    global _last_ha_url, _last_ha_token, _wake_event

    _wake_event = asyncio.Event()

    while True:
        try:
            async with async_session_factory() as db:
                # Check if temperature control is enabled
                temp_control_enabled = await get_config_value(db, "temp_control_enabled")

                if not temp_control_enabled:
                    await _wait_or_wake(CONTROL_INTERVAL_SECONDS)
                    continue

                # Check if HA is enabled
                ha_enabled = await get_config_value(db, "ha_enabled")
                if not ha_enabled:
                    await _wait_or_wake(CONTROL_INTERVAL_SECONDS)
                    continue

                # Get HA client - reinitialize if config changed
                ha_url = await get_config_value(db, "ha_url")
                ha_token = await get_config_value(db, "ha_token")

                if not ha_url or not ha_token:
                    await _wait_or_wake(CONTROL_INTERVAL_SECONDS)
                    continue

                # Reinitialize HA client if URL or token changed
                if ha_url != _last_ha_url or ha_token != _last_ha_token:
                    logger.info("HA config changed, reinitializing client")
                    init_ha_client(ha_url, ha_token)
                    _last_ha_url = ha_url
                    _last_ha_token = ha_token

                ha_client = get_ha_client()
                if not ha_client:
                    init_ha_client(ha_url, ha_token)
                    _last_ha_url = ha_url
                    _last_ha_token = ha_token
                    ha_client = get_ha_client()

                if not ha_client:
                    await _wait_or_wake(CONTROL_INTERVAL_SECONDS)
                    continue

                # Get global control parameters (used as defaults)
                global_target = await get_config_value(db, "temp_target") or 68.0
                global_hysteresis = await get_config_value(db, "temp_hysteresis") or 1.0
                ambient_temp = await get_latest_ambient_temp(db)

                # Get all active batches with heater OR cooler entities configured
                result = await db.execute(
                    select(Batch).where(
                        Batch.status == "fermenting",
                        Batch.device_id.isnot(None),
                        (Batch.heater_entity_id.isnot(None)) | (Batch.cooler_entity_id.isnot(None)),
                    )
                )
                batches = result.scalars().all()

                # Control each batch's temperature concurrently for better performance
                if batches:
                    await asyncio.gather(*[
                        control_batch_temperature(
                            ha_client, batch, db, global_target, global_hysteresis, ambient_temp
                        )
                        for batch in batches
                    ], return_exceptions=True)

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

        except Exception as e:
            logger.error(f"Temperature control error: {e}", exc_info=True)

        await _wait_or_wake(CONTROL_INTERVAL_SECONDS)


def get_control_status() -> dict:
    """Get current temperature control status (legacy global status)."""
    wort_temp = get_latest_tilt_temp()

    return {
        "heater_state": None,  # No longer a single global heater
        "override_active": False,
        "override_state": None,
        "override_until": None,
        "wort_temp": wort_temp,
    }


def get_batch_control_status(batch_id: int) -> dict:
    """Get temperature control status for a specific batch.

    Returns state_available=True if runtime state exists for this batch,
    False if state was cleaned up (e.g., batch completed/archived).
    """
    heater_state = _batch_heater_states.get(batch_id)
    cooler_state = _batch_cooler_states.get(batch_id)
    override = _batch_overrides.get(batch_id)

    # state_available indicates whether runtime state exists for this batch
    # False means state was cleaned up (batch no longer fermenting) or never existed
    state_available = heater_state is not None or cooler_state is not None

    # For backward compatibility, keep override_state (deprecated)
    # It will return heater override state if present, otherwise cooler override state
    legacy_override_state = None
    if override:
        if override.get("heater"):
            legacy_override_state = override["heater"].get("state")
        elif override.get("cooler"):
            legacy_override_state = override["cooler"].get("state")

    return {
        "batch_id": batch_id,
        "enabled": True,  # Batch-level control is always enabled if state exists
        "heater_state": heater_state.get("state") if heater_state else None,
        "heater_entity": heater_state.get("entity_id") if heater_state else None,
        "cooler_state": cooler_state.get("state") if cooler_state else None,
        "cooler_entity": cooler_state.get("entity_id") if cooler_state else None,
        "override_active": override is not None,
        "override_state": legacy_override_state,  # Deprecated - kept for backward compat
        "override_until": serialize_datetime_to_utc(override.get("heater", {}).get("until") or override.get("cooler", {}).get("until")) if override else None,
        "target_temp": None,  # Would need to query DB for batch.temp_target
        "hysteresis": None,  # Would need to query DB for batch.temp_hysteresis
        "wort_temp": None,  # Would need to get from latest_readings
        "state_available": state_available,
    }


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
        batch_id: If provided, override for specific batch; otherwise legacy global override
        device_type: "heater" or "cooler" - which device to override

    Returns:
        True if override was set/cleared successfully
    """
    global _batch_overrides

    if batch_id is None:
        # Legacy global override - no longer supported for multi-batch
        logger.warning("Global override not supported in multi-batch mode. Use batch_id parameter.")
        return False

    if device_type not in ("heater", "cooler"):
        logger.error(f"Invalid device_type: {device_type}. Must be 'heater' or 'cooler'.")
        return False

    if state is None:
        # Cancel override for specific device type
        if batch_id in _batch_overrides and device_type in _batch_overrides[batch_id]:
            del _batch_overrides[batch_id][device_type]
            # Clean up batch entry if no overrides remain
            if not _batch_overrides[batch_id]:
                del _batch_overrides[batch_id]
        logger.info(f"Batch {batch_id}: Manual override cancelled for {device_type}, returning to auto mode")
        _trigger_immediate_check()
        return True

    if state not in ("on", "off"):
        return False

    # Initialize nested structure if needed
    if batch_id not in _batch_overrides:
        _batch_overrides[batch_id] = {}

    _batch_overrides[batch_id][device_type] = {
        "state": state,
        "until": datetime.now(timezone.utc) + timedelta(minutes=duration_minutes) if duration_minutes > 0 else None,
    }
    logger.info(f"Batch {batch_id}: Manual override set: {device_type} {state} for {duration_minutes} minutes")
    _trigger_immediate_check()
    return True


def sync_cached_state(state: Optional[str], batch_id: Optional[int] = None, device_type: str = "heater") -> None:
    """Keep the in-memory device state in sync with external changes (e.g., manual HA toggles).

    Args:
        state: "on", "off", or None
        batch_id: The batch ID to sync state for
        device_type: "heater" or "cooler" - which device to sync
    """
    global _batch_heater_states, _batch_cooler_states

    if state in ("on", "off", None) and batch_id is not None:
        if device_type == "heater":
            _batch_heater_states.setdefault(batch_id, {})["state"] = state
        elif device_type == "cooler":
            _batch_cooler_states.setdefault(batch_id, {})["state"] = state


# Backward compatibility alias
def sync_cached_heater_state(state: Optional[str], batch_id: Optional[int] = None) -> None:
    """Legacy function - use sync_cached_state instead."""
    sync_cached_state(state, batch_id, device_type="heater")


def start_temp_controller() -> None:
    """Start the temperature control background task."""
    global _controller_task
    if _controller_task is None or _controller_task.done():
        _controller_task = asyncio.create_task(temperature_control_loop())
        logger.info("Temperature controller started")


def stop_temp_controller() -> None:
    """Stop the temperature control background task."""
    global _controller_task
    if _controller_task and not _controller_task.done():
        _controller_task.cancel()
        logger.info("Temperature controller stopped")
