"""HTTP endpoints for hydrometer data ingestion."""

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request

from ..ingest import AdapterRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ingest", tags=["ingest"])

# Global adapter router instance
adapter_router = AdapterRouter()


@router.post("/generic")
async def ingest_generic(
    request: Request,
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

    reading = adapter_router.route(payload, source_protocol="http")

    if not reading:
        raise HTTPException(400, "Unknown payload format")

    logger.info(
        "Ingested %s reading from device %s",
        reading.device_type,
        reading.device_id,
    )

    # TODO: Process through calibration and store
    # For now, just acknowledge receipt

    return {
        "status": "ok",
        "device_type": reading.device_type,
        "device_id": reading.device_id,
    }


@router.post("/ispindel")
async def ingest_ispindel(
    request: Request,
    x_device_token: Optional[str] = Header(None, alias="X-Device-Token"),
):
    """Receive iSpindel HTTP POST.

    iSpindel devices should configure their HTTP endpoint to POST here.
    """
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(400, f"Invalid JSON: {e}")

    reading = adapter_router.route(payload, source_protocol="http")

    if not reading or reading.device_type not in ("ispindel", "gravitymon"):
        raise HTTPException(400, "Invalid iSpindel payload")

    logger.info(
        "Ingested iSpindel reading: device=%s, angle=%s, gravity=%s",
        reading.device_id,
        reading.angle,
        reading.gravity_raw,
    )

    return {"status": "ok"}


@router.post("/gravitymon")
async def ingest_gravitymon(
    request: Request,
    x_device_token: Optional[str] = Header(None, alias="X-Device-Token"),
):
    """Receive GravityMon HTTP POST."""
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(400, f"Invalid JSON: {e}")

    reading = adapter_router.route(payload, source_protocol="http")

    if not reading:
        raise HTTPException(400, "Invalid GravityMon payload")

    logger.info(
        "Ingested GravityMon reading: device=%s, gravity=%s, filtered=%s",
        reading.device_id,
        reading.gravity_raw,
        reading.is_pre_filtered,
    )

    return {"status": "ok"}
