"""Home Assistant REST API client."""

import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class HAClientError(Exception):
    """Home Assistant client error."""
    pass


class HAClient:
    """Async HTTP client for Home Assistant REST API."""

    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.token = token
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def test_connection(self) -> bool:
        """Test if HA is reachable and token is valid."""
        try:
            client = await self._get_client()
            response = await client.get(f"{self.url}/api/", headers=self.headers)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"HA connection test failed: {e}")
            return False

    async def get_state(self, entity_id: str) -> Optional[dict[str, Any]]:
        """Get current state of an entity.

        Returns dict with 'state', 'attributes', 'last_changed', etc.
        Returns None if entity not found or error.
        """
        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.url}/api/states/{entity_id}",
                headers=self.headers
            )
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                logger.warning(f"Entity not found: {entity_id}")
                return None
            else:
                logger.error(f"HA get_state failed: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"HA get_state error: {e}")
            return None

    async def call_service(
        self, domain: str, service: str, entity_id: str, data: Optional[dict] = None
    ) -> bool:
        """Call a Home Assistant service.

        Example: call_service("switch", "turn_on", "switch.heat_mat")
        """
        try:
            client = await self._get_client()
            payload = {"entity_id": entity_id}
            if data:
                payload.update(data)

            response = await client.post(
                f"{self.url}/api/services/{domain}/{service}",
                headers=self.headers,
                json=payload
            )
            if response.status_code == 200:
                logger.info(f"HA service called: {domain}/{service} on {entity_id}")
                return True
            else:
                logger.error(f"HA call_service failed: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"HA call_service error: {e}")
            return False

    async def get_entities_by_domain(self, domains: list[str]) -> list[dict[str, Any]]:
        """Get all entities matching the specified domains.

        Args:
            domains: List of domains to filter (e.g., ["switch", "input_boolean"])

        Returns:
            List of entity dicts with entity_id, state, and friendly_name
        """
        try:
            client = await self._get_client()
            response = await client.get(f"{self.url}/api/states", headers=self.headers)
            if response.status_code == 200:
                all_states = response.json()
                entities = []
                for state in all_states:
                    entity_id = state.get("entity_id", "")
                    domain = entity_id.split(".")[0] if "." in entity_id else ""
                    if domain in domains:
                        entities.append({
                            "entity_id": entity_id,
                            "state": state.get("state"),
                            "friendly_name": state.get("attributes", {}).get("friendly_name", entity_id),
                        })
                # Sort by friendly name
                entities.sort(key=lambda x: x["friendly_name"].lower())
                return entities
            else:
                logger.error(f"HA get_entities failed: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"HA get_entities error: {e}")
            return []

    async def get_weather_forecast(self, entity_id: str) -> Optional[list[dict]]:
        """Get weather forecast from HA weather entity."""
        try:
            client = await self._get_client()
            response = await client.post(
                f"{self.url}/api/services/weather/get_forecasts?return_response",
                headers=self.headers,
                json={"entity_id": entity_id, "type": "daily"}
            )
            if response.status_code == 200:
                data = response.json()
                # Extract forecast from service response
                service_response = data.get("service_response", {})
                entity_data = service_response.get(entity_id, {})
                return entity_data.get("forecast", [])
            else:
                logger.error(f"HA get_forecast failed: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"HA get_forecast error: {e}")
            return None


# Singleton instance (initialized when config is loaded)
_ha_client: Optional[HAClient] = None


def get_ha_client() -> Optional[HAClient]:
    """Get the current HA client instance."""
    return _ha_client


def init_ha_client(url: str, token: str) -> HAClient:
    """Initialize or reinitialize the HA client."""
    global _ha_client
    if _ha_client:
        # Close existing client asynchronously would need event loop
        pass
    _ha_client = HAClient(url, token)
    return _ha_client


async def close_ha_client() -> None:
    """Close the HA client."""
    global _ha_client
    if _ha_client:
        await _ha_client.close()
        _ha_client = None
