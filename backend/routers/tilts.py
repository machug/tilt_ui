"""Tilt hydrometer API endpoints."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from ..database import get_db
from ..models import (
    CalibrationPoint,
    CalibrationPointCreate,
    CalibrationPointResponse,
    Device,
    Reading,
    ReadingResponse,
    Tilt,
    TiltResponse,
    TiltUpdate,
)
from ..services.calibration import calibration_service
from ..state import latest_readings
from ..websocket import manager
from ..device_utils import create_tilt_device_record

router = APIRouter(prefix="/api/tilts", tags=["tilts"])


@router.get("", response_model=list[TiltResponse])
async def list_tilts(db: AsyncSession = Depends(get_db)):
    """List all detected Tilts."""
    result = await db.execute(select(Tilt).order_by(Tilt.color))
    return result.scalars().all()


@router.get("/{tilt_id}", response_model=TiltResponse)
async def get_tilt(tilt_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific Tilt by ID."""
    tilt = await db.get(Tilt, tilt_id)
    if not tilt:
        raise HTTPException(status_code=404, detail="Tilt not found")
    return tilt


@router.put("/{tilt_id}", response_model=TiltResponse)
async def update_tilt(
    tilt_id: str,
    update: TiltUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update Tilt properties (e.g., beer name)."""
    tilt = await db.get(Tilt, tilt_id)
    if not tilt:
        raise HTTPException(status_code=404, detail="Tilt not found")

    if update.beer_name is not None:
        tilt.beer_name = update.beer_name
    # Use is_field_set to allow explicitly setting OG to null
    if update.is_field_set("original_gravity"):
        tilt.original_gravity = update.original_gravity

    await db.commit()
    await db.refresh(tilt)

    # Update the in-memory cache and broadcast to WebSocket clients
    if tilt_id in latest_readings:
        if update.beer_name is not None:
            latest_readings[tilt_id]["beer_name"] = tilt.beer_name
        if update.is_field_set("original_gravity"):
            latest_readings[tilt_id]["original_gravity"] = tilt.original_gravity
        # Broadcast updated state to all connected clients
        await manager.broadcast(latest_readings[tilt_id])

    return tilt


@router.delete("/{tilt_id}")
async def delete_tilt(tilt_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a Tilt and all its readings."""
    tilt = await db.get(Tilt, tilt_id)
    if not tilt:
        raise HTTPException(status_code=404, detail="Tilt not found")

    await db.delete(tilt)
    await db.commit()
    return {"status": "deleted"}


@router.get("/{tilt_id}/readings", response_model=list[ReadingResponse])
async def get_readings(
    tilt_id: str,
    start: Optional[datetime] = Query(None, description="Start time (ISO format)"),
    end: Optional[datetime] = Query(None, description="End time (ISO format)"),
    limit: int = Query(1000, ge=1, le=10000, description="Max readings to return"),
    hours: Optional[int] = Query(None, ge=1, le=720, description="Last N hours of data"),
    db: AsyncSession = Depends(get_db),
):
    """Get historical readings for a Tilt.

    Use `hours` for quick time ranges, or `start`/`end` for custom ranges.
    Results are downsampled to return evenly-spaced readings across the time range.
    Default limit is 1000 readings.
    """
    # Verify Tilt exists
    tilt = await db.get(Tilt, tilt_id)
    if not tilt:
        raise HTTPException(status_code=404, detail="Tilt not found")

    query = select(Reading).where(
        Reading.tilt_id == tilt_id,
        Reading.status == "valid"  # Filter out outliers
    )

    # Apply time filters
    if hours:
        start = datetime.now(timezone.utc) - timedelta(hours=hours)
    if start:
        query = query.where(Reading.timestamp >= start)
    if end:
        query = query.where(Reading.timestamp <= end)

    # Get total count in the time range to determine downsampling
    from sqlalchemy import func
    count_query = select(func.count()).select_from(Reading).where(
        Reading.tilt_id == tilt_id,
        Reading.status == "valid"  # Only count valid readings
    )
    if start:
        count_query = count_query.where(Reading.timestamp >= start)
    if end:
        count_query = count_query.where(Reading.timestamp <= end)

    count_result = await db.execute(count_query)
    total_count = count_result.scalar() or 0

    # If total readings exceed limit, downsample using rowid modulo
    # This is much faster than ROW_NUMBER() on large datasets (~0.5s vs ~4s)
    # Rowid modulo works well since readings are inserted sequentially
    if total_count > limit:
        step = total_count // limit

        # Build WHERE clause for raw SQL
        where_parts = ["tilt_id = :tilt_id", "rowid % :step = 0", "status = 'valid'"]
        params = {"tilt_id": tilt_id, "step": step, "limit": limit}

        if start:
            where_parts.append("timestamp >= :start")
            params["start"] = start
        if end:
            where_parts.append("timestamp <= :end")
            params["end"] = end

        where_clause = " AND ".join(where_parts)

        # Use rowid modulo for fast sampling - avoids expensive window function scan
        sql = text(f"""
            SELECT * FROM readings
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT :limit
        """)

        result = await db.execute(sql, params)
        rows = result.fetchall()

        # Convert raw rows to Reading objects for Pydantic serialization
        readings = []
        for row in rows:
            # Map row to Reading model (exclude rn column)
            reading = Reading(
                id=row.id,
                device_id=row.device_id,
                device_type=row.device_type,
                tilt_id=row.tilt_id,
                timestamp=row.timestamp,
                sg_raw=row.sg_raw,
                sg_calibrated=row.sg_calibrated,
                temp_raw=row.temp_raw,
                temp_calibrated=row.temp_calibrated,
                rssi=row.rssi,
                battery_voltage=row.battery_voltage,
                battery_percent=row.battery_percent,
                angle=row.angle,
                source_protocol=row.source_protocol,
                status=row.status,
                is_pre_filtered=row.is_pre_filtered,
            )
            readings.append(reading)
        return readings
    else:
        # No downsampling needed
        query = query.order_by(desc(Reading.timestamp)).limit(limit)
        result = await db.execute(query)
        return result.scalars().all()


# Pairing endpoints
@router.post("/{tilt_id}/pair", response_model=TiltResponse)
async def pair_tilt(tilt_id: str, db: AsyncSession = Depends(get_db)):
    """Pair a Tilt device to enable reading storage."""
    tilt = await db.get(Tilt, tilt_id)
    if not tilt:
        raise HTTPException(status_code=404, detail="Tilt not found")

    paired_at = datetime.now(timezone.utc)

    # Update legacy Tilt table
    tilt.paired = True
    tilt.paired_at = paired_at

    # Also update Device table for universal device support
    device = await db.get(Device, tilt_id)
    if device:
        device.paired = True
        device.paired_at = paired_at
    else:
        # Create missing Device record to maintain data consistency
        logger.info(f"Creating Device record for Tilt {tilt_id} during pairing")
        device = create_tilt_device_record(
            device_id=tilt_id,
            color=tilt.color,
            mac=tilt.mac,
            last_seen=tilt.last_seen,
            paired=True,
            paired_at=paired_at,
        )
        db.add(device)

    await db.commit()
    await db.refresh(tilt)

    # Update in-memory cache
    if tilt_id in latest_readings:
        latest_readings[tilt_id]["paired"] = True
        await manager.broadcast(latest_readings[tilt_id])

    return tilt


@router.post("/{tilt_id}/unpair", response_model=TiltResponse)
async def unpair_tilt(tilt_id: str, db: AsyncSession = Depends(get_db)):
    """Unpair a Tilt device to stop reading storage."""
    tilt = await db.get(Tilt, tilt_id)
    if not tilt:
        raise HTTPException(status_code=404, detail="Tilt not found")

    # Update legacy Tilt table
    tilt.paired = False
    tilt.paired_at = None

    # Also update Device table for universal device support
    device = await db.get(Device, tilt_id)
    if device:
        device.paired = False
        device.paired_at = None
    else:
        # Create missing Device record to maintain data consistency
        logger.info(f"Creating Device record for Tilt {tilt_id} during unpairing")
        device = create_tilt_device_record(
            device_id=tilt_id,
            color=tilt.color,
            mac=tilt.mac,
            last_seen=tilt.last_seen,
            paired=False,
            paired_at=None,
        )
        db.add(device)

    await db.commit()
    await db.refresh(tilt)

    # Update in-memory cache
    if tilt_id in latest_readings:
        latest_readings[tilt_id]["paired"] = False
        await manager.broadcast(latest_readings[tilt_id])

    return tilt


# Calibration endpoints
@router.get("/{tilt_id}/calibration", response_model=list[CalibrationPointResponse])
async def get_calibration(tilt_id: str, db: AsyncSession = Depends(get_db)):
    """Get calibration points for a Tilt."""
    tilt = await db.get(Tilt, tilt_id)
    if not tilt:
        raise HTTPException(status_code=404, detail="Tilt not found")

    result = await db.execute(
        select(CalibrationPoint)
        .where(CalibrationPoint.tilt_id == tilt_id)
        .order_by(CalibrationPoint.type, CalibrationPoint.raw_value)
    )
    return result.scalars().all()


@router.post("/{tilt_id}/calibration", response_model=CalibrationPointResponse)
async def add_calibration_point(
    tilt_id: str,
    point: CalibrationPointCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a calibration point for a Tilt.

    If a point with the same (tilt_id, type, raw_value) exists, it will be updated.
    """
    tilt = await db.get(Tilt, tilt_id)
    if not tilt:
        raise HTTPException(status_code=404, detail="Tilt not found")

    if point.type not in ("sg", "temp"):
        raise HTTPException(status_code=400, detail="Type must be 'sg' or 'temp'")

    # Check for existing point (upsert)
    result = await db.execute(
        select(CalibrationPoint).where(
            CalibrationPoint.tilt_id == tilt_id,
            CalibrationPoint.type == point.type,
            CalibrationPoint.raw_value == point.raw_value,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.actual_value = point.actual_value
        cal_point = existing
    else:
        cal_point = CalibrationPoint(
            tilt_id=tilt_id,
            type=point.type,
            raw_value=point.raw_value,
            actual_value=point.actual_value,
        )
        db.add(cal_point)

    await db.commit()
    await db.refresh(cal_point)

    # Invalidate calibration cache so new points take effect immediately
    calibration_service.invalidate_cache(tilt_id)

    return cal_point


@router.delete("/{tilt_id}/calibration/{cal_type}")
async def clear_calibration(
    tilt_id: str,
    cal_type: str,
    db: AsyncSession = Depends(get_db),
):
    """Clear all calibration points of a specific type for a Tilt."""
    tilt = await db.get(Tilt, tilt_id)
    if not tilt:
        raise HTTPException(status_code=404, detail="Tilt not found")

    if cal_type not in ("sg", "temp"):
        raise HTTPException(status_code=400, detail="Type must be 'sg' or 'temp'")

    await db.execute(
        delete(CalibrationPoint).where(
            CalibrationPoint.tilt_id == tilt_id,
            CalibrationPoint.type == cal_type,
        )
    )
    await db.commit()

    # Invalidate calibration cache so cleared points take effect immediately
    calibration_service.invalidate_cache(tilt_id)

    return {"status": "cleared", "type": cal_type}
