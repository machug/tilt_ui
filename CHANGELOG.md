# Changelog

All notable changes to BrewSignal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2025-11-29

### Changed
- **Project Rebrand** - Renamed from "Tilt UI" to "BrewSignal" to reflect multi-device support

### BREAKING CHANGES

#### Environment Variables
- `TILT_MOCK` → `SCANNER_MOCK`
- `TILT_FILES` → `SCANNER_FILES_PATH`
- `TILT_RELAY` → `SCANNER_RELAY_HOST`

#### File Paths
- Database file renamed: `tiltui.db` → `fermentation.db`
- Log file renamed: `tiltui.log` → `brewsignal.log`

#### System Service
- Systemd service renamed: `tiltui.service` → `brewsignal.service`
- Service users must reinstall/rename service files

#### Migration Notes
- Update environment variables in your deployment configuration
- Rename database file: `mv tiltui.db fermentation.db`
- Reinstall systemd service with new name
- Update any automation/scripts referencing old names

## [1.3.0] - 2025-11-29

### Added
- **Multi-Hydrometer Support** - Universal ingest layer for multiple device types
- **iSpindel Support** - HTTP POST endpoint for iSpindel WiFi hydrometers
- **GravityMon Support** - Extended iSpindel format with pre-filtered readings
- **Device Registry** - Unified device management for all hydrometer types
- **Device API** - CRUD endpoints for device management (`/api/devices`)
- **Polynomial Calibration** - Angle-to-gravity calibration for iSpindel-style devices
- **Unit Conversion** - Automatic Plato↔SG and Celsius↔Fahrenheit conversion

### Technical
- New `backend/ingest/` module with adapter pattern for device formats
- `HydrometerReading` dataclass for universal reading representation
- `IngestManager` service for reading pipeline (parse → calibrate → store → broadcast)
- Database migration adds `devices` table and new columns to `readings`
- Non-destructive migration preserves existing Tilt data
- 114 backend tests with full coverage of new ingest layer

### API Endpoints
- `POST /api/ingest/generic` - Auto-detect device format
- `POST /api/ingest/ispindel` - iSpindel HTTP endpoint
- `POST /api/ingest/gravitymon` - GravityMon HTTP endpoint
- `GET/POST/PUT/DELETE /api/devices` - Device management
- `GET/PUT /api/devices/{id}/calibration` - Device calibration data

## [1.2.1] - 2025-11-28

### Fixed
- **Chart Refresh Spam** - Charts no longer refresh constantly with BLE events
- Added 30-second minimum throttle between automatic data fetches
- User actions (time range, refresh setting, retry) still respond immediately

## [1.2.0] - 2025-11-28

### Changed
- **Compact Dashboard Layout** - Moved room ambient and weather forecast from large cards to compact top bar indicators
- Weather indicator shows today's forecast with expandable 5-day dropdown on click
- Ambient temperature/humidity now displays inline in navigation bar

### Technical
- New `weather.svelte.ts` store for centralized weather/alerts state management

## [1.1.0] - 2025-11-28

### Added
- **Home Assistant Integration** - Connect to Home Assistant for ambient temperature/humidity display
- **Temperature Control** - Automatic heater control via HA switch entity with hysteresis
- **Manual Override** - Force heater on/off for 1 hour, bypassing automatic control
- **Weather Forecast Display** - 5-day forecast from HA weather entity on dashboard
- **Predictive Weather Alerts** - Warnings when forecast temps may affect fermentation
- **Chart Timezone Support** - X-axis now respects system timezone setting

### Fixed
- HA client reinitialization when config changes
- Immediate heater action on manual override
- Timezone-aware datetime consistency throughout backend

## [1.0.1] - 2025-11-28

### Added
- Reading smoothing with configurable sample count (System settings)
- Chart smoothing applies moving average to SG and temperature data

### Fixed
- Temperature chart axis now uses minimum 10-degree range to reduce visual noise
- Settings validation and persistence (#8)
- Timezone selection persistence (#7)
- Beer name editing from dashboard (#2)

## [1.0.0] - 2025-11-28

### Added
- Real-time Tilt hydrometer monitoring dashboard
- BLE scanning using Bleak library for Tilt device detection
- WebSocket-based live updates to frontend
- SG and temperature calibration with linear interpolation
- Calibration point management (add, view, clear)
- Historical readings storage with SQLite/SQLAlchemy async
- CSV export of all readings
- Automatic data cleanup (30-day retention)
- Multi-mode scanner support:
  - BLE mode (production): Direct Bluetooth scanning
  - Mock mode: Simulated readings for development
  - File mode: Read from TiltPi JSON files
  - Relay mode: Fetch from remote TiltPi
- Systemd service for Raspberry Pi deployment
- Svelte frontend with responsive design
- REST API for tilts, readings, calibration, and system info

### Technical
- FastAPI backend with async SQLAlchemy 2.1
- Bleak BLE library with beacontools for iBeacon parsing
- SQLite database with automatic migrations
- WebSocket manager for real-time client updates
