<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import uPlot from 'uplot';
	import {
		fetchReadings,
		fetchAmbientHistory,
		TIME_RANGES,
		type HistoricalReading,
		type AmbientHistoricalReading
	} from '$lib/api';
	import { configState, fahrenheitToCelsius } from '$lib/stores/config.svelte';
	import FermentationStats from './FermentationStats.svelte';

	const REFRESH_STORAGE_KEY = 'brewsignal_chart_refresh_minutes';
	const REFRESH_OPTIONS = [
		{ label: 'Off', value: 0 },
		{ label: '1 min', value: 1 },
		{ label: '3 min', value: 3 },
		{ label: '5 min', value: 5 },
		{ label: '10 min', value: 10 }
	];

	// Get smoothing settings from config
	let smoothingEnabled = $derived(configState.config.smoothing_enabled);
	let smoothingSamples = $derived(configState.config.smoothing_samples);

	// System timezone for chart display
	let systemTimezone = $state<string>('UTC');
	let lastLoadTime = $state(0);
	let refreshMinutes = $state<number>(3);

	interface Props {
		tiltId: string;
		tiltColor: string;
		originalGravity?: number | null;
		onOgChange?: (og: number | null) => void;
	}

	let { tiltId, tiltColor, originalGravity = null, onOgChange }: Props = $props();

	// Reactive check for Celsius mode
	let useCelsius = $derived(configState.config.temp_units === 'C');

	let chartContainer: HTMLDivElement;
	let chart: uPlot | null = null;
	let loading = $state(true);
	let error = $state<string | null>(null);
	let selectedRange = $state(24); // hours
	let readings = $state<HistoricalReading[]>([]);
	let ambientReadings = $state<AmbientHistoricalReading[]>([]);

	// Color mapping for tilt accent in chart
	const tiltColorMap: Record<string, string> = {
		RED: '#f43f5e',
		GREEN: '#10b981',
		BLACK: '#6b7280',
		PURPLE: '#a78bfa',
		ORANGE: '#fb923c',
		BLUE: '#60a5fa',
		YELLOW: '#facc15',
		PINK: '#f472b6'
	};

	// Theme colors - using tilt-yellow instead of amber
	const SG_COLOR = '#facc15'; // tilt-yellow
	const SG_GLOW = 'rgba(250, 204, 21, 0.3)'; // tilt-yellow with transparency
	const TEXT_MUTED = '#71717a';
	const TEXT_SECONDARY = '#a1a1aa';
	const GRID_COLOR = 'rgba(255, 255, 255, 0.04)';
	const CYAN = '#22d3ee'; // Ambient temp color

	// Create a date formatter for the target timezone
	function formatTimeInTz(timestamp: number, tz: string, short: boolean): string {
		const date = new Date(timestamp * 1000);
		try {
			if (short) {
				return date.toLocaleTimeString('en-AU', {
					hour: '2-digit',
					minute: '2-digit',
					hour12: false,
					timeZone: tz
				});
			}
			return date.toLocaleDateString('en-AU', {
				month: 'short',
				day: 'numeric',
				timeZone: tz
			});
		} catch (e) {
			// Fallback if timezone is invalid
			console.warn('Invalid timezone:', tz, e);
			if (short) {
				return date.toLocaleTimeString('en-AU', {
					hour: '2-digit',
					minute: '2-digit',
					hour12: false
				});
			}
			return date.toLocaleDateString('en-AU', {
				month: 'short',
				day: 'numeric'
			});
		}
	}

	function getChartOptions(width: number, celsius: boolean, tz: string): uPlot.Options {
		const sgColor = SG_COLOR;
		const tempColor = tiltColorMap[tiltColor] || TEXT_SECONDARY;

		return {
			width,
			height: 220,
			padding: [16, 12, 0, 0],
			cursor: {
				show: true,
				x: true,
				y: true,
				drag: { x: false, y: false, setScale: false }
			},
			legend: {
				show: false
			},
			scales: {
				x: { time: true },
				sg: {
					auto: true,
					range: (u, min, max) => {
						const padding = (max - min) * 0.1 || 0.005;
						return [min - padding, max + padding];
					}
				},
				temp: {
					auto: true,
					range: (u, min, max) => {
						// Ensure minimum 10-degree range so small fluctuations don't look exaggerated
						const dataRange = max - min;
						const minRange = 10;
						if (dataRange < minRange) {
							const center = (max + min) / 2;
							return [center - minRange / 2, center + minRange / 2];
						}
						const padding = dataRange * 0.1;
						return [min - padding, max + padding];
					}
				}
			},
			axes: [
				{
					// X axis (time)
					stroke: TEXT_MUTED,
					grid: { stroke: GRID_COLOR, width: 1 },
					ticks: { stroke: GRID_COLOR, width: 1, size: 4 },
					font: '11px "JetBrains Mono", monospace',
					labelFont: '11px "JetBrains Mono", monospace',
					values: (u, vals) =>
						vals.map((v) => formatTimeInTz(v, tz, selectedRange <= 24))
				},
				{
					// Y axis left (SG)
					scale: 'sg',
					stroke: sgColor,
					grid: { stroke: GRID_COLOR, width: 1 },
					ticks: { stroke: GRID_COLOR, width: 1, size: 4 },
					font: '11px "JetBrains Mono", monospace',
					labelFont: '11px "JetBrains Mono", monospace',
					values: (u, vals) => vals.map((v) => v.toFixed(3)),
					side: 3 // left
				},
				{
					// Y axis right (Temp)
					scale: 'temp',
					stroke: tempColor,
					grid: { show: false },
					ticks: { stroke: GRID_COLOR, width: 1, size: 4 },
					font: '11px "JetBrains Mono", monospace',
					labelFont: '11px "JetBrains Mono", monospace',
					values: (u, vals) => vals.map((v) => v.toFixed(0) + '°'),
					side: 1 // right
				}
			],
			series: [
				{}, // x series (timestamps)
				{
					// SG series
					label: 'Gravity',
					scale: 'sg',
					stroke: sgColor,
					width: 2,
					fill: (u: uPlot, idx: number) => {
						const gradient = u.ctx.createLinearGradient(0, u.bbox.top, 0, u.bbox.top + u.bbox.height);
						gradient.addColorStop(0, SG_GLOW);
						gradient.addColorStop(1, 'transparent');
						return gradient;
					},
					points: { show: false },
					paths: uPlot.paths.spline?.() // Smooth spline interpolation
				},
				{
					// Wort Temp series
					label: 'Wort Temp',
					scale: 'temp',
					stroke: tempColor,
					width: 1.5,
					dash: [4, 4],
					points: { show: false },
					paths: uPlot.paths.spline?.() // Smooth spline interpolation
				},
				{
					// Ambient Temp series
					label: 'Ambient',
					scale: 'temp',
					stroke: CYAN,
					width: 1.5,
					dash: [2, 4],
					points: { show: false },
					paths: uPlot.paths.spline?.() // Smooth spline interpolation
				}
			]
		};
	}

	// Moving average smoothing function
	function smoothData(values: (number | null)[], windowSize: number): (number | null)[] {
		if (windowSize <= 1) return values;

		const result: (number | null)[] = [];
		for (let i = 0; i < values.length; i++) {
			// Collect valid values in the window
			const windowValues: number[] = [];
			const halfWindow = Math.floor(windowSize / 2);

			for (let j = Math.max(0, i - halfWindow); j <= Math.min(values.length - 1, i + halfWindow); j++) {
				const v = values[j];
				if (v !== null) windowValues.push(v);
			}

			if (windowValues.length > 0) {
				result.push(windowValues.reduce((a, b) => a + b, 0) / windowValues.length);
			} else {
				result.push(null);
			}
		}
		return result;
	}

	// Downsample data for longer time ranges to improve performance
	function downsampleData(
		timestamps: number[],
		sgValues: (number | null)[],
		tempValues: (number | null)[],
		ambientValues: (number | null)[],
		maxPoints: number
	): [number[], (number | null)[], (number | null)[], (number | null)[]] {
		if (timestamps.length <= maxPoints) {
			return [timestamps, sgValues, tempValues, ambientValues];
		}

		const step = Math.ceil(timestamps.length / maxPoints);
		const newTimestamps: number[] = [];
		const newSg: (number | null)[] = [];
		const newTemp: (number | null)[] = [];
		const newAmbient: (number | null)[] = [];

		for (let i = 0; i < timestamps.length; i += step) {
			// Average values in this bucket
			const bucketEnd = Math.min(i + step, timestamps.length);
			let sgSum = 0, sgCount = 0;
			let tempSum = 0, tempCount = 0;
			let ambientSum = 0, ambientCount = 0;

			for (let j = i; j < bucketEnd; j++) {
				if (sgValues[j] !== null) { sgSum += sgValues[j]!; sgCount++; }
				if (tempValues[j] !== null) { tempSum += tempValues[j]!; tempCount++; }
				if (ambientValues[j] !== null) { ambientSum += ambientValues[j]!; ambientCount++; }
			}

			// Use middle timestamp of bucket
			newTimestamps.push(timestamps[Math.floor((i + bucketEnd - 1) / 2)]);
			newSg.push(sgCount > 0 ? sgSum / sgCount : null);
			newTemp.push(tempCount > 0 ? tempSum / tempCount : null);
			newAmbient.push(ambientCount > 0 ? ambientSum / ambientCount : null);
		}

		return [newTimestamps, newSg, newTemp, newAmbient];
	}

	// Parse timestamp string as UTC (backend stores UTC but may omit Z suffix)
	function parseUtcTimestamp(timestamp: string): number {
		// If timestamp doesn't end with Z or timezone offset, treat as UTC
		if (!timestamp.endsWith('Z') && !timestamp.match(/[+-]\d{2}:\d{2}$/)) {
			timestamp = timestamp + 'Z';
		}
		return new Date(timestamp).getTime() / 1000;
	}

	// Interpolate ambient readings to match tilt timestamps
	function interpolateAmbientToTimestamps(
		ambientReadings: AmbientHistoricalReading[],
		targetTimestamps: number[],
		celsius: boolean
	): (number | null)[] {
		if (ambientReadings.length === 0 || targetTimestamps.length === 0) {
			return targetTimestamps.map(() => null);
		}

		// Sort ambient readings by timestamp (oldest first)
		const sortedAmbient = [...ambientReadings].sort(
			(a, b) => parseUtcTimestamp(a.timestamp) - parseUtcTimestamp(b.timestamp)
		);

		// Extract timestamps and temps from ambient readings
		const ambientTimes = sortedAmbient.map(r => parseUtcTimestamp(r.timestamp));
		const ambientTemps = sortedAmbient.map(r => {
			if (r.temperature === null) return null;
			// Ambient is in Celsius from HA, convert to F if needed
			return celsius ? r.temperature : (r.temperature * 9 / 5) + 32;
		});

		// For each target timestamp, find nearest ambient value or interpolate
		return targetTimestamps.map(ts => {
			// Find surrounding ambient readings
			let before: { time: number; temp: number | null } | null = null;
			let after: { time: number; temp: number | null } | null = null;

			for (let i = 0; i < ambientTimes.length; i++) {
				if (ambientTimes[i] <= ts) {
					before = { time: ambientTimes[i], temp: ambientTemps[i] };
				}
				if (ambientTimes[i] >= ts && after === null) {
					after = { time: ambientTimes[i], temp: ambientTemps[i] };
					break;
				}
			}

			// If we have both, interpolate
			if (before && after && before.temp !== null && after.temp !== null) {
				if (before.time === after.time) return before.temp;
				const ratio = (ts - before.time) / (after.time - before.time);
				return before.temp + ratio * (after.temp - before.temp);
			}

			// Use nearest available value
			if (before !== null && before.temp !== null) return before.temp;
			if (after !== null && after.temp !== null) return after.temp;

			return null;
		});
	}

	function processData(
		readings: HistoricalReading[],
		ambient: AmbientHistoricalReading[],
		celsius: boolean
	): uPlot.AlignedData {
		// Readings come newest first, reverse for chronological order
		const sorted = [...readings].reverse();

		let timestamps: number[] = [];
		let sgValues: (number | null)[] = [];
		let tempValues: (number | null)[] = [];

		for (const r of sorted) {
			timestamps.push(parseUtcTimestamp(r.timestamp));
			sgValues.push(r.sg_calibrated ?? r.sg_raw);

			// Convert temp if needed
			const tempF = r.temp_calibrated ?? r.temp_raw;
			if (tempF !== null) {
				tempValues.push(celsius ? fahrenheitToCelsius(tempF) : tempF);
			} else {
				tempValues.push(null);
			}
		}

		// Interpolate ambient readings to match tilt timestamps
		let ambientValues = interpolateAmbientToTimestamps(ambient, timestamps, celsius);

		// Apply smoothing if enabled in config
		if (smoothingEnabled && smoothingSamples > 1) {
			sgValues = smoothData(sgValues, smoothingSamples);
			tempValues = smoothData(tempValues, smoothingSamples);
			ambientValues = smoothData(ambientValues, smoothingSamples);
		}

		// Downsample for performance (max 500 points)
	const maxPoints = 500;
	[timestamps, sgValues, tempValues, ambientValues] = downsampleData(timestamps, sgValues, tempValues, ambientValues, maxPoints);

	return [timestamps, sgValues, tempValues, ambientValues];
}

// Minimum interval between data fetches (30 seconds) to prevent BLE event spam
const MIN_FETCH_INTERVAL_MS = 30000;

async function loadData(userTriggered = false) {
	const now = Date.now();
	const timeSinceLastLoad = now - lastLoadTime;

	// For automatic reloads, respect the minimum fetch interval
	// User-triggered actions (range change, manual refresh) always proceed
	if (!userTriggered && lastLoadTime > 0 && timeSinceLastLoad < MIN_FETCH_INTERVAL_MS) {
		return;
	}

	loading = true;
	error = null;

	try {
		// Fetch tilt readings and ambient history in parallel
		const [tiltData, ambientData] = await Promise.all([
			fetchReadings(tiltId, selectedRange),
			fetchAmbientHistory(selectedRange).catch(() => []) // Don't fail if ambient unavailable
		]);
		readings = tiltData;
		ambientReadings = ambientData;
		updateChart();
	} catch (e) {
		error = e instanceof Error ? e.message : 'Failed to load data';
	} finally {
		lastLoadTime = Date.now();
		loading = false;
	}
}

	function updateChart() {
		if (!chartContainer || readings.length === 0) return;

		const data = processData(readings, ambientReadings, useCelsius);
		const opts = getChartOptions(chartContainer.clientWidth, useCelsius, systemTimezone);

		if (chart) {
			chart.destroy();
		}

		chart = new uPlot(opts, data, chartContainer);
	}

function handleResize() {
	if (chart && chartContainer) {
		chart.setSize({ width: chartContainer.clientWidth, height: 220 });
	}
}

let refreshInterval: ReturnType<typeof setInterval> | null = null;

function resetRefreshInterval() {
	if (refreshInterval) {
		clearInterval(refreshInterval);
		refreshInterval = null;
	}

	if (refreshMinutes > 0) {
		const intervalMs = refreshMinutes * 60 * 1000;
		refreshInterval = setInterval(() => {
			if (!loading) {
				// Automatic refresh - NOT user triggered, subject to throttling
				loadData(false);
			}
		}, intervalMs);
	}
}

onMount(async () => {
	// Load preferred refresh interval from localStorage
	const storedRefresh = localStorage.getItem(REFRESH_STORAGE_KEY);
	if (storedRefresh !== null) {
		const parsed = parseInt(storedRefresh, 10);
		if (!Number.isNaN(parsed)) {
			refreshMinutes = parsed;
		}
	}

	// Fetch system timezone for chart display
	try {
		const response = await fetch('/api/system/timezone');
			if (response.ok) {
				const data = await response.json();
				systemTimezone = data.timezone || 'UTC';
			}
		} catch (e) {
			console.warn('Failed to fetch system timezone, using UTC');
		}

		// Initial load is user-triggered (mounting the component)
		await loadData(true);
		window.addEventListener('resize', handleResize);
		resetRefreshInterval();
	});

	onDestroy(() => {
		chart?.destroy();
		window.removeEventListener('resize', handleResize);
		if (refreshInterval) {
			clearInterval(refreshInterval);
		}
	});

	// Re-render chart when temp units or smoothing settings change
	$effect(() => {
		if (useCelsius !== undefined && readings.length > 0 && chartContainer) {
			updateChart();
		}
	});

	// Re-render chart when smoothing settings change
	$effect(() => {
		// Track smoothing changes
		const _ = [smoothingEnabled, smoothingSamples];
		if (readings.length > 0 && chartContainer) {
			updateChart();
		}
	});

	function handleRefreshChange(event: Event) {
		const minutes = Number((event.target as HTMLSelectElement).value);
		refreshMinutes = minutes;
		localStorage.setItem(REFRESH_STORAGE_KEY, String(minutes));
		resetRefreshInterval();
		// User changed refresh setting - trigger immediate reload
		loadData(true);
	}
</script>

<div class="chart-wrapper">
	<!-- Time range selector -->
	<div class="chart-controls">
		<div class="flex items-center gap-1.5">
			{#each TIME_RANGES as range}
				<button
					type="button"
					class="range-btn"
					class:active={selectedRange === range.hours}
					onclick={() => {
						if (selectedRange !== range.hours) {
							selectedRange = range.hours;
							loadData(true);
						}
					}}
				>
					{range.label}
				</button>
			{/each}
		</div>
		<div class="controls-right">
			<div class="refresh-control">
				<label for="refreshInterval">Refresh</label>
				<select id="refreshInterval" class="refresh-select" value={refreshMinutes} onchange={handleRefreshChange}>
					{#each REFRESH_OPTIONS as option}
						<option value={option.value}>{option.label}</option>
					{/each}
				</select>
			</div>
			<div class="chart-legend">
				<span class="legend-item">
					<span class="legend-dot" style="background: var(--tilt-yellow);"></span>
					<span>SG</span>
				</span>
				<span class="legend-item">
					<span
						class="legend-line"
						style="background: {tiltColorMap[tiltColor] || 'var(--text-secondary)'};"
					></span>
					<span>Wort</span>
				</span>
				<span class="legend-item">
					<span class="legend-line legend-line-dotted" style="background: #22d3ee;"></span>
					<span>Ambient</span>
				</span>
			</div>
		</div>
	</div>

	<!-- Chart container -->
	<div class="chart-container" bind:this={chartContainer}>
		{#if loading}
			<div class="loading-overlay">
				<div class="loading-spinner"></div>
			</div>
		{/if}
		{#if error}
			<div class="chart-error">
				<span>Failed to load chart</span>
				<button type="button" class="retry-btn" onclick={() => loadData(true)}>Retry</button>
			</div>
		{:else if readings.length === 0}
			<div class="chart-empty">
				<span>No historical data yet</span>
				<span class="text-xs opacity-60">Data will appear as readings are logged</span>
			</div>
		{/if}
	</div>

	<!-- Fermentation Stats -->
	{#if readings.length > 0}
		<FermentationStats
			{readings}
			{originalGravity}
			onOgChange={onOgChange ?? (() => {})}
		/>
	{/if}
</div>

<style>
	.chart-wrapper {
		padding-top: 0.5rem;
	}

	.chart-controls {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		flex-wrap: wrap;
		margin-bottom: 0.75rem;
	}

	.controls-right {
		display: flex;
		align-items: center;
		gap: 1rem;
		flex-wrap: wrap;
		justify-content: flex-end;
	}

	.refresh-control {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.6875rem;
		font-family: 'JetBrains Mono', monospace;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.refresh-control label {
		color: var(--text-muted);
	}

	.refresh-select {
		padding: 0.25rem 0.5rem;
		font-size: 0.6875rem;
		font-family: 'JetBrains Mono', monospace;
		border-radius: 0.375rem;
		border: 1px solid var(--border-default);
		background: var(--bg-elevated);
		color: var(--text-primary);
		cursor: pointer;
		transition: border-color 0.15s ease, box-shadow 0.15s ease;
	}

	.refresh-select:focus {
		outline: none;
		border-color: var(--accent);
		box-shadow: 0 0 0 1px var(--accent-muted);
	}

	.range-btn {
		padding: 0.25rem 0.625rem;
		font-size: 0.6875rem;
		font-family: 'JetBrains Mono', monospace;
		font-weight: 500;
		border-radius: 0.375rem;
		color: var(--text-muted);
		background: transparent;
		border: 1px solid transparent;
		transition: all 0.15s ease;
		cursor: pointer;
	}

	.range-btn:hover {
		color: var(--text-secondary);
		background: var(--bg-hover);
	}

	.range-btn.active {
		background: var(--bg-elevated);
		color: var(--text-primary);
		border-color: var(--border-default);
	}

	.chart-legend {
		display: flex;
		align-items: center;
		gap: 1rem;
	}

	.legend-item {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		font-size: 0.625rem;
		font-family: 'JetBrains Mono', monospace;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.legend-dot {
		width: 0.5rem;
		height: 0.5rem;
		border-radius: 50%;
	}

	.legend-line {
		width: 0.75rem;
		height: 2px;
		border-radius: 1px;
	}

	.legend-line-dotted {
		background: linear-gradient(90deg, #22d3ee 2px, transparent 2px) !important;
		background-size: 4px 2px !important;
	}

	.chart-container {
		position: relative;
		width: 100%;
		min-height: 220px;
		border-radius: 0.5rem;
		background: var(--bg-elevated);
		overflow: hidden;
	}

	.loading-overlay {
		position: absolute;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		background: rgba(24, 24, 27, 0.6);
		backdrop-filter: blur(2px);
		z-index: 10;
	}

	.loading-spinner {
		width: 1.5rem;
		height: 1.5rem;
		border: 2px solid var(--border-subtle);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	.chart-container :global(.u-wrap) {
		background: transparent !important;
	}

	.chart-error,
	.chart-empty {
		position: absolute;
		inset: 0;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 0.75rem;
		color: var(--text-muted);
		font-size: 0.75rem;
	}

	.retry-btn {
		padding: 0.375rem 0.75rem;
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--accent);
		background: var(--accent-muted);
		border: 1px solid transparent;
		border-radius: 0.375rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.retry-btn:hover {
		background: var(--accent-hover);
		color: white;
	}

	.chart-empty {
		text-align: center;
	}
</style>
