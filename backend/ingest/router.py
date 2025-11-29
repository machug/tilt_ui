"""Routes incoming payloads to appropriate adapters."""

import logging
from typing import Optional

from .adapters import GravityMonAdapter, ISpindelAdapter, TiltAdapter
from .base import HydrometerReading

logger = logging.getLogger(__name__)


class AdapterRouter:
    """Routes incoming payloads to the appropriate device adapter.

    Adapters are checked in order of specificity - more specific adapters
    (like GravityMon) are checked before more general ones (like iSpindel).
    """

    def __init__(self):
        # Order matters: more specific adapters first
        self.adapters = [
            GravityMonAdapter(),  # Check before iSpindel (extends it)
            ISpindelAdapter(),
            TiltAdapter(),
        ]

    def route(self, payload: dict, source_protocol: str) -> Optional[HydrometerReading]:
        """Find matching adapter and parse payload.

        Args:
            payload: Raw payload dictionary
            source_protocol: How payload was received

        Returns:
            HydrometerReading or None if no adapter matches
        """
        if not payload:
            return None

        for adapter in self.adapters:
            if adapter.can_handle(payload):
                try:
                    reading = adapter.parse(payload, source_protocol)
                    if reading:
                        logger.debug(
                            "Routed payload to %s adapter: device_id=%s",
                            adapter.device_type,
                            reading.device_id,
                        )
                        return reading
                except Exception as e:
                    logger.warning(
                        "Adapter %s failed to parse payload: %s",
                        adapter.device_type,
                        e,
                    )
                    continue

        logger.debug("No adapter found for payload: %s", payload)
        return None
