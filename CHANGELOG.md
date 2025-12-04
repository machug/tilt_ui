# Changelog

All notable changes to BrewSignal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Batch Lifecycle Management** - Complete soft delete and data maintenance system
  - Tab-based navigation on batch list page (Active, Completed, Deleted)
  - Soft delete and restore functionality for batches
  - Hard delete option with cascade to readings
  - Data maintenance page for orphaned reading cleanup
  - Orphaned data detection and reporting
  - Preview-first cleanup pattern for safety
  - Convenience endpoints: `/api/batches/active` and `/api/batches/completed`
  - Maintenance API endpoints for data integrity
- **Chart Crosshair Tooltips** (#55) - Display exact reading values at crosshair position
  - Shows timestamp, gravity (with proper unit formatting), wort temperature, ambient temperature, and trend line values
  - Floating tooltip with semi-transparent background and backdrop blur for readability
  - No more guessing values from axis labels
- **Reading Smoothing at Source** (#55) - Moving average filter applied during BLE reading ingestion
  - Uses existing `smoothing_enabled` and `smoothing_samples` config settings from System page
  - Applied after calibration but before storage for consistent smoothed data across all consumers
  - Per-device buffers maintain recent readings for window calculation
  - Smoothed values stored in database benefit charts, exports, and Home Assistant integration

### Changed
- Batch list page now uses tab navigation instead of status filter chips
- Removed "archived" status in favor of soft delete pattern
- Default batch list now excludes deleted batches
- Enhanced batch filtering with `include_deleted` and `deleted_only` query parameters

### Fixed
- **Chart Outlier Spikes** (#55) - Physically impossible readings no longer corrupt charts
  - Added validation for SG range (0.500-1.200) and temperature range (32-212°F)
  - Invalid readings marked with `status='invalid'` and filtered from all API responses
  - Historical outliers cleaned up via migration (83 outliers marked invalid)
  - Charts now only display validated readings

### Migration
- Added `deleted_at` column to batches table
- Existing "archived" batches automatically migrated to "completed" status

### Technical
- Created `SmoothingService` with moving average algorithm in `backend/services/smoothing.py`
- Added outlier validation in `backend/main.py` `handle_tilt_reading()` function
- Updated `backend/routers/tilts.py` to filter `status='valid'` readings in all queries
- Migration script `backend/migrations/mark_outliers_invalid.py` to clean historical data
- uPlot legend enabled with live updates and custom tooltip styling
- New `backend/routers/maintenance.py` router for orphaned data management
- Soft delete logic in `backend/routers/batches.py` with cascade support

### Code Review Fixes (PR #56)
- **Database Migration**: Added status column migration with index for query performance in `backend/database.py`
- **Validation Order**: Moved outlier validation BEFORE smoothing to prevent invalid readings from contaminating moving average buffer
- **HTTP Device Support**: Extended validation and smoothing to HTTP ingestion path (iSpindel/GravityMon) in `backend/services/ingest_manager.py`
- **Config Caching**: Implemented 30-second cache for smoothing config to reduce DB queries from every-reading to periodic refresh
- **Null Safety**: Fixed smoothing service query to use `is not None` check instead of truthiness to handle edge cases with zero values
- **Buffer Cleanup**: Added automatic cleanup of inactive device buffers (1-hour TTL) to prevent memory growth
- **Data Migration**: Integrated historical outlier marking into `init_db()` for automatic cleanup on deployment

## [2.3.2] - 2025-12-03

### Added
- Modular card-based architecture for batch detail page
- Live readings card with calibrated and raw values
- Signal strength indicator with quality labels and dBm values
- Real-time ABV calculation during active fermentation: `(OG - Current SG) × 131.25`
- Real-time attenuation calculation during fermentation: `((OG - Current SG) / (OG - 1.000)) × 100%`
- Enhanced device status card with signal diagnostics
- Fermentation progress card with visual progress bar
- Clear visual distinction between live/in-progress and final values

### Changed
- Refactored batch detail page sections into reusable card components
- Improved responsive layout with better mobile experience
- FG now shows current gravity during fermentation (instead of "--")
- ABV and attenuation display live values during active fermentation

### Fixed
- Missing aria-label on delete button for accessibility
- Batch detail page now shows same diagnostic data as dashboard

### Technical
- Created 7 new Svelte components in `src/lib/components/batch/`
- Maintained backward compatibility with existing batch data
- Architecture ready for future AI assistant features

## [2.3.1] - 2025-12-03

### Fixed
- **Timezone Display Bug** (#42) - Fixed "Last Seen" times showing incorrect values (e.g., "11h ago" when device is actively transmitting)
  - All datetime fields now serialize with explicit UTC timezone indicator ('Z' suffix) per RFC 3339
  - Prevents JavaScript from misinterpreting UTC timestamps as local time
  - Applied consistently across all API responses, WebSocket broadcasts, and CSV exports
  - Added `serialize_datetime_to_utc()` helper function with comprehensive test coverage

## [2.3.0] - 2025-12-02

### Added
- Recipe library UI for BeerXML import and management (#32)
  - Import page with drag-and-drop BeerXML file upload
  - Recipe list with search and filter
  - Recipe detail view with fermentation-focused layout
  - Laboratory notebook aesthetic with amber accents
  - Integration with batch creation (auto-fill from recipe)
  - Crimson Pro serif font for recipe names
  - JetBrains Mono for measurements
- Device pairing workflow - devices must be paired before logging readings (#35)
  - New `/devices` page for managing paired and unpaired devices
  - Pairing status indicators on dashboard
  - API endpoints for pairing/unpairing devices (`POST /api/tilts/{id}/pair`, `POST /api/tilts/{id}/unpair`)

### Changed
- Readings are only stored for paired devices
- Batch creation only shows paired devices in device selector
- New devices are unpaired by default

### Migration
- Existing devices will be marked as unpaired after upgrade
- Users must manually pair devices to resume reading storage

### Fixed
- Systemd service now points to `.venv` so installs run with the correct virtualenv
- Installer copies frontend assets alongside backend for local installs and builds the frontend during installation

## [2.2.0] - 2025-12-02

### Added
- **Per-Batch Heater Control** (#29) - Independent temperature control for multiple simultaneous fermentations
- Batch-specific heater entity configuration (switch or input_boolean)
- Batch-specific temperature targets and hysteresis settings
- Manual override controls (Force ON/OFF) per batch with configurable duration
- Real-time heater state display with visual indicators on batch detail pages
- Temperature control card shows current heater state, target, and hysteresis per batch

### Technical
- Per-batch control loop processes all fermenting batches independently
- In-memory state tracking (`_batch_heater_states`, `_batch_overrides`) with automatic cleanup
- Database constraints prevent heater entity and device conflicts between fermenting batches
- Minimum cycle time protection (5 minutes) prevents rapid heater cycling
- WebSocket broadcasts for real-time heater state updates
- Comprehensive validation tests for heater entity format and conflict detection

### API Endpoints
- `GET /api/control/batch/{batch_id}/status` - Get temperature control status for specific batch
- `POST /api/control/override` - Set manual override (requires `batch_id` parameter)
- `GET /api/control/heater-entities` - List available switch/input_boolean entities from Home Assistant

### Breaking Changes
- Global heater override endpoint now requires `batch_id` parameter (legacy global control deprecated)
- Temperature control now operates per-batch instead of globally

## [2.1.0] - Unreleased

### Added
- **RSSI Signal Filtering** (#6) - Filter weak Bluetooth signals below configurable threshold to reduce noise
- **Plato/Brix Gravity Units** (#3) - Display gravity as SG, Plato (°P), or Brix (°Bx) with unit toggle in System settings

### Technical
- RSSI filter uses cached config (30s TTL) to minimize DB queries during high-frequency BLE scanning
- Gravity unit conversion functions added to frontend config store

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
