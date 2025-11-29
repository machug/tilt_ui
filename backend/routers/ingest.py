"""HTTP endpoints for hydrometer data ingestion."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services import ingest_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ingest", tags=["ingest"])


@router.post("/generic")
async def ingest_generic(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_device_token: Optional[str] = Header(None, alias="X-Device-Token"),
):
    """Auto-detect payload format and ingest.

    Accepts JSON payloads from any supported device type.
    The adapter router will detect the format and parse accordingly.
    """
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(400, f"Invalid JSON: {e}")

    reading = await ingest_manager.ingest(
        db=db,
        payload=payload,
        source_protocol="http",
        auth_token=x_device_token,
    )

    if not reading:
        raise HTTPException(400, "Unknown payload format or auth failed")

    return {
        "status": "ok",
        "device_type": reading.device_type,
        "device_id": reading.device_id,
    }


@router.post("/ispindel")
async def ingest_ispindel(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_device_token: Optional[str] = Header(None, alias="X-Device-Token"),
):
    """Receive iSpindel HTTP POST.

    iSpindel devices should configure their HTTP endpoint to POST here.
    """
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(400, f"Invalid JSON: {e}")

    reading = await ingest_manager.ingest(
        db=db,
        payload=payload,
        source_protocol="http",
        auth_token=x_device_token,
    )

    if not reading:
        raise HTTPException(400, "Invalid iSpindel payload or auth failed")

    return {"status": "ok"}


@router.post("/gravitymon")
async def ingest_gravitymon(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_device_token: Optional[str] = Header(None, alias="X-Device-Token"),
):
    """Receive GravityMon HTTP POST."""
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(400, f"Invalid JSON: {e}")

    reading = await ingest_manager.ingest(
        db=db,
        payload=payload,
        source_protocol="http",
        auth_token=x_device_token,
    )

    if not reading:
        raise HTTPException(400, "Invalid GravityMon payload or auth failed")

    return {"status": "ok"}
