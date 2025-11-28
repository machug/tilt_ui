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

	// Get smoothing settings from config
	let smoothingEnabled = $derived(configState.config.smoothing_enabled);
	let smoothingSamples = $derived(configState.config.smoothing_samples);

	// System timezone for chart display
	let systemTimezone = $state<string>('UTC');

	interface Props {
		tiltId: string;
		tiltColor: string;
	}

	let { tiltId, tiltColor }: Props = $props();

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

	// Theme colors
	const AMBER = '#fbbf24';
	const AMBER_GLOW = 'rgba(251, 191, 36, 0.3)';
	const TEXT_MUTED = '#71717a';
	const TEXT_SECONDARY = '#a1a1aa';
	const GRID_COLOR = 'rgba(255, 255, 255, 0.04)';
	const CYAN = '#22d3ee'; // Ambient temp color

	function getChartOptions(width: number, celsius: boolean): uPlot.Options {
		const sgColor = AMBER;
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
						vals.map((v) => {
							const d = new Date(v * 1000);
							if (selectedRange <= 24) {
								return d.toLocaleTimeString([], {
									hour: '2-digit',
									minute: '2-digit',
									timeZone: systemTimezone
								});
							}
							return d.toLocaleDateString([], {
								month: 'short',
								day: 'numeric',
								timeZone: systemTimezone
							});
						})
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
						gradient.addColorStop(0, AMBER_GLOW);
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
			(a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
		);

		// Extract timestamps and temps from ambient readings
		const ambientTimes = sortedAmbient.map(r => new Date(r.timestamp).getTime() / 1000);
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
			timestamps.push(new Date(r.timestamp).getTime() / 1000);
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

	async function loadData() {
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
			loading = false;
		}
	}

	function updateChart() {
		if (!chartContainer || readings.length === 0) return;

		const data = processData(readings, ambientReadings, useCelsius);
		const opts = getChartOptions(chartContainer.clientWidth, useCelsius);

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

	onMount(async () => {
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

		loadData();
		window.addEventListener('resize', handleResize);
	});

	onDestroy(() => {
		chart?.destroy();
		window.removeEventListener('resize', handleResize);
	});

	// Reload when range changes
	$effect(() => {
		if (selectedRange) {
			loadData();
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
</script>

<div class="chart-wrapper">
	<!-- Time range selector -->
	<div class="flex items-center justify-between mb-3">
		<div class="flex items-center gap-1.5">
			{#each TIME_RANGES as range}
				<button
					type="button"
					class="range-btn"
					class:active={selectedRange === range.hours}
					onclick={() => (selectedRange = range.hours)}
				>
					{range.label}
				</button>
			{/each}
		</div>
		<div class="chart-legend">
			<span class="legend-item">
				<span class="legend-dot" style="background: var(--amber-400);"></span>
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

	<!-- Chart container -->
	<div class="chart-container" bind:this={chartContainer}>
		{#if loading}
			<div class="chart-loading">
				<div class="loading-spinner"></div>
				<span>Loading chart data...</span>
			</div>
		{:else if error}
			<div class="chart-error">
				<span>Failed to load chart</span>
				<button type="button" class="retry-btn" onclick={loadData}>Retry</button>
			</div>
		{:else if readings.length === 0}
			<div class="chart-empty">
				<span>No historical data yet</span>
				<span class="text-xs opacity-60">Data will appear as readings are logged</span>
			</div>
		{/if}
	</div>
</div>

<style>
	.chart-wrapper {
		padding-top: 0.5rem;
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
		color: var(--amber-400);
		background: rgba(251, 191, 36, 0.1);
		border-color: rgba(251, 191, 36, 0.2);
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

	.chart-container :global(.u-wrap) {
		background: transparent !important;
	}

	.chart-loading,
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

	.loading-spinner {
		width: 1.5rem;
		height: 1.5rem;
		border: 2px solid var(--bg-hover);
		border-top-color: var(--amber-400);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	.retry-btn {
		padding: 0.375rem 0.75rem;
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--amber-400);
		background: rgba(251, 191, 36, 0.1);
		border: 1px solid rgba(251, 191, 36, 0.2);
		border-radius: 0.375rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.retry-btn:hover {
		background: rgba(251, 191, 36, 0.15);
	}

	.chart-empty {
		text-align: center;
	}
</style>
