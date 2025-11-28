"""Temperature control API endpoints."""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import ControlEvent, ControlEventResponse
from ..temp_controller import get_control_status, set_manual_override, get_latest_tilt_temp
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
    since = datetime.utcnow() - timedelta(hours=hours)

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
