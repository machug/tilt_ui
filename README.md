# BrewSignal

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
- **Historical Charts** - Interactive uPlot charts with 1H/6H/24H/7D/30D time ranges
- **Calibration** - Linear interpolation (Tilt) and polynomial calibration (iSpindel)
- **Unit Conversion** - Display gravity as SG, Plato, or Brix; temperature as °C or °F
- **RSSI Filtering** - Filter weak Bluetooth signals to reduce noise from distant devices
- **Home Assistant Integration** - Display ambient temperature/humidity from HA sensors
- **Per-Batch Temperature Control** - Independent heater control for multiple simultaneous fermentations
  - Batch-specific temperature targets and hysteresis settings
  - Manual override controls (Force ON/OFF) per batch
  - Real-time heater state monitoring with visual indicators
- **Weather Alerts** - Predictive alerts when forecast temps may affect fermentation
- **BeerXML Import & Batch Tracking** - Import recipes, link readings to batches, and track against targets
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

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/devices` | GET/POST | List or register devices |
| `/api/devices/{id}` | GET/PUT/DELETE | Device management |
| `/api/devices/{id}/calibration` | GET/PUT | Device calibration data |
| `/api/ingest/generic` | POST | Auto-detect device format |
| `/api/ingest/ispindel` | POST | iSpindel HTTP endpoint |
| `/api/ingest/gravitymon` | POST | GravityMon HTTP endpoint |
| `/api/tilts` | GET | List all detected Tilts |
| `/api/tilts/{id}` | GET/PUT | Get or update Tilt |
| `/api/tilts/{id}/readings` | GET | Historical readings |
| `/api/tilts/{id}/calibration` | GET/POST | Calibration points |
| `/api/config` | GET/PATCH | Application settings |
| `/api/system/info` | GET | System information |
| `/api/ambient` | GET | Ambient temp/humidity from HA |
| `/api/control/status` | GET | Temperature control status (global, deprecated) |
| `/api/control/batch/{id}/status` | GET | Temperature control status for specific batch |
| `/api/control/override` | POST | Set manual heater override (requires batch_id) |
| `/api/control/heater-entities` | GET | List available HA switch/input_boolean entities |
| `/api/alerts` | GET | Weather forecast and alerts |
| `/ws` | WebSocket | Real-time readings |
| `/log.csv` | GET | Export all data as CSV |

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

## Calibration

Add calibration points to correct SG and temperature readings:

1. Take a reference reading with a hydrometer/thermometer
2. Note the raw value shown in BrewSignal
3. Add a calibration point: raw value → actual value
4. The system uses linear interpolation between points

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
- **Frontend**: SvelteKit, TailwindCSS, uPlot
- **Deployment**: Systemd, uvicorn

## License

MIT

## Acknowledgments

- [Tilt Hydrometer](https://tilthydrometer.com/) for the awesome hardware
- [TiltPi](https://github.com/baronbrew/TiltPi) for inspiration
- [iSpindel](https://www.ispindel.de/) for the open-source WiFi hydrometer
- [GravityMon](https://github.com/mp-se/gravitymon) for extended iSpindel firmware
