"""Background task for temperature control via Home Assistant."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from .database import async_session_factory
from .models import ControlEvent, AmbientReading
from .routers.config import get_config_value
from .services.ha_client import get_ha_client, init_ha_client
from .websocket import manager as ws_manager

logger = logging.getLogger(__name__)

_controller_task: asyncio.Task | None = None
CONTROL_INTERVAL_SECONDS = 60

# Track current heater state to avoid redundant API calls
_heater_state: Optional[str] = None  # "on", "off", or None (unknown)
_override_state: Optional[str] = None  # Manual override: "on", "off", or None (auto)
_override_until: Optional[datetime] = None  # When override expires

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


def get_latest_tilt_temp() -> Optional[float]:
    """Get the latest wort temperature from any active Tilt.

    Returns temperature in Fahrenheit (calibrated if available).
    """
    # Import here to avoid circular imports
    from .main import latest_readings

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
    from .main import latest_readings

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
    from sqlalchemy import select, desc

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
    tilt_id: Optional[str]
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
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

    logger.info(f"Control event: {action} (wort={wort_temp}, target={target_temp})")


async def set_heater_state(ha_client, entity_id: str, state: str, db, wort_temp: float, ambient_temp: Optional[float], target_temp: float, tilt_id: Optional[str]) -> bool:
    """Turn heater on or off and log the event."""
    global _heater_state

    logger.debug(f"Attempting to set heater to '{state}' (entity: {entity_id})")

    if state == "on":
        success = await ha_client.call_service("switch", "turn_on", entity_id)
        action = "heat_on"
    else:
        success = await ha_client.call_service("switch", "turn_off", entity_id)
        action = "heat_off"

    if success:
        old_state = _heater_state
        _heater_state = state
        logger.info(f"Heater state changed: {old_state} -> {state}")
        await log_control_event(db, action, wort_temp, ambient_temp, target_temp, tilt_id)
    else:
        logger.error(f"Failed to set heater to '{state}' via HA (entity: {entity_id})")

    return success


async def temperature_control_loop() -> None:
    """Main temperature control loop."""
    global _heater_state, _override_state, _override_until, _last_ha_url, _last_ha_token, _wake_event

    _wake_event = asyncio.Event()

    while True:
        try:
            async with async_session_factory() as db:
                # Check if temperature control is enabled
                temp_control_enabled = await get_config_value(db, "temp_control_enabled")

                if not temp_control_enabled:
                    # Clear override when control is disabled
                    if _override_state is not None:
                        logger.info("Temperature control disabled, clearing override")
                        _override_state = None
                        _override_until = None
                    await _wait_or_wake(CONTROL_INTERVAL_SECONDS)
                    continue

                # Check if HA is enabled
                ha_enabled = await get_config_value(db, "ha_enabled")
                if not ha_enabled:
                    # Clear override when HA is disabled
                    if _override_state is not None:
                        logger.info("Home Assistant disabled, clearing override")
                        _override_state = None
                        _override_until = None
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

                # Get heater entity
                heater_entity = await get_config_value(db, "ha_heater_entity_id")
                if not heater_entity:
                    logger.debug("No heater entity configured")
                    await _wait_or_wake(CONTROL_INTERVAL_SECONDS)
                    continue

                # Sync cached heater state with actual HA state before making control decisions
                # This prevents stale cache from causing incorrect control decisions
                actual_state = await ha_client.get_state(heater_entity)
                if actual_state:
                    ha_state = actual_state.get("state", "").lower()
                    if ha_state in ("on", "off"):
                        if _heater_state != ha_state:
                            logger.debug(f"Syncing heater cache: {_heater_state} -> {ha_state} (from HA)")
                        _heater_state = ha_state
                    elif ha_state == "unavailable":
                        logger.warning(f"Heater entity {heater_entity} is unavailable in HA")
                        await _wait_or_wake(CONTROL_INTERVAL_SECONDS)
                        continue

                # Get control parameters
                target_temp = await get_config_value(db, "temp_target") or 68.0
                hysteresis = await get_config_value(db, "temp_hysteresis") or 1.0

                # Get current wort temperature
                wort_temp = get_latest_tilt_temp()
                if wort_temp is None:
                    logger.debug("No Tilt temperature available")
                    await _wait_or_wake(CONTROL_INTERVAL_SECONDS)
                    continue

                tilt_id = get_latest_tilt_id()
                ambient_temp = await get_latest_ambient_temp(db)

                # Check for manual override
                if _override_state is not None:
                    if _override_until and datetime.now(timezone.utc) > _override_until:
                        # Override expired, return to auto mode
                        logger.info("Manual override expired, returning to auto mode")
                        _override_state = None
                        _override_until = None
                    else:
                        # Manual override active - maintain the override state
                        desired_state = _override_state
                        if _heater_state != desired_state:
                            await set_heater_state(
                                ha_client, heater_entity, desired_state, db,
                                wort_temp, ambient_temp, target_temp, tilt_id
                            )
                        await _wait_or_wake(CONTROL_INTERVAL_SECONDS)
                        continue

                # Calculate thresholds for logging
                # Round thresholds to 1 decimal to match Tilt resolution and avoid floating-point edge cases
                heat_on_threshold = round(target_temp - hysteresis, 1)
                heat_off_threshold = round(target_temp + hysteresis, 1)

                # Log control decision info at DEBUG level for diagnostics
                logger.debug(
                    f"Control check: wort={wort_temp:.2f}F, target={target_temp:.2f}F, "
                    f"hysteresis={hysteresis:.2f}F, on_threshold={heat_on_threshold:.2f}F, "
                    f"off_threshold={heat_off_threshold:.2f}F, cached_state={_heater_state}"
                )

                # Automatic control logic with hysteresis
                # Use <= and >= to handle edge cases where temp is exactly at threshold
                if wort_temp <= heat_on_threshold:
                    # Too cold - turn on heater
                    if _heater_state != "on":
                        logger.info(f"Wort temp {wort_temp:.1f}F at/below target {target_temp:.1f}F (hysteresis={hysteresis:.2f}), turning heater ON")
                        await set_heater_state(
                            ha_client, heater_entity, "on", db,
                            wort_temp, ambient_temp, target_temp, tilt_id
                        )
                    else:
                        logger.debug(f"Heater already ON, wort={wort_temp:.1f}F <= on_threshold={heat_on_threshold:.1f}F")

                elif wort_temp >= heat_off_threshold:
                    # Too warm - turn off heater
                    if _heater_state != "off":
                        logger.info(f"Wort temp {wort_temp:.1f}F at/above target {target_temp:.1f}F (hysteresis={hysteresis:.2f}), turning heater OFF")
                        await set_heater_state(
                            ha_client, heater_entity, "off", db,
                            wort_temp, ambient_temp, target_temp, tilt_id
                        )
                    else:
                        logger.debug(f"Heater already OFF, wort={wort_temp:.1f}F >= off_threshold={heat_off_threshold:.1f}F")

                else:
                    # Within hysteresis band - maintain current state
                    logger.debug(
                        f"Within hysteresis band ({heat_on_threshold:.1f}F-{heat_off_threshold:.1f}F), "
                        f"maintaining heater state: {_heater_state}"
                    )

        except Exception as e:
            logger.error(f"Temperature control error: {e}", exc_info=True)

        await _wait_or_wake(CONTROL_INTERVAL_SECONDS)


def get_control_status() -> dict:
    """Get current temperature control status."""
    wort_temp = get_latest_tilt_temp()

    return {
        "heater_state": _heater_state,
        "override_active": _override_state is not None,
        "override_state": _override_state,
        "override_until": _override_until.isoformat() if _override_until else None,
        "wort_temp": wort_temp,
    }


def set_manual_override(state: Optional[str], duration_minutes: int = 60) -> bool:
    """Set manual override for heater control.

    Args:
        state: "on", "off", or None to cancel override
        duration_minutes: How long override lasts (default 60 min)

    Returns:
        True if override was set/cleared successfully
    """
    global _override_state, _override_until

    if state is None:
        _override_state = None
        _override_until = None
        logger.info("Manual override cancelled, returning to auto mode")
        _trigger_immediate_check()  # Wake loop to apply auto control immediately
        return True

    if state not in ("on", "off"):
        return False

    _override_state = state
    _override_until = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes) if duration_minutes > 0 else None
    logger.info(f"Manual override set: heater {state} for {duration_minutes} minutes")
    _trigger_immediate_check()  # Wake loop to apply override immediately
    return True


def sync_cached_heater_state(state: Optional[str]) -> None:
    """Keep the in-memory heater state in sync with external changes (e.g., manual HA toggles)."""
    global _heater_state
    if state in ("on", "off", None):
        _heater_state = state


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
