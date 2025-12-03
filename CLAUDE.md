# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BrewSignal is a web-based fermentation monitoring dashboard for Raspberry Pi. It supports multiple hydrometer types (Tilt BLE, iSpindel HTTP, GravityMon HTTP) and provides real-time monitoring, historical charts, calibration, batch tracking, and per-batch temperature control via Home Assistant integration.

## Development Environment

### Backend (FastAPI + SQLAlchemy)

```bash
# Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Run development server (auto-reload)
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8080

# Run without reload (production-like)
uvicorn backend.main:app --host 0.0.0.0 --port 8080
```

### Frontend (SvelteKit + TailwindCSS)

```bash
cd frontend

# Install dependencies
npm install

# Development server (port 5173)
npm run dev

# Build frontend (outputs to backend/static/)
npm run build

# Type checking
npm run check
```

### Full Stack Development

1. Start backend: `uvicorn backend.main:app --reload`
2. Start frontend: `cd frontend && npm run dev`
3. Access frontend dev server at `http://localhost:5173` (proxies API to backend)
4. Access production build at `http://localhost:8080` (backend serves static files)

## Architecture

### Backend Structure

**Core Components:**

- `backend/main.py` - FastAPI app entry point, WebSocket manager, scanner lifecycle
- `backend/database.py` - SQLAlchemy async engine, Base model, migration system
- `backend/models.py` - SQLAlchemy ORM models (Tilt, Device, Reading, Recipe, Batch, Style) and Pydantic schemas
- `backend/state.py` - In-memory state (latest readings dict)
- `backend/websocket.py` - WebSocket connection manager for real-time updates

**Services:**

- `backend/scanner.py` - Multi-mode Tilt scanner (BLE/Mock/File/Relay)
- `backend/temp_controller.py` - Per-batch temperature control loop with Home Assistant integration
- `backend/ambient_poller.py` - Polls Home Assistant for ambient temp/humidity
- `backend/cleanup.py` - Background task to clean old readings
- `backend/services/calibration.py` - Calibration logic (linear interpolation, polynomial)
- `backend/services/batch_linker.py` - Auto-links readings to active batches

**Routers:**

- `backend/routers/tilts.py` - Tilt device CRUD
- `backend/routers/devices.py` - Universal device registry (Tilt, iSpindel, GravityMon)
- `backend/routers/ingest.py` - HTTP ingest endpoints for iSpindel/GravityMon
- `backend/routers/batches.py` - Batch management
- `backend/routers/recipes.py` - Recipe import (BeerXML) and CRUD
- `backend/routers/control.py` - Temperature control endpoints
- `backend/routers/config.py` - Application settings
- `backend/routers/system.py` - System info
- `backend/routers/alerts.py` - Weather alerts
- `backend/routers/ambient.py` - Ambient readings
- `backend/routers/ha.py` - Home Assistant integration

### Database Migrations

**Migration System:** Schema migrations run at startup via `init_db()` in `backend/database.py`. The system uses SQLite with manual migrations (not Alembic) to handle schema evolution incrementally.

**Migration Pattern:**

1. Schema migrations run first (ALTER TABLE)
2. Then `create_all()` creates missing tables
3. Then data migrations run (copy/transform data)

**Adding New Migrations:**

1. Add migration function in `database.py` (e.g., `_migrate_add_new_column`)
2. Call it from `init_db()` in correct order
3. Use SQLite `PRAGMA table_info()` to check existing columns
4. For complex changes, recreate table with correct schema (SQLite limitation)

**CRITICAL:** When modifying batch/recipe/reading models, always check if eager loading is needed for nested relationships to avoid `MissingGreenlet` errors. Use `selectinload()` for relationships that will be serialized in API responses.

Example:

```python
# WRONG - will cause MissingGreenlet error
query = select(Batch).options(selectinload(Batch.recipe))

# RIGHT - eagerly loads nested relationship
query = select(Batch).options(selectinload(Batch.recipe).selectinload(Recipe.style))
```

### Frontend Structure

**Framework:** SvelteKit with TailwindCSS v4, adapter-static for production builds

**Key Pages:**

- `src/routes/+page.svelte` - Dashboard (live readings, charts)
- `src/routes/batches/` - Batch management
- `src/routes/recipes/` - Recipe library
- `src/routes/devices/` - Device pairing
- `src/routes/calibration/` - Calibration points
- `src/routes/system/` - Config and system info

**State Management:**

- `src/lib/state.ts` - Svelte stores (config, devices, batches)
- WebSocket connection for real-time readings

**Charts:** uPlot for time series (gravity/temperature over time)

## Raspberry Pi Deployment

### SSH Access

**Connection:**

```bash
ssh pi@192.168.4.117
# Password: tilt
```

**Deployment Directory:** `/opt/brewsignal`

### Deployment Workflow

**1. Build frontend locally:**

```bash
cd frontend
npm run build  # Outputs to backend/static/
```

**2. Commit and push:**

```bash
git add .
git commit -m "Your commit message

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
git push
```

**3. Deploy to Raspberry Pi:**

```bash
sshpass -p 'tilt' ssh -o StrictHostKeyChecking=no pi@192.168.4.117 \
  "cd /opt/brewsignal && git fetch origin && git reset --hard origin/master && sudo systemctl restart brewsignal"
```

**4. Verify deployment:**

```bash
# Check service status
sshpass -p 'tilt' ssh -o StrictHostKeyChecking=no pi@192.168.4.117 "sudo systemctl status brewsignal"

# View logs
sshpass -p 'tilt' ssh -o StrictHostKeyChecking=no pi@192.168.4.117 "sudo journalctl -u brewsignal -n 100 --no-pager"

# Live log tail
sshpass -p 'tilt' ssh -o StrictHostKeyChecking=no pi@192.168.4.117 "sudo journalctl -u brewsignal -f"
```

**One-liner deploy (all steps):**

```bash
cd frontend && npm run build && cd .. && \
git add . && git commit -m "build: deploy to RPi" && git push && \
sshpass -p 'tilt' ssh -o StrictHostKeyChecking=no pi@192.168.4.117 \
  "cd /opt/brewsignal && git fetch origin && git reset --hard origin/master && sudo systemctl restart brewsignal"
```

### Service Management

**Systemd service:** `/etc/systemd/system/brewsignal.service`

```bash
# Start service
sudo systemctl start brewsignal

# Stop service
sudo systemctl stop brewsignal

# Restart service
sudo systemctl restart brewsignal

# Enable on boot
sudo systemctl enable brewsignal

# View status
sudo systemctl status brewsignal

# View logs (last 100 lines)
sudo journalctl -u brewsignal -n 100

# Follow logs in real-time
sudo journalctl -u brewsignal -f
```

**Service Configuration:**

- User: `pi`
- Working Directory: `/opt/brewsignal`
- Virtual Environment: `/opt/brewsignal/.venv`
- Data Directory: `/opt/brewsignal/data` (SQLite database)
- Port: `8080`

### Testing with Browser DevTools

Use the MCP Chrome DevTools integration to visually validate the deployed application:

```bash
# Navigate to the app
mcp__chrome-devtools__new_page http://192.168.4.117:8080

# Take snapshot
mcp__chrome-devtools__take_snapshot

# Check for errors
mcp__chrome-devtools__list_console_messages

# Inspect network requests
mcp__chrome-devtools__list_network_requests
```

## Key Technical Details

### Device Pairing System

Devices (Tilts) must be **paired** before logging readings. This prevents data pollution from nearby devices.

- Unpaired devices appear on dashboard but don't log to database
- Pairing happens via Devices page or API: `PUT /api/devices/{id}`
- Check `paired` field on Tilt/Device models

### Temperature Control

**Per-Batch Control:** Each batch can have independent temperature control with its own heater entity, target, and hysteresis.

**Architecture:**

- `temp_controller.py` runs background loop (every 10s)
- Fetches fermenting batches with heaters
- Compares current temp (from latest_readings state) to target
- Sends Home Assistant API calls to control switch entities
- Supports manual override (Force ON/OFF) per batch

**Control Logic:**

- Turn ON if: `current_temp < (target - hysteresis/2)`
- Turn OFF if: `current_temp > (target + hysteresis/2)`
- Within band: maintain current state (prevent oscillation)

### Calibration

**Tilt (BLE):** Linear interpolation between calibration points
**iSpindel/GravityMon:** Polynomial calibration (up to 3rd degree)

Calibration stored in `devices.calibration_data` as JSON with `sg_points` and `temp_points` arrays.

### WebSocket Real-time Updates

WebSocket endpoint: `ws://host:8080/ws`

**Message Format:**

```json
{
  "type": "reading",
  "device_id": "BLUE",
  "color": "BLUE",
  "sg": 1.050,
  "temp": 68.5,
  "timestamp": "2025-12-04T08:00:00Z"
}
```

Frontend connects on mount, receives live readings, updates charts.

## Common Patterns

### Adding a New API Endpoint

1. Create route function in appropriate router file
2. Use `Depends(get_db)` for database session
3. Use `selectinload()` for eager loading relationships
4. Return Pydantic response model
5. Add route to `backend/main.py` if creating new router

### Adding a New Database Column

1. Add field to SQLAlchemy model in `backend/models.py`
2. Add migration function in `backend/database.py`
3. Call migration from `init_db()` in correct order
4. Update Pydantic schemas if needed for API

### Testing Database Changes

```bash
# Delete database to test fresh migration
rm data/fermentation.db

# Run app to trigger migrations
uvicorn backend.main:app --reload
```

### DateTime Serialization

All datetime fields must be serialized with `serialize_datetime_to_utc()` helper to ensure JavaScript Date() interprets timestamps as UTC (not local time). Use `@field_serializer` on Pydantic models:

```python
@field_serializer('created_at', 'updated_at')
def serialize_dt(self, dt: Optional[datetime]) -> Optional[str]:
    return serialize_datetime_to_utc(dt)
```

## Environment Variables

- `SCANNER_MOCK=true` - Use mock scanner (development without Bluetooth)
- `SCANNER_FILES_PATH=/path` - Read from TiltPi JSON files (legacy mode)
- `SCANNER_RELAY_HOST=192.168.1.100` - Relay from remote TiltPi

## API Documentation

Access interactive API docs at `http://host:8080/docs` (Swagger UI)
