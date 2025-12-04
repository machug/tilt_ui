"""Maintenance API endpoints for orphaned data cleanup."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Batch, Reading

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


# Pydantic Models
class OrphanedDataReport(BaseModel):
    """Report of orphaned readings linked to soft-deleted batches."""
    model_config = ConfigDict(from_attributes=True)

    orphaned_readings_count: int
    orphaned_readings: list[int]  # List of reading IDs
    batches_with_orphans: dict[int, int]  # batch_id -> count


class CleanupPreview(BaseModel):
    """Preview or result of cleanup operation."""
    model_config = ConfigDict(from_attributes=True)

    readings_to_delete: list[int]  # List of reading IDs
    total_count: int
    batch_breakdown: dict[int, int]  # batch_id -> count


class CleanupRequest(BaseModel):
    """Request to cleanup readings for deleted batches."""
    deleted_batch_ids: list[int]
    dry_run: bool = True


@router.get("/orphaned-data", response_model=OrphanedDataReport)
async def get_orphaned_data(db: AsyncSession = Depends(get_db)):
    """Find readings linked to soft-deleted batches.

    Returns:
        OrphanedDataReport with counts and details of orphaned readings
    """
    # Use JOIN instead of IN for better performance
    # Find all readings linked to soft-deleted batches in a single query
    orphaned_readings_query = (
        select(Reading.id, Reading.batch_id)
        .join(Batch, Reading.batch_id == Batch.id)
        .where(Batch.deleted_at.is_not(None))
    )
    orphaned_readings_result = await db.execute(orphaned_readings_query)
    orphaned_readings_rows = orphaned_readings_result.all()

    if not orphaned_readings_rows:
        # No orphaned readings found
        return OrphanedDataReport(
            orphaned_readings_count=0,
            orphaned_readings=[],
            batches_with_orphans={},
        )

    # Build response
    orphaned_reading_ids = [row[0] for row in orphaned_readings_rows]

    # Count readings per batch
    batches_with_orphans: dict[int, int] = {}
    for row in orphaned_readings_rows:
        batch_id = row[1]
        if batch_id is not None:
            batches_with_orphans[batch_id] = batches_with_orphans.get(batch_id, 0) + 1

    return OrphanedDataReport(
        orphaned_readings_count=len(orphaned_reading_ids),
        orphaned_readings=orphaned_reading_ids,
        batches_with_orphans=batches_with_orphans,
    )


@router.post("/cleanup-readings", response_model=CleanupPreview)
async def cleanup_orphaned_readings(
    request: CleanupRequest,
    db: AsyncSession = Depends(get_db),
):
    """Preview or execute cleanup of readings for deleted batches.

    Args:
        request: CleanupRequest with batch IDs and dry_run flag

    Returns:
        CleanupPreview showing what will be (or was) deleted

    Raises:
        HTTPException: If any batch ID is not actually deleted
    """
    if not request.deleted_batch_ids:
        return CleanupPreview(
            readings_to_delete=[],
            total_count=0,
            batch_breakdown={},
        )

    # Verify all specified batches are actually soft-deleted
    batches_query = select(Batch).where(Batch.id.in_(request.deleted_batch_ids))
    batches_result = await db.execute(batches_query)
    batches = batches_result.scalars().all()

    # Check for non-deleted batches
    non_deleted = [b.id for b in batches if b.deleted_at is None]
    if non_deleted:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cleanup readings for non-deleted batches: {non_deleted}. Only deleted batches can be cleaned up.",
        )

    # Check for batch IDs that don't exist
    found_batch_ids = {b.id for b in batches}
    not_found = set(request.deleted_batch_ids) - found_batch_ids
    if not_found:
        raise HTTPException(
            status_code=404,
            detail=f"Batch IDs not found: {sorted(not_found)}",
        )

    # Find readings to delete
    readings_query = select(Reading.id, Reading.batch_id).where(
        Reading.batch_id.in_(request.deleted_batch_ids)
    )
    readings_result = await db.execute(readings_query)
    readings_rows = readings_result.all()

    reading_ids = [row[0] for row in readings_rows]

    # Count readings per batch
    batch_breakdown: dict[int, int] = {}
    for row in readings_rows:
        batch_id = row[1]
        if batch_id is not None:
            batch_breakdown[batch_id] = batch_breakdown.get(batch_id, 0) + 1

    # Execute deletion if not dry run
    if not request.dry_run:
        if reading_ids:
            delete_stmt = delete(Reading).where(Reading.id.in_(reading_ids))
            await db.execute(delete_stmt)
            await db.commit()

    return CleanupPreview(
        readings_to_delete=reading_ids,
        total_count=len(reading_ids),
        batch_breakdown=batch_breakdown,
    )
