"""Utility functions for device management."""

from datetime import datetime
from typing import Optional

from .models import Device


def create_tilt_device_record(
    device_id: str,
    color: str,
    mac: Optional[str] = None,
    last_seen: Optional[datetime] = None,
    paired: bool = False,
    paired_at: Optional[datetime] = None,
) -> Device:
    """Create a Device record for a Tilt hydrometer.

    This is a shared factory function to ensure consistent Device creation
    across the codebase (pairing endpoints, reading handler, etc.).

    Args:
        device_id: Unique identifier (same as Tilt color)
        color: Tilt color
        mac: MAC address (if known)
        last_seen: Last seen timestamp
        paired: Pairing status
        paired_at: Pairing timestamp

    Returns:
        New Device instance (not yet added to session)
    """
    device = Device(
        id=device_id,
        device_type="tilt",
        name=color,
        display_name=None,
        native_gravity_unit="sg",
        native_temp_unit="F",
        calibration_type="linear",
        paired=paired,
        paired_at=paired_at,
    )
    device.color = color
    if mac:
        device.mac = mac
    if last_seen:
        device.last_seen = last_seen

    return device
