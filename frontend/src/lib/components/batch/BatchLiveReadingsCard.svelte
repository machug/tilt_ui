<script lang="ts">
	import type { TiltReading } from '$lib/stores/tilts.svelte';
	import { formatGravity, getGravityUnit, formatTemp, getTempUnit } from '$lib/stores/config.svelte';
	import { getSignalStrength, timeSince } from '$lib/utils/signal';
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
		background: color-mix(in srgb, var(--recipe-accent) 12%, transparent);
		border-radius: 9999px;
		font-size: 0.6875rem;
		font-weight: 600;
		color: var(--recipe-accent);
		text-transform: uppercase;
		letter-spacing: 0.025em;
	}

	.live-dot {
		width: 6px;
		height: 6px;
		background: var(--recipe-accent);
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
