# TiltPi Reverse Engineering Notes

**Source Image**: `tiltpi2-bookworm-HDMI-May25.img.gz`
**Analysis Date**: 2025-11-27

## Overview

The Tilt Hydrometer is a wireless digital hydrometer/thermometer used by homebrewers. It floats in fermenting liquid and broadcasts specific gravity and temperature readings via Bluetooth Low Energy (BLE) as iBeacon advertisements.

TiltPi is a Raspberry Pi image that receives these BLE broadcasts and provides a web-based dashboard for monitoring fermentation.

---

## System Architecture

### Components

1. **Bluetooth Scanner**: `aioblescan` Python library
2. **Application Server**: Node-RED (port 1880)
3. **Dashboard UI**: Node-RED Dashboard (AngularJS-based)
4. **Startup**: Chromium in kiosk mode loading the dashboard

### Services

- `nodered.service` - Main application server
- Runs as user `pi` with 256MB heap limit
- Auto-restarts on crash

---

## Bluetooth Protocol

### Scanner Command

```bash
python3 -m aioblescan -T
```

Outputs JSON to stdout for each detected Tilt beacon.

### iBeacon Data Format

The Tilt broadcasts as an Apple iBeacon with manufacturer-specific data.

**Identifier**: `4c000215a495` (Apple iBeacon prefix + Tilt UUID preamble)

### UUID to Color Mapping

| UUID                                   | Color  |
|----------------------------------------|--------|
| `a495bb10c5b14b44b5121370f02d74de`     | RED    |
| `a495bb20c5b14b44b5121370f02d74de`     | GREEN  |
| `a495bb30c5b14b44b5121370f02d74de`     | BLACK  |
| `a495bb40c5b14b44b5121370f02d74de`     | PURPLE |
| `a495bb50c5b14b44b5121370f02d74de`     | ORANGE |
| `a495bb60c5b14b44b5121370f02d74de`     | BLUE   |
| `a495bb70c5b14b44b5121370f02d74de`     | YELLOW |
| `a495bb80c5b14b44b5121370f02d74de`     | PINK   |

### Data Fields

| Field      | Description                                              |
|------------|----------------------------------------------------------|
| `uuid`     | 32-char hex string identifying Tilt color                |
| `major`    | Temperature in °F (uint16, big-endian)                   |
| `minor`    | Specific Gravity × 1000 (uint16, big-endian)             |
| `tx_power` | Weeks since battery change (int8, 0-152 unsigned)        |
| `rssi`     | Signal strength in dBm                                   |
| `mac`      | Bluetooth MAC address                                    |

### HD (High Definition) Tilt Detection

If `minor > 2000`, it's an HD Tilt:
- SG = `minor / 10000` (4 decimal places)
- Temperature = `major / 10`

Otherwise (standard Tilt):
- SG = `minor / 1000` (3 decimal places)
- Temperature = `major`

### Example JSON Output

```json
{
  "uuid": "a495bb60c5b14b44b5121370f02d74de",
  "major": 72,
  "minor": 1045,
  "tx_power": -59,
  "rssi": -65,
  "mac": "aa:bb:cc:dd:ee:ff"
}
```

This represents: BLUE Tilt, 72°F, SG 1.045

---

## Unit Conversions

### Specific Gravity to Plato

```javascript
Plato = 1111.14 * SG - 630.272 * SG² + 135.997 * SG³ - 616.868
```

### Specific Gravity to Brix

```javascript
Brix = ((182.4601 * SG - 775.6821) * SG + 1262.7794) * SG - 669.5622
```

### Fahrenheit to Celsius

```javascript
Celsius = (Fahrenheit - 32) * 0.5555
```

---

## Calibration System

Uses linear interpolation between user-defined calibration points.

### Data Structure

Per-color calibration stored as:
- `actualSGpoints-{COLOR}` - Array of actual (reference) SG values
- `uncalSGpoints-{COLOR}` - Array of raw Tilt SG readings
- `actualTemppoints-{COLOR}` - Array of actual temperature values
- `uncalTemppoints-{COLOR}` - Array of raw Tilt temperature readings

### Interpolation Algorithm

```javascript
function linearInterpolation(x, x0, y0, x1, y1) {
  var a = (y1 - y0) / (x1 - x0);
  var b = -a * x0 + y0;
  return a * x + b;
}
```

---

## Cloud Logging

### Default Cloud URL

```
https://script.google.com/macros/s/AKfycbwNXh6rEWoULd0vxWxDylG_PJwQwe0dn5hdtSkuC4k3D9AXBSA/exec
```

### POST Payload Format

```
Content-Type: application/x-www-form-urlencoded

Timepoint={excel_timestamp}&Temp={temp}&SG={sg}&Beer={beer_name}&Color={color}&Comment={comment}
```

### Timepoint Calculation

Excel-compatible timestamp:
```javascript
Timepoint = timestamp_ms / 1000 / 60 / 60 / 24 + 25569 - timezoneOffset
```

---

## Node-RED Dashboard Structure

### Tabs

1. **Tilt Pi** - Main display showing all detected Tilts
2. **Logging** - Cloud and local logging configuration
3. **Calibration** - SG and temperature calibration interface
4. **System** - Time, display units, WiFi, hostname, reboot

### Node Statistics

| Node Type       | Count |
|-----------------|-------|
| function        | 106   |
| change          | 77    |
| inject          | 50    |
| ui_group        | 40    |
| ui_template     | 29    |
| exec            | 29    |
| ui_text         | 15    |
| ui_button       | 14    |
| ui_switch       | 13    |
| delay           | 13    |
| debug           | 13    |
| **Total**       | **518** |

### UI Template Structure

Each Tilt display card shows:
- Beer name
- Tilt color (with color bar)
- SG/Concentration (calibrated and pre-calibrated)
- Temperature (calibrated and pre-calibrated)
- Timestamp
- Signal strength (RSSI)
- Time since last reading

---

## Configuration Options

### Display Units
- Temperature: °F or °C
- Fermentation: SG, °P (Plato), or °Bx (Brix)

### Filtering Options
- Minimum RSSI threshold
- Identify Tilt by MAC address (for multiple same-color Tilts)

### Smoothing Options
- Alpha values for SG and Temperature (exponential smoothing)
- Number of samples to average

### Range Boost
- Multiple TiltPis can share data via HTTP
- Configure hostnames of other TiltPi devices

---

## File Locations on TiltPi

```
/home/pi/
├── .node-red/
│   ├── flows_tiltpi.json    # Main application logic
│   ├── settings.js          # Node-RED configuration
│   ├── package.json         # Node dependencies
│   └── node_modules/        # Installed packages
├── Desktop/
│   └── tiltpi.html          # Splash/loading page
├── {COLOR}.json             # Per-Tilt state files
└── log.csv                  # Local data log

/usr/local/lib/python3.11/dist-packages/
└── aioblescan-0.2.4-py3.11.egg  # BLE scanner

/etc/xdg/lxsession/LXDE-pi/autostart
# Launches Chromium to file:///home/pi/Desktop/tiltpi.html
```

---

## Extracted Files

Located in `extracted/` directory:

```
extracted/
├── aioblescan/
│   └── aioblescan/
│       ├── __init__.py
│       ├── __main__.py         # CLI entry point
│       ├── aioblescan.py       # Core BLE scanning
│       └── plugins/
│           ├── __init__.py
│           ├── tilt.py         # Tilt decoder
│           ├── eddystone.py
│           ├── ruuviweather.py
│           └── bluemaestro.py
├── node-red-config/
│   ├── flows_tiltpi.json       # 518 nodes, ~250KB
│   ├── settings.js
│   └── package.json
└── tiltpi.html
```

---

## Known Issues with Current UI

1. **Dated Technology**: AngularJS 1.x in Node-RED Dashboard
2. **Duplicated Code**: 25 nearly identical UI templates for each Tilt slot
3. **Limited Responsiveness**: Fixed-width design
4. **No Historical Charts**: Only current readings displayed
5. **Complex Configuration**: Many nested settings screens
6. **No Dark/Light Theme Toggle**: Single custom theme only

---

## Dependencies

### Node-RED Packages

```json
{
  "node-red-contrib-buffer-parser": "^3.2.2",
  "node-red-contrib-play-audio": "^2.5.0",
  "node-red-node-pi-gpio": "^2.0.6",
  "node-red-node-ping": "^0.3.3",
  "node-red-node-random": "^0.4.1",
  "node-red-node-serialport": "^2.0.3",
  "node-red-node-smooth": "^0.1.2"
}
```

### Python Packages

- `aioblescan` 0.2.4

---

## References

- [Tilt Hydrometer Official](https://tilthydrometer.com)
- [aioblescan GitHub](https://github.com/frawau/aioblescan)
- [Node-RED Dashboard](https://flows.nodered.org/node/node-red-dashboard)
