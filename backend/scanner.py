"""
BLE Scanner for Tilt Hydrometers.

Supports four modes:
1. Mock mode (TILT_MOCK=true): Generates fake readings for development
2. File mode (TILT_FILES=<path>): Reads from local TiltPi JSON files
3. Relay mode (TILT_RELAY=<ip>): Fetches from remote TiltPi
4. Real mode: Scans BLE for actual Tilt devices
"""

import asyncio
import json
import logging
import os
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import httpx

logger = logging.getLogger(__name__)

TILT_COLORS = {
    "a495bb10c5b14b44b5121370f02d74de": "RED",
    "a495bb20c5b14b44b5121370f02d74de": "GREEN",
    "a495bb30c5b14b44b5121370f02d74de": "BLACK",
    "a495bb40c5b14b44b5121370f02d74de": "PURPLE",
    "a495bb50c5b14b44b5121370f02d74de": "ORANGE",
    "a495bb60c5b14b44b5121370f02d74de": "BLUE",
    "a495bb70c5b14b44b5121370f02d74de": "YELLOW",
    "a495bb80c5b14b44b5121370f02d74de": "PINK",
}

COLOR_TO_UUID = {v: k for k, v in TILT_COLORS.items()}


@dataclass
class TiltReading:
    color: str
    mac: str
    temp_f: float
    sg: float
    rssi: int
    timestamp: datetime

    @property
    def id(self) -> str:
        return self.color

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "color": self.color,
            "mac": self.mac,
            "temp_f": self.temp_f,
            "sg": self.sg,
            "rssi": self.rssi,
            "timestamp": self.timestamp.isoformat(),
        }


class MockScanner:
    """Generates fake Tilt readings for development."""

    def __init__(self):
        self.base_sg = 1.050
        self.base_temp = 68.0
        self.color = "RED"

    async def scan(self) -> Optional[TiltReading]:
        # Simulate fermentation: SG slowly drops, temp fluctuates
        self.base_sg = max(1.000, self.base_sg - random.uniform(0, 0.0005))
        self.base_temp += random.uniform(-0.5, 0.5)
        self.base_temp = max(60, min(80, self.base_temp))

        return TiltReading(
            color=self.color,
            mac="AA:BB:CC:DD:EE:FF",
            temp_f=round(self.base_temp, 1),
            sg=round(self.base_sg, 4),
            rssi=random.randint(-80, -50),
            timestamp=datetime.utcnow(),
        )


class RelayScanner:
    """Fetches readings from a remote TiltPi."""

    def __init__(self, host: str):
        self.host = host
        self.client = httpx.AsyncClient(timeout=5.0)

    async def scan(self) -> Optional[TiltReading]:
        # TiltPi stores readings in /home/pi/{COLOR}.json
        for color in TILT_COLORS.values():
            try:
                url = f"http://{self.host}:1880/{color}.json"
                resp = await self.client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    return TiltReading(
                        color=color,
                        mac=data.get("mac", ""),
                        temp_f=float(data.get("Temp", 0)),
                        sg=float(data.get("SG", 1.000)),
                        rssi=int(data.get("rssi", -100)),
                        timestamp=datetime.utcnow(),
                    )
            except Exception:
                continue
        return None

    async def close(self):
        await self.client.aclose()


class FileScanner:
    """Reads Tilt readings from local JSON files (TiltPi format).

    TiltPi Node-RED writes files like /home/pi/RED.json, /home/pi/GREEN.json etc.
    This scanner reads those files directly when running on the same machine.
    """

    def __init__(self, path: str = "/home/pi"):
        self.path = Path(path)
        self._last_timestamps: dict[str, float] = {}  # Track file mtimes to avoid duplicates

    async def scan(self) -> Optional[TiltReading]:
        """Scan for Tilt JSON files and return the first one with new data."""
        for color in TILT_COLORS.values():
            json_file = self.path / f"{color}.json"
            if not json_file.exists():
                continue

            try:
                # Check if file was modified since last read
                mtime = json_file.stat().st_mtime
                last_mtime = self._last_timestamps.get(color, 0)

                if mtime <= last_mtime:
                    continue  # No new data

                self._last_timestamps[color] = mtime

                # Read and parse JSON
                data = json.loads(json_file.read_text())

                return TiltReading(
                    color=color,
                    mac=data.get("mac", ""),
                    temp_f=float(data.get("Temp", 0)),
                    sg=float(data.get("SG", 1.000)),
                    rssi=int(data.get("rssi", -100)),
                    timestamp=datetime.utcnow(),
                )
            except Exception as e:
                logger.debug("Error reading %s: %s", json_file, e)
                continue

        return None


class BLEScanner:
    """Real BLE scanner using Bleak."""

    def __init__(self):
        self._latest_reading: Optional[TiltReading] = None
        self._running = False
        self._scanner = None
        self._scan_task: Optional[asyncio.Task] = None

    def _detection_callback(self, device, advertisement_data):
        """Called by Bleak for each BLE advertisement."""
        # Only process Apple manufacturer data (ID 76 = 0x004C)
        if 76 not in advertisement_data.manufacturer_data:
            return

        try:
            from beacontools import parse_packet

            # Reconstruct iBeacon frame for beacontools
            # Format: flags + manufacturer header + data
            beacon_bytes = b'\x02\x01\x06\x1a\xff\x4c\x00' + advertisement_data.manufacturer_data[76]
            adv = parse_packet(beacon_bytes)

            if not adv:
                return

            # Check if it's a Tilt (UUID matches known Tilt colors)
            uuid = adv.uuid.replace('-', '')
            color = TILT_COLORS.get(uuid)

            if not color:
                return

            # Skip disconnected repeaters (SG = 0)
            if adv.minor == 0:
                return

            # Parse temperature and SG (handle high-precision mode)
            if adv.minor < 5000:
                temp_f = float(adv.major)
                sg = adv.minor / 1000.0
            else:
                temp_f = adv.major / 10.0
                sg = adv.minor / 10000.0

            self._latest_reading = TiltReading(
                color=color,
                mac=device.address,
                temp_f=temp_f,
                sg=sg,
                rssi=advertisement_data.rssi,
                timestamp=datetime.utcnow(),
            )
            print(f"BLE: Detected {color} Tilt - {temp_f:.1f}F, SG {sg:.4f}")

        except Exception as e:
            logger.debug("Error parsing BLE packet: %s", e)

    async def start(self, device: int = 0):
        """Start BLE scanning."""
        try:
            from bleak import BleakScanner
        except ImportError as e:
            raise RuntimeError("bleak not available - install it or use mock mode") from e

        self._running = True
        print("BLEScanner: Starting Bleak scanner (active mode)", flush=True)

        async def run_scanner():
            try:
                # Use active scanning mode (passive requires bluez or_patterns)
                self._scanner = BleakScanner(
                    detection_callback=self._detection_callback,
                    scanning_mode="active"
                )
                async with self._scanner:
                    print("BLEScanner: Now scanning for Tilts", flush=True)
                    while self._running:
                        await asyncio.sleep(1)
                print("BLEScanner: Scanner stopped", flush=True)
            except Exception as e:
                print(f"BLEScanner ERROR: {e}", flush=True)
                logger.exception("BLE scanner error: %s", e)

        self._scan_task = asyncio.create_task(run_scanner())
        await asyncio.sleep(0.5)  # Give scanner time to start

    async def scan(self) -> Optional[TiltReading]:
        """Return latest reading and clear it."""
        reading = self._latest_reading
        self._latest_reading = None
        return reading

    async def stop(self):
        """Stop BLE scanning."""
        self._running = False
        if self._scan_task:
            try:
                await asyncio.wait_for(self._scan_task, timeout=2.0)
            except asyncio.TimeoutError:
                self._scan_task.cancel()


class TiltScanner:
    """Main scanner that selects mode based on environment."""

    def __init__(self, on_reading: Callable[[TiltReading], None]):
        self.on_reading = on_reading
        self._running = False
        self._scanner: MockScanner | FileScanner | RelayScanner | BLEScanner

        # Select mode based on environment
        if os.environ.get("TILT_MOCK", "").lower() in ("true", "1", "yes"):
            logger.info("Scanner mode: MOCK")
            self._scanner = MockScanner()
            self._interval = 5.0  # Mock every 5 seconds
        elif files_path := os.environ.get("TILT_FILES"):
            # File mode: read from local TiltPi JSON files
            logger.info("Scanner mode: FILES (%s)", files_path)
            self._scanner = FileScanner(files_path)
            self._interval = 5.0  # Check files every 5 seconds
        elif relay_host := os.environ.get("TILT_RELAY"):
            logger.info("Scanner mode: RELAY (%s)", relay_host)
            self._scanner = RelayScanner(relay_host)
            self._interval = 5.0
        else:
            print("Scanner mode: BLE")
            logger.info("Scanner mode: BLE")
            self._scanner = BLEScanner()
            self._interval = 1.0  # BLE scans continuously, check every second

    async def start(self):
        self._running = True

        if isinstance(self._scanner, BLEScanner):
            await self._scanner.start()

        while self._running:
            try:
                reading = await self._scanner.scan()
                if reading:
                    await self.on_reading(reading)
            except Exception as e:
                logger.exception("Scanner error: %s", e)

            await asyncio.sleep(self._interval)

    async def stop(self):
        self._running = False
        if isinstance(self._scanner, BLEScanner):
            await self._scanner.stop()
        elif isinstance(self._scanner, RelayScanner):
            await self._scanner.close()
