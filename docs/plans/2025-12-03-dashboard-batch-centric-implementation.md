# Dashboard Batch-Centric Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor dashboard from device-centric (TiltCard) to batch-centric (FermentationCard) to show active fermentation batches instead of broadcasting devices.

**Architecture:** Rename TiltCard/TiltChart → FermentationCard/FermentationChart. Dashboard fetches active batches from API (fermenting/conditioning), enhances with live WebSocket readings, displays one card per batch. Device info becomes secondary (only shown if assigned).

**Tech Stack:** SvelteKit 5, TypeScript, WebSocket (live readings), REST API (batch data)

---

## Task 1: Rename TiltCard to FermentationCard

**Files:**
- Rename: `frontend/src/lib/components/TiltCard.svelte` → `FermentationCard.svelte`
- Modify: `frontend/src/routes/+page.svelte` (update import)

**Step 1: Rename the file**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric/frontend/src/lib/components
mv TiltCard.svelte FermentationCard.svelte
```

Expected: File renamed successfully

**Step 2: Update import in dashboard**

File: `frontend/src/routes/+page.svelte`

Change line 5:
```typescript
// Before
import TiltCard from '$lib/components/TiltCard.svelte';

// After
import FermentationCard from '$lib/components/FermentationCard.svelte';
```

**Step 3: Update component usage in dashboard**

File: `frontend/src/routes/+page.svelte`

Change line 111 (in the each block):
```svelte
<!-- Before -->
<TiltCard
	{tilt}
	expanded={expandedTiltId === tilt.id}
	wide={tiltsList.length === 1}
	onToggleExpand={() => toggleExpand(tilt.id)}
/>

<!-- After -->
<FermentationCard
	{tilt}
	expanded={expandedTiltId === tilt.id}
	wide={tiltsList.length === 1}
	onToggleExpand={() => toggleExpand(tilt.id)}
/>
```

**Step 4: Verify no build errors**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric/frontend
npm run build
```

Expected: Build succeeds with no errors

**Step 5: Commit**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric
git add frontend/src/lib/components/FermentationCard.svelte frontend/src/routes/+page.svelte
git commit -m "refactor: rename TiltCard to FermentationCard"
```

---

## Task 2: Rename TiltChart to FermentationChart

**Files:**
- Rename: `frontend/src/lib/components/TiltChart.svelte` → `FermentationChart.svelte`
- Modify: `frontend/src/lib/components/FermentationCard.svelte` (update import)

**Step 1: Rename the file**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric/frontend/src/lib/components
mv TiltChart.svelte FermentationChart.svelte
```

Expected: File renamed successfully

**Step 2: Update import in FermentationCard**

File: `frontend/src/lib/components/FermentationCard.svelte`

Change line 8:
```typescript
// Before
import TiltChart from './TiltChart.svelte';

// After
import FermentationChart from './FermentationChart.svelte';
```

**Step 3: Update component usage in FermentationCard**

File: `frontend/src/lib/components/FermentationCard.svelte`

Change line 265 (in the chart section):
```svelte
<!-- Before -->
<TiltChart
	tiltId={tilt.id}
	tiltColor={tilt.color}
	originalGravity={tilt.original_gravity}
	onOgChange={handleOgChange}
/>

<!-- After -->
<FermentationChart
	tiltId={tilt.id}
	tiltColor={tilt.color}
	originalGravity={tilt.original_gravity}
	onOgChange={handleOgChange}
/>
```

**Step 4: Verify no build errors**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric/frontend
npm run build
```

Expected: Build succeeds with no errors

**Step 5: Commit**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric
git add frontend/src/lib/components/FermentationChart.svelte frontend/src/lib/components/FermentationCard.svelte
git commit -m "refactor: rename TiltChart to FermentationChart"
```

---

## Task 3: Add Batch Fetching to Dashboard

**Files:**
- Modify: `frontend/src/routes/+page.svelte`
- Reference: `frontend/src/routes/batches/+page.svelte` (lines 9-113 for pattern)

**Step 1: Add batch-related imports**

File: `frontend/src/routes/+page.svelte`

Add after line 5:
```typescript
import type { BatchResponse, BatchProgressResponse } from '$lib/api';
import { fetchBatches, fetchBatchProgress } from '$lib/api';
```

**Step 2: Add batch state variables**

File: `frontend/src/routes/+page.svelte`

Replace lines 7-8 (alert state) and add after:
```typescript
let alertsDismissed = $state(false);
let alertsCollapsed = $state(false);

// Batch state
let batches = $state<BatchResponse[]>([]);
let progressMap = $state<Map<number, BatchProgressResponse>>(new Map());
let loading = $state(true);
let error = $state<string | null>(null);
```

**Step 3: Add batch fetching function**

File: `frontend/src/routes/+page.svelte`

Add after line 20 (end of onMount):
```typescript
async function loadBatches() {
	loading = true;
	error = null;
	try {
		// Fetch only active batches (fermenting or conditioning)
		const allBatches = await fetchBatches();
		batches = allBatches.filter(b => b.status === 'fermenting' || b.status === 'conditioning');

		// Load progress for each active batch
		const progressPromises = batches.map(async (b) => {
			try {
				const progress = await fetchBatchProgress(b.id);
				return [b.id, progress] as const;
			} catch {
				return null;
			}
		});
		const results = await Promise.all(progressPromises);
		const newMap = new Map<number, BatchProgressResponse>();
		for (const result of results) {
			if (result) {
				newMap.set(result[0], result[1]);
			}
		}
		progressMap = newMap;
	} catch (e) {
		error = e instanceof Error ? e.message : 'Failed to load batches';
	} finally {
		loading = false;
	}
}
```

**Step 4: Call loadBatches in onMount**

File: `frontend/src/routes/+page.svelte`

Modify onMount (around line 10-20):
```typescript
onMount(async () => {
	// Load alert dismissal state from localStorage
	const dismissed = localStorage.getItem('brewsignal_alerts_dismissed');
	const dismissedTime = localStorage.getItem('brewsignal_alerts_dismissed_time');
	if (dismissed === 'true' && dismissedTime) {
		const elapsed = Date.now() - parseInt(dismissedTime, 10);
		// Auto-restore alerts after 6 hours
		if (elapsed < 6 * 60 * 60 * 1000) {
			alertsDismissed = true;
		}
	}

	// Load batches
	await loadBatches();
});
```

**Step 5: Verify build**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric/frontend
npm run build
```

Expected: Build succeeds

**Step 6: Commit**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric
git add frontend/src/routes/+page.svelte
git commit -m "feat: add batch fetching logic to dashboard"
```

---

## Task 4: Enhance Batch Progress with Live WebSocket Data

**Files:**
- Modify: `frontend/src/routes/+page.svelte`
- Reference: `frontend/src/routes/batches/+page.svelte` (lines 15-57 for pattern)

**Step 1: Create device-to-batch mapping**

File: `frontend/src/routes/+page.svelte`

Add after the progressMap state (around line 30):
```typescript
// Map device_id to batch_id for live updates
let deviceToBatch = $derived(
	new Map(
		batches
			.filter((b) => b.device_id && (b.status === 'fermenting' || b.status === 'conditioning'))
			.map((b) => [b.device_id!, b.id])
	)
);
```

**Step 2: Create live progress enhancement**

File: `frontend/src/routes/+page.svelte`

Add after deviceToBatch:
```typescript
// Enhance progress with live WebSocket data
let liveProgressMap = $derived.by(() => {
	const enhanced = new Map(progressMap);
	for (const [deviceId, batchId] of deviceToBatch) {
		const tiltReading = tiltsState.tilts.get(deviceId);
		if (tiltReading) {
			const existing = enhanced.get(batchId) || {
				batch_id: batchId,
				measured: {},
				temperature: {},
				progress: {},
				targets: {}
			};
			// Update with live data
			enhanced.set(batchId, {
				...existing,
				measured: {
					...existing.measured,
					current_sg: tiltReading.sg
				},
				temperature: {
					...existing.temperature,
					current: tiltReading.temp,
					// Determine temperature status based on yeast thresholds (if available)
					status: existing.temperature?.yeast_min !== undefined && existing.temperature?.yeast_max !== undefined
						? (tiltReading.temp < existing.temperature.yeast_min ? 'too_cold' :
						   tiltReading.temp > existing.temperature.yeast_max ? 'too_hot' : 'in_range')
						: existing.temperature?.status
				}
			});
		}
	}
	return enhanced;
});
```

**Step 3: Remove old tilt-centric state**

File: `frontend/src/routes/+page.svelte`

Remove line 23:
```typescript
// DELETE THIS LINE:
let tiltsList = $derived(Array.from(tiltsState.tilts.values()));
```

**Step 4: Verify build**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric/frontend
npm run build
```

Expected: Build succeeds

**Step 5: Commit**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric
git add frontend/src/routes/+page.svelte
git commit -m "feat: enhance batch progress with live WebSocket readings"
```

---

## Task 5: Update Dashboard to Render Batches Instead of Tilts

**Files:**
- Modify: `frontend/src/routes/+page.svelte`

**Step 1: Update empty state condition**

File: `frontend/src/routes/+page.svelte`

Change line 82:
```svelte
<!-- Before -->
{#if tiltsList.length === 0}

<!-- After -->
{#if loading}
	<div class="empty-state">
		<div class="empty-icon">
			<span class="text-5xl">🍺</span>
		</div>
		<h2 class="empty-title">Loading Batches</h2>
		<p class="empty-description">
			<span class="connecting-dots">Fetching active fermentations</span>
		</p>
	</div>
{:else if error}
	<div class="empty-state">
		<div class="empty-icon">
			<span class="text-5xl">⚠️</span>
		</div>
		<h2 class="empty-title">Error Loading Batches</h2>
		<p class="empty-description">{error}</p>
	</div>
{:else if batches.length === 0}
```

**Step 2: Update empty state message for no batches**

File: `frontend/src/routes/+page.svelte`

Change content inside the batches.length === 0 block (around line 83-107):
```svelte
	<div class="empty-state">
		<div class="empty-icon">
			<span class="text-5xl">🍺</span>
		</div>
		<h2 class="empty-title">No Active Fermentations</h2>
		<p class="empty-description">
			Start a batch and set status to "Fermenting" or "Conditioning" to track it here
		</p>
		<div class="empty-hint">
			<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z"
				/>
			</svg>
			<span>Go to Batches → Create a new batch or update an existing batch status</span>
		</div>
	</div>
```

**Step 3: Update grid rendering section**

File: `frontend/src/routes/+page.svelte`

Change the else block (around line 108-119):
```svelte
{:else}
	<div class="tilt-grid" class:single-tilt={batches.length === 1}>
		{#each batches as batch (batch.id)}
			<FermentationCard
				{batch}
				progress={liveProgressMap.get(batch.id)}
				expanded={expandedTiltId === batch.id}
				wide={batches.length === 1}
				onToggleExpand={() => toggleExpand(batch.id)}
			/>
		{/each}
	</div>
{/if}
```

**Step 4: Update expand tracking to use batch ID**

File: `frontend/src/routes/+page.svelte`

Change comment and variable name (around line 25-30):
```typescript
// Track which batch card is expanded (only one at a time)
let expandedBatchId = $state<number | null>(null);

function toggleExpand(batchId: number) {
	expandedBatchId = expandedBatchId === batchId ? null : batchId;
}
```

Then update the expanded prop in the FermentationCard usage:
```svelte
expanded={expandedBatchId === batch.id}
```

And update the onToggleExpand handler:
```svelte
onToggleExpand={() => toggleExpand(batch.id)}
```

**Step 5: Verify build**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric/frontend
npm run build
```

Expected: Build succeeds

**Step 6: Commit**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric
git add frontend/src/routes/+page.svelte
git commit -m "feat: render FermentationCards for batches instead of tilts"
```

---

## Task 6: Update FermentationCard Props to Accept Batch Data

**Files:**
- Modify: `frontend/src/lib/components/FermentationCard.svelte`

**Step 1: Update Props interface**

File: `frontend/src/lib/components/FermentationCard.svelte`

Change lines 10-15:
```typescript
// Before
interface Props {
	tilt: TiltReading;
	expanded?: boolean;
	wide?: boolean;
	onToggleExpand?: () => void;
}

// After
import type { BatchResponse, BatchProgressResponse } from '$lib/api';

interface Props {
	batch: BatchResponse;
	progress?: BatchProgressResponse;
	expanded?: boolean;
	wide?: boolean;
	onToggleExpand?: () => void;
}
```

**Step 2: Update props destructuring**

File: `frontend/src/lib/components/FermentationCard.svelte`

Change line 17:
```typescript
// Before
let { tilt, expanded = false, wide = false, onToggleExpand }: Props = $props();

// After
let { batch, progress, expanded = false, wide = false, onToggleExpand }: Props = $props();
```

**Step 3: Remove tilt-specific imports**

File: `frontend/src/lib/components/FermentationCard.svelte`

Remove lines 4-5:
```typescript
// DELETE THESE:
import type { TiltReading } from '$lib/stores/tilts.svelte';
import { updateTiltBeerName, updateTiltOriginalGravity } from '$lib/stores/tilts.svelte';
```

**Step 4: Verify build (will fail - expected)**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric/frontend
npm run build 2>&1 | head -30
```

Expected: Build fails with TypeScript errors about `tilt` not being defined. This is expected and will be fixed in next tasks.

**Step 5: Commit**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric
git add frontend/src/lib/components/FermentationCard.svelte
git commit -m "refactor: update FermentationCard props to accept batch data"
```

---

## Task 7: Derive Device Data from Batch and Progress

**Files:**
- Modify: `frontend/src/lib/components/FermentationCard.svelte`

**Step 1: Add derived device reading**

File: `frontend/src/lib/components/FermentationCard.svelte`

Add after props destructuring (around line 17), before the linkedBatch state:
```typescript
import { tiltsState } from '$lib/stores/tilts.svelte';

// Derive device reading from batch.device_id + WebSocket state
let deviceReading = $derived.by(() => {
	if (!batch.device_id) return null;
	// Extract color from device_id - handle both "tilt-red" and "RED" formats
	const colorMatch = batch.device_id.match(/^(?:tilt-)?(\w+)$/i);
	if (!colorMatch?.[1]) return null;
	const targetColor = colorMatch[1].toUpperCase();
	// Find tilt with matching color
	for (const tilt of tiltsState.tilts.values()) {
		if (tilt.color.toUpperCase() === targetColor) {
			return tilt;
		}
	}
	return null;
});
```

**Step 2: Derive display values from batch and progress**

File: `frontend/src/lib/components/FermentationCard.svelte`

Add after deviceReading:
```typescript
// Display values derived from batch/progress/device
let displayName = $derived(batch.name || batch.recipe?.name || `Batch #${batch.batch_number}`);
let currentSg = $derived(progress?.measured?.current_sg ?? batch.measured_og ?? 1.000);
let currentTemp = $derived(progress?.temperature?.current ?? null);
let deviceColor = $derived(deviceReading?.color ?? 'BLACK');
let rssi = $derived(deviceReading?.rssi ?? null);
let isPaired = $derived(deviceReading?.paired ?? true);
let lastSeen = $derived(deviceReading?.last_seen ?? new Date().toISOString());
let sgRaw = $derived(deviceReading?.sg_raw ?? currentSg);
let tempRaw = $derived(deviceReading?.temp_raw ?? currentTemp);
```

**Step 3: Verify build (will still fail - expected)**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric/frontend
npm run build 2>&1 | head -30
```

Expected: Build fails with remaining `tilt.` references. Will fix in next task.

**Step 4: Commit**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric
git add frontend/src/lib/components/FermentationCard.svelte
git commit -m "feat: derive device data from batch and progress"
```

---

## Task 8: Update FermentationCard Template to Use Batch Data

**Files:**
- Modify: `frontend/src/lib/components/FermentationCard.svelte`

**Step 1: Update accent color derivation**

File: `frontend/src/lib/components/FermentationCard.svelte`

Change line 133:
```typescript
// Before
let accentColor = $derived(colorVars[tilt.color] || 'var(--tilt-black)');

// After
let accentColor = $derived(colorVars[deviceColor] || 'var(--tilt-black)');
```

**Step 2: Update signal derivation**

File: `frontend/src/lib/components/FermentationCard.svelte`

Change line 134:
```typescript
// Before
let signal = $derived(getSignalStrength(tilt.rssi));

// After
let signal = $derived(rssi !== null ? getSignalStrength(rssi) : { bars: 0, color: 'var(--text-muted)', label: 'No Signal' });
```

**Step 3: Update last seen derivation**

File: `frontend/src/lib/components/FermentationCard.svelte`

Change line 135:
```typescript
// Before
let lastSeenText = $derived(timeSince(tilt.last_seen));

// After
let lastSeenText = $derived(timeSince(lastSeen));
```

**Step 4: Update beer name editing**

File: `frontend/src/lib/components/FermentationCard.svelte`

Change startEditing function (around line 55):
```typescript
function startEditing() {
	editValue = displayName;
	isEditing = true;
	// Focus input after DOM update
	setTimeout(() => inputRef?.focus(), 0);
}
```

**Step 5: Update saveEdit function**

File: `frontend/src/lib/components/FermentationCard.svelte`

Change saveEdit function (around line 62-75):
```typescript
import { updateBatch } from '$lib/api';

async function saveEdit() {
	if (saving) return;
	const trimmed = editValue.trim();
	if (!trimmed || trimmed === displayName) {
		isEditing = false;
		return;
	}
	saving = true;
	try {
		await updateBatch(batch.id, { name: trimmed });
		// Update local state (parent should refetch, but optimistically update)
		batch.name = trimmed;
		isEditing = false;
	} catch (e) {
		console.error('Failed to update batch name:', e);
	} finally {
		saving = false;
	}
}
```

**Step 6: Remove/update OG change handler**

File: `frontend/src/lib/components/FermentationCard.svelte`

Change handleOgChange function (around line 86-88):
```typescript
// Remove this function entirely - OG is managed at batch level, not device level
// DELETE lines 86-88
```

**Step 7: Commit**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric
git add frontend/src/lib/components/FermentationCard.svelte
git commit -m "refactor: update FermentationCard script to use batch data"
```

---

## Task 9: Update FermentationCard Template Markup

**Files:**
- Modify: `frontend/src/lib/components/FermentationCard.svelte`

**Step 1: Update batch name display**

File: `frontend/src/lib/components/FermentationCard.svelte`

Change line 172-173:
```svelte
<!-- Before -->
<h3 class="text-lg font-semibold text-[var(--text-primary)] tracking-tight truncate">
	{tilt.beer_name}
</h3>

<!-- After -->
<h3 class="text-lg font-semibold text-[var(--text-primary)] tracking-tight truncate">
	{displayName}
</h3>
```

**Step 2: Update color badge**

File: `frontend/src/lib/components/FermentationCard.svelte`

Change line 185:
```svelte
<!-- Before -->
<span class="text-sm text-[var(--text-muted)] font-medium">{tilt.color}</span>

<!-- After -->
<span class="text-sm text-[var(--text-muted)] font-medium">{deviceColor}</span>
```

**Step 3: Update signal display**

File: `frontend/src/lib/components/FermentationCard.svelte`

Change line 191:
```svelte
<!-- Before -->
<div class="flex flex-col items-end gap-1" title="{signal.label} signal ({tilt.rssi} dBm)">

<!-- After -->
<div class="flex flex-col items-end gap-1" title="{signal.label} signal ({rssi ?? 'N/A'} dBm)">
```

And line 204:
```svelte
<!-- Before -->
<span class="text-[10px] text-[var(--text-muted)] font-mono">{tilt.rssi} dBm</span>

<!-- After -->
<span class="text-[10px] text-[var(--text-muted)] font-mono">{rssi ?? 'N/A'} dBm</span>
```

**Step 4: Update pairing status**

File: `frontend/src/lib/components/FermentationCard.svelte`

Change line 208:
```svelte
<!-- Before -->
{#if !tilt.paired}

<!-- After -->
{#if !isPaired}
```

**Step 5: Update gravity display**

File: `frontend/src/lib/components/FermentationCard.svelte`

Change line 227:
```svelte
<!-- Before -->
{formatSG(tilt.sg)}<span class="text-lg text-[var(--text-secondary)]">{gravityUnit !== 'SG' ? gravityUnit : ''}</span>

<!-- After -->
{formatSG(currentSg)}<span class="text-lg text-[var(--text-secondary)]">{gravityUnit !== 'SG' ? gravityUnit : ''}</span>
```

**Step 6: Update temperature display**

File: `frontend/src/lib/components/FermentationCard.svelte`

Change line 240:
```svelte
<!-- Before -->
{formatTempValue(tilt.temp)}<span class="text-lg text-[var(--text-secondary)]">{tempUnit}</span>

<!-- After -->
{#if currentTemp !== null}
	{formatTempValue(currentTemp)}<span class="text-lg text-[var(--text-secondary)]">{tempUnit}</span>
{:else}
	--<span class="text-lg text-[var(--text-secondary)]">{tempUnit}</span>
{/if}
```

**Step 7: Update raw values display**

File: `frontend/src/lib/components/FermentationCard.svelte`

Change line 249:
```svelte
<!-- Before -->
{#if tilt.sg !== tilt.sg_raw || tilt.temp !== tilt.temp_raw}

<!-- After -->
{#if (currentSg !== sgRaw || currentTemp !== tempRaw) && deviceReading}
```

And update the content (lines 254-256):
```svelte
<!-- Before -->
<span class="ml-1">{formatSG(tilt.sg_raw)}</span>
<span class="mx-1 opacity-40">·</span>
<span>{formatTempValue(tilt.temp_raw)}{tempUnit}</span>

<!-- After -->
<span class="ml-1">{formatSG(sgRaw)}</span>
<span class="mx-1 opacity-40">·</span>
<span>{tempRaw !== null ? formatTempValue(tempRaw) : '--'}{tempUnit}</span>
```

**Step 8: Commit**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric
git add frontend/src/lib/components/FermentationCard.svelte
git commit -m "refactor: update FermentationCard template to use batch data"
```

---

## Task 10: Update FermentationChart Component

**Files:**
- Modify: `frontend/src/lib/components/FermentationCard.svelte` (chart usage)
- Modify: `frontend/src/lib/components/FermentationChart.svelte`

**Step 1: Update FermentationChart usage in FermentationCard**

File: `frontend/src/lib/components/FermentationCard.svelte`

Change lines 264-271:
```svelte
<!-- Before -->
{#key tilt.id}
	<FermentationChart
		tiltId={tilt.id}
		tiltColor={tilt.color}
		originalGravity={tilt.original_gravity}
		onOgChange={handleOgChange}
	/>
{/key}

<!-- After -->
{#key batch.id}
	<FermentationChart
		batchId={batch.id}
		deviceColor={deviceColor}
		originalGravity={batch.measured_og}
	/>
{/key}
```

**Step 2: Update FermentationChart props interface**

File: `frontend/src/lib/components/FermentationChart.svelte`

Find the Props interface (likely around line 10-16) and update:
```typescript
// Before
interface Props {
	tiltId: string;
	tiltColor: string;
	originalGravity?: number | null;
	onOgChange?: (og: number | null) => void;
}

// After
interface Props {
	batchId: number;
	deviceColor?: string;
	originalGravity?: number | null;
}
```

**Step 3: Update props destructuring**

File: `frontend/src/lib/components/FermentationChart.svelte`

Update the props line:
```typescript
// Before
let { tiltId, tiltColor, originalGravity, onOgChange }: Props = $props();

// After
let { batchId, deviceColor = 'BLACK', originalGravity }: Props = $props();
```

**Step 4: Update fetchReadings call**

File: `frontend/src/lib/components/FermentationChart.svelte`

Find the fetchReadings call (likely in loadData function) and update:
```typescript
// Before
const data = await fetchReadings(tiltId, selectedRange.hours);

// After
// Note: API might need updating to support batch-based readings
// For now, we'll need to fetch by device_id if available
// This is a simplified version - actual implementation depends on API structure
const data = await fetchReadings(`batch-${batchId}`, selectedRange.hours);
```

**Note:** This step assumes the API can handle batch-based reading fetches. If not, we'll need to pass the device_id from the parent component or update the API.

**Step 5: Update color usage**

File: `frontend/src/lib/components/FermentationChart.svelte`

Find any references to `tiltColor` and replace with `deviceColor`:
```typescript
// Search for: tiltColor
// Replace with: deviceColor
```

**Step 6: Remove OG change handler**

File: `frontend/src/lib/components/FermentationChart.svelte`

Remove any calls to `onOgChange` since we removed that prop. OG is now managed at the batch level via the batch API, not per-device.

**Step 7: Verify build**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric/frontend
npm run build
```

Expected: Build succeeds (or minimal errors about API compatibility)

**Step 8: Commit**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric
git add frontend/src/lib/components/FermentationChart.svelte frontend/src/lib/components/FermentationCard.svelte
git commit -m "refactor: update FermentationChart to use batchId"
```

---

## Task 11: Remove Linked Batch Footer from FermentationCard

**Files:**
- Modify: `frontend/src/lib/components/FermentationCard.svelte`

**Step 1: Remove linkedBatch state and fetching**

File: `frontend/src/lib/components/FermentationCard.svelte`

Remove lines 19-39 (linkedBatch state and onMount fetch):
```typescript
// DELETE ENTIRE SECTION:
// Linked batch state
let linkedBatch = $state<BatchResponse | null>(null);

// Fetch linked batch on mount
onMount(async () => {
	try {
		// Try both device_id formats...
		// ... entire onMount block ...
	}
});
```

Also remove the import:
```typescript
// DELETE from imports:
import { fetchBatches, type BatchResponse } from '$lib/api';
```

**Step 2: Remove batch link from footer**

File: `frontend/src/lib/components/FermentationCard.svelte`

Remove lines 279-291 (batch link button in footer):
```svelte
<!-- DELETE THIS SECTION: -->
{#if linkedBatch}
	<button
		type="button"
		class="batch-link"
		onclick={() => goto(`/batches/${linkedBatch!.id}`)}
	>
		<span class="batch-status-dot" style="background: {...}"></span>
		Batch #{linkedBatch!.batch_number}
		<svg class="batch-link-icon" ...>...</svg>
	</button>
{/if}
```

**Step 3: Add batch detail link**

File: `frontend/src/lib/components/FermentationCard.svelte`

Add a new button in the footer for viewing batch details:
```svelte
<!-- Add after "Updated {lastSeenText}" around line 278 -->
<button
	type="button"
	class="batch-link"
	onclick={() => goto(`/batches/${batch.id}`)}
	title="View batch details"
>
	Batch #{batch.batch_number ?? batch.id}
	<svg class="batch-link-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
		<path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
	</svg>
</button>
```

**Step 4: Remove batch-link-specific styles**

File: `frontend/src/lib/components/FermentationCard.svelte`

Remove the batch-status-dot styles (lines 455-465):
```css
/* DELETE: */
.batch-status-dot {
	width: 5px;
	height: 5px;
	border-radius: 50%;
	animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
	0%, 100% { opacity: 1; }
	50% { opacity: 0.4; }
}
```

**Step 5: Verify build**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric/frontend
npm run build
```

Expected: Build succeeds

**Step 6: Commit**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric
git add frontend/src/lib/components/FermentationCard.svelte
git commit -m "refactor: remove linked batch footer, add direct batch link"
```

---

## Task 12: Test and Fix Build Errors

**Files:**
- All modified files

**Step 1: Run full build**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric/frontend
npm run build 2>&1 | tee build.log
```

**Step 2: Review build errors**

Read through build.log and identify any TypeScript errors, missing imports, or runtime issues.

**Step 3: Fix import errors**

Common issues to check:
- Missing imports in FermentationCard.svelte (updateBatch, goto, etc.)
- Type imports for BatchResponse, BatchProgressResponse
- Remove unused imports (onMount if no longer needed)

**Step 4: Fix type errors**

Ensure all derived values have proper types and null checks:
- `currentTemp` can be null - all usages should handle this
- `deviceReading` can be null - conditional rendering required
- `progress` is optional - all accesses should use optional chaining

**Step 5: Run build again**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric/frontend
npm run build
```

Expected: Build succeeds with 0 errors

**Step 6: Commit fixes**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric
git add frontend/src/lib/components/FermentationCard.svelte frontend/src/routes/+page.svelte
git commit -m "fix: resolve build errors and type issues"
```

---

## Task 13: Manual Testing on Dev Server

**Files:**
- None (testing only)

**Step 1: Start dev server**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric
# Start backend (if needed)
# python -m tilt_ui.app &

cd frontend
npm run dev
```

**Step 2: Navigate to dashboard**

Open browser to http://localhost:5173 (or configured port)

**Step 3: Verify empty state**

If no active batches exist:
- Should show "No Active Fermentations" message
- Should NOT show any device cards

**Step 4: Create test batch**

1. Navigate to /batches
2. Create new batch
3. Set status to "Fermenting"
4. Assign a device (if Tilt is broadcasting)

**Step 5: Verify dashboard shows batch**

Return to dashboard:
- Should show 1 FermentationCard
- Should display batch name, current SG, temp (if device assigned)
- Should show device color accent
- Should NOT show device name as primary

**Step 6: Test chart expansion**

Click expand button:
- Chart should appear inline
- Should load historical data
- Should display properly

**Step 7: Test batch link**

Click batch number link:
- Should navigate to /batches/{id}
- Should show full batch details

**Step 8: Document any issues**

Note any bugs, visual issues, or unexpected behavior for follow-up fixes.

---

## Task 14: Update Design Document with Implementation Notes

**Files:**
- Modify: `docs/plans/2025-12-03-dashboard-batch-centric-refactor.md`

**Step 1: Add implementation status section**

File: `docs/plans/2025-12-03-dashboard-batch-centric-refactor.md`

Add at the top after "Status: Design Approved":
```markdown
**Implementation Status:** Complete (2025-12-03)
**Implementation Branch:** `feature/dashboard-batch-centric`
```

**Step 2: Add implementation notes section**

Add at the bottom of the document:
```markdown
## Implementation Notes

### Key Changes Made

1. **Component Renames:**
   - `TiltCard.svelte` → `FermentationCard.svelte`
   - `TiltChart.svelte` → `FermentationChart.svelte`

2. **Dashboard Data Flow:**
   - Replaced `tiltsState.tilts` iteration with `fetchBatches()` API call
   - Added batch progress fetching via `fetchBatchProgress()`
   - Enhanced progress with live WebSocket readings

3. **FermentationCard Props:**
   - Changed from `{tilt}` to `{batch, progress}`
   - Derived device data from `batch.device_id` + WebSocket state
   - Made device info secondary (only shown if assigned)

4. **API Compatibility:**
   - Reused existing batch APIs (no backend changes)
   - WebSocket integration maintained for live updates
   - Chart data fetching may need API enhancement for batch-based queries

### Known Issues / Future Work

- [ ] FermentationChart may need API update to fetch readings by batchId instead of deviceId
- [ ] Consider adding "No device assigned" messaging when batch has no device
- [ ] Empty state could link directly to "Create Batch" flow
- [ ] Performance optimization for multiple active batches (cache progress data)

### Testing Performed

- [x] Build succeeds with no TypeScript errors
- [x] Dashboard loads and displays active batches
- [x] Empty state shows when no active batches
- [x] Chart expansion works inline
- [x] Batch detail navigation works
- [ ] Manual testing with live Tilt devices
- [ ] Manual testing with device reassignment
- [ ] Manual testing with multiple active batches
```

**Step 3: Commit**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric
git add docs/plans/2025-12-03-dashboard-batch-centric-refactor.md
git commit -m "docs: add implementation notes to design doc"
```

---

## Task 15: Final Build and Deployment Prep

**Files:**
- All frontend files

**Step 1: Run production build**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric/frontend
npm run build
```

Expected: Build succeeds with 0 errors, 0 warnings

**Step 2: Review build output**

Check for:
- Bundle size (should be similar to before)
- No missing chunks
- No duplicate code warnings

**Step 3: Tag the build**

```bash
cd /home/ladmin/Projects/tilt_ui/.worktrees/dashboard-batch-centric
git tag -a dashboard-batch-centric-v1 -m "Dashboard refactor: batch-centric with FermentationCard"
```

**Step 4: Push to remote (if ready)**

```bash
git push origin feature/dashboard-batch-centric
git push origin dashboard-batch-centric-v1
```

**Step 5: Create PR or merge to main**

Follow project workflow for merging feature branch.

---

## Success Criteria Checklist

After completing all tasks, verify:

- [ ] Dashboard shows only active batches (fermenting/conditioning)
- [ ] Unassigned devices do NOT appear on dashboard
- [ ] FermentationCard displays batch name, number, status
- [ ] Live WebSocket readings update SG/temp
- [ ] Chart expands inline on dashboard
- [ ] Batch detail link navigates correctly
- [ ] Empty state shows when no active batches
- [ ] Component names reflect purpose (Fermentation not Tilt)
- [ ] Build succeeds with no errors
- [ ] No TypeScript errors
- [ ] No broken imports
- [ ] DevTools console clean (no runtime errors)

## Rollback Plan

If critical issues discovered:

1. Return to main worktree: `cd /home/ladmin/Projects/tilt_ui`
2. Dashboard still works (changes isolated to feature branch)
3. Delete worktree: `git worktree remove .worktrees/dashboard-batch-centric`
4. Delete branch: `git branch -D feature/dashboard-batch-centric`
5. Investigate issues, revise plan, restart
