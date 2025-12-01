"""Background task for temperature control via Home Assistant."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from .database import async_session_factory
from .models import Batch, ControlEvent, AmbientReading
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

# Track per-batch manual overrides
# Keys are batch_id, values are {"state": "on"/"off", "until": datetime or None}
_batch_overrides: dict[int, dict] = {}

# Track HA config to detect changes
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
        "timestamp": datetime.now(timezone.utc).isoformat()
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


async def control_batch_heater(
    ha_client,
    batch: Batch,
    db,
    global_target: float,
    global_hysteresis: float,
    ambient_temp: Optional[float],
) -> None:
    """Control heater for a single batch."""
    batch_id = batch.id
    device_id = batch.device_id
    heater_entity = batch.heater_entity_id

    if not heater_entity:
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
    actual_state = await ha_client.get_state(heater_entity)
    if actual_state:
        ha_state = actual_state.get("state", "").lower()
        if ha_state in ("on", "off"):
            if batch_id in _batch_heater_states:
                if _batch_heater_states[batch_id].get("state") != ha_state:
                    logger.debug(f"Batch {batch_id}: Syncing heater cache: {_batch_heater_states[batch_id].get('state')} -> {ha_state} (from HA)")
            # Only update the state, preserve the last_change timestamp
            _batch_heater_states.setdefault(batch_id, {})["state"] = ha_state
        elif ha_state == "unavailable":
            logger.warning(f"Batch {batch_id}: Heater entity {heater_entity} is unavailable in HA")
            return

    current_state = _batch_heater_states.get(batch_id, {}).get("state")

    # Check for manual override for this batch
    if batch_id in _batch_overrides:
        override = _batch_overrides[batch_id]
        override_until = override.get("until")
        if override_until and datetime.now(timezone.utc) > override_until:
            # Override expired
            logger.info(f"Batch {batch_id}: Manual override expired, returning to auto mode")
            del _batch_overrides[batch_id]
        else:
            # Override active
            desired_state = override.get("state")
            if current_state != desired_state:
                await set_heater_state_for_batch(
                    ha_client, heater_entity, desired_state, db, batch_id,
                    wort_temp, ambient_temp, target_temp, device_id, force=True
                )
            return

    # Calculate thresholds
    heat_on_threshold = round(target_temp - hysteresis, 1)
    heat_off_threshold = round(target_temp + hysteresis, 1)

    logger.debug(
        f"Batch {batch_id}: Control check: wort={wort_temp:.2f}F, target={target_temp:.2f}F, "
        f"hysteresis={hysteresis:.2f}F, on_threshold={heat_on_threshold:.2f}F, "
        f"off_threshold={heat_off_threshold:.2f}F, cached_state={current_state}"
    )

    # Automatic control logic with hysteresis
    if wort_temp <= heat_on_threshold:
        if current_state != "on":
            logger.info(f"Batch {batch_id}: Wort temp {wort_temp:.1f}F at/below threshold {heat_on_threshold:.1f}F, turning heater ON")
            await set_heater_state_for_batch(
                ha_client, heater_entity, "on", db, batch_id,
                wort_temp, ambient_temp, target_temp, device_id
            )
        else:
            logger.debug(f"Batch {batch_id}: Heater already ON, wort={wort_temp:.1f}F <= on_threshold={heat_on_threshold:.1f}F")

    elif wort_temp >= heat_off_threshold:
        if current_state != "off":
            logger.info(f"Batch {batch_id}: Wort temp {wort_temp:.1f}F at/above threshold {heat_off_threshold:.1f}F, turning heater OFF")
            await set_heater_state_for_batch(
                ha_client, heater_entity, "off", db, batch_id,
                wort_temp, ambient_temp, target_temp, device_id
            )
        else:
            logger.debug(f"Batch {batch_id}: Heater already OFF, wort={wort_temp:.1f}F >= off_threshold={heat_off_threshold:.1f}F")

    else:
        logger.debug(
            f"Batch {batch_id}: Within hysteresis band ({heat_on_threshold:.1f}F-{heat_off_threshold:.1f}F), "
            f"maintaining heater state: {current_state}"
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

                # Get all active batches with heater entities configured
                result = await db.execute(
                    select(Batch).where(
                        Batch.status == "fermenting",
                        Batch.heater_entity_id.isnot(None),
                        Batch.device_id.isnot(None),
                    )
                )
                batches = result.scalars().all()

                # Control each batch's heater
                for batch in batches:
                    await control_batch_heater(
                        ha_client, batch, db, global_target, global_hysteresis, ambient_temp
                    )

                # Cleanup old batch entries from in-memory state dictionaries
                active_batch_ids = {b.id for b in batches}
                for batch_id in list(_batch_heater_states.keys()):
                    if batch_id not in active_batch_ids:
                        logger.debug(f"Cleaning up heater state for inactive batch {batch_id}")
                        del _batch_heater_states[batch_id]
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
    batch_state = _batch_heater_states.get(batch_id)
    override = _batch_overrides.get(batch_id)

    # state_available indicates whether runtime state exists for this batch
    # False means state was cleaned up (batch no longer fermenting) or never existed
    state_available = batch_state is not None

    return {
        "batch_id": batch_id,
        "heater_state": batch_state.get("state") if batch_state else None,
        "heater_entity": batch_state.get("entity_id") if batch_state else None,
        "override_active": override is not None,
        "override_state": override.get("state") if override else None,
        "override_until": override.get("until").isoformat() if override and override.get("until") else None,
        "state_available": state_available,
    }


def set_manual_override(state: Optional[str], duration_minutes: int = 60, batch_id: Optional[int] = None) -> bool:
    """Set manual override for heater control.

    Args:
        state: "on", "off", or None to cancel override
        duration_minutes: How long override lasts (default 60 min)
        batch_id: If provided, override for specific batch; otherwise legacy global override

    Returns:
        True if override was set/cleared successfully
    """
    global _batch_overrides

    if batch_id is None:
        # Legacy global override - no longer supported for multi-batch
        logger.warning("Global heater override not supported in multi-batch mode. Use batch_id parameter.")
        return False

    if state is None:
        # Cancel override for batch
        if batch_id in _batch_overrides:
            del _batch_overrides[batch_id]
        logger.info(f"Batch {batch_id}: Manual override cancelled, returning to auto mode")
        _trigger_immediate_check()
        return True

    if state not in ("on", "off"):
        return False

    _batch_overrides[batch_id] = {
        "state": state,
        "until": datetime.now(timezone.utc) + timedelta(minutes=duration_minutes) if duration_minutes > 0 else None,
    }
    logger.info(f"Batch {batch_id}: Manual override set: heater {state} for {duration_minutes} minutes")
    _trigger_immediate_check()
    return True


def sync_cached_heater_state(state: Optional[str], batch_id: Optional[int] = None) -> None:
    """Keep the in-memory heater state in sync with external changes (e.g., manual HA toggles)."""
    global _batch_heater_states
    if state in ("on", "off", None) and batch_id is not None:
        _batch_heater_states.setdefault(batch_id, {})["state"] = state


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
