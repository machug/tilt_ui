# Device Pairing Workflow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement device pairing workflow so Tilt devices must be explicitly paired before readings are logged to the database.

**Architecture:** Add a `paired` boolean field to both the legacy `Tilt` and universal `Device` models. Modify reading storage logic to only save readings when devices are paired. Create a new Devices management page in the frontend for pairing/unpairing devices.

**Tech Stack:**
- Backend: Python FastAPI, SQLAlchemy, SQLite
- Frontend: Svelte 5, TypeScript
- Database: SQLite with async SQLAlchemy migrations

---

## Task 1: Database Schema - Add `paired` Field to Models

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/database.py`

**Step 1: Write failing test for Tilt model with paired field**

Create test file:

```python
# tests/test_models.py
import pytest
from datetime import datetime, timezone
from backend.models import Tilt, Device

def test_tilt_model_has_paired_field():
    """Test that Tilt model includes paired field with default False."""
    tilt = Tilt(
        id="tilt-red",
        color="RED",
        beer_name="Test Beer"
    )
    assert hasattr(tilt, 'paired')
    assert tilt.paired is False

def test_device_model_has_paired_field():
    """Test that Device model includes paired field with default False."""
    device = Device(
        id="tilt-blue",
        device_type="tilt",
        name="Blue Tilt"
    )
    assert hasattr(device, 'paired')
    assert device.paired is False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py::test_tilt_model_has_paired_field -v`
Expected: FAIL with "AttributeError: 'Tilt' object has no attribute 'paired'"

**Step 3: Add paired field to Tilt model**

In `backend/models.py` at line 22 (after `last_seen`):

```python
    last_seen: Mapped[Optional[datetime]] = mapped_column()
    paired: Mapped[bool] = mapped_column(default=False)  # Add this line

    readings: Mapped[list["Reading"]] = relationship(back_populates="tilt", cascade="all, delete-orphan")
```

**Step 4: Add paired field to Device model**

In `backend/models.py` at line 76 (after `created_at`):

```python
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    paired: Mapped[bool] = mapped_column(default=False)  # Add this line

    # Relationships
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: PASS (2 tests)

**Step 6: Create database migration for paired field**

Add migration function in `backend/database.py` after `_migrate_add_batch_id_to_control_events`:

```python
def _migrate_add_paired_to_tilts_and_devices(conn):
    """Add paired boolean field to tilts and devices tables."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    # Migrate tilts table
    if "tilts" in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns("tilts")]
        if "paired" not in columns:
            conn.execute(text("ALTER TABLE tilts ADD COLUMN paired INTEGER DEFAULT 0"))
            print("Migration: Added paired column to tilts table")

    # Migrate devices table
    if "devices" in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns("devices")]
        if "paired" not in columns:
            conn.execute(text("ALTER TABLE devices ADD COLUMN paired INTEGER DEFAULT 0"))
            print("Migration: Added paired column to devices table")
```

**Step 7: Register migration in init_db function**

In `backend/database.py`, add to the migrations sequence at line 60:

```python
        await conn.run_sync(_migrate_add_batch_id_to_control_events)  # Add batch_id to control_events
        await conn.run_sync(_migrate_add_paired_to_tilts_and_devices)  # Add paired field

        # Step 4: Data migrations
```

**Step 8: Test migration runs successfully**

Run: `python -c "import asyncio; from backend.database import init_db; asyncio.run(init_db())"`
Expected: Output "Migration: Added paired column to tilts table" and "Migration: Added paired column to devices table"

**Step 9: Commit**

```bash
git add backend/models.py backend/database.py tests/test_models.py
git commit -m "feat: add paired field to Tilt and Device models with migration"
```

---

## Task 2: Update Pydantic Schemas for API

**Files:**
- Modify: `backend/models.py:318-325` (TiltResponse)
- Modify: `backend/routers/devices.py` (if exists, or create device schemas)

**Step 1: Write test for TiltResponse with paired field**

Add to `tests/test_models.py`:

```python
def test_tilt_response_includes_paired():
    """Test that TiltResponse schema includes paired field."""
    from backend.models import TiltResponse
    from datetime import datetime, timezone

    response = TiltResponse(
        id="tilt-red",
        color="RED",
        beer_name="Test Beer",
        mac="AA:BB:CC:DD:EE:FF",
        original_gravity=1.050,
        last_seen=datetime.now(timezone.utc),
        paired=True
    )
    assert response.paired is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py::test_tilt_response_includes_paired -v`
Expected: FAIL with "unexpected keyword argument 'paired'"

**Step 3: Add paired to TiltResponse schema**

In `backend/models.py` at line 323 (in TiltResponse class):

```python
class TiltResponse(TiltBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    mac: Optional[str]
    original_gravity: Optional[float]
    last_seen: Optional[datetime]
    paired: bool = False  # Add this line
```

**Step 4: Add paired to TiltUpdate schema**

In `backend/models.py` at line 302 (in TiltUpdate class):

```python
class TiltUpdate(BaseModel):
    beer_name: Optional[str] = None
    original_gravity: Optional[float] = None
    paired: Optional[bool] = None  # Add this line

    @field_validator("original_gravity")
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_models.py::test_tilt_response_includes_paired -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/models.py tests/test_models.py
git commit -m "feat: add paired field to Tilt API schemas"
```

---

## Task 3: Modify Reading Storage Logic

**Files:**
- Modify: `backend/main.py:35-96` (handle_tilt_reading function)

**Step 1: Write test for reading storage respecting pairing**

Create `tests/test_reading_storage.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from backend.main import handle_tilt_reading
from backend.scanner import TiltReading

@pytest.mark.asyncio
async def test_unpaired_tilt_does_not_store_reading():
    """Test that readings from unpaired Tilts are not stored."""
    reading = TiltReading(
        id="tilt-red",
        color="RED",
        mac="AA:BB:CC:DD:EE:FF",
        sg=1.050,
        temp_f=68.0,
        rssi=-45
    )

    # Mock database session
    with patch('backend.main.async_session_factory') as mock_factory:
        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__.return_value = mock_session

        # Simulate unpaired tilt
        mock_tilt = MagicMock()
        mock_tilt.paired = False
        mock_tilt.beer_name = "Untitled"
        mock_tilt.original_gravity = None
        mock_session.get.return_value = mock_tilt

        # Mock calibration service
        with patch('backend.main.calibration_service.calibrate_reading',
                   return_value=(1.050, 68.0)):
            await handle_tilt_reading(reading)

        # Verify reading was NOT added to session
        mock_session.add.assert_not_called()

@pytest.mark.asyncio
async def test_paired_tilt_stores_reading():
    """Test that readings from paired Tilts are stored."""
    reading = TiltReading(
        id="tilt-blue",
        color="BLUE",
        mac="BB:CC:DD:EE:FF:AA",
        sg=1.048,
        temp_f=66.0,
        rssi=-50
    )

    with patch('backend.main.async_session_factory') as mock_factory:
        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__.return_value = mock_session

        # Simulate paired tilt
        mock_tilt = MagicMock()
        mock_tilt.paired = True
        mock_tilt.beer_name = "IPA"
        mock_tilt.original_gravity = 1.055
        mock_session.get.return_value = mock_tilt

        with patch('backend.main.calibration_service.calibrate_reading',
                   return_value=(1.048, 66.0)):
            with patch('backend.main.link_reading_to_batch', return_value=None):
                await handle_tilt_reading(reading)

        # Verify reading WAS added to session
        assert mock_session.add.called
        # Verify it's a Reading object being added
        call_args = mock_session.add.call_args[0][0]
        assert call_args.tilt_id == "tilt-blue"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_reading_storage.py -v`
Expected: FAIL - readings are stored regardless of pairing status

**Step 3: Modify handle_tilt_reading to check paired status**

In `backend/main.py`, replace the `handle_tilt_reading` function (lines 35-96):

```python
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

        # Apply calibration
        sg_calibrated, temp_calibrated = await calibration_service.calibrate_reading(
            session, reading.id, reading.sg, reading.temp_f
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
                temp_raw=reading.temp_f,
                temp_calibrated=temp_calibrated,
                rssi=reading.rssi,
            )
            session.add(db_reading)

        await session.commit()

        # Build reading data for WebSocket broadcast (always broadcast)
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
            "paired": tilt.paired,  # Include pairing status
        }

        # Update in-memory cache
        latest_readings[reading.id] = reading_data

        # Broadcast to all WebSocket clients
        await manager.broadcast(reading_data)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_reading_storage.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/main.py tests/test_reading_storage.py
git commit -m "feat: only store readings from paired devices"
```

---

## Task 4: Add Pairing Endpoints to Tilts Router

**Files:**
- Modify: `backend/routers/tilts.py`

**Step 1: Write test for pairing endpoint**

Create `tests/test_pairing_endpoints.py`:

```python
import pytest
from httpx import AsyncClient
from backend.main import app

@pytest.mark.asyncio
async def test_pair_tilt_endpoint():
    """Test that pairing endpoint sets paired=True."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Assuming a tilt exists with id "tilt-red"
        response = await client.post("/api/tilts/tilt-red/pair")
        assert response.status_code == 200
        data = response.json()
        assert data["paired"] is True

@pytest.mark.asyncio
async def test_unpair_tilt_endpoint():
    """Test that unpairing endpoint sets paired=False."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/tilts/tilt-red/unpair")
        assert response.status_code == 200
        data = response.json()
        assert data["paired"] is False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_pairing_endpoints.py -v`
Expected: FAIL with 404 Not Found

**Step 3: Add pairing endpoints to tilts router**

In `backend/routers/tilts.py` at the end before calibration endpoints:

```python
@router.post("/{tilt_id}/pair", response_model=TiltResponse)
async def pair_tilt(tilt_id: str, db: AsyncSession = Depends(get_db)):
    """Pair a Tilt device to enable reading storage."""
    tilt = await db.get(Tilt, tilt_id)
    if not tilt:
        raise HTTPException(status_code=404, detail="Tilt not found")

    tilt.paired = True
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

    tilt.paired = False
    await db.commit()
    await db.refresh(tilt)

    # Update in-memory cache
    if tilt_id in latest_readings:
        latest_readings[tilt_id]["paired"] = False
        await manager.broadcast(latest_readings[tilt_id])

    return tilt
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pairing_endpoints.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/routers/tilts.py tests/test_pairing_endpoints.py
git commit -m "feat: add pair/unpair endpoints for Tilt devices"
```

---

## Task 5: Update Frontend TypeScript Types

**Files:**
- Modify: `frontend/src/lib/stores/tilts.svelte.ts`

**Step 1: Add paired field to TiltReading interface**

In `frontend/src/lib/stores/tilts.svelte.ts`, locate the `TiltReading` interface and add:

```typescript
export interface TiltReading {
	id: string;
	color: string;
	beer_name: string;
	original_gravity: number | null;
	sg: number;
	sg_raw: number;
	temp: number;
	temp_raw: number;
	rssi: number;
	last_seen: string;
	paired: boolean;  // Add this line
}
```

**Step 2: Update initial state to handle paired field**

Ensure WebSocket message handler properly sets the `paired` field when updating tilts.

**Step 3: Commit**

```bash
git add frontend/src/lib/stores/tilts.svelte.ts
git commit -m "feat: add paired field to TiltReading interface"
```

---

## Task 6: Create Devices Management Page (Frontend)

**Files:**
- Create: `frontend/src/routes/devices/+page.svelte`
- Create: `frontend/src/lib/api/devices.ts`
- Modify: `backend/main.py` (add route handler)

**Step 1: Create devices API functions**

Create `frontend/src/lib/api/devices.ts`:

```typescript
import { fetchApi } from './index';

export interface DeviceResponse {
	id: string;
	color: string;
	beer_name: string;
	paired: boolean;
	last_seen: string | null;
	mac: string | null;
}

export async function fetchAllDevices(): Promise<DeviceResponse[]> {
	return fetchApi('/api/tilts');
}

export async function pairDevice(deviceId: string): Promise<DeviceResponse> {
	return fetchApi(`/api/tilts/${deviceId}/pair`, {
		method: 'POST'
	});
}

export async function unpairDevice(deviceId: string): Promise<DeviceResponse> {
	return fetchApi(`/api/tilts/${deviceId}/unpair`, {
		method: 'POST'
	});
}
```

**Step 2: Create devices page component**

Create `frontend/src/routes/devices/+page.svelte`:

```svelte
<script lang="ts">
	import { onMount } from 'svelte';
	import { fetchAllDevices, pairDevice, unpairDevice, type DeviceResponse } from '$lib/api/devices';

	let devices = $state<DeviceResponse[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	onMount(async () => {
		await loadDevices();
	});

	async function loadDevices() {
		loading = true;
		error = null;
		try {
			devices = await fetchAllDevices();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load devices';
		} finally {
			loading = false;
		}
	}

	async function handlePair(deviceId: string) {
		try {
			await pairDevice(deviceId);
			await loadDevices();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to pair device';
		}
	}

	async function handleUnpair(deviceId: string) {
		try {
			await unpairDevice(deviceId);
			await loadDevices();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to unpair device';
		}
	}

	function timeSince(isoString: string | null): string {
		if (!isoString) return 'Never seen';
		const seconds = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
		if (seconds < 10) return 'just now';
		if (seconds < 60) return `${seconds}s ago`;
		const minutes = Math.floor(seconds / 60);
		if (minutes < 60) return `${minutes}m ago`;
		const hours = Math.floor(minutes / 60);
		if (hours < 24) return `${hours}h ago`;
		const days = Math.floor(hours / 24);
		return `${days}d ago`;
	}

	let pairedDevices = $derived(devices.filter(d => d.paired));
	let unpairedDevices = $derived(devices.filter(d => !d.paired));
</script>

<svelte:head>
	<title>Devices | BrewSignal</title>
</svelte:head>

<div class="page-header">
	<h1 class="page-title">Devices</h1>
	<p class="page-description">Manage your Tilt hydrometer devices</p>
</div>

{#if loading}
	<div class="loading-state">Loading devices...</div>
{:else if error}
	<div class="error-state">
		<p>{error}</p>
		<button onclick={loadDevices} class="btn-secondary">Retry</button>
	</div>
{:else}
	<div class="devices-container">
		<!-- Paired Devices Section -->
		<section class="device-section">
			<h2 class="section-title">Paired Devices ({pairedDevices.length})</h2>
			<p class="section-description">These devices are actively logging readings</p>

			{#if pairedDevices.length === 0}
				<div class="empty-state">
					<p>No paired devices. Pair a device below to start logging readings.</p>
				</div>
			{:else}
				<div class="device-grid">
					{#each pairedDevices as device}
						<div class="device-card paired">
							<div class="device-header">
								<div class="device-info">
									<div class="device-color-badge" style="background: var(--tilt-{device.color.toLowerCase()})"></div>
									<div>
										<h3 class="device-name">{device.color} Tilt</h3>
										<p class="device-id">{device.id}</p>
									</div>
								</div>
								<div class="device-status paired">
									<span class="status-dot"></span>
									Paired
								</div>
							</div>

							<div class="device-details">
								<div class="detail-row">
									<span class="detail-label">Beer Name:</span>
									<span class="detail-value">{device.beer_name}</span>
								</div>
								<div class="detail-row">
									<span class="detail-label">Last Seen:</span>
									<span class="detail-value">{timeSince(device.last_seen)}</span>
								</div>
								{#if device.mac}
									<div class="detail-row">
										<span class="detail-label">MAC:</span>
										<span class="detail-value mono">{device.mac}</span>
									</div>
								{/if}
							</div>

							<button
								onclick={() => handleUnpair(device.id)}
								class="btn-secondary btn-sm"
							>
								Unpair Device
							</button>
						</div>
					{/each}
				</div>
			{/if}
		</section>

		<!-- Unpaired Devices Section -->
		<section class="device-section">
			<h2 class="section-title">Detected Devices ({unpairedDevices.length})</h2>
			<p class="section-description">These devices are detected but not logging readings</p>

			{#if unpairedDevices.length === 0}
				<div class="empty-state">
					<p>No unpaired devices detected. Make sure your Tilt is floating and within Bluetooth range.</p>
				</div>
			{:else}
				<div class="device-grid">
					{#each unpairedDevices as device}
						<div class="device-card unpaired">
							<div class="device-header">
								<div class="device-info">
									<div class="device-color-badge" style="background: var(--tilt-{device.color.toLowerCase()})"></div>
									<div>
										<h3 class="device-name">{device.color} Tilt</h3>
										<p class="device-id">{device.id}</p>
									</div>
								</div>
								<div class="device-status unpaired">
									<span class="status-dot"></span>
									Unpaired
								</div>
							</div>

							<div class="device-details">
								<div class="detail-row">
									<span class="detail-label">Last Seen:</span>
									<span class="detail-value">{timeSince(device.last_seen)}</span>
								</div>
								{#if device.mac}
									<div class="detail-row">
										<span class="detail-label">MAC:</span>
										<span class="detail-value mono">{device.mac}</span>
									</div>
								{/if}
							</div>

							<button
								onclick={() => handlePair(device.id)}
								class="btn-primary btn-sm"
							>
								Pair Device
							</button>
						</div>
					{/each}
				</div>
			{/if}
		</section>
	</div>
{/if}

<style>
	.page-header {
		margin-bottom: 2rem;
	}

	.page-title {
		font-size: 1.875rem;
		font-weight: 700;
		color: var(--text-primary);
		margin-bottom: 0.5rem;
	}

	.page-description {
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.devices-container {
		display: flex;
		flex-direction: column;
		gap: 3rem;
	}

	.device-section {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.5rem;
		padding: 1.5rem;
	}

	.section-title {
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--text-primary);
		margin-bottom: 0.25rem;
	}

	.section-description {
		font-size: 0.875rem;
		color: var(--text-muted);
		margin-bottom: 1.5rem;
	}

	.device-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
		gap: 1rem;
	}

	.device-card {
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 0.5rem;
		padding: 1.25rem;
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.device-card.paired {
		border-left: 3px solid var(--positive);
	}

	.device-card.unpaired {
		border-left: 3px solid var(--text-muted);
	}

	.device-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 1rem;
	}

	.device-info {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex: 1;
		min-width: 0;
	}

	.device-color-badge {
		width: 2.5rem;
		height: 2.5rem;
		border-radius: 0.375rem;
		flex-shrink: 0;
	}

	.device-name {
		font-size: 1rem;
		font-weight: 600;
		color: var(--text-primary);
		margin-bottom: 0.125rem;
	}

	.device-id {
		font-size: 0.75rem;
		color: var(--text-muted);
		font-family: monospace;
	}

	.device-status {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		font-size: 0.75rem;
		font-weight: 500;
		padding: 0.25rem 0.625rem;
		border-radius: 9999px;
		white-space: nowrap;
	}

	.device-status.paired {
		background: var(--positive-muted);
		color: var(--positive);
	}

	.device-status.unpaired {
		background: var(--bg-hover);
		color: var(--text-muted);
	}

	.status-dot {
		width: 0.5rem;
		height: 0.5rem;
		border-radius: 50%;
		background: currentColor;
	}

	.device-details {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		padding: 0.75rem 0;
		border-top: 1px solid var(--border-subtle);
		border-bottom: 1px solid var(--border-subtle);
	}

	.detail-row {
		display: flex;
		justify-content: space-between;
		font-size: 0.8125rem;
	}

	.detail-label {
		color: var(--text-muted);
	}

	.detail-value {
		color: var(--text-secondary);
		font-weight: 500;
	}

	.detail-value.mono {
		font-family: monospace;
		font-size: 0.75rem;
	}

	.btn-primary,
	.btn-secondary {
		padding: 0.5rem 1rem;
		border-radius: 0.375rem;
		font-size: 0.875rem;
		font-weight: 500;
		cursor: pointer;
		transition: all var(--transition);
		border: 1px solid transparent;
	}

	.btn-primary {
		background: var(--accent);
		color: white;
	}

	.btn-primary:hover {
		background: var(--accent-hover);
	}

	.btn-secondary {
		background: var(--bg-surface);
		border-color: var(--border-default);
		color: var(--text-secondary);
	}

	.btn-secondary:hover {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.btn-sm {
		padding: 0.375rem 0.75rem;
		font-size: 0.8125rem;
	}

	.empty-state {
		padding: 2rem;
		text-align: center;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.loading-state {
		padding: 3rem;
		text-align: center;
		color: var(--text-muted);
	}

	.error-state {
		padding: 2rem;
		text-align: center;
		color: var(--negative);
	}

	.error-state button {
		margin-top: 1rem;
	}
</style>
```

**Step 3: Add devices page route handler**

In `backend/main.py` at line 297 (after /system route):

```python
@app.get("/devices", response_class=FileResponse)
async def serve_devices():
    """Serve the devices page."""
    return FileResponse(static_dir / "devices.html")
```

**Step 4: Add navigation link in layout**

In `frontend/src/routes/+layout.svelte`, add link to navigation:

```svelte
<a href="/devices" class:active={$page.url.pathname === '/devices'}>Devices</a>
```

**Step 5: Test manually**

Start the server and navigate to http://localhost:8000/devices
Expected: Devices page loads with detected devices

**Step 6: Commit**

```bash
git add frontend/src/routes/devices/ frontend/src/lib/api/devices.ts backend/main.py frontend/src/routes/+layout.svelte
git commit -m "feat: add devices management page for pairing workflow"
```

---

## Task 7: Update Dashboard to Show Pairing Status

**Files:**
- Modify: `frontend/src/lib/components/TiltCard.svelte`

**Step 1: Add visual indicator for unpaired devices**

In `frontend/src/lib/components/TiltCard.svelte` at line 205 (after signal indicator):

```svelte
			<!-- Signal indicator -->
			<div class="flex flex-col items-end gap-1" title="{signal.label} signal ({tilt.rssi} dBm)">
				<!-- ... existing signal bars ... -->
			</div>

			<!-- Pairing status indicator (new) -->
			{#if !tilt.paired}
				<div class="pairing-badge" title="Device not paired - readings not being logged">
					<svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
					</svg>
					Unpaired
				</div>
			{/if}
		</div>
```

**Step 2: Add styling for pairing badge**

In the `<style>` section at the end:

```css
	.pairing-badge {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		padding: 0.25rem 0.5rem;
		background: var(--warning-muted);
		color: var(--warning);
		border: 1px solid var(--warning);
		border-radius: 0.25rem;
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.025em;
	}
```

**Step 3: Commit**

```bash
git add frontend/src/lib/components/TiltCard.svelte
git commit -m "feat: show pairing status indicator on dashboard"
```

---

## Task 8: Update Batch Creation to Only Show Paired Devices

**Files:**
- Modify: `frontend/src/routes/batches/new/+page.svelte`
- Modify: `backend/routers/devices.py` (add query param for paired filter)

**Step 1: Add paired filter to devices endpoint**

In `backend/routers/devices.py` (if it doesn't exist, modify tilts router):

```python
@router.get("/api/devices", response_model=list[DeviceResponse])
async def list_devices(
    paired_only: bool = Query(False, description="Only return paired devices"),
    db: AsyncSession = Depends(get_db)
):
    """List all devices, optionally filtering to paired only."""
    query = select(Device).order_by(Device.name)
    if paired_only:
        query = query.where(Device.paired == True)

    result = await db.execute(query)
    return result.scalars().all()
```

**Step 2: Update batch form to fetch only paired devices**

In `frontend/src/routes/batches/new/+page.svelte`, modify device fetching:

```typescript
// Fetch only paired devices for batch assignment
const devices = await fetchApi('/api/devices?paired_only=true');
```

**Step 3: Add user-friendly message if no paired devices**

Add conditional rendering in the form:

```svelte
{#if availableDevices.length === 0}
	<div class="warning-message">
		<p>No paired devices available. Please <a href="/devices">pair a device</a> before creating a batch.</p>
	</div>
{/if}
```

**Step 4: Commit**

```bash
git add backend/routers/devices.py frontend/src/routes/batches/new/+page.svelte
git commit -m "feat: only show paired devices in batch creation"
```

---

## Task 9: Documentation and User Guide

**Files:**
- Create: `docs/device-pairing.md`
- Modify: `README.md`

**Step 1: Create device pairing documentation**

Create `docs/device-pairing.md`:

```markdown
# Device Pairing Workflow

## Overview

As of v2.3.0, BrewSignal requires devices to be explicitly paired before logging readings to the database. This prevents unwanted data pollution from nearby Tilt devices that aren't actively being used for fermentation monitoring.

## How It Works

### Detection vs. Pairing

- **Detection**: BrewSignal continuously scans for Tilt devices via Bluetooth. All detected devices appear on the dashboard with live readings.
- **Pairing**: Only paired devices have their readings logged to the database and can be assigned to batches.

### Workflow

1. **New Device Detected**: When a Tilt is first detected, it's created in the database with `paired=False`
2. **Dashboard Display**: The device appears on the dashboard with an "Unpaired" badge
3. **Manual Pairing**: Navigate to `/devices` and click "Pair Device"
4. **Reading Storage**: Once paired, readings are stored in the database
5. **Batch Assignment**: Only paired devices can be selected when creating a new batch

## Managing Devices

### Pairing a Device

1. Navigate to **Devices** page
2. Find the device in the "Detected Devices" section
3. Click **Pair Device**
4. The device moves to "Paired Devices" and readings start logging

### Unpairing a Device

1. Navigate to **Devices** page
2. Find the device in the "Paired Devices" section
3. Click **Unpair Device**
4. Reading storage stops immediately (but device remains detected)

## API Endpoints

### Pair Device
```
POST /api/tilts/{tilt_id}/pair
```

### Unpair Device
```
POST /api/tilts/{tilt_id}/unpair
```

### List Devices
```
GET /api/tilts
GET /api/devices?paired_only=true
```

## Migration Notes

Existing installations will have all previously detected Tilts set to `paired=False` by default. You'll need to manually pair devices after upgrading to continue logging readings.
```

**Step 2: Update README with pairing workflow info**

Add section to `README.md`:

```markdown
## Device Pairing (v2.3.0+)

Tilt devices must be **paired** before readings are logged. This prevents data pollution from nearby devices.

- Navigate to **Devices** page to pair/unpair devices
- Only paired devices log readings and can be assigned to batches
- Unpaired devices still appear on dashboard with live readings
```

**Step 3: Commit**

```bash
git add docs/device-pairing.md README.md
git commit -m "docs: add device pairing workflow documentation"
```

---

## Task 10: Integration Testing

**Files:**
- Create: `tests/integration/test_pairing_workflow.py`

**Step 1: Write end-to-end pairing workflow test**

Create `tests/integration/test_pairing_workflow.py`:

```python
import pytest
import asyncio
from httpx import AsyncClient
from backend.main import app
from backend.database import init_db, async_session_factory
from backend.models import Tilt, Reading
from sqlalchemy import select, func

@pytest.mark.asyncio
async def test_full_pairing_workflow():
    """Test complete pairing workflow from detection to reading storage."""

    # Initialize test database
    await init_db()

    async with AsyncClient(app=app, base_url="http://test") as client:
        # Step 1: Simulate device detection (unpaired by default)
        async with async_session_factory() as session:
            tilt = Tilt(
                id="tilt-green",
                color="GREEN",
                beer_name="Untitled",
                paired=False
            )
            session.add(tilt)
            await session.commit()

        # Step 2: Verify device appears in list as unpaired
        response = await client.get("/api/tilts")
        assert response.status_code == 200
        tilts = response.json()
        green_tilt = next(t for t in tilts if t["id"] == "tilt-green")
        assert green_tilt["paired"] is False

        # Step 3: Simulate reading - should NOT be stored
        from backend.scanner import TiltReading
        from backend.main import handle_tilt_reading

        reading = TiltReading(
            id="tilt-green",
            color="GREEN",
            mac="AA:BB:CC:DD:EE:FF",
            sg=1.050,
            temp_f=68.0,
            rssi=-45
        )

        await handle_tilt_reading(reading)

        # Verify no reading was stored
        async with async_session_factory() as session:
            result = await session.execute(
                select(func.count()).select_from(Reading).where(Reading.tilt_id == "tilt-green")
            )
            count = result.scalar()
            assert count == 0, "Reading should not be stored for unpaired device"

        # Step 4: Pair the device
        response = await client.post("/api/tilts/tilt-green/pair")
        assert response.status_code == 200
        data = response.json()
        assert data["paired"] is True

        # Step 5: Simulate another reading - should BE stored
        reading2 = TiltReading(
            id="tilt-green",
            color="GREEN",
            mac="AA:BB:CC:DD:EE:FF",
            sg=1.048,
            temp_f=67.0,
            rssi=-47
        )

        await handle_tilt_reading(reading2)

        # Verify reading WAS stored
        async with async_session_factory() as session:
            result = await session.execute(
                select(func.count()).select_from(Reading).where(Reading.tilt_id == "tilt-green")
            )
            count = result.scalar()
            assert count == 1, "Reading should be stored for paired device"

        # Step 6: Unpair the device
        response = await client.post("/api/tilts/tilt-green/unpair")
        assert response.status_code == 200
        data = response.json()
        assert data["paired"] is False

        # Step 7: Simulate third reading - should NOT be stored
        reading3 = TiltReading(
            id="tilt-green",
            color="GREEN",
            mac="AA:BB:CC:DD:EE:FF",
            sg=1.046,
            temp_f=66.0,
            rssi=-48
        )

        await handle_tilt_reading(reading3)

        # Verify reading count unchanged (still 1)
        async with async_session_factory() as session:
            result = await session.execute(
                select(func.count()).select_from(Reading).where(Reading.tilt_id == "tilt-green")
            )
            count = result.scalar()
            assert count == 1, "No additional reading should be stored after unpairing"
```

**Step 2: Run integration test**

Run: `pytest tests/integration/test_pairing_workflow.py -v -s`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/integration/test_pairing_workflow.py
git commit -m "test: add end-to-end pairing workflow integration test"
```

---

## Task 11: Final Verification and Cleanup

**Step 1: Run all tests**

Run: `pytest -v`
Expected: All tests pass

**Step 2: Manual testing checklist (use TodoWrite)**

- [ ] Start fresh instance, detect new Tilt (should be unpaired)
- [ ] Verify dashboard shows "Unpaired" badge
- [ ] Verify readings are NOT stored while unpaired
- [ ] Navigate to /devices page
- [ ] Pair the device
- [ ] Verify readings ARE stored after pairing
- [ ] Create new batch - verify only paired devices shown
- [ ] Unpair device
- [ ] Verify readings stop being stored

**Step 3: Update CHANGELOG**

Add to `CHANGELOG.md`:

```markdown
## [2.3.0] - 2025-12-02

### Added
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
```

**Step 4: Bump version**

Update version in:
- `backend/routers/system.py` (VERSION constant)
- `package.json` (if exists)

**Step 5: Final commit**

```bash
git add CHANGELOG.md backend/routers/system.py
git commit -m "chore: bump version to 2.3.0 for device pairing release"
```

**Step 6: Create pull request**

```bash
git push origin feature/device-pairing
gh pr create --title "feat: implement device pairing workflow (#35)" --body "Closes #35

## Summary
- Added `paired` field to Tilt and Device models
- Modified reading storage to only log paired devices
- Created /devices management page for pairing workflow
- Updated dashboard to show pairing status
- Added migration for existing databases

## Testing
- Unit tests for models, endpoints, reading storage logic
- Integration test for full pairing workflow
- Manual testing completed

## Breaking Changes
Existing devices will be unpaired after upgrade and must be manually paired to resume logging."
```

---

## Plan Complete

**Execution handoff:**

Plan complete and saved to `docs/plans/2025-12-02-device-pairing-workflow.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
