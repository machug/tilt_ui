import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Configure logging to show INFO level
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, desc

from . import models  # noqa: F401 - Import models so SQLAlchemy sees them
from .database import async_session_factory, init_db
from .models import Reading, Tilt
from .routers import alerts, ambient, batches, config, control, devices, ha, ingest, recipes, system, tilts
from .ambient_poller import start_ambient_poller, stop_ambient_poller
from .temp_controller import start_temp_controller, stop_temp_controller
from .cleanup import CleanupService
from .scanner import TiltReading, TiltScanner
from .services.calibration import calibration_service
from .services.batch_linker import link_reading_to_batch
from .state import latest_readings
from .websocket import manager

# Global scanner instance
scanner: Optional[TiltScanner] = None
scanner_task: Optional[asyncio.Task] = None
cleanup_service: Optional[CleanupService] = None


async def handle_tilt_reading(reading: TiltReading):
    """Process a new Tilt reading: update DB and broadcast to WebSocket clients."""
    async with async_session_factory() as session:
        # Upsert Tilt record
        tilt = await session.get(Tilt, reading.id)
        if not tilt:
            tilt = Tilt(
                id=reading.id,
                color=reading.color,
                mac=reading.mac,
                beer_name="Untitled",
            )
            session.add(tilt)

        tilt.last_seen = datetime.now(timezone.utc)
        tilt.mac = reading.mac

        # Apply calibration
        sg_calibrated, temp_calibrated = await calibration_service.calibrate_reading(
            session, reading.id, reading.sg, reading.temp_f
        )

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
            temp_raw=reading.temp_f,
            temp_calibrated=temp_calibrated,
            rssi=reading.rssi,
        )
        session.add(db_reading)
        await session.commit()

        # Build reading data for WebSocket broadcast
        reading_data = {
            "id": reading.id,
            "color": reading.color,
            "beer_name": tilt.beer_name,
            "original_gravity": tilt.original_gravity,
            "sg": sg_calibrated,
            "sg_raw": reading.sg,
            "temp": temp_calibrated,
            "temp_raw": reading.temp_f,
            "rssi": reading.rssi,
            "last_seen": datetime.now(timezone.utc).isoformat(),
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


from .routers.system import VERSION
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
                    reading.timestamp.isoformat() if reading.timestamp else "",
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
            "oldest_reading": oldest_time.isoformat() if oldest_time else None,
            "newest_reading": newest_time.isoformat() if newest_time else None,
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
