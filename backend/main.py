import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Configure logging to show INFO level
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Imports after logging configuration
from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.responses import FileResponse, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from sqlalchemy import select, desc  # noqa: E402

from . import models  # noqa: E402, F401 - Import models so SQLAlchemy sees them
from .database import async_session_factory, init_db  # noqa: E402
from .models import Reading, Tilt, serialize_datetime_to_utc  # noqa: E402
from .routers import alerts, ambient, batches, config, control, devices, ha, ingest, maintenance, recipes, system, tilts  # noqa: E402
from .routers.config import get_config_value  # noqa: E402
from .ambient_poller import start_ambient_poller, stop_ambient_poller  # noqa: E402
from .temp_controller import start_temp_controller, stop_temp_controller  # noqa: E402
from .cleanup import CleanupService  # noqa: E402
from .scanner import TiltReading, TiltScanner  # noqa: E402
from .services.calibration import calibration_service  # noqa: E402
from .services.batch_linker import link_reading_to_batch  # noqa: E402
from .services.smoothing import smoothing_service  # noqa: E402
from .state import latest_readings  # noqa: E402
from .websocket import manager  # noqa: E402
import time  # noqa: E402

# Global scanner instance
scanner: Optional[TiltScanner] = None
scanner_task: Optional[asyncio.Task] = None

# Config cache for BLE reading handler (avoid DB query on every reading)
_smoothing_config_cache: tuple[bool, Optional[int]] = (False, None)
_smoothing_cache_time: float = 0
CONFIG_CACHE_TTL = 30  # seconds
cleanup_service: Optional[CleanupService] = None


async def calculate_time_since_batch_start(session, batch_id: Optional[int]) -> float:
    """Calculate hours since batch start.

    Args:
        session: Database session
        batch_id: Batch ID

    Returns:
        Hours since batch start_time (0.0 if no batch or no start_time)
    """
    if not batch_id:
        return 0.0

    batch = await session.get(models.Batch, batch_id)
    if not batch or not batch.start_time:
        return 0.0

    now = datetime.now(timezone.utc)
    start_time = batch.start_time

    # Handle naive datetime (database stores in UTC but without timezone info)
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)

    delta = now - start_time
    return delta.total_seconds() / 3600.0  # Convert to hours


async def handle_tilt_reading(reading: TiltReading):
    """Process a new Tilt reading: update DB and broadcast to WebSocket clients."""
    async with async_session_factory() as session:
        # Upsert Tilt record (always track detected devices)
        tilt = await session.get(Tilt, reading.id)
        if not tilt:
            tilt = Tilt(
                id=reading.id,
                color=reading.color,
                mac=reading.mac,
                beer_name="Untitled",
                paired=False,  # New devices start unpaired
            )
            session.add(tilt)

        tilt.last_seen = datetime.now(timezone.utc)
        tilt.mac = reading.mac

        # Convert Tilt's Fahrenheit to Celsius immediately
        temp_raw_c = (reading.temp_f - 32) * 5.0 / 9.0

        # Apply calibration in Celsius
        sg_calibrated, temp_calibrated_c = await calibration_service.calibrate_reading(
            session, reading.id, reading.sg, temp_raw_c
        )

        # Validate reading for outliers (physical impossibility check)
        # Valid SG range: 0.500-1.200 (beer is typically 1.000-1.120)
        # Valid temp range: 0-100°C (freezing to boiling)
        # IMPORTANT: Validate BEFORE smoothing to prevent invalid readings from polluting the moving average buffer
        status = "valid"
        if not (0.500 <= sg_calibrated <= 1.200):
            status = "invalid"
            logging.warning(
                f"Outlier SG detected: {sg_calibrated:.4f} (valid: 0.500-1.200) for device {reading.id}"
            )
        elif not (0.0 <= temp_calibrated_c <= 100.0):
            status = "invalid"
            logging.warning(
                f"Outlier temperature detected: {temp_calibrated_c:.1f}°C (valid: 0-100) for device {reading.id}"
            )

        # Apply smoothing if enabled (only for valid readings)
        if status == "valid":
            global _smoothing_config_cache, _smoothing_cache_time
            now = time.monotonic()

            # Refresh cache if expired
            if now - _smoothing_cache_time > CONFIG_CACHE_TTL:
                smoothing_enabled = await get_config_value(session, "smoothing_enabled")
                smoothing_samples = await get_config_value(session, "smoothing_samples")
                _smoothing_config_cache = (smoothing_enabled or False, smoothing_samples)
                _smoothing_cache_time = now
            else:
                smoothing_enabled, smoothing_samples = _smoothing_config_cache

            if smoothing_enabled and smoothing_samples and smoothing_samples > 1:
                sg_calibrated, temp_calibrated_c = await smoothing_service.smooth_reading(
                    session, reading.id, sg_calibrated, temp_calibrated_c, smoothing_samples
                )

        # Only store reading if device is paired
        if tilt.paired:
            # Device ID for Tilts is the same as tilt_id (e.g., "tilt-red")
            device_id = reading.id

            # Link to active batch if one exists for this device
            batch_id = await link_reading_to_batch(session, device_id)

            # Store reading in DB
            db_reading = Reading(
                tilt_id=reading.id,
                device_id=device_id,
                batch_id=batch_id,
                sg_raw=reading.sg,
                sg_calibrated=sg_calibrated,
                temp_raw=temp_raw_c,
                temp_calibrated=temp_calibrated_c,
                rssi=reading.rssi,
                status=status,  # Mark as valid or invalid
            )
            session.add(db_reading)

        await session.commit()

        # Build reading data for WebSocket broadcast (always broadcast)
        # Temperatures are in Celsius (converted from Tilt's Fahrenheit)
        # Frontend will convert based on user preference
        reading_data = {
            "id": reading.id,
            "color": reading.color,
            "beer_name": tilt.beer_name,
            "original_gravity": tilt.original_gravity,
            "sg": sg_calibrated,
            "sg_raw": reading.sg,
            "temp": temp_calibrated_c,
            "temp_raw": temp_raw_c,
            "rssi": reading.rssi,
            "last_seen": serialize_datetime_to_utc(datetime.now(timezone.utc)),
            "paired": tilt.paired,  # Include pairing status
        }

        # Update in-memory cache
        latest_readings[reading.id] = reading_data

        # Broadcast to all WebSocket clients
        await manager.broadcast(reading_data)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scanner, scanner_task, cleanup_service

    # Startup
    print("Starting BrewSignal...")
    await init_db()
    print("Database initialized")

    # Start scanner
    scanner = TiltScanner(on_reading=handle_tilt_reading)
    scanner_task = asyncio.create_task(scanner.start())
    print("Scanner started")

    # Start cleanup service (30-day retention, hourly check)
    cleanup_service = CleanupService(retention_days=30, interval_hours=1)
    await cleanup_service.start()

    # Start ambient poller for Home Assistant integration
    start_ambient_poller()
    print("Ambient poller started")

    # Start temperature controller for HA-based temperature control
    start_temp_controller()
    print("Temperature controller started")

    yield

    # Shutdown
    print("Shutting down BrewSignal...")
    stop_temp_controller()
    stop_ambient_poller()
    if cleanup_service:
        await cleanup_service.stop()
    if scanner:
        await scanner.stop()
    if scanner_task:
        scanner_task.cancel()
        try:
            await scanner_task
        except asyncio.CancelledError:
            pass
    print("Scanner stopped")


from .routers.system import VERSION  # noqa: E402
app = FastAPI(title="BrewSignal", version=VERSION, lifespan=lifespan)

# Register routers
app.include_router(tilts.router)
app.include_router(devices.router)
app.include_router(config.router)
app.include_router(system.router)
app.include_router(ambient.router)
app.include_router(ha.router)
app.include_router(control.router)
app.include_router(alerts.router)
app.include_router(ingest.router)
app.include_router(recipes.router)
app.include_router(batches.router)
app.include_router(maintenance.router)


@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "websocket_connections": manager.connection_count,
        "active_tilts": len(latest_readings),
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    # Send current state of all Tilts on connect
    for reading in latest_readings.values():
        await websocket.send_json(reading)

    try:
        while True:
            # Keep connection alive, ignore any messages from client
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/log.csv")
async def download_log():
    """Download all readings as CSV file."""
    import csv
    import io

    async def generate_csv():
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            "timestamp", "tilt_id", "color", "beer_name",
            "sg_raw", "sg_calibrated", "temp_raw", "temp_calibrated", "rssi"
        ])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        # Stream readings in batches
        async with async_session_factory() as session:
            # Get all tilts for beer_name lookup
            tilts_result = await session.execute(select(Tilt))
            tilts_map = {t.id: t for t in tilts_result.scalars()}

            # Get readings ordered by timestamp
            result = await session.execute(
                select(Reading).order_by(Reading.timestamp)
            )
            for reading in result.scalars():
                tilt = tilts_map.get(reading.tilt_id)
                writer.writerow([
                    serialize_datetime_to_utc(reading.timestamp) if reading.timestamp else "",
                    reading.tilt_id,
                    tilt.color if tilt else "",
                    tilt.beer_name if tilt else "",
                    reading.sg_raw,
                    reading.sg_calibrated,
                    reading.temp_raw,
                    reading.temp_calibrated,
                    reading.rssi
                ])
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)

    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=tilt_readings.csv"}
    )


@app.get("/api/stats")
async def get_stats():
    """Get database statistics for the logging page."""
    async with async_session_factory() as session:
        # Count total readings
        from sqlalchemy import func
        readings_count = await session.execute(
            select(func.count()).select_from(Reading)
        )
        total_readings = int(readings_count.scalar() or 0)

        # Get oldest and newest reading timestamps
        oldest = await session.execute(
            select(Reading.timestamp).order_by(Reading.timestamp).limit(1)
        )
        oldest_time = oldest.scalar()

        newest = await session.execute(
            select(Reading.timestamp).order_by(desc(Reading.timestamp)).limit(1)
        )
        newest_time = newest.scalar()

        # Estimate size (rough: ~100 bytes per reading)
        estimated_size_bytes = total_readings * 100

        return {
            "total_readings": total_readings,
            "oldest_reading": serialize_datetime_to_utc(oldest_time) if oldest_time else None,
            "newest_reading": serialize_datetime_to_utc(newest_time) if newest_time else None,
            "estimated_size_bytes": estimated_size_bytes,
        }


# SPA page routes - serve pre-rendered HTML files
static_dir = Path(__file__).parent / "static"


@app.get("/", response_class=FileResponse)
async def serve_index():
    """Serve the main dashboard page."""
    return FileResponse(static_dir / "index.html")


@app.get("/logging", response_class=FileResponse)
async def serve_logging():
    """Serve the logging page."""
    return FileResponse(static_dir / "logging.html")


@app.get("/calibration", response_class=FileResponse)
async def serve_calibration():
    """Serve the calibration page."""
    return FileResponse(static_dir / "calibration.html")


@app.get("/system", response_class=FileResponse)
async def serve_system():
    """Serve the system page."""
    return FileResponse(static_dir / "system.html")


@app.get("/system/{path:path}", response_class=FileResponse)
async def serve_system_subpages(path: str):
    """Serve system subpages (maintenance, etc.) - SPA handles routing."""
    # Try to find a prerendered HTML file for this path
    # e.g., /system/maintenance -> static/system/maintenance.html
    html_path = static_dir / "system" / f"{path}.html"
    if html_path.exists():
        return FileResponse(html_path)

    # Check if path is a directory with index.html
    index_path = static_dir / "system" / path / "index.html"
    if index_path.exists():
        return FileResponse(index_path)

    # Fall back to index.html for dynamic routes
    return FileResponse(static_dir / "index.html")


@app.get("/devices", response_class=FileResponse)
async def serve_devices():
    """Serve the devices page."""
    return FileResponse(static_dir / "devices.html")


@app.get("/batches", response_class=FileResponse)
async def serve_batches():
    """Serve the batches page."""
    return FileResponse(static_dir / "batches.html")


@app.get("/recipes", response_class=FileResponse)
async def serve_recipes():
    """Serve the recipes page."""
    return FileResponse(static_dir / "recipes.html")


@app.get("/batches/{path:path}", response_class=FileResponse)
async def serve_batches_subpages(path: str):
    """Serve batches subpages (detail, new, etc.) - SPA handles routing.

    Tries to find the matching prerendered HTML file first,
    falls back to index.html for dynamic routes (uses absolute paths).
    """
    # Try to find a prerendered HTML file for this path
    # e.g., /batches/new -> static/batches/new.html
    html_path = static_dir / "batches" / f"{path}.html"
    if html_path.exists():
        return FileResponse(html_path)

    # Check if path is a directory with index.html
    # e.g., /batches/new/ -> static/batches/new/index.html
    index_path = static_dir / "batches" / path / "index.html"
    if index_path.exists():
        return FileResponse(index_path)

    # Fall back to index.html for dynamic routes (e.g., /batches/123)
    # index.html uses absolute paths which work for nested routes
    return FileResponse(static_dir / "index.html")


@app.get("/recipes/{path:path}", response_class=FileResponse)
async def serve_recipes_subpages(path: str):
    """Serve recipes subpages (detail, import, etc.) - SPA handles routing.

    Tries to find the matching prerendered HTML file first,
    falls back to index.html for dynamic routes (uses absolute paths).
    """
    # Try to find a prerendered HTML file for this path
    # e.g., /recipes/import -> static/recipes/import.html
    html_path = static_dir / "recipes" / f"{path}.html"
    if html_path.exists():
        return FileResponse(html_path)

    # Check if path is a directory with index.html
    # e.g., /recipes/import/ -> static/recipes/import/index.html
    index_path = static_dir / "recipes" / path / "index.html"
    if index_path.exists():
        return FileResponse(index_path)

    # Fall back to index.html for dynamic routes (e.g., /recipes/123)
    # index.html uses absolute paths which work for nested routes
    return FileResponse(static_dir / "index.html")


@app.get("/favicon.png", response_class=FileResponse)
async def serve_favicon():
    """Serve the favicon."""
    return FileResponse(static_dir / "favicon.png")


# Mount static files (Svelte build output)
# Mount _app separately for Svelte's hashed assets, keeping /docs and /redoc accessible
if static_dir.exists():
    app_assets = static_dir / "_app"
    if app_assets.exists():
        app.mount("/_app", StaticFiles(directory=app_assets), name="app_assets")
