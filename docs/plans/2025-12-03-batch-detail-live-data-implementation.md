# Batch Detail Live Data Enhancement - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add comprehensive live measurement data, real-time fermentation calculations, and diagnostic information to the batch detail page using a modular card-based architecture.

**Architecture:** Extract existing batch detail sections into reusable card components, create new cards for live readings and fermentation metrics with real-time calculations, maintain responsive 2-column grid layout that collapses on mobile.

**Tech Stack:** SvelteKit, TypeScript, Svelte 5 runes ($state, $derived), existing API layer, WebSocket for live data

---

## Prerequisites

- Design document: `docs/plans/2025-12-03-batch-detail-live-data-design.md`
- Issue: #48 - Batch detail page missing live measurement data
- Current directory: `.worktrees/batch-detail-live-data/frontend`
- Dependencies installed and build passing

---

## Task 1: Create BatchCard Base Component

**Files:**
- Create: `src/lib/components/batch/BatchCard.svelte`

**Step 1: Create the batch components directory**

```bash
mkdir -p src/lib/components/batch
```

**Step 2: Create BatchCard base component**

Create `src/lib/components/batch/BatchCard.svelte`:

```svelte
<script lang="ts">
	interface Props {
		title: string;
		icon?: string;
		highlight?: boolean;
		collapsible?: boolean;
		expanded?: boolean;
		onToggle?: () => void;
	}

	let {
		title,
		icon,
		highlight = false,
		collapsible = false,
		expanded = false,
		onToggle,
		children
	}: Props = $props();
</script>

<div class="batch-card" class:highlight>
	{#if highlight}
		<div class="accent-bar"></div>
	{/if}

	<div class="card-header">
		<div class="header-left">
			{#if icon}
				<span class="card-icon">{icon}</span>
			{/if}
			<h3 class="card-title">{title}</h3>
		</div>

		{#if collapsible && onToggle}
			<button
				type="button"
				class="expand-btn"
				onclick={onToggle}
				aria-label={expanded ? 'Collapse' : 'Expand'}
			>
				<svg
					class="expand-icon"
					class:rotate-180={expanded}
					fill="none"
					viewBox="0 0 24 24"
					stroke="currentColor"
					stroke-width="2"
				>
					<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
				</svg>
			</button>
		{/if}
	</div>

	<div class="card-content" class:collapsed={collapsible && !expanded}>
		{@render children()}
	</div>
</div>

<style>
	.batch-card {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.75rem;
		overflow: hidden;
		transition: border-color var(--transition);
	}

	.batch-card:hover {
		border-color: var(--border-default);
	}

	.batch-card.highlight {
		border-color: rgba(245, 158, 11, 0.3);
	}

	.accent-bar {
		height: 2px;
		background: linear-gradient(90deg, #f59e0b, #f97316);
	}

	.card-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 1.25rem 1.25rem 0 1.25rem;
		margin-bottom: 1rem;
	}

	.header-left {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.card-icon {
		font-size: 1rem;
	}

	.card-title {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0;
	}

	.expand-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 1.5rem;
		height: 1.5rem;
		border-radius: 0.25rem;
		color: var(--text-muted);
		background: transparent;
		border: none;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.expand-btn:hover {
		color: var(--text-primary);
		background: var(--bg-hover);
	}

	.expand-icon {
		width: 1rem;
		height: 1rem;
		transition: transform 0.2s ease;
	}

	.expand-icon.rotate-180 {
		transform: rotate(180deg);
	}

	.card-content {
		padding: 0 1.25rem 1.25rem 1.25rem;
	}

	.card-content.collapsed {
		display: none;
	}
</style>
```

**Step 3: Test the component visually**

Import and test in batch detail page temporarily to verify styling:

Add to `src/routes/batches/[id]/+page.svelte` at line 275 (after the `{:else}` for `isEditing`):

```svelte
<!-- Test BatchCard component -->
<div style="padding: 1rem;">
	<BatchCard title="Test Card" icon="🧪">
		<p>This is a test card</p>
	</BatchCard>
</div>
```

Add import at top of script section (around line 6):

```typescript
import BatchCard from '$lib/components/batch/BatchCard.svelte';
```

**Step 4: Run dev server and verify**

```bash
npm run dev
```

Navigate to any batch detail page and verify the test card renders with proper styling.

**Step 5: Remove test code**

Remove the test card and import added in Step 3.

**Step 6: Commit**

```bash
git add src/lib/components/batch/BatchCard.svelte
git commit -m "feat: add BatchCard base component for modular card layout"
```

---

## Task 2: Create BatchLiveReadingsCard Component

**Files:**
- Create: `src/lib/components/batch/BatchLiveReadingsCard.svelte`

**Step 1: Create BatchLiveReadingsCard component**

> **IMPORTANT:** Use the `frontend-design:frontend-design` skill when implementing this component to ensure high-quality, polished visual design that matches the BrewSignal aesthetic.

Create `src/lib/components/batch/BatchLiveReadingsCard.svelte`:

```svelte
<script lang="ts">
	import type { TiltReading } from '$lib/stores/tilts.svelte';
	import { formatGravity, getGravityUnit, formatTemp, getTempUnit } from '$lib/stores/config.svelte';
	import BatchCard from './BatchCard.svelte';

	interface Props {
		liveReading: TiltReading | null;
		currentSg?: number | null;
		currentTemp?: number | null;
	}

	let { liveReading, currentSg, currentTemp }: Props = $props();

	// Use live reading if available, otherwise fall back to provided values
	let displaySg = $derived(liveReading?.sg ?? currentSg);
	let displayTemp = $derived(liveReading?.temp ?? currentTemp);
	let rawSg = $derived(liveReading?.sg_raw);
	let rawTemp = $derived(liveReading?.temp_raw);
	let rssi = $derived(liveReading?.rssi);
	let lastSeen = $derived(liveReading?.last_seen);

	// Show raw values if different from calibrated
	let showRaw = $derived(
		liveReading &&
		(liveReading.sg !== liveReading.sg_raw || liveReading.temp !== liveReading.temp_raw)
	);

	let gravityUnit = $derived(getGravityUnit());
	let tempUnit = $derived(getTempUnit());

	function formatSG(value?: number | null): string {
		if (value === undefined || value === null) return '--';
		return formatGravity(value);
	}

	function formatTempValue(value?: number | null): string {
		if (value === undefined || value === null) return '--';
		return formatTemp(value);
	}

	function getSignalStrength(rssiValue: number): { bars: number; color: string; label: string } {
		if (rssiValue >= -50) return { bars: 4, color: 'var(--positive)', label: 'Excellent' };
		if (rssiValue >= -60) return { bars: 3, color: 'var(--positive)', label: 'Good' };
		if (rssiValue >= -70) return { bars: 2, color: 'var(--warning)', label: 'Fair' };
		return { bars: 1, color: 'var(--negative)', label: 'Weak' };
	}

	function timeSince(isoString: string): string {
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

	let signal = $derived(rssi ? getSignalStrength(rssi) : null);
	let lastSeenText = $derived(lastSeen ? timeSince(lastSeen) : null);
</script>

<BatchCard title="Live Readings" highlight={true}>
	<div class="live-badge">
		<span class="live-dot"></span>
		<span class="live-text">LIVE</span>
	</div>

	<div class="readings-grid">
		<div class="reading">
			<div class="reading-value">
				{formatSG(displaySg)}
				{#if gravityUnit !== 'SG'}
					<span class="unit">{gravityUnit}</span>
				{/if}
			</div>
			<div class="reading-label">
				{gravityUnit === 'SG' ? 'Gravity' : gravityUnit === '°P' ? 'Plato' : 'Brix'}
			</div>
		</div>

		<div class="reading">
			<div class="reading-value temp">
				{formatTempValue(displayTemp)}
				<span class="unit">{tempUnit}</span>
			</div>
			<div class="reading-label">Temperature</div>
		</div>
	</div>

	{#if showRaw}
		<div class="raw-values">
			<span class="raw-label">Raw:</span>
			<span class="raw-value">{formatSG(rawSg)}</span>
			<span class="raw-separator">·</span>
			<span class="raw-value">{formatTempValue(rawTemp)}{tempUnit}</span>
		</div>
	{/if}

	{#if signal && rssi}
		<div class="signal-section">
			<div class="signal-bars">
				{#each Array(4) as _, i}
					<div
						class="signal-bar"
						style="
							height: {8 + i * 4}px;
							background: {i < signal.bars ? signal.color : 'var(--bg-hover)'};
							opacity: {i < signal.bars ? 1 : 0.4};
						"
					></div>
				{/each}
			</div>
			<div class="signal-info">
				<span class="signal-label" style="color: {signal.color}">{signal.label} Signal</span>
				<span class="signal-rssi">{rssi} dBm</span>
			</div>
		</div>
	{/if}

	{#if lastSeenText}
		<div class="last-seen">
			Updated {lastSeenText}
		</div>
	{/if}
</BatchCard>

<style>
	.live-badge {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		margin-bottom: 1rem;
		padding: 0.25rem 0.625rem;
		background: rgba(245, 158, 11, 0.12);
		border-radius: 9999px;
		font-size: 0.6875rem;
		font-weight: 600;
		color: #f59e0b;
		text-transform: uppercase;
		letter-spacing: 0.025em;
	}

	.live-dot {
		width: 6px;
		height: 6px;
		background: #f59e0b;
		border-radius: 50%;
		animation: pulse 2s ease-in-out infinite;
	}

	@keyframes pulse {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.4; }
	}

	.live-text {
		line-height: 1;
	}

	.readings-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 1rem;
		margin-bottom: 1rem;
	}

	.reading {
		text-align: center;
		padding: 1rem;
		background: var(--bg-elevated);
		border-radius: 0.5rem;
	}

	.reading-value {
		font-family: var(--font-mono);
		font-size: 2.5rem;
		font-weight: 500;
		color: var(--text-primary);
		line-height: 1;
		margin-bottom: 0.5rem;
	}

	.reading-value.temp {
		color: var(--positive);
	}

	.unit {
		font-size: 1.25rem;
		color: var(--text-secondary);
		margin-left: 0.125rem;
	}

	.reading-label {
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.raw-values {
		font-family: var(--font-mono);
		font-size: 0.6875rem;
		color: var(--text-muted);
		margin-bottom: 1rem;
		padding: 0.5rem 0.75rem;
		background: var(--bg-elevated);
		border-radius: 0.375rem;
	}

	.raw-label {
		opacity: 0.6;
	}

	.raw-value {
		margin-left: 0.25rem;
	}

	.raw-separator {
		margin: 0 0.375rem;
		opacity: 0.4;
	}

	.signal-section {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.75rem;
		background: var(--bg-elevated);
		border-radius: 0.375rem;
		margin-bottom: 0.75rem;
	}

	.signal-bars {
		display: flex;
		align-items: flex-end;
		gap: 0.25rem;
	}

	.signal-bar {
		width: 4px;
		border-radius: 2px;
		transition: all 0.2s ease;
	}

	.signal-info {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
	}

	.signal-label {
		font-size: 0.8125rem;
		font-weight: 500;
	}

	.signal-rssi {
		font-family: var(--font-mono);
		font-size: 0.6875rem;
		color: var(--text-muted);
	}

	.last-seen {
		font-size: 0.75rem;
		color: var(--text-muted);
		text-align: center;
	}

	@media (max-width: 640px) {
		.reading-value {
			font-size: 2rem;
		}
	}
</style>
```

**Step 2: Commit**

```bash
git add src/lib/components/batch/BatchLiveReadingsCard.svelte
git commit -m "feat: add BatchLiveReadingsCard with signal strength and raw values"
```

---

## Task 3: Create BatchFermentationCard Component

**Files:**
- Create: `src/lib/components/batch/BatchFermentationCard.svelte`

**Step 1: Create BatchFermentationCard component**

> **IMPORTANT:** Use the `frontend-design:frontend-design` skill when implementing this component to ensure high-quality, polished visual design.

Create `src/lib/components/batch/BatchFermentationCard.svelte`:

```svelte
<script lang="ts">
	import type { BatchResponse, BatchProgressResponse } from '$lib/api';
	import { formatGravity } from '$lib/stores/config.svelte';
	import BatchCard from './BatchCard.svelte';

	interface Props {
		batch: BatchResponse;
		currentSg?: number | null;
		progress?: BatchProgressResponse | null;
	}

	let { batch, currentSg, progress }: Props = $props();

	// Calculate real-time metrics
	let metrics = $derived.by(() => {
		if (!batch.measured_og) return null;

		const sg = currentSg ?? progress?.measured?.current_sg;
		if (!sg) return null;

		// ABV: (OG - Current SG) × 131.25
		const abv = (batch.measured_og - sg) * 131.25;

		// Attenuation: ((OG - Current SG) / (OG - 1.000)) × 100
		const attenuation = ((batch.measured_og - sg) / (batch.measured_og - 1.0)) * 100;

		return {
			currentSg: sg,
			abv: Math.max(0, abv),
			attenuation: Math.max(0, Math.min(100, attenuation)),
			isFermenting: batch.status === 'fermenting' || batch.status === 'conditioning'
		};
	});

	// Show live calculations or final measurements
	let showLive = $derived(metrics?.isFermenting ?? false);

	function formatSG(value?: number | null): string {
		if (value === undefined || value === null) return '--';
		return formatGravity(value);
	}

	function formatPercent(value?: number | null): string {
		if (value === undefined || value === null) return '--';
		return `${value.toFixed(1)}%`;
	}
</script>

<BatchCard title={showLive ? 'Fermentation Progress' : 'Fermentation Measurements'}>
	{#if metrics && showLive}
		<!-- Active fermentation with live calculations -->
		<div class="current-sg">
			<div class="sg-label">Current SG</div>
			<div class="sg-value">
				{formatSG(metrics.currentSg)}
				<span class="fermenting-badge">(fermenting)</span>
			</div>
		</div>

		<div class="gravity-timeline">
			<div class="gravity-point">
				<div class="point-label">OG</div>
				<div class="point-value">{formatSG(batch.measured_og)}</div>
			</div>
			{#if batch.recipe?.fg_target}
				<div class="gravity-point">
					<div class="point-label">FG (Target)</div>
					<div class="point-value target">{formatSG(batch.recipe.fg_target)}</div>
				</div>
			{/if}
			<div class="gravity-point">
				<div class="point-label">FG (Current)</div>
				<div class="point-value current">{formatSG(metrics.currentSg)}</div>
			</div>
		</div>

		<div class="metrics-grid">
			<div class="metric">
				<div class="metric-label">ABV</div>
				<div class="metric-value">
					{formatPercent(metrics.abv)}
					<span class="live-indicator">(live)</span>
				</div>
			</div>
			<div class="metric">
				<div class="metric-label">Attenuation</div>
				<div class="metric-value">
					{formatPercent(metrics.attenuation)}
					<span class="live-indicator">(live)</span>
				</div>
			</div>
		</div>

		{#if progress?.progress?.percent_complete != null}
			<div class="progress-section">
				<div class="progress-header">
					<span class="progress-label">Progress</span>
					<span class="progress-percent">{progress.progress.percent_complete.toFixed(0)}%</span>
				</div>
				<div class="progress-bar-container">
					<div
						class="progress-bar"
						style="width: {progress.progress.percent_complete}%"
					></div>
				</div>
				{#if progress.progress.sg_remaining != null}
					<div class="progress-remaining">
						{progress.progress.sg_remaining.toFixed(3)} SG remaining
					</div>
				{/if}
			</div>
		{/if}

	{:else if batch.measured_og}
		<!-- Completed batch or no current readings -->
		<div class="measurements-grid">
			<div class="measurement">
				<div class="measurement-label">OG</div>
				<div class="measurement-value">{formatSG(batch.measured_og)}</div>
			</div>
			<div class="measurement">
				<div class="measurement-label">FG</div>
				<div class="measurement-value">{formatSG(batch.measured_fg)}</div>
			</div>
			<div class="measurement">
				<div class="measurement-label">ABV</div>
				<div class="measurement-value">
					{batch.measured_abv != null ? formatPercent(batch.measured_abv) : '--'}
				</div>
			</div>
			<div class="measurement">
				<div class="measurement-label">Attenuation</div>
				<div class="measurement-value">
					{batch.measured_attenuation != null ? formatPercent(batch.measured_attenuation) : '--'}
				</div>
			</div>
		</div>
	{:else}
		<!-- No OG set -->
		<div class="no-data">
			<p class="no-data-text">Set Original Gravity to see fermentation metrics</p>
		</div>
	{/if}
</BatchCard>

<style>
	.current-sg {
		text-align: center;
		margin-bottom: 1.5rem;
	}

	.sg-label {
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin-bottom: 0.375rem;
	}

	.sg-value {
		font-family: var(--font-mono);
		font-size: 2rem;
		font-weight: 500;
		color: var(--text-primary);
		line-height: 1;
	}

	.fermenting-badge {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin-left: 0.5rem;
	}

	.gravity-timeline {
		display: flex;
		justify-content: space-around;
		gap: 0.75rem;
		margin-bottom: 1.5rem;
		padding: 1rem;
		background: var(--bg-elevated);
		border-radius: 0.5rem;
	}

	.gravity-point {
		text-align: center;
	}

	.point-label {
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		margin-bottom: 0.25rem;
	}

	.point-value {
		font-family: var(--font-mono);
		font-size: 1rem;
		font-weight: 500;
		color: var(--text-primary);
	}

	.point-value.target {
		color: var(--text-secondary);
	}

	.point-value.current {
		color: #f59e0b;
	}

	.metrics-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 1rem;
		margin-bottom: 1.5rem;
	}

	.metric {
		text-align: center;
		padding: 1rem;
		background: var(--bg-elevated);
		border-radius: 0.5rem;
	}

	.metric-label {
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		margin-bottom: 0.375rem;
	}

	.metric-value {
		font-family: var(--font-mono);
		font-size: 1.5rem;
		font-weight: 500;
		color: var(--text-primary);
		line-height: 1;
	}

	.live-indicator {
		font-size: 0.75rem;
		color: #f59e0b;
		margin-left: 0.375rem;
	}

	.progress-section {
		padding: 1rem;
		background: var(--bg-elevated);
		border-radius: 0.5rem;
	}

	.progress-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
	}

	.progress-label {
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
	}

	.progress-percent {
		font-family: var(--font-mono);
		font-size: 1.25rem;
		font-weight: 500;
		color: var(--positive);
	}

	.progress-bar-container {
		height: 8px;
		background: var(--bg-surface);
		border-radius: 4px;
		overflow: hidden;
		margin-bottom: 0.5rem;
	}

	.progress-bar {
		height: 100%;
		background: linear-gradient(90deg, #f59e0b, #84cc16);
		border-radius: 4px;
		transition: width 0.5s ease-out;
	}

	.progress-remaining {
		font-size: 0.75rem;
		color: var(--text-muted);
		text-align: center;
	}

	.measurements-grid {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 0.75rem;
	}

	.measurement {
		text-align: center;
	}

	.measurement-label {
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		margin-bottom: 0.375rem;
	}

	.measurement-value {
		font-family: var(--font-mono);
		font-size: 1rem;
		font-weight: 500;
		color: var(--text-primary);
	}

	.no-data {
		text-align: center;
		padding: 2rem 1rem;
	}

	.no-data-text {
		font-size: 0.875rem;
		color: var(--text-muted);
		margin: 0;
	}

	@media (max-width: 640px) {
		.measurements-grid {
			grid-template-columns: repeat(2, 1fr);
		}

		.gravity-timeline {
			flex-direction: column;
			gap: 0.5rem;
		}
	}
</style>
```

**Step 2: Commit**

```bash
git add src/lib/components/batch/BatchFermentationCard.svelte
git commit -m "feat: add BatchFermentationCard with real-time ABV and attenuation"
```

---

## Task 4: Extract Existing Sections into Card Components

**Files:**
- Create: `src/lib/components/batch/BatchTimelineCard.svelte`
- Create: `src/lib/components/batch/BatchDeviceCard.svelte`
- Create: `src/lib/components/batch/BatchRecipeTargetsCard.svelte`
- Create: `src/lib/components/batch/BatchNotesCard.svelte`

**Step 1: Create BatchTimelineCard**

Create `src/lib/components/batch/BatchTimelineCard.svelte`:

```svelte
<script lang="ts">
	import type { BatchResponse } from '$lib/api';
	import BatchCard from './BatchCard.svelte';

	interface Props {
		batch: BatchResponse;
	}

	let { batch }: Props = $props();

	function formatDate(dateStr?: string | null): string {
		if (!dateStr) return '--';
		return new Date(dateStr).toLocaleDateString('en-GB', {
			weekday: 'short',
			day: 'numeric',
			month: 'short',
			year: 'numeric'
		});
	}

	function formatDateTime(dateStr?: string | null): string {
		if (!dateStr) return '--';
		return new Date(dateStr).toLocaleString('en-GB', {
			day: 'numeric',
			month: 'short',
			hour: 'numeric',
			minute: '2-digit'
		});
	}
</script>

<BatchCard title="Timeline">
	<div class="timeline">
		<div class="timeline-item">
			<span class="timeline-label">Brew Date</span>
			<span class="timeline-value">{formatDate(batch.brew_date)}</span>
		</div>
		<div class="timeline-item">
			<span class="timeline-label">Started</span>
			<span class="timeline-value">{formatDateTime(batch.start_time)}</span>
		</div>
		<div class="timeline-item">
			<span class="timeline-label">Ended</span>
			<span class="timeline-value">{formatDateTime(batch.end_time)}</span>
		</div>
		<div class="timeline-item">
			<span class="timeline-label">Created</span>
			<span class="timeline-value">{formatDateTime(batch.created_at)}</span>
		</div>
	</div>
</BatchCard>

<style>
	.timeline {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.timeline-item {
		display: flex;
		justify-content: space-between;
		gap: 1rem;
	}

	.timeline-label {
		font-size: 0.8125rem;
		color: var(--text-muted);
	}

	.timeline-value {
		font-size: 0.8125rem;
		font-weight: 500;
		color: var(--text-secondary);
		text-align: right;
	}
</style>
```

**Step 2: Create BatchDeviceCard with enhanced signal info**

Create `src/lib/components/batch/BatchDeviceCard.svelte`:

```svelte
<script lang="ts">
	import type { BatchResponse } from '$lib/api';
	import type { TiltReading } from '$lib/stores/tilts.svelte';
	import BatchCard from './BatchCard.svelte';

	interface Props {
		batch: BatchResponse;
		liveReading: TiltReading | null;
		onEdit?: () => void;
	}

	let { batch, liveReading, onEdit }: Props = $props();

	function timeSince(isoString: string): string {
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

	function getSignalStrength(rssi: number): { bars: number; color: string; label: string } {
		if (rssi >= -50) return { bars: 4, color: 'var(--positive)', label: 'Excellent' };
		if (rssi >= -60) return { bars: 3, color: 'var(--positive)', label: 'Good' };
		if (rssi >= -70) return { bars: 2, color: 'var(--warning)', label: 'Fair' };
		return { bars: 1, color: 'var(--negative)', label: 'Weak' };
	}

	let signal = $derived(liveReading?.rssi ? getSignalStrength(liveReading.rssi) : null);
	let lastSeenText = $derived(liveReading?.last_seen ? timeSince(liveReading.last_seen) : null);
</script>

<BatchCard title="Tracking Device">
	{#if batch.device_id}
		<div class="device-info">
			{#if liveReading}
				<div class="device-status online">
					<span class="device-dot"></span>
					{liveReading.color} Tilt - Connected
				</div>

				{#if signal}
					<div class="signal-details">
						<div class="signal-bars">
							{#each Array(4) as _, i}
								<div
									class="signal-bar"
									style="
										height: {6 + i * 3}px;
										background: {i < signal.bars ? signal.color : 'var(--bg-hover)'};
										opacity: {i < signal.bars ? 1 : 0.4};
									"
								></div>
							{/each}
						</div>
						<span class="signal-text" style="color: {signal.color}">
							{signal.label} ({liveReading.rssi} dBm)
						</span>
					</div>
				{/if}

				{#if lastSeenText}
					<div class="device-last-seen">
						Updated {lastSeenText}
					</div>
				{/if}
			{:else}
				<div class="device-status offline">
					<span class="device-dot"></span>
					Device: {batch.device_id}
				</div>
				<div class="device-last-seen">Not receiving data</div>
			{/if}
		</div>
	{:else}
		<div class="no-device">
			<span>No device assigned</span>
			{#if onEdit}
				<button type="button" class="link-btn" onclick={onEdit}>
					Link a device
				</button>
			{/if}
		</div>
	{/if}
</BatchCard>

<style>
	.device-info {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.device-status {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.875rem;
		font-weight: 500;
	}

	.device-status.online {
		color: var(--positive);
	}

	.device-status.offline {
		color: var(--text-muted);
	}

	.device-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: currentColor;
	}

	.signal-details {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem 0.75rem;
		background: var(--bg-elevated);
		border-radius: 0.375rem;
	}

	.signal-bars {
		display: flex;
		align-items: flex-end;
		gap: 0.1875rem;
	}

	.signal-bar {
		width: 3px;
		border-radius: 1.5px;
		transition: all 0.2s ease;
	}

	.signal-text {
		font-size: 0.75rem;
		font-weight: 500;
	}

	.device-last-seen {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.no-device {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		font-size: 0.875rem;
		color: var(--text-muted);
	}

	.link-btn {
		align-self: flex-start;
		font-size: 0.8125rem;
		font-weight: 500;
		color: var(--accent);
		background: none;
		border: none;
		padding: 0;
		cursor: pointer;
	}

	.link-btn:hover {
		text-decoration: underline;
	}
</style>
```

**Step 3: Create BatchRecipeTargetsCard**

Create `src/lib/components/batch/BatchRecipeTargetsCard.svelte`:

```svelte
<script lang="ts">
	import type { RecipeResponse } from '$lib/api';
	import { formatGravity } from '$lib/stores/config.svelte';
	import BatchCard from './BatchCard.svelte';

	interface Props {
		recipe: RecipeResponse;
	}

	let { recipe }: Props = $props();

	function formatSG(value?: number | null): string {
		if (value === undefined || value === null) return '--';
		return formatGravity(value);
	}
</script>

<BatchCard title="Recipe Targets">
	<div class="targets-grid">
		<div class="target">
			<span class="target-label">OG</span>
			<span class="target-value">{formatSG(recipe.og_target)}</span>
		</div>
		<div class="target">
			<span class="target-label">FG</span>
			<span class="target-value">{formatSG(recipe.fg_target)}</span>
		</div>
		<div class="target">
			<span class="target-label">ABV</span>
			<span class="target-value">
				{recipe.abv_target != null ? `${recipe.abv_target.toFixed(1)}%` : '--'}
			</span>
		</div>
		{#if recipe.yeast_name}
			<div class="target wide">
				<span class="target-label">Yeast</span>
				<span class="target-value">{recipe.yeast_name}</span>
			</div>
		{/if}
	</div>
</BatchCard>

<style>
	.targets-grid {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 0.75rem;
	}

	.target {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.target.wide {
		grid-column: span 2;
	}

	.target-label {
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
	}

	.target-value {
		font-family: var(--font-mono);
		font-size: 1rem;
		font-weight: 500;
		color: var(--text-secondary);
	}

	@media (max-width: 640px) {
		.targets-grid {
			grid-template-columns: repeat(2, 1fr);
		}
	}
</style>
```

**Step 4: Create BatchNotesCard**

Create `src/lib/components/batch/BatchNotesCard.svelte`:

```svelte
<script lang="ts">
	import BatchCard from './BatchCard.svelte';

	interface Props {
		notes: string;
	}

	let { notes }: Props = $props();
</script>

<BatchCard title="Notes">
	<p class="notes-content">{notes}</p>
</BatchCard>

<style>
	.notes-content {
		font-size: 0.875rem;
		color: var(--text-secondary);
		line-height: 1.6;
		margin: 0;
		white-space: pre-wrap;
	}
</style>
```

**Step 5: Commit**

```bash
git add src/lib/components/batch/BatchTimelineCard.svelte \
        src/lib/components/batch/BatchDeviceCard.svelte \
        src/lib/components/batch/BatchRecipeTargetsCard.svelte \
        src/lib/components/batch/BatchNotesCard.svelte
git commit -m "feat: extract batch detail sections into card components"
```

---

## Task 5: Integrate Card Components into Batch Detail Page

**Files:**
- Modify: `src/routes/batches/[id]/+page.svelte`

**Step 1: Add imports for all card components**

In `src/routes/batches/[id]/+page.svelte`, add after existing imports (around line 9):

```typescript
import BatchCard from '$lib/components/batch/BatchCard.svelte';
import BatchLiveReadingsCard from '$lib/components/batch/BatchLiveReadingsCard.svelte';
import BatchFermentationCard from '$lib/components/batch/BatchFermentationCard.svelte';
import BatchTimelineCard from '$lib/components/batch/BatchTimelineCard.svelte';
import BatchDeviceCard from '$lib/components/batch/BatchDeviceCard.svelte';
import BatchRecipeTargetsCard from '$lib/components/batch/BatchRecipeTargetsCard.svelte';
import BatchNotesCard from '$lib/components/batch/BatchNotesCard.svelte';
```

**Step 2: Replace existing content grid section**

Find the section starting with `<!-- Main content grid -->` (around line 321) and replace everything from there until the closing `{/if}` before the `</div>` that closes `page-container` (around line 580).

Replace with:

```svelte
		<!-- Main content grid -->
		<div class="content-grid">
			<!-- Left column -->
			<div class="stats-section">
				<!-- Live Readings Card (only if device is linked and has live data) -->
				{#if liveReading || progress?.measured?.current_sg != null}
					<BatchLiveReadingsCard
						{liveReading}
						currentSg={progress?.measured?.current_sg}
						currentTemp={progress?.temperature?.current}
					/>
				{/if}

				<!-- Fermentation Card -->
				<BatchFermentationCard
					{batch}
					currentSg={liveReading?.sg ?? progress?.measured?.current_sg}
					{progress}
				/>

				<!-- Recipe Targets Card (only if recipe exists) -->
				{#if batch.recipe}
					<BatchRecipeTargetsCard recipe={batch.recipe} />
				{/if}
			</div>

			<!-- Right column -->
			<div class="info-section">
				<!-- Timeline Card -->
				<BatchTimelineCard {batch} />

				<!-- Device Card -->
				<BatchDeviceCard
					{batch}
					{liveReading}
					onEdit={() => (isEditing = true)}
				/>

				<!-- Heater Control Card (existing) -->
				{#if hasHeaterControl && batch.status === 'fermenting'}
					<div class="info-card heater-card" class:heater-on={controlStatus?.heater_state === 'on'}>
						<h3 class="info-title">Temperature Control</h3>
						<div class="heater-status">
							<div class="heater-icon-wrap" class:heating={controlStatus?.heater_state === 'on'}>
								🔥
							</div>
							<div class="heater-info">
								<span class="heater-state" class:on={controlStatus?.heater_state === 'on'}>
									{controlStatus?.heater_state === 'on' ? 'HEATING' : controlStatus?.heater_state === 'off' ? 'OFF' : 'Unknown'}
								</span>
								<span class="heater-entity">{batch.heater_entity_id}</span>
							</div>
						</div>
						{#if controlStatus}
							<div class="heater-details">
								<div class="heater-detail">
									<span class="detail-label">Target</span>
									<span class="detail-value">{formatTempValue(controlStatus.target_temp)}{tempUnit}</span>
								</div>
								<div class="heater-detail">
									<span class="detail-label">Hysteresis</span>
									<span class="detail-value">±{controlStatus.hysteresis?.toFixed(1) || '--'}{tempUnit}</span>
								</div>
							</div>
							{#if controlStatus.override_active}
								<div class="override-banner">
									<span class="override-icon">⚡</span>
									<span>Override active: {controlStatus.override_state?.toUpperCase()}</span>
									<button
										type="button"
										class="override-cancel-inline"
										onclick={() => handleOverride(null)}
										disabled={heaterLoading}
									>
										Cancel
									</button>
								</div>
							{/if}
							<div class="override-controls">
								<span class="override-label">Manual Override (1hr)</span>
								<div class="override-btns">
									<button
										type="button"
										class="override-btn"
										class:active={controlStatus.override_state === 'on'}
										onclick={() => handleOverride('on')}
										disabled={heaterLoading}
									>
										Force ON
									</button>
									<button
										type="button"
										class="override-btn"
										class:active={controlStatus.override_state === 'off'}
										onclick={() => handleOverride('off')}
										disabled={heaterLoading}
									>
										Force OFF
									</button>
								</div>
							</div>
						{/if}
					</div>
				{:else if batch.heater_entity_id && batch.status !== 'fermenting'}
					<div class="info-card">
						<h3 class="info-title">Temperature Control</h3>
						<div class="no-device">
							<span>Heater: {batch.heater_entity_id}</span>
							<span class="hint">Active only during fermentation</span>
						</div>
					</div>
				{/if}

				<!-- Notes Card (only if notes exist) -->
				{#if batch.notes}
					<BatchNotesCard notes={batch.notes} />
				{/if}
			</div>
		</div>
```

**Step 3: Remove old styles that are now in card components**

In the `<style>` section, remove these style blocks (they're now in the card components):
- `.stat-card` and related styles (lines 805-948)
- `.measurements-grid` and `.measurement` styles (lines 916-948)
- `.timeline` and `.timeline-item` styles (lines 973-994)
- Most device styles (keep `.no-device` and `.hint` for heater card compatibility)

Keep all the heater control styles as they're still inline.

**Step 4: Verify build**

```bash
npm run build
```

Expected: Build succeeds with no new errors (same accessibility warnings as baseline).

**Step 5: Test visually in dev mode**

```bash
npm run dev
```

Navigate to a batch detail page and verify:
1. New cards display correctly
2. Live readings show when device is connected
3. Fermentation card shows real-time calculations during active fermentation
4. Layout is responsive (test at different screen sizes)
5. All existing functionality still works

**Step 6: Commit**

```bash
git add src/routes/batches/[id]/+page.svelte
git commit -m "feat: integrate modular card components into batch detail page"
```

---

## Task 6: Add Accessibility Improvements

**Files:**
- Modify: `src/routes/batches/[id]/+page.svelte`

**Step 1: Add aria-label to delete button**

Find the delete button (around line 313) and add `aria-label`:

```svelte
<button type="button" class="delete-btn" onclick={handleDelete} aria-label="Delete batch">
```

**Step 2: Verify build**

```bash
npm run build
```

Expected: One less accessibility warning (delete button warning should be gone).

**Step 3: Commit**

```bash
git add src/routes/batches/[id]/+page.svelte
git commit -m "fix: add aria-label to delete button for accessibility"
```

---

## Task 7: Final Testing and Documentation

**Files:**
- Modify: `docs/plans/2025-12-03-batch-detail-live-data-design.md`

**Step 1: Comprehensive manual testing**

Test the following scenarios:

1. **Active fermentation with live device:**
   - Verify LiveReadingsCard shows current + raw values
   - Verify signal strength indicator displays
   - Verify FermentationCard shows real-time ABV and attenuation
   - Verify "(live)" badges are present

2. **Active fermentation without device:**
   - Verify LiveReadingsCard hidden
   - Verify FermentationCard uses progress API data
   - Verify DeviceCard shows "no device assigned"

3. **Completed batch:**
   - Verify FermentationCard shows final values
   - Verify no "(live)" badges
   - Verify static measurements display correctly

4. **Batch without OG:**
   - Verify FermentationCard shows hint to set OG
   - Verify no calculations displayed

5. **Responsive behavior:**
   - Test at desktop width (>900px) - 2 columns
   - Test at tablet width (600-900px) - stacked
   - Test at mobile width (<600px) - stacked

6. **Heater control:**
   - Verify heater card still works for fermenting batches
   - Verify manual overrides function

**Step 2: Update design document with implementation status**

Add to the end of `docs/plans/2025-12-03-batch-detail-live-data-design.md`:

```markdown
---

## Implementation Status

**Completed:** 2025-12-03

### Components Created

- ✅ `BatchCard.svelte` - Base wrapper component
- ✅ `BatchLiveReadingsCard.svelte` - Live data with signal strength
- ✅ `BatchFermentationCard.svelte` - Real-time calculations
- ✅ `BatchTimelineCard.svelte` - Extracted timeline section
- ✅ `BatchDeviceCard.svelte` - Enhanced device status
- ✅ `BatchRecipeTargetsCard.svelte` - Extracted targets section
- ✅ `BatchNotesCard.svelte` - Extracted notes section

### Integration

- ✅ All cards integrated into batch detail page
- ✅ Responsive layout (2-column → 1-column at 900px)
- ✅ Real-time ABV and attenuation calculations
- ✅ Signal strength diagnostics
- ✅ Raw value display when calibrated
- ✅ Accessibility improvements

### Testing

- ✅ Active fermentation with live device
- ✅ Active fermentation without device
- ✅ Completed batch display
- ✅ Batch without OG set
- ✅ Responsive behavior verified
- ✅ Heater control compatibility

### Future Enhancements Ready

The modular architecture is ready for:
- AI insights card
- Signal history chart
- Fermentation velocity display
- Batch comparison features
```

**Step 3: Commit**

```bash
git add docs/plans/2025-12-03-batch-detail-live-data-design.md
git commit -m "docs: update design doc with implementation status"
```

---

## Task 8: Build and Deploy Preparation

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `VERSION`

**Step 1: Run final production build**

```bash
npm run build
```

Expected: Clean build with only pre-existing warnings.

**Step 2: Update VERSION file**

```bash
cd .. # Back to project root
echo "2.3.2" > VERSION
```

**Step 3: Update CHANGELOG.md**

Add to the top of `CHANGELOG.md` (after the header):

```markdown
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
```

**Step 4: Commit version bump**

```bash
git add VERSION CHANGELOG.md
git commit -m "chore: bump version to 2.3.2"
```

**Step 5: Create summary of changes**

```bash
git log --oneline master..HEAD
```

Expected output showing all commits from this feature branch.

---

## Completion Checklist

- [ ] All 7 card components created
- [ ] Batch detail page refactored to use cards
- [ ] Real-time calculations working (ABV, attenuation)
- [ ] Signal strength and raw values displayed
- [ ] Responsive layout tested
- [ ] Accessibility improvements made
- [ ] Build passes with no new errors
- [ ] Manual testing completed for all scenarios
- [ ] Documentation updated
- [ ] Version bumped to 2.3.2
- [ ] CHANGELOG.md updated

---

## Next Steps

After completing this implementation:

1. **Merge to master:**
   - Review all commits
   - Create PR or merge directly
   - Delete feature branch and worktree

2. **Deploy:**
   - Build and copy static files to backend
   - Restart backend service
   - Verify on production

3. **Monitor:**
   - Watch for any issues with live data display
   - Verify WebSocket updates trigger card updates
   - Check performance on mobile devices

4. **Future enhancements** (separate issues):
   - Add signal history chart (#37 - loading skeletons)
   - Implement AI insights card (future issue)
   - Add fermentation velocity calculations (future issue)
   - Notification triggers for fermentation events (#44)

---

## Skills to Use During Implementation

- **frontend-design:frontend-design** - Use when implementing BatchLiveReadingsCard and BatchFermentationCard to ensure polished, production-grade UI
- **verification-before-completion** - Use before marking any task complete to verify it works
- **systematic-debugging** - Use if any bugs or unexpected behavior occurs during testing

---

**Plan saved:** `docs/plans/2025-12-03-batch-detail-live-data-implementation.md`
