# Tilt UI Design Document

**Date:** 2025-11-27
**Status:** Approved

## Overview

A modern web UI for monitoring Tilt Hydrometers on Raspberry Pi, replacing the existing Node-RED dashboard with a Python/Svelte stack.

## Goals

- Feature parity with existing TiltPi (minus cloud logging)
- Modern, responsive UI with historical charting
- Standalone application (replaces Node-RED entirely)
- Low resource footprint for Raspberry Pi

## Tech Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Backend | Python + FastAPI | Async, WebSocket support, matches BLE scanner |
| Frontend | Svelte + SvelteKit | Tiny compiled output, reactive, no runtime |
| Database | SQLite | Simple, no server, good enough for Pi |
| BLE Scanner | aioblescan | Existing, proven, Python async |
| Charts | uPlot | Lightweight, fast, good for Pi |
| Styling | Tailwind CSS | Utility classes, easy dark mode |

## Architecture

Single-process monolith with embedded BLE scanner:

```
┌─────────────────────────────────────────────┐
│              FastAPI Application            │
│  ┌─────────────┐  ┌──────────────────────┐  │
│  │ BLE Scanner │  │   WebSocket Manager  │  │
│  │ (asyncio)   │──│   (real-time push)   │  │
│  └──────┬──────┘  └──────────────────────┘  │
│         │                    ▲              │
│         ▼                    │              │
│  ┌─────────────┐  ┌──────────┴───────────┐  │
│  │  SQLite DB  │  │  REST API + Static   │  │
│  │  (logs/cfg) │  │  (serves Svelte SPA) │  │
│  └─────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────┘
```

## Project Structure

```
tilt_ui/
├── backend/
│   ├── main.py              # FastAPI app entry point
│   ├── scanner.py           # BLE scanner (aioblescan wrapper)
│   ├── models.py            # Pydantic models + SQLAlchemy
│   ├── database.py          # SQLite connection
│   ├── routers/
│   │   ├── tilts.py         # /api/tilts endpoints
│   │   ├── config.py        # /api/config endpoints
│   │   ├── calibration.py   # /api/calibration endpoints
│   │   └── system.py        # /api/system endpoints
│   ├── services/
│   │   ├── local_logger.py  # CSV/SQLite logging
│   │   └── calibration.py   # Linear interpolation logic
│   └── websocket.py         # WebSocket manager
├── frontend/
│   ├── src/
│   │   ├── routes/
│   │   │   ├── +page.svelte       # Main dashboard
│   │   │   ├── +layout.svelte     # App shell
│   │   │   ├── logging/+page.svelte
│   │   │   ├── calibration/+page.svelte
│   │   │   └── system/+page.svelte
│   │   ├── lib/
│   │   │   ├── components/
│   │   │   ├── stores/
│   │   │   └── api.ts
│   │   └── app.html
│   ├── static/
│   ├── package.json
│   ├── svelte.config.js
│   └── tailwind.config.js
├── data/                    # SQLite DB + logs (runtime)
├── pyproject.toml
└── README.md
```

## Database Schema

```sql
-- Detected Tilts (current state)
CREATE TABLE tilts (
    id TEXT PRIMARY KEY,        -- color or "color:mac"
    color TEXT NOT NULL,
    mac TEXT,
    beer_name TEXT DEFAULT 'Untitled',
    last_seen TIMESTAMP
);

-- Historical readings
CREATE TABLE readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tilt_id TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sg_raw REAL,
    sg_calibrated REAL,
    temp_raw REAL,
    temp_calibrated REAL,
    rssi INTEGER,
    FOREIGN KEY (tilt_id) REFERENCES tilts(id)
);

-- Calibration points
CREATE TABLE calibration_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tilt_id TEXT NOT NULL,
    type TEXT NOT NULL,         -- 'sg' or 'temp'
    raw_value REAL NOT NULL,
    actual_value REAL NOT NULL,
    FOREIGN KEY (tilt_id) REFERENCES tilts(id)
);

-- App configuration
CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value TEXT                  -- JSON encoded
);
```

**Data retention:** 30 days, nightly cleanup job.

## API Endpoints

### WebSocket
```
WS /ws    # Real-time Tilt readings
```

### Tilts
```
GET    /api/tilts                  # List all Tilts
GET    /api/tilts/{id}             # Single Tilt
GET    /api/tilts/{id}/readings    # Historical data
PUT    /api/tilts/{id}             # Update beer name
DELETE /api/tilts/{id}             # Remove Tilt
```

### Calibration
```
GET    /api/tilts/{id}/calibration          # Get points
POST   /api/tilts/{id}/calibration          # Add point
DELETE /api/tilts/{id}/calibration/{type}   # Clear points
```

### Config
```
GET   /api/config     # All settings
PATCH /api/config     # Update settings
```

### System
```
GET  /api/system/info        # Hostname, IP, uptime
POST /api/system/reboot
POST /api/system/shutdown
GET  /api/system/timezones
PUT  /api/system/timezone
```

### Static
```
GET /              # Svelte SPA
GET /log.csv       # Download log
```

## Configuration Keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `temp_units` | string | "F" | "F" or "C" |
| `sg_units` | string | "sg" | "sg", "plato", or "brix" |
| `local_logging_enabled` | boolean | true | Enable local logging |
| `local_interval_minutes` | integer | 15 | Log frequency |
| `min_rssi` | integer | -100 | Signal strength filter |
| `smoothing_enabled` | boolean | false | Enable averaging |
| `smoothing_samples` | integer | 5 | Samples to average |
| `id_by_mac` | boolean | false | Identify by MAC |

## Frontend Pages

1. **Dashboard** (`/`) - Tilt cards + charts
2. **Logging** (`/logging`) - Local log settings, export
3. **Calibration** (`/calibration`) - SG/temp calibration
4. **System** (`/system`) - Units, timezone, hostname, reboot

## Deployment

**Location:** `/opt/tiltui/`

**Systemd service:**
```ini
[Unit]
Description=Tilt UI
After=network.target bluetooth.target

[Service]
Type=simple
User=pi
WorkingDirectory=/opt/tiltui
ExecStart=/opt/tiltui/venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 80
Restart=on-failure
RestartSec=5
AmbientCapabilities=CAP_NET_RAW CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
```

**Sudoers (non-interactive control):**
```
pi ALL=(root) NOPASSWD: /usr/bin/systemctl reboot
pi ALL=(root) NOPASSWD: /usr/bin/systemctl poweroff
pi ALL=(root) NOPASSWD: /usr/bin/timedatectl set-timezone *
```

## Out of Scope

- Cloud logging (Google Sheets) - replaced by local charts + CSV export
- Range Boost (multi-Pi sharing) - can add later if needed
- WiFi configuration - use raspi-config or Pi Imager instead

## Development Resources

**Existing TiltPi for testing:**
- IP: `192.168.4.117`
- SSH: `ssh pi@192.168.4.117`
- Has RED Tilt currently in use
- Can use as BLE relay during development (forward readings to dev machine)
- Current readings stored at `/home/pi/RED.json`

**Tooling:** Chrome DevTools MCP is available for live frontend inspection, and the frontend-design plugin skill is available to accelerate UI work and keep layouts intentional.

**Scanner modes:**
1. `TILT_MOCK=true` - Fake scanner with simulated readings (default for dev)
2. `TILT_RELAY=192.168.4.117` - Relay mode, fetches from remote TiltPi
3. Normal - Local BLE scanning (production)
