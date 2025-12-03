# Batch Lifecycle Management Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement comprehensive batch lifecycle management with soft delete, historical viewing, and data cleanup tools.

**Architecture:** Incremental enhancement of existing status-based lifecycle. Add `deleted_at` timestamp for soft delete, create maintenance API for cleanup operations, add frontend tabs for active/completed/deleted batch views. Preview-first pattern for all destructive operations.

**Tech Stack:** FastAPI, SQLAlchemy (async), SQLite, SvelteKit, TailwindCSS

---

## Prerequisites

- Backend: Python 3.11+, FastAPI, SQLAlchemy
- Frontend: Node.js, SvelteKit, TailwindCSS
- Database: SQLite with async support
- Working directory: `.worktrees/batch-lifecycle/`

## Phase 1: Database Migration

### Task 1: Add deleted_at Column Migration

**Files:**
- Modify: `backend/database.py` (add migration function)
- Modify: `backend/models.py` (add deleted_at field)

**Step 1: Add deleted_at field to Batch model**

In `backend/models.py`, find the `Batch` class (around line 317) and add the new field:

```python
class Batch(Base):
    # ... existing fields ...

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # NEW: Soft delete timestamp
    deleted_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Relationships
    recipe: Mapped[Optional["Recipe"]] = relationship(back_populates="batches")
```

**Step 2: Add helper property to Batch model**

Add this property method after the fields in the Batch class:

```python
    @property
    def is_deleted(self) -> bool:
        """Check if batch is soft-deleted."""
        return self.deleted_at is not None
```

**Step 3: Write migration function**

In `backend/database.py`, add the migration function before `init_db()`:

```python
async def _migrate_add_deleted_at(db: AsyncConnection):
    """Add deleted_at column to batches table and migrate archived status."""
    try:
        # Check if column already exists
        cursor = await db.execute(text("PRAGMA table_info(batches)"))
        rows = cursor.fetchall()
        columns = {row[1] for row in rows}

        if 'deleted_at' not in columns:
            logger.info("Adding deleted_at column to batches table")
            await db.execute(text("ALTER TABLE batches ADD COLUMN deleted_at TIMESTAMP"))

            # Migrate any 'archived' status to 'completed'
            result = await db.execute(
                text("UPDATE batches SET status = 'completed' WHERE status = 'archived'")
            )
            updated = result.rowcount
            if updated > 0:
                logger.info(f"Migrated {updated} batches from 'archived' to 'completed' status")

            await db.commit()
            logger.info("Migration completed: deleted_at column added")
        else:
            logger.info("Migration skipped: deleted_at column already exists")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise
```

**Step 4: Call migration in init_db**

In `backend/database.py`, find the `init_db()` function and add the migration call after existing migrations:

```python
async def init_db():
    async with engine.begin() as conn:
        # ... existing migrations ...
        await _migrate_add_deleted_at(conn)

        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
```

**Step 5: Test migration**

Run the backend to trigger migration:

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/batch-lifecycle
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8081
```

Expected: Server starts successfully, logs show "Migration completed: deleted_at column added"

Check the database:

```bash
sqlite3 data/fermentation.db "PRAGMA table_info(batches);" | grep deleted_at
```

Expected: Output shows `deleted_at|TIMESTAMP|0||0`

**Step 6: Commit**

```bash
git add backend/models.py backend/database.py
git commit -m "feat: add soft delete support to batches with deleted_at column

- Add deleted_at timestamp field to Batch model
- Add is_deleted helper property
- Create migration to add column and migrate archived status
- Migrate existing 'archived' batches to 'completed' status

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

## Phase 2: Backend API - Batch Filtering

### Task 2: Update List Batches Endpoint

**Files:**
- Modify: `backend/routers/batches.py:26-48` (list_batches function)

**Step 1: Add query parameters for soft delete filtering**

In `backend/routers/batches.py`, update the `list_batches` function signature:

```python
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
```

**Step 2: Add soft delete filtering logic**

Replace the query building section with:

```python
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
```

**Step 3: Test filtering with curl**

Start the backend server and test:

```bash
# Test default (should exclude deleted)
curl http://localhost:8081/api/batches | jq '.[] | {id, name, deleted_at}'

# Test include_deleted
curl "http://localhost:8081/api/batches?include_deleted=true" | jq '.[] | {id, name, deleted_at}'

# Test deleted_only
curl "http://localhost:8081/api/batches?deleted_only=true" | jq '.[] | {id, name, deleted_at}'
```

Expected: Default returns only non-deleted batches, other params work correctly

**Step 4: Commit**

```bash
git add backend/routers/batches.py
git commit -m "feat: add soft delete filtering to list batches endpoint

- Add include_deleted and deleted_only query parameters
- Default behavior excludes soft-deleted batches
- Maintain backward compatibility with existing API consumers

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 3: Add Convenience Endpoints for Active and Completed Batches

**Files:**
- Modify: `backend/routers/batches.py` (add new endpoints after list_batches)

**Step 1: Add /active endpoint**

Add this endpoint after the `list_batches` function:

```python
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
```

**Step 2: Add /completed endpoint**

Add this endpoint after the `/active` endpoint:

```python
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
```

**Step 3: Test convenience endpoints**

```bash
# Test /active
curl http://localhost:8081/api/batches/active | jq '.[] | {id, name, status}'

# Test /completed
curl http://localhost:8081/api/batches/completed | jq '.[] | {id, name, status}'
```

Expected: /active returns planning and fermenting batches, /completed returns completed and conditioning

**Step 4: Commit**

```bash
git add backend/routers/batches.py
git commit -m "feat: add convenience endpoints for active and completed batches

- Add GET /api/batches/active for planning/fermenting batches
- Add GET /api/batches/completed for historical view
- Both endpoints exclude soft-deleted batches by default

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 4: Add Soft Delete and Restore Endpoints

**Files:**
- Modify: `backend/routers/batches.py` (add endpoints after delete_batch)

**Step 1: Replace hard delete endpoint with soft/hard delete**

Replace the existing `delete_batch` function (around line 248) with:

```python
@router.post("/{batch_id}/delete")
async def soft_delete_batch(
    batch_id: int,
    hard_delete: bool = Query(False, description="Cascade delete readings"),
    db: AsyncSession = Depends(get_db),
):
    """Soft delete or hard delete a batch.

    - Soft delete (default): Sets deleted_at timestamp, preserves all data
    - Hard delete: Cascade removes all readings via relationship
    """
    batch = await db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    if hard_delete:
        # Hard delete: cascade removes readings via relationship
        await db.delete(batch)
        await db.commit()
        return {"status": "deleted", "type": "hard", "batch_id": batch_id}
    else:
        # Soft delete: set timestamp
        batch.deleted_at = datetime.now(timezone.utc)
        await db.commit()
        return {"status": "deleted", "type": "soft", "batch_id": batch_id}
```

**Step 2: Add restore endpoint**

Add this endpoint after the soft_delete_batch function:

```python
@router.post("/{batch_id}/restore")
async def restore_batch(batch_id: int, db: AsyncSession = Depends(get_db)):
    """Restore a soft-deleted batch."""
    batch = await db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if not batch.deleted_at:
        raise HTTPException(status_code=400, detail="Batch is not deleted")

    batch.deleted_at = None
    await db.commit()
    return {"status": "restored", "batch_id": batch_id}
```

**Step 3: Test soft delete and restore**

Create a test batch and try soft delete:

```bash
# Soft delete
curl -X POST http://localhost:8081/api/batches/1/delete | jq

# Verify it's hidden
curl http://localhost:8081/api/batches | jq '.[] | select(.id == 1)'

# Verify it appears in deleted_only
curl "http://localhost:8081/api/batches?deleted_only=true" | jq '.[] | select(.id == 1)'

# Restore it
curl -X POST http://localhost:8081/api/batches/1/restore | jq

# Verify it's visible again
curl http://localhost:8081/api/batches | jq '.[] | select(.id == 1)'
```

Expected: Batch disappears from default list when soft-deleted, reappears when restored

**Step 4: Test hard delete**

```bash
# Hard delete (WARNING: destroys data)
curl -X POST "http://localhost:8081/api/batches/999/delete?hard_delete=true" | jq
```

Expected: Batch and all readings are permanently deleted

**Step 5: Commit**

```bash
git add backend/routers/batches.py
git commit -m "feat: add soft delete and restore endpoints for batches

- Replace DELETE with POST /delete endpoint supporting soft/hard delete
- Add POST /restore endpoint for recovering soft-deleted batches
- Soft delete is default, hard delete requires explicit query parameter
- Hard delete cascades to readings via SQLAlchemy relationship

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

## Phase 3: Maintenance API

### Task 5: Create Maintenance Router

**Files:**
- Create: `backend/routers/maintenance.py`
- Modify: `backend/main.py` (register router)

**Step 1: Create maintenance router file**

Create `backend/routers/maintenance.py`:

```python
"""Data maintenance and cleanup operations."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import delete, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Batch, Device, Reading, serialize_datetime_to_utc

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


class OrphanedDataReport(BaseModel):
    """Report of orphaned readings and unused devices."""
    readings_without_batch: int
    readings_from_deleted_batches: int
    devices_without_active_batch: int
    unpaired_devices_with_readings: int


class CleanupPreview(BaseModel):
    """Preview of cleanup operation results."""
    readings_to_delete: int
    affected_batches: list[int]
    affected_devices: list[str]
    date_range: Optional[tuple[str, str]] = None


class CleanupRequest(BaseModel):
    """Request parameters for cleanup operation."""
    batch_id: Optional[int] = None
    device_id: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    include_deleted_batches: bool = False
    preview_only: bool = True  # Safety: default to preview
```

**Step 2: Add orphaned data report endpoint**

Add this endpoint to the maintenance router:

```python
@router.get("/orphaned-data", response_model=OrphanedDataReport)
async def get_orphaned_data_report(db: AsyncSession = Depends(get_db)):
    """Identify orphaned readings and unused devices for data integrity check."""

    # Readings with no batch linkage
    no_batch = await db.execute(
        select(func.count(Reading.id)).where(Reading.batch_id.is_(None))
    )

    # Readings linked to deleted batches
    deleted_batch_query = (
        select(func.count(Reading.id))
        .join(Batch, Reading.batch_id == Batch.id)
        .where(Batch.deleted_at.is_not(None))
    )
    deleted_batch = await db.execute(deleted_batch_query)

    # Devices not assigned to any active batch
    unused_devices_query = (
        select(func.count(Device.id))
        .outerjoin(
            Batch,
            (Device.id == Batch.device_id) & (Batch.status == "fermenting")
        )
        .where(Batch.id.is_(None))
    )
    unused_devices = await db.execute(unused_devices_query)

    # Unpaired devices with readings (data pollution)
    unpaired_with_data_query = (
        select(func.count(distinct(Reading.device_id)))
        .join(Device, Reading.device_id == Device.id)
        .where(Device.paired == False, Reading.device_id.is_not(None))
    )
    unpaired_with_data = await db.execute(unpaired_with_data_query)

    return OrphanedDataReport(
        readings_without_batch=no_batch.scalar() or 0,
        readings_from_deleted_batches=deleted_batch.scalar() or 0,
        devices_without_active_batch=unused_devices.scalar() or 0,
        unpaired_devices_with_readings=unpaired_with_data.scalar() or 0,
    )
```

**Step 3: Add cleanup readings endpoint**

Add this endpoint after the orphaned data report:

```python
@router.post("/cleanup-readings", response_model=CleanupPreview)
async def cleanup_readings(
    request: CleanupRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete readings by batch, device, or date range. Preview by default.

    Safety features:
    - Defaults to preview_only=True (must explicitly set to False to execute)
    - Shows exact count, affected entities, and date range before deletion
    - Supports filtering by batch, device, date range, or combinations
    """

    # Build query for readings to delete
    query = select(Reading)

    # Apply filters
    if request.batch_id:
        query = query.where(Reading.batch_id == request.batch_id)
    if request.device_id:
        query = query.where(Reading.device_id == request.device_id)
    if request.date_from:
        query = query.where(Reading.timestamp >= request.date_from)
    if request.date_to:
        query = query.where(Reading.timestamp <= request.date_to)
    if request.include_deleted_batches:
        # Include readings from deleted batches
        query = query.outerjoin(Batch).where(
            (Batch.deleted_at.is_not(None)) | (Reading.batch_id.is_(None))
        )

    # Get preview data
    result = await db.execute(query)
    reading_list = result.scalars().all()

    # Calculate preview metadata
    affected_batches = sorted(list(set(r.batch_id for r in reading_list if r.batch_id)))
    affected_devices = sorted(list(set(r.device_id for r in reading_list if r.device_id)))

    date_range = None
    if reading_list:
        timestamps = [r.timestamp for r in reading_list]
        min_date = min(timestamps)
        max_date = max(timestamps)
        date_range = (
            serialize_datetime_to_utc(min_date),
            serialize_datetime_to_utc(max_date),
        )

    # Execute deletion if not preview
    if not request.preview_only:
        delete_query = delete(Reading)

        # Apply same filters as select query
        if request.batch_id:
            delete_query = delete_query.where(Reading.batch_id == request.batch_id)
        if request.device_id:
            delete_query = delete_query.where(Reading.device_id == request.device_id)
        if request.date_from:
            delete_query = delete_query.where(Reading.timestamp >= request.date_from)
        if request.date_to:
            delete_query = delete_query.where(Reading.timestamp <= request.date_to)

        await db.execute(delete_query)
        await db.commit()

    return CleanupPreview(
        readings_to_delete=len(reading_list),
        affected_batches=affected_batches,
        affected_devices=affected_devices,
        date_range=date_range,
    )
```

**Step 4: Register maintenance router in main.py**

In `backend/main.py`, add the import and router registration:

```python
# Add to imports section
from .routers import maintenance

# Add to router registration section (after other routers)
app.include_router(maintenance.router)
```

**Step 5: Test maintenance endpoints**

```bash
# Test orphaned data report
curl http://localhost:8081/api/maintenance/orphaned-data | jq

# Test cleanup preview
curl -X POST http://localhost:8081/api/maintenance/cleanup-readings \
  -H "Content-Type: application/json" \
  -d '{"batch_id": 1, "preview_only": true}' | jq
```

Expected: Report shows data integrity metrics, preview shows affected readings

**Step 6: Commit**

```bash
git add backend/routers/maintenance.py backend/main.py
git commit -m "feat: add data maintenance API for cleanup operations

- Create maintenance router with orphaned data reporting
- Add cleanup-readings endpoint with preview/execute modes
- Support filtering by batch, device, and date range
- Default to preview mode for safety

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

## Phase 4: Frontend - Batch List Tabs

### Task 6: Add Tab Navigation to Batch List Page

**Files:**
- Modify: `frontend/src/routes/batches/+page.svelte`

**Step 1: Read current batch list page structure**

```bash
cat frontend/src/routes/batches/+page.svelte
```

**Step 2: Add tab state and API calls**

Replace the script section with:

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';

  type TabType = 'active' | 'completed' | 'deleted';
  let activeTab: TabType = 'active';

  let activeBatches: any[] = [];
  let completedBatches: any[] = [];
  let deletedBatches: any[] = [];
  let loading = false;

  async function loadBatches() {
    loading = true;
    try {
      let url = '/api/batches';
      if (activeTab === 'active') {
        url = '/api/batches/active';
      } else if (activeTab === 'completed') {
        url = '/api/batches/completed';
      } else {
        url = '/api/batches?deleted_only=true';
      }

      const res = await fetch(url);
      const data = await res.json();

      if (activeTab === 'active') {
        activeBatches = data;
      } else if (activeTab === 'completed') {
        completedBatches = data;
      } else {
        deletedBatches = data;
      }
    } finally {
      loading = false;
    }
  }

  $: activeTab && loadBatches();

  $: currentBatches =
    activeTab === 'active' ? activeBatches :
    activeTab === 'completed' ? completedBatches :
    deletedBatches;

  async function handleRestore(batchId: number) {
    await fetch(`/api/batches/${batchId}/restore`, { method: 'POST' });
    loadBatches();
  }

  async function handleDelete(batchId: number, hard: boolean = false) {
    const confirmed = hard
      ? confirm('Permanently delete this batch and all readings? This cannot be undone.')
      : confirm('Move this batch to deleted? You can restore it later.');

    if (!confirmed) return;

    const url = `/api/batches/${batchId}/delete${hard ? '?hard_delete=true' : ''}`;
    await fetch(url, { method: 'POST' });
    loadBatches();
  }
</script>
```

**Step 3: Add tab navigation UI**

Replace the template with:

```svelte
<div class="batches-page">
  <header class="page-header">
    <h1>Batches</h1>
    <a href="/batches/new" class="btn-primary">+ New Batch</a>
  </header>

  <nav class="tabs">
    <button
      class="tab"
      class:active={activeTab === 'active'}
      on:click={() => activeTab = 'active'}
    >
      Active ({activeBatches.length})
    </button>
    <button
      class="tab"
      class:active={activeTab === 'completed'}
      on:click={() => activeTab = 'completed'}
    >
      History ({completedBatches.length})
    </button>
    <button
      class="tab"
      class:active={activeTab === 'deleted'}
      on:click={() => activeTab = 'deleted'}
    >
      Deleted ({deletedBatches.length})
    </button>
  </nav>

  {#if loading}
    <div class="loading">Loading batches...</div>
  {:else}
    <div class="batch-list">
      {#each currentBatches as batch (batch.id)}
        <div class="batch-card">
          <div class="batch-header">
            <h3>{batch.name || `Batch #${batch.batch_number}`}</h3>
            <span class="status-badge status-{batch.status}">{batch.status}</span>
          </div>

          {#if batch.recipe}
            <p class="recipe-name">{batch.recipe.name}</p>
          {/if}

          <div class="batch-actions">
            {#if activeTab === 'deleted'}
              <button on:click={() => handleRestore(batch.id)} class="btn-secondary">
                Restore
              </button>
              <button on:click={() => handleDelete(batch.id, true)} class="btn-danger">
                Delete Permanently
              </button>
            {:else}
              <a href="/batches/{batch.id}" class="btn-secondary">View Details</a>
              {#if activeTab === 'completed'}
                <a href="/batches/{batch.id}/history" class="btn-secondary">View History</a>
              {/if}
              <button on:click={() => handleDelete(batch.id)} class="btn-danger-outline">
                Delete
              </button>
            {/if}
          </div>
        </div>
      {/each}

      {#if currentBatches.length === 0}
        <p class="empty-state">
          {activeTab === 'active' ? 'No active batches. Create one to get started!' :
           activeTab === 'completed' ? 'No completed batches yet.' :
           'No deleted batches.'}
        </p>
      {/if}
    </div>
  {/if}
</div>

<style>
  .batches-page {
    max-width: 1200px;
    margin: 0 auto;
    padding: 2rem;
  }

  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 2rem;
  }

  .tabs {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 2rem;
    border-bottom: 2px solid var(--border);
  }

  .tab {
    padding: 0.75rem 1.5rem;
    background: none;
    border: none;
    border-bottom: 3px solid transparent;
    cursor: pointer;
    font-size: 1rem;
    color: var(--text-secondary);
    transition: all 0.2s;
  }

  .tab:hover {
    color: var(--text-primary);
    background: var(--surface-hover);
  }

  .tab.active {
    color: var(--primary);
    border-bottom-color: var(--primary);
    font-weight: 600;
  }

  .batch-list {
    display: grid;
    gap: 1rem;
  }

  .batch-card {
    padding: 1.5rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
  }

  .batch-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
  }

  .status-badge {
    padding: 0.25rem 0.75rem;
    border-radius: 12px;
    font-size: 0.875rem;
    font-weight: 500;
  }

  .status-planning { background: var(--info-bg); color: var(--info); }
  .status-fermenting { background: var(--success-bg); color: var(--success); }
  .status-conditioning { background: var(--warning-bg); color: var(--warning); }
  .status-completed { background: var(--surface-secondary); color: var(--text-secondary); }

  .recipe-name {
    color: var(--text-secondary);
    font-size: 0.875rem;
    margin-bottom: 1rem;
  }

  .batch-actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 1rem;
  }

  .empty-state {
    text-align: center;
    padding: 3rem;
    color: var(--text-secondary);
  }

  .loading {
    text-align: center;
    padding: 2rem;
    color: var(--text-secondary);
  }
</style>
```

**Step 4: Test tab navigation**

Start frontend dev server:

```bash
cd frontend
npm run dev
```

Visit http://localhost:5173/batches and test:
- Click each tab (Active, History, Deleted)
- Verify correct batches show in each tab
- Test soft delete moves batch to Deleted tab
- Test restore moves batch back to appropriate tab

Expected: Tabs filter batches correctly, counts update, actions work

**Step 5: Commit**

```bash
git add frontend/src/routes/batches/+page.svelte
git commit -m "feat: add tabbed navigation to batch list page

- Add Active, History, and Deleted tabs
- Connect tabs to /active, /completed, and ?deleted_only endpoints
- Add restore and delete actions per tab context
- Show batch counts in tab labels

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

## Phase 5: Frontend - Data Maintenance UI

### Task 7: Create Data Maintenance Page

**Files:**
- Create: `frontend/src/routes/system/maintenance/+page.svelte`

**Step 1: Create system/maintenance directory**

```bash
mkdir -p frontend/src/routes/system/maintenance
```

**Step 2: Create maintenance page**

Create `frontend/src/routes/system/maintenance/+page.svelte`:

```svelte
<script lang="ts">
  import { onMount } from 'svelte';

  let orphanedReport = {
    readings_without_batch: 0,
    readings_from_deleted_batches: 0,
    devices_without_active_batch: 0,
    unpaired_devices_with_readings: 0,
  };

  let cleanupRequest = {
    batch_id: null as number | null,
    device_id: null as string | null,
    date_from: null as string | null,
    date_to: null as string | null,
    include_deleted_batches: false,
    preview_only: true,
  };

  let cleanupPreview: any = null;
  let isExecuting = false;
  let loading = false;

  async function loadOrphanedReport() {
    loading = true;
    try {
      const res = await fetch('/api/maintenance/orphaned-data');
      orphanedReport = await res.json();
    } finally {
      loading = false;
    }
  }

  async function previewCleanup() {
    const res = await fetch('/api/maintenance/cleanup-readings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...cleanupRequest, preview_only: true }),
    });
    cleanupPreview = await res.json();
  }

  async function executeCleanup() {
    if (!cleanupPreview) return;

    const confirmed = confirm(
      `Delete ${cleanupPreview.readings_to_delete} readings?\n\n` +
      `Affected batches: ${cleanupPreview.affected_batches.length}\n` +
      `Affected devices: ${cleanupPreview.affected_devices.length}\n\n` +
      `This action cannot be undone.`
    );

    if (!confirmed) return;

    isExecuting = true;
    try {
      await fetch('/api/maintenance/cleanup-readings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...cleanupRequest, preview_only: false }),
      });

      alert('Cleanup completed successfully');

      // Refresh reports and reset form
      await loadOrphanedReport();
      cleanupPreview = null;
      cleanupRequest = {
        batch_id: null,
        device_id: null,
        date_from: null,
        date_to: null,
        include_deleted_batches: false,
        preview_only: true,
      };
    } finally {
      isExecuting = false;
    }
  }

  onMount(loadOrphanedReport);
</script>

<div class="maintenance-page">
  <header class="page-header">
    <h1>Data Maintenance</h1>
    <a href="/system" class="btn-secondary">← Back to System</a>
  </header>

  <!-- Orphaned Data Report -->
  <section class="card">
    <div class="card-header">
      <h2>Data Integrity Report</h2>
      <button on:click={loadOrphanedReport} class="btn-secondary" disabled={loading}>
        {loading ? 'Loading...' : 'Refresh'}
      </button>
    </div>

    <dl class="report">
      <div class="report-item">
        <dt>Readings without batch:</dt>
        <dd class:warn={orphanedReport.readings_without_batch > 0}>
          {orphanedReport.readings_without_batch}
        </dd>
      </div>

      <div class="report-item">
        <dt>Readings from deleted batches:</dt>
        <dd class:warn={orphanedReport.readings_from_deleted_batches > 0}>
          {orphanedReport.readings_from_deleted_batches}
        </dd>
      </div>

      <div class="report-item">
        <dt>Devices without active batch:</dt>
        <dd>{orphanedReport.devices_without_active_batch}</dd>
      </div>

      <div class="report-item">
        <dt>Unpaired devices with data:</dt>
        <dd class:warn={orphanedReport.unpaired_devices_with_readings > 0}>
          {orphanedReport.unpaired_devices_with_readings}
        </dd>
      </div>
    </dl>
  </section>

  <!-- Cleanup Tool -->
  <section class="card">
    <h2>Cleanup Readings</h2>

    <form on:submit|preventDefault={previewCleanup}>
      <div class="form-grid">
        <label>
          <span>Batch ID</span>
          <input
            type="number"
            bind:value={cleanupRequest.batch_id}
            placeholder="All batches"
          />
        </label>

        <label>
          <span>Device ID</span>
          <input
            type="text"
            bind:value={cleanupRequest.device_id}
            placeholder="All devices"
          />
        </label>

        <label>
          <span>Date From</span>
          <input type="date" bind:value={cleanupRequest.date_from} />
        </label>

        <label>
          <span>Date To</span>
          <input type="date" bind:value={cleanupRequest.date_to} />
        </label>
      </div>

      <label class="checkbox-label">
        <input
          type="checkbox"
          bind:checked={cleanupRequest.include_deleted_batches}
        />
        <span>Include readings from deleted batches</span>
      </label>

      <button type="submit" class="btn-primary">Preview Cleanup</button>
    </form>

    {#if cleanupPreview}
      <div class="preview-box">
        <h3>Preview Results</h3>
        <dl class="preview-details">
          <div class="preview-item">
            <dt>Readings to delete:</dt>
            <dd class="highlight">{cleanupPreview.readings_to_delete}</dd>
          </div>

          <div class="preview-item">
            <dt>Affected batches:</dt>
            <dd>{cleanupPreview.affected_batches.join(', ') || 'None'}</dd>
          </div>

          <div class="preview-item">
            <dt>Affected devices:</dt>
            <dd>{cleanupPreview.affected_devices.join(', ') || 'None'}</dd>
          </div>

          {#if cleanupPreview.date_range}
            <div class="preview-item">
              <dt>Date range:</dt>
              <dd>
                {new Date(cleanupPreview.date_range[0]).toLocaleDateString()}
                to
                {new Date(cleanupPreview.date_range[1]).toLocaleDateString()}
              </dd>
            </div>
          {/if}
        </dl>

        <button
          on:click={executeCleanup}
          disabled={isExecuting || cleanupPreview.readings_to_delete === 0}
          class="btn-danger"
        >
          {isExecuting ? 'Executing...' : 'Execute Cleanup'}
        </button>
      </div>
    {/if}
  </section>
</div>

<style>
  .maintenance-page {
    max-width: 900px;
    margin: 0 auto;
    padding: 2rem;
  }

  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 2rem;
  }

  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 2rem;
  }

  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
  }

  .report {
    display: grid;
    gap: 1rem;
  }

  .report-item {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 1rem;
    align-items: center;
    padding: 0.75rem;
    background: var(--surface-secondary);
    border-radius: 4px;
  }

  .report-item dt {
    font-weight: 500;
  }

  .report-item dd {
    font-size: 1.25rem;
    font-weight: 600;
    text-align: right;
  }

  .report-item dd.warn {
    color: var(--warning);
  }

  .form-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
    margin-bottom: 1rem;
  }

  label {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  label span {
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--text-secondary);
  }

  input[type="number"],
  input[type="text"],
  input[type="date"] {
    padding: 0.5rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--surface);
    color: var(--text-primary);
  }

  .checkbox-label {
    flex-direction: row;
    align-items: center;
    gap: 0.5rem;
    margin: 1rem 0;
  }

  .preview-box {
    margin-top: 1.5rem;
    padding: 1.5rem;
    border: 2px solid var(--warning);
    border-radius: 8px;
    background: var(--surface-secondary);
  }

  .preview-box h3 {
    margin-top: 0;
    margin-bottom: 1rem;
  }

  .preview-details {
    display: grid;
    gap: 0.75rem;
    margin-bottom: 1rem;
  }

  .preview-item {
    display: grid;
    grid-template-columns: 150px 1fr;
    gap: 1rem;
  }

  .preview-item dt {
    font-weight: 500;
  }

  .highlight {
    font-size: 1.5rem;
    font-weight: bold;
    color: var(--danger);
  }

  .btn-danger {
    width: 100%;
    padding: 0.75rem;
    background: var(--danger);
    color: white;
    border: none;
    border-radius: 4px;
    font-weight: 600;
    cursor: pointer;
  }

  .btn-danger:hover:not(:disabled) {
    background: var(--danger-hover);
  }

  .btn-danger:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>
```

**Step 3: Test maintenance page**

Visit http://localhost:5173/system/maintenance and test:
- Orphaned data report loads correctly
- Cleanup form accepts filters
- Preview shows accurate counts
- Execute confirmation works
- Refresh updates report after cleanup

Expected: Full maintenance workflow functions correctly

**Step 4: Commit**

```bash
git add frontend/src/routes/system/maintenance/+page.svelte
git commit -m "feat: add data maintenance UI for cleanup operations

- Create maintenance page with orphaned data report
- Add cleanup form with batch, device, and date filters
- Implement preview-first workflow with confirmation
- Show affected entities before executing cleanup

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

## Phase 6: Testing & Documentation

### Task 8: End-to-End Testing

**Step 1: Test complete lifecycle workflow**

```bash
# 1. Create a test batch
curl -X POST http://localhost:8081/api/batches \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Batch", "status": "fermenting"}' | jq

# 2. Verify it appears in active list
curl http://localhost:8081/api/batches/active | jq '.[] | select(.name == "Test Batch")'

# 3. Update to completed status
curl -X PUT http://localhost:8081/api/batches/1 \
  -H "Content-Type: application/json" \
  -d '{"status": "completed"}' | jq

# 4. Verify it appears in completed list
curl http://localhost:8081/api/batches/completed | jq '.[] | select(.name == "Test Batch")'

# 5. Soft delete it
curl -X POST http://localhost:8081/api/batches/1/delete | jq

# 6. Verify it appears in deleted list
curl "http://localhost:8081/api/batches?deleted_only=true" | jq '.[] | select(.name == "Test Batch")'

# 7. Restore it
curl -X POST http://localhost:8081/api/batches/1/restore | jq

# 8. Verify it's back in completed list
curl http://localhost:8081/api/batches/completed | jq '.[] | select(.name == "Test Batch")'
```

Expected: Batch moves correctly through lifecycle stages

**Step 2: Test maintenance operations**

```bash
# Check orphaned data
curl http://localhost:8081/api/maintenance/orphaned-data | jq

# Preview cleanup for a batch
curl -X POST http://localhost:8081/api/maintenance/cleanup-readings \
  -H "Content-Type: application/json" \
  -d '{"batch_id": 1, "preview_only": true}' | jq

# Execute cleanup (if preview looks good)
curl -X POST http://localhost:8081/api/maintenance/cleanup-readings \
  -H "Content-Type: application/json" \
  -d '{"batch_id": 1, "preview_only": false}' | jq
```

Expected: Maintenance operations work correctly

**Step 3: Test frontend tabs**

Manual testing in browser:
1. Visit http://localhost:5173/batches
2. Click each tab (Active, History, Deleted)
3. Create a new batch
4. Move it through statuses
5. Soft delete and restore
6. Visit maintenance page
7. Run cleanup preview

Expected: All UI interactions work smoothly

**Step 4: Document test results**

Create test notes in a comment on the design doc or create a test results file.

### Task 9: Update Documentation

**Files:**
- Modify: `CLAUDE.md` (add new endpoints)
- Modify: `CHANGELOG.md` (document changes)

**Step 1: Update CLAUDE.md with new endpoints**

Add to the API Documentation section in `CLAUDE.md`:

```markdown
### Batch Lifecycle Endpoints

**List batches with filtering:**
- `GET /api/batches?include_deleted=true` - Include soft-deleted batches
- `GET /api/batches?deleted_only=true` - Show only deleted batches
- `GET /api/batches/active` - Active batches (planning, fermenting)
- `GET /api/batches/completed` - Historical batches (completed, conditioning)

**Soft delete and restore:**
- `POST /api/batches/{id}/delete` - Soft delete (default)
- `POST /api/batches/{id}/delete?hard_delete=true` - Hard delete with cascade
- `POST /api/batches/{id}/restore` - Restore soft-deleted batch

### Data Maintenance Endpoints

- `GET /api/maintenance/orphaned-data` - Report orphaned readings and devices
- `POST /api/maintenance/cleanup-readings` - Preview or execute reading cleanup
  - Default: `preview_only=true` (shows what will be deleted)
  - Set `preview_only=false` to execute deletion
  - Supports filtering by batch_id, device_id, date_from, date_to
```

**Step 2: Update CHANGELOG.md**

Add entry to `CHANGELOG.md`:

```markdown
## [Unreleased]

### Added
- Batch lifecycle management with soft delete support (#41)
  - Soft delete batches without losing fermentation data
  - Restore accidentally deleted batches
  - Tab navigation for Active, History, and Deleted batches
  - Data maintenance page with orphaned data reporting
  - Cleanup tools for readings with preview-first workflow
  - Convenience endpoints for active and completed batches

### Changed
- Migrated `archived` status to `completed` for consistency
- Batch list now excludes deleted batches by default
- Enhanced batch filtering with `include_deleted` and `deleted_only` parameters

### Database
- Added `deleted_at` timestamp column to batches table
- Migration automatically converts `archived` to `completed` status
```

**Step 3: Commit documentation updates**

```bash
git add CLAUDE.md CHANGELOG.md
git commit -m "docs: update documentation for batch lifecycle management

- Add new batch filtering and lifecycle endpoints to CLAUDE.md
- Document maintenance API endpoints
- Update CHANGELOG with batch lifecycle features

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

## Final Steps

### Task 10: Build and Test Deployment

**Step 1: Build frontend for production**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/batch-lifecycle/frontend
npm run build
```

Expected: Build completes successfully, outputs to `backend/static/`

**Step 2: Test production build locally**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/batch-lifecycle
uvicorn backend.main:app --host 0.0.0.0 --port 8081
```

Visit http://localhost:8081 and test:
- All batch lifecycle features work
- Tabs navigate correctly
- Maintenance page accessible
- Soft delete/restore functional

**Step 3: Commit built frontend**

```bash
git add backend/static
git commit -m "build: compile frontend for batch lifecycle deployment

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

**Step 4: Merge to main branch**

```bash
git checkout master
git merge --no-ff feature/batch-lifecycle
git push origin master
```

**Step 5: Deploy to Raspberry Pi**

```bash
sshpass -p 'tilt' ssh -o StrictHostKeyChecking=no pi@192.168.4.117 \
  "cd /opt/brewsignal && git fetch origin && git reset --hard origin/master && sudo systemctl restart brewsignal"
```

**Step 6: Verify deployment**

```bash
# Check service status
sshpass -p 'tilt' ssh -o StrictHostKeyChecking=no pi@192.168.4.117 \
  "sudo systemctl status brewsignal"

# Check logs for migration
sshpass -p 'tilt' ssh -o StrictHostKeyChecking=no pi@192.168.4.117 \
  "sudo journalctl -u brewsignal -n 50 --no-pager | grep -i migration"
```

Expected: Service running, migration completed successfully

---

## Implementation Complete!

**Deliverables:**
✅ Soft delete functionality for batches
✅ Tab navigation (Active/History/Deleted)
✅ Data maintenance API and UI
✅ Orphaned data detection
✅ Preview-first cleanup operations
✅ Convenience endpoints for batch filtering
✅ Migration for existing data
✅ Updated documentation
✅ Production build and deployment

**Next Steps:**
- Monitor for any issues in production
- Consider adding batch history export (CSV, PDF)
- Future: Add batch comparison view
- Future: Automated cleanup scheduling
