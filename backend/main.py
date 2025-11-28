import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
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
from .routers import config, system, tilts
from .cleanup import CleanupService
from .scanner import TiltReading, TiltScanner
from .services.calibration import calibration_service
from .websocket import manager

# Global scanner instance
scanner: Optional[TiltScanner] = None
scanner_task: Optional[asyncio.Task] = None
cleanup_service: Optional[CleanupService] = None

# In-memory cache of latest readings per Tilt
latest_readings: dict[str, dict] = {}


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

        tilt.last_seen = datetime.utcnow()
        tilt.mac = reading.mac

        # Apply calibration
        sg_calibrated, temp_calibrated = await calibration_service.calibrate_reading(
            session, reading.id, reading.sg, reading.temp_f
        )

        # Store reading in DB
        db_reading = Reading(
            tilt_id=reading.id,
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
            "sg": sg_calibrated,
            "sg_raw": reading.sg,
            "temp": temp_calibrated,
            "temp_raw": reading.temp_f,
            "rssi": reading.rssi,
            "last_seen": datetime.utcnow().isoformat(),
        }

        # Update in-memory cache
        latest_readings[reading.id] = reading_data

        # Broadcast to all WebSocket clients
        await manager.broadcast(reading_data)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scanner, scanner_task, cleanup_service

    # Startup
    print("Starting Tilt UI...")
    await init_db()
    print("Database initialized")

    # Start scanner
    scanner = TiltScanner(on_reading=handle_tilt_reading)
    scanner_task = asyncio.create_task(scanner.start())
    print("Scanner started")

    # Start cleanup service (30-day retention, hourly check)
    cleanup_service = CleanupService(retention_days=30, interval_hours=1)
    await cleanup_service.start()

    yield

    # Shutdown
    print("Shutting down Tilt UI...")
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


app = FastAPI(title="Tilt UI", version="0.1.0", lifespan=lifespan)

# Register routers
app.include_router(tilts.router)
app.include_router(config.router)
app.include_router(system.router)


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


@app.get("/logging")
async def serve_logging():
    """Serve the logging page."""
    return FileResponse(static_dir / "logging.html")


@app.get("/calibration")
async def serve_calibration():
    """Serve the calibration page."""
    return FileResponse(static_dir / "calibration.html")


@app.get("/system")
async def serve_system():
    """Serve the system page."""
    return FileResponse(static_dir / "system.html")


# Mount static files (Svelte build output) - MUST be last
if static_dir.exists():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
