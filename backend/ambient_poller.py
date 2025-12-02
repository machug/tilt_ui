"""Background task to poll Home Assistant for ambient readings."""

import asyncio
import logging
from datetime import datetime, timezone

from .database import async_session_factory
from .models import AmbientReading, serialize_datetime_to_utc
from .routers.config import get_config_value
from .services.ha_client import get_ha_client, init_ha_client
from .websocket import manager as ws_manager

logger = logging.getLogger(__name__)

_polling_task: asyncio.Task | None = None
POLL_INTERVAL_SECONDS = 30


async def poll_ambient() -> None:
    """Poll HA for ambient temperature and humidity, store and broadcast."""
    while True:
        try:
            async with async_session_factory() as db:
                ha_enabled = await get_config_value(db, "ha_enabled")

                if not ha_enabled:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                # Ensure HA client is initialized
                ha_url = await get_config_value(db, "ha_url")
                ha_token = await get_config_value(db, "ha_token")

                if not ha_url or not ha_token:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                ha_client = get_ha_client()
                if not ha_client:
                    init_ha_client(ha_url, ha_token)
                    ha_client = get_ha_client()

                if not ha_client:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                # Get entity IDs
                temp_entity = await get_config_value(db, "ha_ambient_temp_entity_id")
                humidity_entity = await get_config_value(db, "ha_ambient_humidity_entity_id")

                if not temp_entity and not humidity_entity:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                # Fetch values
                temperature = None
                humidity = None

                if temp_entity:
                    state = await ha_client.get_state(temp_entity)
                    if state and state.get("state") not in ("unavailable", "unknown"):
                        try:
                            temperature = float(state["state"])
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid temp state: {state.get('state')}")

                if humidity_entity:
                    state = await ha_client.get_state(humidity_entity)
                    if state and state.get("state") not in ("unavailable", "unknown"):
                        try:
                            humidity = float(state["state"])
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid humidity state: {state.get('state')}")

                # Store reading if we got any data
                if temperature is not None or humidity is not None:
                    reading = AmbientReading(
                        temperature=temperature,
                        humidity=humidity,
                        entity_id=temp_entity or humidity_entity
                    )
                    db.add(reading)
                    await db.commit()

                    # Broadcast via WebSocket
                    await ws_manager.broadcast_json({
                        "type": "ambient",
                        "temperature": temperature,
                        "humidity": humidity,
                        "timestamp": serialize_datetime_to_utc(datetime.now(timezone.utc))
                    })

                    logger.debug(f"Ambient: temp={temperature}, humidity={humidity}")

        except Exception as e:
            logger.error(f"Ambient polling error: {e}")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


def start_ambient_poller() -> None:
    """Start the ambient polling background task."""
    global _polling_task
    if _polling_task is None or _polling_task.done():
        _polling_task = asyncio.create_task(poll_ambient())
        logger.info("Ambient poller started")


def stop_ambient_poller() -> None:
    """Stop the ambient polling background task."""
    global _polling_task
    if _polling_task and not _polling_task.done():
        _polling_task.cancel()
        logger.info("Ambient poller stopped")
