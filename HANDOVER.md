# BrewSignal Project Handover

## Quick Start for New Session

```
cd /home/ladmin/Projects/tilt_ui
```

**Read these first:**
1. `docs/plans/2025-11-27-tilt-ui-design.md` - Architecture & decisions
2. `docs/plans/2025-11-27-tilt-ui-implementation-plan.md` - 22 tasks across 8 phases
3. `TILTPI_REVERSE_ENGINEERING.md` - How the original TiltPi works

## What We're Building

A modern replacement for TiltPi's Node-RED dashboard to monitor Tilt Hydrometers.

**Tech stack:**
- Python + FastAPI (backend)
- Svelte + SvelteKit (frontend)
- SQLite (database)
- uPlot (charts)
- Tailwind CSS (styling)

**Key features:**
- Real-time Tilt display via WebSocket
- Historical charts (the big improvement over original)
- Calibration UI
- Local logging + CSV export
- No cloud logging (removed - we have proper charts now)

## Architecture

Single-process monolith:
```
FastAPI app
├── BLE Scanner (async task, uses aioblescan)
├── WebSocket Manager (real-time push to UI)
├── REST API (/api/tilts, /api/config, etc.)
├── SQLite (readings, calibration, config)
└── Static files (compiled Svelte SPA)
```

## Development Resources

**Existing TiltPi for testing:**
- IP: `192.168.4.117`
- SSH: `ssh pi@192.168.4.117`
- RED Tilt currently in use
- Can relay readings to dev machine

**Scanner modes:**
1. `SCANNER_MOCK=true` - Fake data (default for dev)
2. `SCANNER_RELAY_HOST=192.168.4.117` - Fetch from remote TiltPi
3. Normal - Local BLE (production)

## Project Structure (to create)

```
brewsignal/
├── backend/
│   ├── main.py
│   ├── scanner.py
│   ├── models.py
│   ├── database.py
│   ├── websocket.py
│   ├── routers/
│   └── services/
├── frontend/
│   ├── src/routes/
│   ├── src/lib/components/
│   └── src/lib/stores/
├── data/
├── docs/plans/
└── pyproject.toml
```

## Implementation Order

1. **Phase 1** - Project setup (Python + Svelte scaffolding)
2. **Phase 2** - BLE scanner integration
3. **Phase 3** - WebSocket real-time
4. **Phase 4** - REST API endpoints
5. **Phase 5** - Frontend core (dashboard, cards, charts)
6. **Phase 6** - Settings pages (logging, calibration, system)
7. **Phase 7** - Local logging & CSV export
8. **Phase 8** - Polish & deployment

## Extracted Reference Files

From the original TiltPi image:
- `extracted/aioblescan/` - Python BLE scanner with Tilt plugin
- `extracted/node-red-config/flows_tiltpi.json` - Original UI logic (518 nodes)
- `extracted/tiltpi.html` - Splash page

## Key Technical Details

**Tilt iBeacon format:**
- UUID prefix `a495bb` identifies color (10=RED, 20=GREEN, etc.)
- `major` = Temperature °F
- `minor` = SG × 1000 (or ×10000 if >2000 for HD Tilts)

**Calibration:** Linear interpolation between user-defined points

**Data retention:** 30 days of readings, nightly cleanup

## Ready to Implement

No code written yet - start with Phase 1, Task 1.1 (Initialize Python Backend).
