"""Weather alerts and predictive alerts API endpoints."""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.ha_client import get_ha_client, init_ha_client
from .config import get_config_value

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def fahrenheit_to_celsius(f: float) -> float:
    """Convert Fahrenheit to Celsius."""
    return (f - 32) * 5 / 9


def celsius_to_fahrenheit(c: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return c * 9 / 5 + 32


class WeatherForecast(BaseModel):
    """Single day weather forecast (temps in Celsius)."""
    datetime: str
    condition: str
    temperature: Optional[float]  # High temp (°C)
    templow: Optional[float]  # Low temp (°C)


class Alert(BaseModel):
    """Predictive alert based on weather forecast."""
    level: str  # "info", "warning", "critical"
    message: str
    day: str  # Day name (e.g., "Monday")


class AlertsResponse(BaseModel):
    """Response containing forecast and alerts."""
    forecast: list[WeatherForecast]
    alerts: list[Alert]
    weather_entity: Optional[str]
    alerts_enabled: bool


class AlertsConfigResponse(BaseModel):
    """Current alerts configuration."""
    weather_alerts_enabled: bool
    alert_temp_threshold: float  # In Celsius
    ha_weather_entity_id: str
    temp_target: Optional[float]  # In Celsius


def generate_alerts(
    forecast: list[dict],
    target_temp_c: Optional[float],
    threshold_c: float
) -> list[Alert]:
    """Generate predictive alerts based on weather forecast.

    All temperatures should be in Celsius.
    Compares forecast temps against the fermentation target temp
    to warn about potential temperature control issues.
    """
    alerts = []

    if target_temp_c is None or not forecast:
        return alerts

    for day in forecast[:3]:  # Next 3 days
        try:
            # Parse datetime for day name
            dt_str = day.get("datetime", "")
            if dt_str:
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                day_name = dt.strftime("%A")
            else:
                day_name = "Upcoming"

            # HA forecast temps are in HA's configured unit system (assume Celsius)
            temp_high = day.get("temperature")
            temp_low = day.get("templow")

            # Check for cold conditions that may stress heater
            if temp_low is not None and temp_low < (target_temp_c - threshold_c):
                diff = target_temp_c - temp_low
                alerts.append(Alert(
                    level="warning" if diff > threshold_c * 2 else "info",
                    message=f"Low of {temp_low:.0f}°C, heater will likely run frequently",
                    day=day_name
                ))

            # Check for hot conditions that may require cooling
            if temp_high is not None and temp_high > (target_temp_c + threshold_c):
                diff = temp_high - target_temp_c
                alerts.append(Alert(
                    level="warning" if diff > threshold_c * 2 else "info",
                    message=f"High of {temp_high:.0f}°C, consider cooling or relocating fermenter",
                    day=day_name
                ))

            # Warn about large temperature swings (8°C = ~15°F)
            if temp_high is not None and temp_low is not None:
                swing = temp_high - temp_low
                if swing > 8:
                    alerts.append(Alert(
                        level="info",
                        message=f"Large temp swing ({swing:.0f}°C), monitor fermentation closely",
                        day=day_name
                    ))

        except (ValueError, TypeError) as e:
            logger.warning(f"Error processing forecast day: {e}")
            continue

    return alerts


@router.get("/config", response_model=AlertsConfigResponse)
async def get_alerts_config(db: AsyncSession = Depends(get_db)):
    """Get current alerts configuration."""
    target_temp_f = await get_config_value(db, "temp_target")
    # Threshold is stored in Celsius
    threshold_c = await get_config_value(db, "alert_temp_threshold") or 3.0

    return AlertsConfigResponse(
        weather_alerts_enabled=await get_config_value(db, "weather_alerts_enabled") or False,
        alert_temp_threshold=threshold_c,
        ha_weather_entity_id=await get_config_value(db, "ha_weather_entity_id") or "",
        temp_target=fahrenheit_to_celsius(target_temp_f) if target_temp_f else None,
    )


@router.get("", response_model=AlertsResponse)
async def get_alerts(db: AsyncSession = Depends(get_db)):
    """Get weather forecast and predictive alerts."""
    ha_enabled = await get_config_value(db, "ha_enabled")
    weather_alerts_enabled = await get_config_value(db, "weather_alerts_enabled") or False
    weather_entity = await get_config_value(db, "ha_weather_entity_id") or ""

    empty_response = AlertsResponse(
        forecast=[],
        alerts=[],
        weather_entity=weather_entity,
        alerts_enabled=weather_alerts_enabled
    )

    if not ha_enabled:
        return empty_response

    if not weather_entity:
        return empty_response

    # Get or initialize HA client
    ha_client = get_ha_client()
    if not ha_client:
        # Try to initialize if we have config
        ha_url = await get_config_value(db, "ha_url")
        ha_token = await get_config_value(db, "ha_token")
        if ha_url and ha_token:
            init_ha_client(ha_url, ha_token)
            ha_client = get_ha_client()

    if not ha_client:
        logger.warning("HA client not available for weather alerts")
        return empty_response

    # Fetch forecast from HA
    raw_forecast = await ha_client.get_weather_forecast(weather_entity)

    if not raw_forecast:
        return empty_response

    # Convert to response format (temps stay in HA units, assumed Celsius)
    forecast = []
    for day in raw_forecast[:5]:  # Return up to 5 days
        forecast.append(WeatherForecast(
            datetime=day.get("datetime", ""),
            condition=day.get("condition", "unknown"),
            temperature=day.get("temperature"),
            templow=day.get("templow"),
        ))

    # Generate alerts if enabled
    alerts = []
    if weather_alerts_enabled:
        # Get target temp (stored in F) and convert to C for comparison
        target_temp_f = await get_config_value(db, "temp_target")
        target_temp_c = fahrenheit_to_celsius(target_temp_f) if target_temp_f else None

        # Get threshold (stored in Celsius)
        threshold_c = await get_config_value(db, "alert_temp_threshold") or 3.0

        alerts = generate_alerts(raw_forecast, target_temp_c, threshold_c)

    return AlertsResponse(
        forecast=forecast,
        alerts=alerts,
        weather_entity=weather_entity,
        alerts_enabled=weather_alerts_enabled
    )
