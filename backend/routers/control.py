"""Temperature control API endpoints."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import ControlEvent, ControlEventResponse
from ..temp_controller import (
    get_control_status,
    set_manual_override,
    get_latest_tilt_temp,
    sync_cached_heater_state,
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


class OverrideRequest(BaseModel):
    state: Optional[str] = None  # "on", "off", or null to cancel
    duration_minutes: int = 60


class OverrideResponse(BaseModel):
    success: bool
    message: str
    override_state: Optional[str]
    override_until: Optional[str]


class HeaterStateResponse(BaseModel):
    state: Optional[str]  # "on", "off", or null if unavailable
    entity_id: Optional[str]
    last_changed: Optional[str]
    available: bool


class HeaterToggleRequest(BaseModel):
    state: str  # "on" or "off"


class HeaterToggleResponse(BaseModel):
    success: bool
    message: str
    new_state: Optional[str]


@router.get("/status", response_model=ControlStatusResponse)
async def get_status(db: AsyncSession = Depends(get_db)):
    """Get current temperature control status."""
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
    """Set or cancel manual heater override.

    - state: "on" to force heater on, "off" to force heater off, null to cancel override
    - duration_minutes: how long override lasts (default 60 min, 0 = indefinite)
    """
    temp_control_enabled = await get_config_value(db, "temp_control_enabled")
    if not temp_control_enabled:
        return OverrideResponse(
            success=False,
            message="Temperature control is not enabled",
            override_state=None,
            override_until=None
        )

    if request.state is not None and request.state not in ("on", "off"):
        return OverrideResponse(
            success=False,
            message="State must be 'on', 'off', or null",
            override_state=None,
            override_until=None
        )

    success = set_manual_override(request.state, request.duration_minutes)

    if success:
        status = get_control_status()
        if request.state is None:
            message = "Override cancelled, returning to automatic control"
        else:
            duration_msg = f"for {request.duration_minutes} minutes" if request.duration_minutes > 0 else "indefinitely"
            message = f"Heater override set to {request.state} {duration_msg}"

        return OverrideResponse(
            success=True,
            message=message,
            override_state=status["override_state"],
            override_until=status["override_until"]
        )
    else:
        return OverrideResponse(
            success=False,
            message="Failed to set override",
            override_state=None,
            override_until=None
        )


@router.get("/heater", response_model=HeaterStateResponse)
async def get_heater_state(db: AsyncSession = Depends(get_db)):
    """Get current heater switch state from Home Assistant."""
    ha_enabled = await get_config_value(db, "ha_enabled")
    heater_entity = await get_config_value(db, "ha_heater_entity_id")

    if not ha_enabled or not heater_entity:
        return HeaterStateResponse(
            state=None,
            entity_id=heater_entity,
            last_changed=None,
            available=False
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
            available=False
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
                available=False
            )
        else:
            heater_state = None

        # Keep controller cache aligned with the actual HA state so auto logic can react
        sync_cached_heater_state(heater_state)

        return HeaterStateResponse(
            state=heater_state,
            entity_id=heater_entity,
            last_changed=entity_state.get("last_changed"),
            available=True
        )

    return HeaterStateResponse(
        state=None,
        entity_id=heater_entity,
        last_changed=None,
        available=False
    )


@router.post("/heater", response_model=HeaterToggleResponse)
async def toggle_heater(request: HeaterToggleRequest, db: AsyncSession = Depends(get_db)):
    """Directly toggle heater switch via Home Assistant."""
    if request.state not in ("on", "off"):
        return HeaterToggleResponse(
            success=False,
            message="State must be 'on' or 'off'",
            new_state=None
        )

    ha_enabled = await get_config_value(db, "ha_enabled")
    heater_entity = await get_config_value(db, "ha_heater_entity_id")

    if not ha_enabled:
        return HeaterToggleResponse(
            success=False,
            message="Home Assistant integration is not enabled",
            new_state=None
        )

    if not heater_entity:
        return HeaterToggleResponse(
            success=False,
            message="No heater entity configured",
            new_state=None
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
            new_state=None
        )

    # Call HA service to toggle heater
    service = "turn_on" if request.state == "on" else "turn_off"
    success = await ha_client.call_service("switch", service, heater_entity)

    if success:
        logger.info(f"Heater manually toggled to {request.state}")
        # Keep controller cache aligned with manual toggles so auto logic can disable if needed
        sync_cached_heater_state(request.state)
        return HeaterToggleResponse(
            success=True,
            message=f"Heater turned {request.state}",
            new_state=request.state
        )
    else:
        return HeaterToggleResponse(
            success=False,
            message="Failed to control heater via Home Assistant",
            new_state=None
        )
