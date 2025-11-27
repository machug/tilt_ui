"""
BLE Scanner for Tilt Hydrometers.

Supports three modes:
1. Mock mode (TILT_MOCK=true): Generates fake readings for development
2. Relay mode (TILT_RELAY=<ip>): Fetches from remote TiltPi
3. Real mode: Scans BLE for actual Tilt devices
"""

import asyncio
import json
import logging
import os
import random
from dataclasses import dataclass
from datetime import datetime
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


class BLEScanner:
    """Real BLE scanner using aioblescan."""

    def __init__(self):
        self._socket = None
        self._transport = None
        self._protocol = None
        self._latest_reading: Optional[TiltReading] = None

    async def start(self, device: int = 0):
        try:
            import aioblescan as aiobs
            from aioblescan.plugins import Tilt
        except ImportError as e:
            raise RuntimeError("aioblescan not available - install it or use mock mode") from e

        self._socket = aiobs.create_bt_socket(device)
        loop = asyncio.get_event_loop()

        class TiltRequester(aiobs.BLEScanRequester):
            def __init__(self, scanner: "BLEScanner"):
                super().__init__()
                self.scanner = scanner
                self.tilt_plugin = Tilt()

            def process(self, data):
                ev = aiobs.HCI_Event()
                ev.decode(data)
                result = self.tilt_plugin.decode(ev)
                if result:
                    reading_data = json.loads(result)
                    uuid = reading_data.get("uuid", "")
                    color = TILT_COLORS.get(uuid, "UNKNOWN")
                    if color != "UNKNOWN":
                        # major = temp F, minor = SG * 1000
                        sg = reading_data["minor"] / 1000.0
                        # Handle HD Tilts (SG > 2.0 means it's actually SG * 10000)
                        if sg > 2.0:
                            sg = reading_data["minor"] / 10000.0

                        self.scanner._latest_reading = TiltReading(
                            color=color,
                            mac=reading_data.get("mac", ""),
                            temp_f=float(reading_data["major"]),
                            sg=sg,
                            rssi=reading_data.get("rssi", -100),
                            timestamp=datetime.utcnow(),
                        )

        self._transport, self._protocol = await loop._create_connection_transport(
            self._socket, lambda: TiltRequester(self), None, None
        )
        self._protocol.send_scan_request()

    async def scan(self) -> Optional[TiltReading]:
        reading = self._latest_reading
        self._latest_reading = None
        return reading

    async def stop(self):
        if self._protocol:
            self._protocol.stop_scan_request()
        if self._transport:
            self._transport.close()


class TiltScanner:
    """Main scanner that selects mode based on environment."""

    def __init__(self, on_reading: Callable[[TiltReading], None]):
        self.on_reading = on_reading
        self._running = False
        self._scanner: MockScanner | RelayScanner | BLEScanner

        # Select mode based on environment
        if os.environ.get("TILT_MOCK", "").lower() in ("true", "1", "yes"):
            logger.info("Scanner mode: MOCK")
            self._scanner = MockScanner()
            self._interval = 5.0  # Mock every 5 seconds
        elif relay_host := os.environ.get("TILT_RELAY"):
            logger.info("Scanner mode: RELAY (%s)", relay_host)
            self._scanner = RelayScanner(relay_host)
            self._interval = 5.0
        else:
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
