# Tilt UI Implementation Plan

**Date:** 2025-11-27
**Design Doc:** [2025-11-27-tilt-ui-design.md](./2025-11-27-tilt-ui-design.md)

**Tooling:** Chrome DevTools MCP is available for live frontend inspection/debugging against the running Svelte app, and the frontend-design plugin skill should be used to keep UI work sharp and intentional.

## Phase 1: Project Setup

### Task 1.1: Initialize Python Backend

**Files to create:**
- `pyproject.toml`
- `backend/__init__.py`
- `backend/main.py`

**pyproject.toml contents:**
```toml
[project]
name = "tilt-ui"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.104",
    "uvicorn[standard]>=0.24",
    "sqlalchemy>=2.0",
    "aiosqlite>=0.19",
    "pydantic>=2.5",
    "pydantic-settings>=2.1",
    "aioblescan>=0.2.4",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4",
    "pytest-asyncio>=0.21",
    "httpx>=0.25",
]
```

**backend/main.py minimal structure:**
```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: init DB, start scanner
    yield
    # Shutdown: stop scanner

app = FastAPI(title="Tilt UI", lifespan=lifespan)

# Mount static files (Svelte build output)
# app.mount("/", StaticFiles(directory="static", html=True), name="static")
```

**Verification:** `uv run uvicorn backend.main:app` starts without error.

---

### Task 1.2: Initialize Svelte Frontend

**Commands:**
```bash
cd frontend
npm create svelte@latest . -- --template skeleton --types typescript
npm install
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
npm install uplot
```

**Files to configure:**
- `svelte.config.js` - set adapter-static for SPA output
- `tailwind.config.js` - content paths, dark mode
- `src/app.css` - Tailwind directives

**svelte.config.js:**
```javascript
import adapter from '@sveltejs/adapter-static';

export default {
    kit: {
        adapter: adapter({
            pages: '../backend/static',
            assets: '../backend/static',
            fallback: 'index.html'
        })
    }
};
```

**Verification:** `npm run build` outputs to `backend/static/`.

---

### Task 1.3: Database Setup

**Files to create:**
- `backend/database.py`
- `backend/models.py`

**backend/database.py:**
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "sqlite+aiosqlite:///./data/tiltui.db"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

**backend/models.py:**
- SQLAlchemy models: `Tilt`, `Reading`, `CalibrationPoint`, `Config`
- Pydantic schemas: `TiltResponse`, `TiltReading`, `ConfigUpdate`, etc.

**Verification:** App starts and creates `data/tiltui.db` with correct tables.

---

## Phase 2: BLE Scanner

### Task 2.1: Scanner Service

**Files to create:**
- `backend/scanner.py`

**Implementation:**
```python
import asyncio
import json
from typing import Callable
import aioblescan as aiobs
from aioblescan.plugins import Tilt

TILT_UUIDS = {
    "a495bb10c5b14b44b5121370f02d74de": "RED",
    "a495bb20c5b14b44b5121370f02d74de": "GREEN",
    "a495bb30c5b14b44b5121370f02d74de": "BLACK",
    "a495bb40c5b14b44b5121370f02d74de": "PURPLE",
    "a495bb50c5b14b44b5121370f02d74de": "ORANGE",
    "a495bb60c5b14b44b5121370f02d74de": "BLUE",
    "a495bb70c5b14b44b5121370f02d74de": "YELLOW",
    "a495bb80c5b14b44b5121370f02d74de": "PINK",
}

class TiltScanner:
    def __init__(self, on_reading: Callable):
        self.on_reading = on_reading
        self._running = False

    async def start(self, device: int = 0):
        self._running = True
        socket = aiobs.create_bt_socket(device)
        loop = asyncio.get_event_loop()
        conn, btctrl = await loop._create_connection_transport(
            socket, aiobs.BLEScanRequester, None, None
        )
        btctrl.process = self._handle_packet
        btctrl.send_scan_request()

        while self._running:
            await asyncio.sleep(1)

        btctrl.stop_scan_request()
        conn.close()

    def stop(self):
        self._running = False

    def _handle_packet(self, data):
        ev = aiobs.HCI_Event()
        ev.decode(data)
        result = Tilt().decode(ev)
        if result:
            reading = json.loads(result)
            reading["color"] = TILT_UUIDS.get(reading["uuid"], "UNKNOWN")
            asyncio.create_task(self.on_reading(reading))
```

**Verification:** Run scanner standalone, verify JSON output for detected Tilts (or simulated beacons).

---

### Task 2.2: Integrate Scanner with FastAPI

**Update backend/main.py:**
- Start scanner in lifespan startup
- Create `handle_tilt_reading()` callback
- Store readings in database

**Verification:** App starts, scanner runs, readings appear in database.

---

## Phase 3: WebSocket & Real-time

### Task 3.1: WebSocket Manager

**Files to create:**
- `backend/websocket.py`

**Implementation:**
```python
from fastapi import WebSocket
from typing import List

class ConnectionManager:
    def __init__(self):
        self.connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.connections.remove(websocket)

    async def broadcast(self, data: dict):
        for conn in self.connections:
            try:
                await conn.send_json(data)
            except:
                self.disconnect(conn)

manager = ConnectionManager()
```

**Add to main.py:**
```python
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep alive
    except:
        manager.disconnect(websocket)
```

**Update handle_tilt_reading():** Call `await manager.broadcast(reading)`.

**Verification:** Connect via wscat, see live readings.

---

## Phase 4: REST API

### Task 4.1: Tilts Router

**Files to create:**
- `backend/routers/tilts.py`

**Endpoints:**
- `GET /api/tilts` - list all
- `GET /api/tilts/{id}` - single tilt
- `GET /api/tilts/{id}/readings` - historical (with start, end, limit query params)
- `PUT /api/tilts/{id}` - update beer name
- `DELETE /api/tilts/{id}` - remove tilt

**Verification:** Test each endpoint with curl/httpie.

---

### Task 4.2: Calibration Router

**Files to create:**
- `backend/routers/calibration.py`
- `backend/services/calibration.py`

**calibration.py service:**
```python
def linear_interpolate(x: float, points: list[tuple[float, float]]) -> float:
    """Linear interpolation between calibration points."""
    if not points:
        return x
    points = sorted(points, key=lambda p: p[0])
    # ... interpolation logic from reverse engineering doc
```

**Endpoints:**
- `GET /api/tilts/{id}/calibration`
- `POST /api/tilts/{id}/calibration` - body: `{type, raw_value, actual_value}`
- `DELETE /api/tilts/{id}/calibration/{type}`

**Verification:** Add calibration points, verify readings are calibrated.

---

### Task 4.3: Config Router

**Files to create:**
- `backend/routers/config.py`

**Endpoints:**
- `GET /api/config`
- `PATCH /api/config` - partial update

**Default config on first run:**
```python
DEFAULT_CONFIG = {
    "temp_units": "F",
    "sg_units": "sg",
    "local_logging_enabled": True,
    "local_interval_minutes": 15,
    "min_rssi": -100,
    "smoothing_enabled": False,
    "smoothing_samples": 5,
    "id_by_mac": False,
}
```

**Verification:** GET returns defaults, PATCH updates persist.

---

### Task 4.4: System Router

**Files to create:**
- `backend/routers/system.py`

**Endpoints:**
- `GET /api/system/info` - hostname, IP (via `socket.gethostname()`, `hostname -I`)
- `POST /api/system/reboot` - `subprocess.run(["sudo", "reboot"])`
- `POST /api/system/shutdown` - `subprocess.run(["sudo", "shutdown", "-h", "now"])`
- `GET /api/system/timezones` - read from `/usr/share/zoneinfo`
- `PUT /api/system/timezone` - update symlink

**Sudoers (non-interactive control):**
```
pi ALL=(root) NOPASSWD: /usr/bin/systemctl reboot
pi ALL=(root) NOPASSWD: /usr/bin/systemctl poweroff
pi ALL=(root) NOPASSWD: /usr/bin/timedatectl set-timezone *
```

**Verification:** Test info endpoint, skip destructive tests until deployment.

---

## Phase 5: Frontend - Core

### Task 5.1: App Layout

**Files to create/update:**
- `src/routes/+layout.svelte`
- `src/app.css`

**Layout structure:**
- Navigation bar (Dashboard, Logging, Calibration, System)
- Dark theme default
- Mobile hamburger menu

**Verification:** Nav works, dark theme applied.

---

### Task 5.2: WebSocket Store

**Files to create:**
- `src/lib/stores/tilts.ts`
- `src/lib/stores/connection.ts`
- `src/lib/api.ts`

**tilts.ts:**
```typescript
import { writable } from 'svelte/store';

export interface TiltReading {
    id: string;
    color: string;
    sg: number;
    sg_raw: number;
    temp: number;
    temp_raw: number;
    rssi: number;
    last_seen: string;
    beer_name: string;
}

export const tilts = writable<Map<string, TiltReading>>(new Map());

export function connectWebSocket() {
    const ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onmessage = (event) => {
        const reading = JSON.parse(event.data);
        tilts.update(map => {
            map.set(reading.id, reading);
            return map;
        });
    };
    // Handle reconnection...
}
```

**Verification:** Console log shows incoming readings.

---

### Task 5.3: Dashboard Page

**Files to create:**
- `src/routes/+page.svelte`
- `src/lib/components/TiltCard.svelte`

**TiltCard displays:**
- Color bar (matching Tilt color)
- Beer name
- SG (calibrated) with units
- Temperature (calibrated) with units
- Pre-calibrated values (smaller)
- Last seen timestamp
- RSSI signal indicator

**Dashboard layout:**
- Responsive grid of TiltCards
- "No Tilts detected" message when empty

**Verification:** Cards appear and update in real-time.

---

### Task 5.4: Historical Chart

**Files to create:**
- `src/lib/components/TiltChart.svelte`

**Implementation:**
- uPlot line chart
- Dual Y-axis (SG left, Temp right)
- Time X-axis
- Fetch data from `/api/tilts/{id}/readings`
- Time range selector (1h, 6h, 24h, 7d, 30d)

**Add to Dashboard:** Expandable chart per Tilt card, or separate chart section.

**Verification:** Chart renders historical data correctly.

---

## Phase 6: Frontend - Settings Pages

### Task 6.1: Logging Page

**Files to create:**
- `src/routes/logging/+page.svelte`

**Features:**
- Toggle local logging on/off
- Set logging interval
- Download CSV button
- Show log file size

**Verification:** Settings persist, CSV downloads.

---

### Task 6.2: Calibration Page

**Files to create:**
- `src/routes/calibration/+page.svelte`
- `src/lib/components/CalibrationTable.svelte`

**Features:**
- Tilt selector dropdown
- SG calibration section (table of points, add/remove)
- Temp calibration section (table of points, add/remove)
- Clear all button per type

**Verification:** Add calibration points, see calibrated values change on dashboard.

---

### Task 6.3: System Page

**Files to create:**
- `src/routes/system/+page.svelte`

**Features:**
- Display units (temp: F/C, SG: sg/plato/brix)
- Hostname display
- IP address display
- Timezone selector
- Reboot/Shutdown buttons (with confirmation)
- Smoothing settings
- RSSI filter setting
- ID by MAC toggle

**Verification:** All settings persist and take effect.

---

## Phase 7: Local Logging & Export

### Task 7.1: Logger Service

**Files to create:**
- `backend/services/local_logger.py`

**Implementation:**
- Background task checks interval
- Writes to readings table
- Cleanup job removes readings > 30 days

**Verification:** Readings accumulate in DB at configured interval.

---

### Task 7.2: CSV Export

**Add to main.py:**
```python
@app.get("/log.csv")
async def download_log():
    # Query readings, format as CSV
    # Return StreamingResponse with CSV content
```

**Verification:** Download produces valid CSV with all readings.

---

## Phase 8: Polish & Deployment

### Task 8.1: Error Handling

- Add try/catch around scanner
- WebSocket reconnection logic in frontend
- Toast notifications for errors
- API error responses

---

### Task 8.2: Systemd Service

**Files to create:**
- `deploy/tiltui.service`
- `deploy/install.sh`

**install.sh:**
```bash
#!/bin/bash
set -e

# Create directory
sudo mkdir -p /opt/tiltui
sudo cp -r backend /opt/tiltui/
sudo cp -r data /opt/tiltui/

# Create venv and install
python3 -m venv /opt/tiltui/venv
/opt/tiltui/venv/bin/pip install .

# Install service
sudo cp deploy/tiltui.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tiltui
sudo systemctl start tiltui
```

**Verification:** Service starts on boot, UI accessible on port 80.

**Sudoers setup (required for system endpoints):**

Install the sudoers file to allow passwordless system control:
```bash
cat << 'EOF' | sudo tee /etc/sudoers.d/tiltui
# Allow tiltui service to manage system without password prompts
pi ALL=(ALL) NOPASSWD: /usr/bin/systemctl reboot
pi ALL=(ALL) NOPASSWD: /usr/bin/systemctl poweroff
pi ALL=(ALL) NOPASSWD: /usr/bin/timedatectl set-timezone *
EOF
sudo chmod 440 /etc/sudoers.d/tiltui
sudo visudo -c  # Validate syntax
```

---

### Task 8.3: Documentation

**Files to create:**
- `README.md` - Installation, usage, development
- Update `TILTPI_REVERSE_ENGINEERING.md` with link to new project

---

## Summary

| Phase | Tasks | Estimated Complexity |
|-------|-------|---------------------|
| 1. Project Setup | 3 | Low |
| 2. BLE Scanner | 2 | Medium |
| 3. WebSocket | 1 | Low |
| 4. REST API | 4 | Medium |
| 5. Frontend Core | 4 | Medium |
| 6. Settings Pages | 3 | Medium |
| 7. Logging & Export | 2 | Low |
| 8. Polish & Deploy | 3 | Low |

**Total: 22 tasks**

## Development Order Recommendation

1. Phase 1 (setup) - get both stacks running
2. Phase 2 + 3 (scanner + websocket) - core data flow
3. Phase 5.1-5.3 (layout + dashboard) - see something working end-to-end
4. Phase 4 (REST API) - fill in API endpoints
5. Phase 5.4 (charts) - historical visualization
6. Phase 6 (settings pages) - configuration UI
7. Phase 7 (logging) - persistence
8. Phase 8 (polish) - deployment ready
