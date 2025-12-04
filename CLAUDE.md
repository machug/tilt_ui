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
- `backend/routers/maintenance.py` - Orphaned data detection and cleanup

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
ssh pi@192.168.4.218
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
sshpass -p 'tilt' ssh -o StrictHostKeyChecking=no pi@192.168.4.218 \
  "cd /opt/brewsignal && git fetch origin && git reset --hard origin/master && sudo systemctl restart brewsignal"
```

**4. Verify deployment:**

```bash
# Check service status
sshpass -p 'tilt' ssh -o StrictHostKeyChecking=no pi@192.168.4.218 "sudo systemctl status brewsignal"

# View logs
sshpass -p 'tilt' ssh -o StrictHostKeyChecking=no pi@192.168.4.218 "sudo journalctl -u brewsignal -n 100 --no-pager"

# Live log tail
sshpass -p 'tilt' ssh -o StrictHostKeyChecking=no pi@192.168.4.218 "sudo journalctl -u brewsignal -f"
```

**One-liner deploy (all steps):**

```bash
cd frontend && npm run build && cd .. && \
git add . && git commit -m "build: deploy to RPi" && git push && \
sshpass -p 'tilt' ssh -o StrictHostKeyChecking=no pi@192.168.4.218 \
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
mcp__chrome-devtools__new_page http://192.168.4.218:8080

# Take snapshot
mcp__chrome-devtools__take_snapshot

# Check for errors
mcp__chrome-devtools__list_console_messages

# Inspect network requests
mcp__chrome-devtools__list_network_requests
```

## Key Technical Details

### Temperature Units

**CRITICAL: Always use Celsius (°C) for internal calculations, storage, and API responses.**

- **Database:** All temperature values stored in Celsius
- **Backend Logic:** All temperature calculations, control logic, and ML models use Celsius
- **API:** All temperature values in JSON responses are Celsius
- **UI Conversion:** Frontend converts to user's preferred unit (C/F) based on system preferences
- **Tilt BLE Boundary:** Tilt devices broadcast in Fahrenheit - convert immediately on ingestion
- **iSpindel/GravityMon:** Already send Celsius - no conversion needed

**Temperature Conversion Helpers:**
- `backend/services/temp_utils.py` - Centralized conversion utilities
- Frontend stores: `src/lib/state.ts` - User preference for display units
- UI components: Handle display conversion automatically based on preferences

**Why Celsius?**
- International standard for scientific/brewing calculations
- Home Assistant default unit system
- iSpindel/GravityMon native format
- Only Tilt hardware requires conversion at boundary

**When Adding Temperature Features:**
1. Always work in Celsius internally
2. Only convert for display in UI based on user preference
3. Document any Fahrenheit values in comments as "for Tilt BLE compatibility only"
4. Never hardcode temperature values - use config or calculations

### Device Pairing System

Devices (Tilts) must be **paired** before logging readings. This prevents data pollution from nearby devices.

- Unpaired devices appear on dashboard but don't log to database
- Pairing happens via Devices page or API: `PUT /api/devices/{id}`
- Check `paired` field on Tilt/Device models

### Temperature Control

**Per-Batch Control:** Each batch can have independent temperature control with its own heater and/or cooler entity, target, and hysteresis.

**Architecture:**

- `temp_controller.py` runs background loop (every 60s)
- Fetches fermenting batches with heater/cooler entities
- Compares current temp (from latest_readings state) to target
- Sends Home Assistant API calls to control switch entities
- Supports manual override (Force ON/OFF) per device per batch
- Enforces mutual exclusion (heater and cooler never run simultaneously)

**Control Logic (Symmetric Hysteresis):**

- Turn heater ON if: `current_temp <= (target - hysteresis)`
- Turn heater OFF if: `current_temp >= (target + hysteresis)`
- Turn cooler ON if: `current_temp >= (target + hysteresis)`
- Turn cooler OFF if: `current_temp <= (target - hysteresis)`
- Within deadband: maintain current states (prevent oscillation)
- Mutual exclusion: Turning heater ON ensures cooler is OFF (and vice versa)

**Operational Modes:**
- Heating-only: `heater_entity_id` set, `cooler_entity_id` NULL
- Cooling-only: `cooler_entity_id` set, `heater_entity_id` NULL
- Dual-mode: Both entities set (full temperature regulation)

**Min Cycle Time:** 5 minutes for both heater and cooler to prevent equipment damage and compressor short-cycling.

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

### Batch Lifecycle Management

**Soft Delete Pattern:** Batches use soft delete (deleted_at timestamp) to preserve historical data while removing from active views.

**Status Flow:**
- Planning → Fermenting → Completed/Conditioning
- Any status can be soft deleted (marked with deleted_at)
- Deleted batches can be restored (deleted_at set to null)
- Hard delete cascades to readings

**Tab-Based Filtering:**
- Active tab: Shows batches with status "planning" or "fermenting" (not deleted)
- Completed tab: Shows batches with status "completed" or "conditioning" (not deleted)
- Deleted tab: Shows soft-deleted batches (deleted_at is not null)

**Orphaned Data Cleanup:**
- Orphaned readings: Readings linked to soft-deleted batches
- Maintenance page: `/system/maintenance`
- Preview-first pattern: dry_run=true before actual cleanup
- Safety checks: Cannot cleanup readings for active batches

**API Endpoints:**
- GET `/api/batches` - List batches (supports `include_deleted`, `deleted_only` query params)
- GET `/api/batches/active` - Convenience endpoint for active batches
- GET `/api/batches/completed` - Convenience endpoint for completed batches
- POST `/api/batches/{id}/delete` - Soft delete (default) or hard delete (with `hard_delete=true`)
- POST `/api/batches/{id}/restore` - Restore soft-deleted batch
- GET `/api/maintenance/orphaned-data` - Detect orphaned readings
- POST `/api/maintenance/cleanup-readings` - Preview/execute cleanup

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
