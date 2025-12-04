"""Temperature control API endpoints."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Batch, ControlEvent, ControlEventResponse
from ..temp_controller import (
    get_control_status,
    get_batch_control_status,
    set_manual_override,
    get_latest_tilt_temp,
    get_device_temp,
    sync_cached_state,
)
from ..services.ha_client import get_ha_client, init_ha_client
from .config import get_config_value

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/control", tags=["control"])


class ControlStatusResponse(BaseModel):
    enabled: bool
    heater_state: Optional[str]
    override_active: bool
    override_state: Optional[str]
    override_until: Optional[str]
    target_temp: Optional[float]
    hysteresis: Optional[float]
    wort_temp: Optional[float]
    heater_entity: Optional[str]


class BatchControlStatusResponse(BaseModel):
    batch_id: int
    enabled: bool
    heater_state: Optional[str]
    heater_entity: Optional[str]
    cooler_state: Optional[str]  # NEW: Cooler state ("on", "off", or None)
    cooler_entity: Optional[str]  # NEW: Cooler entity ID
    override_active: bool
    override_state: Optional[str]  # Deprecated - kept for backward compatibility
    override_until: Optional[str]
    target_temp: Optional[float]
    hysteresis: Optional[float]
    wort_temp: Optional[float]
    state_available: bool  # True if runtime state exists, False if cleaned up (batch completed/archived)


class OverrideRequest(BaseModel):
    device_type: str = "heater"  # "heater" or "cooler"
    state: Optional[str] = None  # "on", "off", or null to cancel
    duration_minutes: int = 60
    batch_id: Optional[int] = None  # Required for batch-specific override


class OverrideResponse(BaseModel):
    success: bool
    message: str
    override_state: Optional[str]
    override_until: Optional[str]
    batch_id: Optional[int] = None


class HeaterStateResponse(BaseModel):
    state: Optional[str]  # "on", "off", or null if unavailable
    entity_id: Optional[str]
    last_changed: Optional[str]
    available: bool
    batch_id: Optional[int] = None


class HeaterToggleRequest(BaseModel):
    state: str  # "on" or "off"
    entity_id: Optional[str] = None  # For batch-specific heater control
    batch_id: Optional[int] = None


class HeaterToggleResponse(BaseModel):
    success: bool
    message: str
    new_state: Optional[str]
    batch_id: Optional[int] = None


class HeaterEntityResponse(BaseModel):
    entity_id: str
    friendly_name: str
    state: Optional[str]


@router.get("/heater-entities", response_model=list[HeaterEntityResponse])
async def get_heater_entities(db: AsyncSession = Depends(get_db)):
    """Get available heater entities from Home Assistant.

    Returns switch.* and input_boolean.* entities that can be used as heaters.
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


@router.get("/cooler-entities", response_model=list[HeaterEntityResponse])
async def get_cooler_entities(db: AsyncSession = Depends(get_db)):
    """Get available cooler entities from Home Assistant.

    Returns switch.* and input_boolean.* entities that can be used as coolers.
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


@router.get("/status", response_model=ControlStatusResponse)
async def get_status(db: AsyncSession = Depends(get_db)):
    """Get current temperature control status (global settings)."""
    temp_control_enabled = await get_config_value(db, "temp_control_enabled") or False
    target_temp = await get_config_value(db, "temp_target")
    hysteresis = await get_config_value(db, "temp_hysteresis")
    heater_entity = await get_config_value(db, "ha_heater_entity_id")

    status = get_control_status()

    return ControlStatusResponse(
        enabled=temp_control_enabled,
        heater_state=status["heater_state"],
        override_active=status["override_active"],
        override_state=status["override_state"],
        override_until=status["override_until"],
        target_temp=target_temp,
        hysteresis=hysteresis,
        wort_temp=status["wort_temp"],
        heater_entity=heater_entity or None,
    )


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


@router.get("/events", response_model=list[ControlEventResponse])
async def get_events(
    hours: int = Query(default=24, ge=1, le=720),
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db)
):
    """Get temperature control event history."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    result = await db.execute(
        select(ControlEvent)
        .where(ControlEvent.timestamp >= since)
        .order_by(desc(ControlEvent.timestamp))
        .limit(limit)
    )

    return result.scalars().all()


@router.post("/override", response_model=OverrideResponse)
async def set_override(request: OverrideRequest, db: AsyncSession = Depends(get_db)):
    """Set or cancel manual heater or cooler override.

    Each device type (heater/cooler) has independent override state.
    - device_type: "heater" or "cooler" (default: "heater")
    - state: "on" to force device on, "off" to force device off, null to cancel override
    - duration_minutes: how long override lasts (default 60 min, 0 = indefinite)
    - batch_id: required for batch-specific override
    """
    temp_control_enabled = await get_config_value(db, "temp_control_enabled")

    # Validate device_type
    if request.device_type not in ("heater", "cooler"):
        return OverrideResponse(
            success=False,
            message=f"Invalid device_type: {request.device_type}. Must be 'heater' or 'cooler'.",
            override_state=None,
            override_until=None,
            batch_id=request.batch_id
        )

    # Require batch_id for override (multi-batch mode) - validate early
    if request.batch_id is None:
        return OverrideResponse(
            success=False,
            message=f"batch_id is required for {request.device_type} override",
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

    # Validate that batch has the requested device entity configured
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
        state=request.state,
        duration_minutes=request.duration_minutes,
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
            override_state=batch_status["override_state"],
            override_until=batch_status["override_until"],
            batch_id=request.batch_id
        )
    else:
        return OverrideResponse(
            success=False,
            message=f"Failed to set {request.device_type} override",
            override_state=None,
            override_until=None,
            batch_id=request.batch_id
        )


@router.get("/heater", response_model=HeaterStateResponse)
async def get_heater_state(
    entity_id: Optional[str] = Query(None, description="Specific entity ID to query"),
    batch_id: Optional[int] = Query(None, description="Batch ID to get heater state for"),
    db: AsyncSession = Depends(get_db)
):
    """Get current heater switch state from Home Assistant."""
    ha_enabled = await get_config_value(db, "ha_enabled")

    # Determine which entity to query
    heater_entity = entity_id
    if not heater_entity and batch_id:
        batch = await db.get(Batch, batch_id)
        if batch:
            heater_entity = batch.heater_entity_id
    if not heater_entity:
        heater_entity = await get_config_value(db, "ha_heater_entity_id")

    if not ha_enabled or not heater_entity:
        return HeaterStateResponse(
            state=None,
            entity_id=heater_entity,
            last_changed=None,
            available=False,
            batch_id=batch_id
        )

    # Get or initialize HA client
    ha_client = get_ha_client()
    if not ha_client:
        ha_url = await get_config_value(db, "ha_url")
        ha_token = await get_config_value(db, "ha_token")
        if ha_url and ha_token:
            ha_client = init_ha_client(ha_url, ha_token)

    if not ha_client:
        return HeaterStateResponse(
            state=None,
            entity_id=heater_entity,
            last_changed=None,
            available=False,
            batch_id=batch_id
        )

    # Fetch live state from HA
    entity_state = await ha_client.get_state(heater_entity)

    if entity_state:
        state = entity_state.get("state", "").lower()
        # Normalize state to "on" or "off"
        if state in ("on", "off"):
            heater_state = state
        elif state == "unavailable":
            return HeaterStateResponse(
                state=None,
                entity_id=heater_entity,
                last_changed=entity_state.get("last_changed"),
                available=False,
                batch_id=batch_id
            )
        else:
            heater_state = None

        # Keep controller cache aligned with the actual HA state
        if batch_id:
            sync_cached_state(heater_state, batch_id=batch_id, device_type="heater")

        return HeaterStateResponse(
            state=heater_state,
            entity_id=heater_entity,
            last_changed=entity_state.get("last_changed"),
            available=True,
            batch_id=batch_id
        )

    return HeaterStateResponse(
        state=None,
        entity_id=heater_entity,
        last_changed=None,
        available=False,
        batch_id=batch_id
    )


@router.post("/heater", response_model=HeaterToggleResponse)
async def toggle_heater(request: HeaterToggleRequest, db: AsyncSession = Depends(get_db)):
    """Directly toggle heater switch via Home Assistant."""
    if request.state not in ("on", "off"):
        return HeaterToggleResponse(
            success=False,
            message="State must be 'on' or 'off'",
            new_state=None,
            batch_id=request.batch_id
        )

    ha_enabled = await get_config_value(db, "ha_enabled")
    if not ha_enabled:
        return HeaterToggleResponse(
            success=False,
            message="Home Assistant integration is not enabled",
            new_state=None,
            batch_id=request.batch_id
        )

    # Determine which entity to control
    heater_entity = request.entity_id
    if not heater_entity and request.batch_id:
        batch = await db.get(Batch, request.batch_id)
        if batch:
            heater_entity = batch.heater_entity_id
    if not heater_entity:
        heater_entity = await get_config_value(db, "ha_heater_entity_id")

    if not heater_entity:
        return HeaterToggleResponse(
            success=False,
            message="No heater entity configured",
            new_state=None,
            batch_id=request.batch_id
        )

    # Get or initialize HA client
    ha_client = get_ha_client()
    if not ha_client:
        ha_url = await get_config_value(db, "ha_url")
        ha_token = await get_config_value(db, "ha_token")
        if ha_url and ha_token:
            ha_client = init_ha_client(ha_url, ha_token)

    if not ha_client:
        return HeaterToggleResponse(
            success=False,
            message="Failed to connect to Home Assistant",
            new_state=None,
            batch_id=request.batch_id
        )

    # Call HA service to toggle heater
    service = "turn_on" if request.state == "on" else "turn_off"
    success = await ha_client.call_service("switch", service, heater_entity)

    if success:
        batch_info = f" (batch {request.batch_id})" if request.batch_id else ""
        logger.info(f"Heater {heater_entity} manually toggled to {request.state}{batch_info}")
        # Keep controller cache aligned with manual toggles
        if request.batch_id:
            sync_cached_state(request.state, batch_id=request.batch_id, device_type="heater")
        return HeaterToggleResponse(
            success=True,
            message=f"Heater turned {request.state}",
            new_state=request.state,
            batch_id=request.batch_id
        )
    else:
        return HeaterToggleResponse(
            success=False,
            message="Failed to control heater via Home Assistant",
            new_state=None,
            batch_id=request.batch_id
        )
