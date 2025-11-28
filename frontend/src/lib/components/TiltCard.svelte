<script lang="ts">
	import type { TiltReading } from '$lib/stores/tilts.svelte';
	import { updateTiltBeerName } from '$lib/stores/tilts.svelte';
	import { configState, formatTemp, getTempUnit } from '$lib/stores/config.svelte';
	import TiltChart from './TiltChart.svelte';

	interface Props {
		tilt: TiltReading;
		expanded?: boolean;
		onToggleExpand?: () => void;
	}

	let { tilt, expanded = false, onToggleExpand }: Props = $props();

	// Beer name editing state
	let isEditing = $state(false);
	let editValue = $state('');
	let inputRef = $state<HTMLInputElement | null>(null);
	let saving = $state(false);

	function startEditing() {
		editValue = tilt.beer_name;
		isEditing = true;
		// Focus input after DOM update
		setTimeout(() => inputRef?.focus(), 0);
	}

	async function saveEdit() {
		if (saving) return;
		const trimmed = editValue.trim();
		if (!trimmed || trimmed === tilt.beer_name) {
			isEditing = false;
			return;
		}
		saving = true;
		const success = await updateTiltBeerName(tilt.id, trimmed);
		saving = false;
		if (success) {
			isEditing = false;
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			saveEdit();
		} else if (e.key === 'Escape') {
			isEditing = false;
		}
	}

	// Reactive temp unit from config
	let tempUnit = $derived(getTempUnit());

	// CSS variable colors for the tilt accent
	const colorVars: Record<string, string> = {
		RED: 'var(--tilt-red)',
		GREEN: 'var(--tilt-green)',
		BLACK: 'var(--tilt-black)',
		PURPLE: 'var(--tilt-purple)',
		ORANGE: 'var(--tilt-orange)',
		BLUE: 'var(--tilt-blue)',
		YELLOW: 'var(--tilt-yellow)',
		PINK: 'var(--tilt-pink)'
	};

	function formatSG(sg: number): string {
		return sg.toFixed(3);
	}

	function formatTempValue(temp: number): string {
		return formatTemp(temp);
	}

	function getSignalStrength(rssi: number): { bars: number; color: string } {
		if (rssi >= -50) return { bars: 4, color: 'var(--positive)' };
		if (rssi >= -60) return { bars: 3, color: 'var(--positive)' };
		if (rssi >= -70) return { bars: 2, color: 'var(--warning)' };
		return { bars: 1, color: 'var(--negative)' };
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

	let accentColor = $derived(colorVars[tilt.color] || 'var(--tilt-black)');
	let signal = $derived(getSignalStrength(tilt.rssi));
	let lastSeenText = $derived(timeSince(tilt.last_seen));
</script>

<div
	class="card rounded-lg overflow-hidden animate-fade-in"
	class:expanded
	style="background: var(--bg-surface); border: 1px solid var(--border-subtle);"
>
	<!-- Accent bar -->
	<div
		class="h-0.5"
		style="background: {accentColor};"
	></div>

	<div class="p-5">
		<!-- Header row -->
		<div class="flex justify-between items-start mb-5">
			<div class="flex-1 min-w-0 mr-3">
				{#if isEditing}
					<input
						type="text"
						bind:this={inputRef}
						bind:value={editValue}
						onblur={saveEdit}
						onkeydown={handleKeydown}
						disabled={saving}
						class="beer-name-input"
						maxlength="100"
					/>
				{:else}
					<button
						type="button"
						class="beer-name-btn"
						onclick={startEditing}
						title="Click to edit beer name"
					>
						<h3 class="text-lg font-semibold text-[var(--text-primary)] tracking-tight truncate">
							{tilt.beer_name}
						</h3>
						<svg class="edit-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
						</svg>
					</button>
				{/if}
				<div class="flex items-center gap-2 mt-1">
					<span
						class="w-2 h-2 rounded-full"
						style="background: {accentColor};"
					></span>
					<span class="text-sm text-[var(--text-muted)] font-medium">{tilt.color}</span>
				</div>
			</div>

			<!-- Signal indicator -->
			<div class="flex flex-col items-end gap-1">
				<div class="flex items-end gap-0.5">
					{#each Array(4) as _, i}
						<div
							class="w-1 rounded-sm transition-all"
							style="
								height: {8 + i * 4}px;
								background: {i < signal.bars ? signal.color : 'var(--bg-hover)'};
								opacity: {i < signal.bars ? 1 : 0.4};
							"
						></div>
					{/each}
				</div>
				<span class="text-[10px] text-[var(--text-muted)] font-mono">{tilt.rssi} dBm</span>
			</div>
		</div>

		<!-- Main readings grid -->
		<div class="grid grid-cols-2 gap-3 mb-4">
			<!-- Specific Gravity -->
			<div
				class="rounded-md p-4 text-center"
				style="background: var(--bg-elevated);"
			>
				<p class="text-3xl font-medium font-mono tracking-tight" style="color: var(--text-primary);">
					{formatSG(tilt.sg)}
				</p>
				<p class="text-[11px] text-[var(--text-muted)] uppercase tracking-wider mt-1 font-medium">
					Gravity
				</p>
			</div>

			<!-- Temperature -->
			<div
				class="rounded-md p-4 text-center"
				style="background: var(--bg-elevated);"
			>
				<p class="text-3xl font-medium font-mono tracking-tight text-[var(--text-primary)]">
					{formatTempValue(tilt.temp)}<span class="text-lg text-[var(--text-secondary)]">{tempUnit}</span>
				</p>
				<p class="text-[11px] text-[var(--text-muted)] uppercase tracking-wider mt-1 font-medium">
					Temp
				</p>
			</div>
		</div>

		<!-- Raw values (if calibrated) -->
		{#if tilt.sg !== tilt.sg_raw || tilt.temp !== tilt.temp_raw}
			<div
				class="text-[11px] text-[var(--text-muted)] font-mono mb-3 px-1"
			>
				<span class="opacity-60">Raw:</span>
				<span class="ml-1">{formatSG(tilt.sg_raw)}</span>
				<span class="mx-1 opacity-40">·</span>
				<span>{formatTempValue(tilt.temp_raw)}{tempUnit}</span>
			</div>
		{/if}

		<!-- Expandable chart section -->
		{#if expanded}
			<div class="chart-section">
				<TiltChart tiltId={tilt.id} tiltColor={tilt.color} />
			</div>
		{/if}

		<!-- Footer -->
		<div class="flex justify-between items-center pt-3 border-t border-[var(--bg-hover)]">
			<span class="text-[11px] text-[var(--text-muted)]">Updated {lastSeenText}</span>
			<div class="flex items-center gap-2">
				{#if onToggleExpand}
					<button
						type="button"
						class="expand-btn"
						onclick={onToggleExpand}
						aria-label={expanded ? 'Collapse chart' : 'Expand chart'}
					>
						<svg
							class="w-4 h-4 transition-transform"
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
				<div
					class="w-1.5 h-1.5 rounded-full"
					style="background: var(--positive);"
				></div>
			</div>
		</div>
	</div>
</div>

<style>
	.card {
		transition: border-color var(--transition);
	}

	.card:hover {
		border-color: var(--border-default);
	}

	.expanded {
		grid-column: span 2;
	}

	@media (max-width: 768px) {
		.expanded {
			grid-column: span 1;
		}
	}

	.chart-section {
		margin-top: 1rem;
		padding-top: 1rem;
		border-top: 1px solid var(--bg-hover);
	}

	.expand-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 1.75rem;
		height: 1.75rem;
		border-radius: 0.375rem;
		color: var(--text-muted);
		background: var(--bg-elevated);
		border: 1px solid var(--bg-hover);
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.expand-btn:hover {
		color: var(--accent);
		border-color: var(--accent-muted);
		background: var(--accent-muted);
	}

	/* Beer name editing */
	.beer-name-btn {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		background: none;
		border: none;
		padding: 0;
		cursor: pointer;
		text-align: left;
		max-width: 100%;
	}

	.beer-name-btn:hover .edit-icon {
		opacity: 1;
	}

	.edit-icon {
		flex-shrink: 0;
		width: 0.875rem;
		height: 0.875rem;
		color: var(--text-muted);
		opacity: 0;
		transition: opacity 0.15s ease;
	}

	.beer-name-input {
		width: 100%;
		font-size: 1.125rem;
		font-weight: 600;
		color: var(--text-primary);
		background: var(--bg-elevated);
		border: 1px solid var(--accent);
		border-radius: 0.375rem;
		padding: 0.25rem 0.5rem;
		outline: none;
	}

	.beer-name-input:disabled {
		opacity: 0.6;
	}
</style>
