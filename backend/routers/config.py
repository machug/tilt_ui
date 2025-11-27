"""Configuration API endpoints."""

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Config, ConfigResponse, ConfigUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])

DEFAULT_CONFIG: dict[str, Any] = {
    "temp_units": "C",
    "sg_units": "sg",
    "local_logging_enabled": True,
    "local_interval_minutes": 15,
    "min_rssi": -100,
    "smoothing_enabled": False,
    "smoothing_samples": 5,
    "id_by_mac": False,
}


async def get_config_value(db: AsyncSession, key: str) -> Any:
    """Get a single config value, returning default if not set."""
    result = await db.execute(select(Config).where(Config.key == key))
    config = result.scalar_one_or_none()
    if config is None:
        return DEFAULT_CONFIG.get(key)
    return json.loads(config.value)


async def set_config_value(db: AsyncSession, key: str, value: Any) -> None:
    """Set a single config value."""
    result = await db.execute(select(Config).where(Config.key == key))
    config = result.scalar_one_or_none()
    if config is None:
        config = Config(key=key, value=json.dumps(value))
        db.add(config)
    else:
        config.value = json.dumps(value)


@router.get("", response_model=ConfigResponse)
async def get_config(db: AsyncSession = Depends(get_db)):
    """Get all configuration settings."""
    # Start with defaults
    config_dict = DEFAULT_CONFIG.copy()

    # Override with stored values
    result = await db.execute(select(Config))
    for config in result.scalars():
        if config.key in config_dict:
            try:
                config_dict[config.key] = json.loads(config.value)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON for config key %s", config.key)

    return ConfigResponse(**config_dict)


@router.patch("", response_model=ConfigResponse)
async def update_config(
    update: ConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Partially update configuration settings.

    Only provided fields are updated; others remain unchanged.
    Values are validated via Pydantic schema before saving.
    """
    # Get fields that were actually provided (not None)
    update_data = update.model_dump(exclude_unset=True)

    # Update each provided field
    for key, value in update_data.items():
        await set_config_value(db, key, value)

    await db.commit()

    # Return full config after update
    return await get_config(db)
