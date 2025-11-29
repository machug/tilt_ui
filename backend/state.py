"""Shared application state.

This module holds global state that needs to be accessed from multiple
parts of the application without creating circular dependencies.
"""

# In-memory cache of latest readings per device
# Format: {device_id: {reading_payload_dict}}
latest_readings: dict[str, dict] = {}
