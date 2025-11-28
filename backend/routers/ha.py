"""Home Assistant integration API endpoints."""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.ha_client import HAClient, get_ha_client
from .config import get_config_value

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ha", tags=["homeassistant"])


class HAStatusResponse(BaseModel):
    enabled: bool
    connected: bool
    url: str
    error: str | None = None


class HATestRequest(BaseModel):
    url: str
    token: str


class HATestResponse(BaseModel):
    success: bool
    message: str


@router.get("/status", response_model=HAStatusResponse)
async def get_ha_status(db: AsyncSession = Depends(get_db)):
    """Get Home Assistant connection status."""
    ha_enabled = await get_config_value(db, "ha_enabled")
    ha_url = await get_config_value(db, "ha_url") or ""

    if not ha_enabled:
        return HAStatusResponse(enabled=False, connected=False, url=ha_url)

    ha_client = get_ha_client()
    if not ha_client:
        return HAStatusResponse(
            enabled=True,
            connected=False,
            url=ha_url,
            error="Client not initialized"
        )

    connected = await ha_client.test_connection()
    return HAStatusResponse(enabled=True, connected=connected, url=ha_url)


@router.post("/test", response_model=HATestResponse)
async def test_ha_connection(request: HATestRequest):
    """Test Home Assistant connection with provided credentials."""
    if not request.url or not request.token:
        return HATestResponse(success=False, message="URL and token are required")

    client = HAClient(request.url, request.token)
    try:
        connected = await client.test_connection()
        if connected:
            return HATestResponse(success=True, message="Connection successful")
        else:
            return HATestResponse(success=False, message="Connection failed - check URL and token")
    except Exception as e:
        return HATestResponse(success=False, message=f"Error: {str(e)}")
    finally:
        await client.close()


@router.get("/weather")
async def get_weather_forecast(db: AsyncSession = Depends(get_db)):
    """Get weather forecast from Home Assistant."""
    ha_enabled = await get_config_value(db, "ha_enabled")
    if not ha_enabled:
        return {"error": "Home Assistant not enabled", "forecast": []}

    weather_entity = await get_config_value(db, "ha_weather_entity_id")
    if not weather_entity:
        return {"error": "Weather entity not configured", "forecast": []}

    ha_client = get_ha_client()
    if not ha_client:
        return {"error": "HA client not initialized", "forecast": []}

    forecast = await ha_client.get_weather_forecast(weather_entity)
    return {"forecast": forecast or []}
