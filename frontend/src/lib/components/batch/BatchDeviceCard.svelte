<script lang="ts">
	import type { BatchResponse } from '$lib/api';
	import type { TiltReading } from '$lib/stores/tilts.svelte';
	import { getSignalStrength, timeSince } from '$lib/utils/signal';
	import BatchCard from './BatchCard.svelte';

	interface Props {
		batch: BatchResponse;
		liveReading: TiltReading | null;
		onEdit?: () => void;
	}

	let { batch, liveReading, onEdit }: Props = $props();

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
