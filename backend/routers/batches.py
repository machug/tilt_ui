"""Batch API endpoints."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models import (
    Batch,
    BatchCreate,
    BatchProgressResponse,
    BatchResponse,
    BatchUpdate,
    Reading,
    Recipe,
)
from ..state import latest_readings

router = APIRouter(prefix="/api/batches", tags=["batches"])


@router.get("", response_model=list[BatchResponse])
async def list_batches(
    status: Optional[str] = Query(None, description="Filter by status"),
    device_id: Optional[str] = Query(None, description="Filter by device"),
    include_deleted: bool = Query(False, description="Include soft-deleted batches"),
    deleted_only: bool = Query(False, description="Show only deleted batches (for maintenance)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List batches with optional filters. By default excludes deleted batches."""
    query = (
        select(Batch)
        .options(selectinload(Batch.recipe).selectinload(Recipe.style))
        .order_by(Batch.created_at.desc())
    )

    # Soft delete filter (default: hide deleted)
    if deleted_only:
        query = query.where(Batch.deleted_at.is_not(None))
    elif not include_deleted:
        query = query.where(Batch.deleted_at.is_(None))

    if status:
        query = query.where(Batch.status == status)
    if device_id:
        query = query.where(Batch.device_id == device_id)

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/active", response_model=list[BatchResponse])
async def list_active_batches(db: AsyncSession = Depends(get_db)):
    """Active batches: planning or fermenting status, not deleted."""
    query = (
        select(Batch)
        .options(selectinload(Batch.recipe).selectinload(Recipe.style))
        .where(
            Batch.deleted_at.is_(None),
            Batch.status.in_(["planning", "fermenting"])
        )
        .order_by(Batch.created_at.desc())
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/completed", response_model=list[BatchResponse])
async def list_completed_batches(db: AsyncSession = Depends(get_db)):
    """Historical batches: completed or conditioning, not deleted."""
    query = (
        select(Batch)
        .options(selectinload(Batch.recipe).selectinload(Recipe.style))
        .where(
            Batch.deleted_at.is_(None),
            Batch.status.in_(["completed", "conditioning"])
        )
        .order_by(Batch.updated_at.desc())
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{batch_id}", response_model=BatchResponse)
async def get_batch(batch_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific batch by ID."""
    query = (
        select(Batch)
        .options(selectinload(Batch.recipe).selectinload(Recipe.style))
        .where(Batch.id == batch_id)
    )
    result = await db.execute(query)
    batch = result.scalar_one_or_none()

    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


@router.post("", response_model=BatchResponse, status_code=201)
async def create_batch(
    batch: BatchCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new batch."""
    # Check for heater entity conflicts if a heater is specified
    if batch.heater_entity_id:
        conflict_result = await db.execute(
            select(Batch).where(
                Batch.status == "fermenting",
                Batch.heater_entity_id == batch.heater_entity_id,
            )
        )
        conflicting_batch = conflict_result.scalar_one_or_none()
        if conflicting_batch:
            raise HTTPException(
                status_code=400,
                detail=f"Heater entity '{batch.heater_entity_id}' is already in use by fermenting batch '{conflicting_batch.name}' (ID: {conflicting_batch.id}). Each heater can only control one fermenting batch at a time."
            )

    # Check for device_id conflicts if a device is specified and status is fermenting
    if batch.device_id and batch.status == "fermenting":
        conflict_result = await db.execute(
            select(Batch).where(
                Batch.status == "fermenting",
                Batch.device_id == batch.device_id,
            )
        )
        conflicting_batch = conflict_result.scalar_one_or_none()
        if conflicting_batch:
            raise HTTPException(
                status_code=400,
                detail=f"Device (Tilt) '{batch.device_id}' is already assigned to fermenting batch '{conflicting_batch.name}' (ID: {conflicting_batch.id}). Each device can only track one fermenting batch at a time."
            )

    # Get next batch number
    result = await db.execute(select(func.max(Batch.batch_number)))
    max_num = result.scalar() or 0

    # Get recipe name for batch name default
    batch_name = batch.name
    if batch.recipe_id and not batch_name:
        recipe = await db.get(Recipe, batch.recipe_id)
        if recipe:
            batch_name = recipe.name

    db_batch = Batch(
        recipe_id=batch.recipe_id,
        device_id=batch.device_id,
        batch_number=max_num + 1,
        name=batch_name,
        status=batch.status,
        brew_date=batch.brew_date,
        measured_og=batch.measured_og,
        notes=batch.notes,
        heater_entity_id=batch.heater_entity_id,
        temp_target=batch.temp_target,
        temp_hysteresis=batch.temp_hysteresis,
    )

    # Auto-set start_time if status is fermenting
    if batch.status == "fermenting":
        db_batch.start_time = datetime.now(timezone.utc)

    db.add(db_batch)
    await db.commit()
    await db.refresh(db_batch)

    # Load recipe relationship for response
    if db_batch.recipe_id:
        await db.refresh(db_batch, ["recipe"])

    return db_batch


@router.put("/{batch_id}", response_model=BatchResponse)
async def update_batch(
    batch_id: int,
    update: BatchUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a batch."""
    batch = await db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    # Check for heater entity conflicts if changing heater and batch is/will be fermenting
    new_status = update.status if update.status is not None else batch.status
    new_heater = update.heater_entity_id if update.heater_entity_id is not None else batch.heater_entity_id
    new_device_id = update.device_id if update.device_id is not None else batch.device_id

    if new_heater and new_status == "fermenting":
        # Only check for conflicts if the heater entity is actually changing
        if update.heater_entity_id is not None and update.heater_entity_id != batch.heater_entity_id:
            conflict_result = await db.execute(
                select(Batch).where(
                    Batch.status == "fermenting",
                    Batch.heater_entity_id == new_heater,
                    Batch.id != batch_id,
                )
            )
            conflicting_batch = conflict_result.scalar_one_or_none()
            if conflicting_batch:
                raise HTTPException(
                    status_code=400,
                    detail=f"Heater entity '{new_heater}' is already in use by fermenting batch '{conflicting_batch.name}' (ID: {conflicting_batch.id}). Each heater can only control one fermenting batch at a time."
                )

    # Check for device_id conflicts if changing device and batch is/will be fermenting
    if new_device_id and new_status == "fermenting":
        # Only check for conflicts if the device_id is actually changing
        if update.device_id is not None and update.device_id != batch.device_id:
            conflict_result = await db.execute(
                select(Batch).where(
                    Batch.status == "fermenting",
                    Batch.device_id == new_device_id,
                    Batch.id != batch_id,
                )
            )
            conflicting_batch = conflict_result.scalar_one_or_none()
            if conflicting_batch:
                raise HTTPException(
                    status_code=400,
                    detail=f"Device (Tilt) '{new_device_id}' is already assigned to fermenting batch '{conflicting_batch.name}' (ID: {conflicting_batch.id}). Each device can only track one fermenting batch at a time."
                )

    # Update fields if provided
    if update.recipe_id is not None:
        batch.recipe_id = update.recipe_id
    if update.name is not None:
        batch.name = update.name
    if update.status is not None:
        old_status = batch.status
        batch.status = update.status
        # Auto-set timestamps on status change
        if update.status == "fermenting" and old_status != "fermenting":
            batch.start_time = datetime.now(timezone.utc)
        elif update.status in ["conditioning", "completed"] and old_status == "fermenting":
            batch.end_time = datetime.now(timezone.utc)

        # Clean up runtime state when batch leaves fermenting status
        if old_status == "fermenting" and update.status != "fermenting":
            from ..temp_controller import cleanup_batch_state
            cleanup_batch_state(batch_id)
    if update.device_id is not None:
        batch.device_id = update.device_id
    if update.brew_date is not None:
        batch.brew_date = update.brew_date
    if update.start_time is not None:
        batch.start_time = update.start_time
    if update.end_time is not None:
        batch.end_time = update.end_time
    if update.measured_og is not None:
        batch.measured_og = update.measured_og
    if update.measured_fg is not None:
        batch.measured_fg = update.measured_fg
        # Calculate ABV and attenuation when FG is set
        if batch.measured_og:
            batch.measured_abv = (batch.measured_og - update.measured_fg) * 131.25
            batch.measured_attenuation = ((batch.measured_og - update.measured_fg) / (batch.measured_og - 1.0)) * 100
    if update.notes is not None:
        batch.notes = update.notes
    # Temperature control fields
    if update.heater_entity_id is not None:
        batch.heater_entity_id = update.heater_entity_id
    if update.temp_target is not None:
        batch.temp_target = update.temp_target
    if update.temp_hysteresis is not None:
        batch.temp_hysteresis = update.temp_hysteresis

    await db.commit()
    await db.refresh(batch)

    # Load recipe relationship for response
    if batch.recipe_id:
        await db.refresh(batch, ["recipe"])

    return batch


@router.delete("/{batch_id}")
async def delete_batch(batch_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a batch."""
    batch = await db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    await db.delete(batch)
    await db.commit()
    return {"status": "deleted"}


@router.get("/{batch_id}/progress", response_model=BatchProgressResponse)
async def get_batch_progress(batch_id: int, db: AsyncSession = Depends(get_db)):
    """Get fermentation progress for a batch."""
    # Get batch with recipe
    query = (
        select(Batch)
        .options(selectinload(Batch.recipe).selectinload(Recipe.style))
        .where(Batch.id == batch_id)
    )
    result = await db.execute(query)
    batch = result.scalar_one_or_none()

    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    # Get current SG and temperature from latest reading
    # Temperature is in Fahrenheit (from Tilt device)
    # Frontend will convert based on user preference
    current_sg = None
    current_temp = None
    if batch.device_id and batch.device_id in latest_readings:
        reading = latest_readings[batch.device_id]
        current_sg = reading.get("sg")
        current_temp = reading.get("temp")

    # Calculate targets from recipe
    targets = {}
    if batch.recipe:
        targets = {
            "og": batch.recipe.og_target,
            "fg": batch.recipe.fg_target,
            "attenuation": None,
            "abv": batch.recipe.abv_target,
        }
        if batch.recipe.og_target and batch.recipe.fg_target:
            targets["attenuation"] = round(
                ((batch.recipe.og_target - batch.recipe.fg_target) / (batch.recipe.og_target - 1.0)) * 100, 1
            )

    # Calculate measured values
    measured = {
        "og": batch.measured_og,
        "current_sg": current_sg,
        "attenuation": None,
        "abv": None,
    }
    if batch.measured_og and current_sg:
        measured["attenuation"] = round(
            ((batch.measured_og - current_sg) / (batch.measured_og - 1.0)) * 100, 1
        )
        measured["abv"] = round((batch.measured_og - current_sg) * 131.25, 1)

    # Calculate progress
    progress = {
        "percent_complete": None,
        "sg_remaining": None,
        "estimated_days_remaining": None,
    }
    og = batch.measured_og or (targets.get("og") if targets else None)
    fg = targets.get("fg") if targets else None
    if og and fg and current_sg:
        total_drop = og - fg
        current_drop = og - current_sg
        if total_drop > 0:
            progress["percent_complete"] = round(min(100, (current_drop / total_drop) * 100), 1)
            progress["sg_remaining"] = round(current_sg - fg, 4)

    # Temperature status
    temperature = {
        "current": current_temp,
        "yeast_min": batch.recipe.yeast_temp_min if batch.recipe else None,
        "yeast_max": batch.recipe.yeast_temp_max if batch.recipe else None,
        "status": "unknown",
    }
    if current_temp and batch.recipe:
        ymin = batch.recipe.yeast_temp_min
        ymax = batch.recipe.yeast_temp_max
        if ymin and ymax:
            if ymin <= current_temp <= ymax:
                temperature["status"] = "in_range"
            elif current_temp < ymin:
                temperature["status"] = "too_cold"
            else:
                temperature["status"] = "too_hot"

    return BatchProgressResponse(
        batch_id=batch.id,
        recipe_name=batch.recipe.name if batch.recipe else batch.name,
        status=batch.status,
        targets=targets,
        measured=measured,
        progress=progress,
        temperature=temperature,
    )
