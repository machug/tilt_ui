# BrewSignal

![CI](https://github.com/machug/brewsignal/actions/workflows/ci.yml/badge.svg) ![Version](https://img.shields.io/badge/version-2.4.0-blue) ![Python](https://img.shields.io/badge/python-3.11+-blue) ![License](https://img.shields.io/badge/license-MIT-green)

A modern web interface for monitoring fermentation hydrometers on Raspberry Pi. Supports Tilt, iSpindel, and GravityMon devices.

![Dashboard](docs/screenshots/dashboard.png)

## Quick Install (Raspberry Pi)

```bash
git clone https://github.com/machug/brewsignal.git
cd brewsignal
python3 -m venv venv && source venv/bin/activate
pip install -e .
uvicorn backend.main:app --host 0.0.0.0 --port 8080
```

## Features

- **Multi-Device Support** - Tilt (BLE), iSpindel (HTTP), GravityMon (HTTP) hydrometers
- **Real-time Monitoring** - Live SG and temperature readings via WebSocket
- **Historical Charts** - Interactive uPlot charts with crosshair tooltips, 1H/6H/24H/7D/30D time ranges
- **Calibration** - Linear interpolation (Tilt) and polynomial calibration (iSpindel/GravityMon)
- **Unit Conversion** - Display gravity as SG, Plato, or Brix; temperature as °C or °F
- **RSSI Filtering** - Filter weak Bluetooth signals to reduce noise from distant devices
- **Reading Smoothing** (v2.4.0) - Configurable moving average filter to reduce sensor noise
- **Outlier Validation** (v2.4.0) - Physical impossibility checks reject invalid readings
- **Home Assistant Integration** - Display ambient temperature/humidity from HA sensors
- **Dual-Mode Temperature Control** (v2.4.0) - Independent heater AND cooler control per batch
  - Heating-only, cooling-only, or full dual-mode operation
  - Batch-specific temperature targets and hysteresis settings
  - Manual override controls (Force ON/OFF) per device per batch
  - Real-time heater and cooler state monitoring with visual indicators
  - Mutual exclusion logic prevents simultaneous heating and cooling
  - Minimum 5-minute cycle protection for equipment safety
- **Batch Lifecycle Management** (v2.4.0) - Soft delete, restoration, and data maintenance
  - Tab-based navigation (Active, Completed, Deleted)
  - Orphaned data detection and cleanup
  - Safe batch deletion with preview mode
- **Weather Alerts** - Predictive alerts when forecast temps may affect fermentation
- **BeerXML Import & Batch Tracking** - Import recipes with full ingredients, link readings to batches, track against targets
- **Data Export** - Download all readings as CSV
- **Dark Theme** - Easy on the eyes during late-night brew checks

## Device Pairing (v2.3.0+)

Tilt devices must be **paired** before readings are logged. This prevents data pollution from nearby devices.

- Navigate to **Devices** page to pair/unpair devices
- Only paired devices log readings and can be assigned to batches
- Unpaired devices still appear on dashboard with live readings

## Requirements

- Raspberry Pi (3B+ or newer recommended)
- Python 3.11+
- Bluetooth adapter (built-in or USB) for Tilt devices
- Supported hydrometer: Tilt, iSpindel, or GravityMon

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/machug/brewsignal.git
cd brewsignal

# Create virtual environment and install
python3 -m venv venv
source venv/bin/activate
pip install -e .

# Run the server
uvicorn backend.main:app --host 0.0.0.0 --port 8080
```

Access the UI at `http://<raspberry-pi-ip>:8080`

### Systemd Service (Production)

```bash
# Copy service file
sudo cp deploy/brewsignal.service /etc/systemd/system/

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable brewsignal
sudo systemctl start brewsignal
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SCANNER_MOCK` | Enable mock scanner for development | `false` |
| `SCANNER_FILES_PATH` | Path to TiltPi JSON files (legacy mode) | - |
| `SCANNER_RELAY_HOST` | IP of remote TiltPi to relay from | - |

### Scanner Modes

1. **BLE Mode** (default) - Direct Bluetooth scanning for Tilt devices
2. **Mock Mode** - Simulated readings for development (`SCANNER_MOCK=true`)
3. **File Mode** - Read from TiltPi JSON files (`SCANNER_FILES_PATH=/home/pi`)
4. **Relay Mode** - Fetch from remote TiltPi (`SCANNER_RELAY_HOST=192.168.1.100`)

### Reading Smoothing (v2.4.0)

Configure in System Settings:
- **Smoothing Enabled** - Apply moving average filter to raw readings
- **Smoothing Samples** - Number of samples for moving average (default: 5)

Smoothing is applied after calibration but before storage, benefiting all consumers (charts, exports, Home Assistant).

### Temperature Control

Configure per batch in Batch form:
- **Heating-only Mode** - Set only `heater_entity_id` from Home Assistant
- **Cooling-only Mode** - Set only `cooler_entity_id` from Home Assistant
- **Dual-mode** - Set both for full temperature regulation
- **Temperature Target** - Desired fermentation temperature
- **Hysteresis** - Temperature buffer to prevent oscillation (symmetric for heat/cool)
- **Manual Override** - Force heater/cooler ON/OFF for testing

Control logic:
- Heater turns ON when `temp <= (target - hysteresis)`, OFF when `temp >= (target + hysteresis)`
- Cooler turns ON when `temp >= (target + hysteresis)`, OFF when `temp <= (target - hysteresis)`
- Mutual exclusion enforced (heater and cooler never run simultaneously)
- Minimum 5-minute cycle time protects compressor equipment

## Batch Management

### Batch Statuses

- **Planning** - Recipe selected, not started
- **Fermenting** - Active fermentation in progress
- **Conditioning** - Fermentation complete, conditioning
- **Completed** - Finished, ready for packaging

### Batch Lifecycle (v2.4.0)

**Tab-Based Navigation:**
- **Active Tab** - Shows batches with status "planning" or "fermenting" (not deleted)
- **Completed Tab** - Shows batches with status "completed" or "conditioning" (not deleted)
- **Deleted Tab** - Shows soft-deleted batches (restorable)

**Soft Delete:**
- Batches can be soft-deleted to preserve historical data
- Soft-deleted batches are hidden from active views but restorable
- Readings remain linked to soft-deleted batches

**Hard Delete:**
- Permanently removes batch and cascades to all linked readings
- Use with caution - this operation cannot be undone

**Data Maintenance:**
- Access `/system/maintenance` to detect orphaned readings
- Orphaned readings are linked to soft-deleted batches
- Preview cleanup operations (dry-run mode) before executing
- Safe cleanup only removes readings for deleted batches

## API Endpoints

### Devices & Sensors

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/devices` | GET/POST | List or register devices |
| `/api/devices/{id}` | GET/PUT/DELETE | Device management |
| `/api/devices/{id}/calibration` | GET/PUT | Device calibration data |
| `/api/tilts` | GET | List all detected Tilts |
| `/api/tilts/{id}` | GET/PUT | Get or update Tilt |
| `/api/tilts/{id}/readings` | GET | Historical readings |
| `/api/tilts/{id}/calibration` | GET/POST | Calibration points |

### Data Ingestion

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/ingest/generic` | POST | Auto-detect device format |
| `/api/ingest/ispindel` | POST | iSpindel HTTP endpoint |
| `/api/ingest/gravitymon` | POST | GravityMon HTTP endpoint |

### Batches & Recipes

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/batches` | GET/POST | List or create batches |
| `/api/batches/active` | GET | List active batches |
| `/api/batches/completed` | GET | List completed batches |
| `/api/batches/{id}` | GET/PUT | Get or update batch |
| `/api/batches/{id}/progress` | GET | Detailed fermentation progress |
| `/api/batches/{id}/delete` | POST | Soft or hard delete batch |
| `/api/batches/{id}/restore` | POST | Restore soft-deleted batch |
| `/api/recipes` | GET/POST | List or create recipes |
| `/api/recipes/{id}` | GET/PUT/DELETE | Recipe with full ingredients |
| `/api/recipes/import` | POST | Import BeerXML file |

### Temperature Control

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/control/status` | GET | Global temperature control status (deprecated) |
| `/api/control/batch/{id}/status` | GET | Temperature control status for specific batch |
| `/api/control/override` | POST | Set manual heater/cooler override (requires batch_id and device_type) |
| `/api/control/heater-entities` | GET | List available HA heater entities |
| `/api/control/cooler-entities` | GET | List available HA cooler entities |

### Data Maintenance

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/maintenance/orphaned-data` | GET | Detect orphaned readings |
| `/api/maintenance/cleanup-readings` | POST | Preview/execute orphaned reading cleanup |

### System & Config

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/config` | GET/PATCH | Application settings (smoothing, units, etc.) |
| `/api/system/info` | GET | System information |
| `/api/ambient` | GET | Ambient temp/humidity from HA |
| `/api/alerts` | GET | Weather forecast and alerts |
| `/ws` | WebSocket | Real-time readings |
| `/log.csv` | GET | Export all data as CSV |

### Interactive API Documentation

Full API documentation with request/response examples available at:
- Local: `http://localhost:8080/docs`
- Raspberry Pi: `http://<raspberry-pi-ip>:8080/docs`

## iSpindel/GravityMon Setup

Configure your iSpindel or GravityMon to POST to:

```
http://<raspberry-pi-ip>:8080/api/ingest/ispindel
```

The server auto-detects GravityMon extended format. Readings appear on the dashboard alongside Tilt devices.

## BeerXML Import

Import a BeerXML file to auto-populate recipe targets and link batches:

```bash
curl -X POST "http://<raspberry-pi-ip>:8080/api/recipes/import" \
  -F "file=@/path/to/recipe.xml"
```

Imports include:
- Recipe metadata (name, brewer, style, etc.)
- Fermentables with weights and colors
- Hops with timing and alpha acids
- Yeast strains and attenuation
- BJCP style guidelines (OG, FG, ABV, IBU ranges)

## Calibration

Add calibration points to correct SG and temperature readings:

1. Take a reference reading with a hydrometer/thermometer
2. Note the raw value shown in BrewSignal
3. Add a calibration point: raw value → actual value
4. The system uses linear interpolation (Tilt) or polynomial fitting (iSpindel/GravityMon) between points

## Development

```bash
# Backend (FastAPI)
cd brewsignal
pip install -e ".[dev]"
uvicorn backend.main:app --reload

# Frontend (Svelte)
cd frontend
npm install
npm run dev
```

### Building Frontend

```bash
cd frontend
npm run build  # Outputs to backend/static/
```

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy 2.0 (async), SQLite, Bleak (BLE)
- **Frontend**: SvelteKit 2.x, Svelte 5, TailwindCSS v4, uPlot
- **Deployment**: Systemd, uvicorn

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for detailed version history.

## License

MIT

## Acknowledgments

- [Tilt Hydrometer](https://tilthydrometer.com/) for the awesome hardware
- [TiltPi](https://github.com/baronbrew/TiltPi) for inspiration
- [iSpindel](https://www.ispindel.de/) for the open-source WiFi hydrometer
- [GravityMon](https://github.com/mp-se/gravitymon) for extended iSpindel firmware
