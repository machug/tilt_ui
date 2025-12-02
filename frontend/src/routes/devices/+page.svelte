<script lang="ts">
	import { onMount } from 'svelte';
	import { pairDevice, unpairDevice, type DeviceResponse } from '$lib/api/devices';
	import { deviceCache } from '$lib/stores/deviceCache.svelte';

	let devices = $state<DeviceResponse[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	onMount(async () => {
		// Try to load from cache first for instant display
		const cached = deviceCache.getCachedDevices();
		if (cached) {
			devices = cached;
			loading = false;
		}
		await loadDevices();
	});

	async function loadDevices(forceRefresh = false) {
		loading = true;
		error = null;
		try {
			devices = await deviceCache.getDevices(forceRefresh);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load devices';
		} finally {
			loading = false;
		}
	}

	async function handlePair(deviceId: string) {
		error = null;
		try {
			await pairDevice(deviceId);
			deviceCache.invalidate();
			await loadDevices(true);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to pair device';
		}
	}

	async function handleUnpair(deviceId: string) {
		error = null;
		try {
			await unpairDevice(deviceId);
			deviceCache.invalidate();
			await loadDevices(true);
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
		<button onclick={() => loadDevices(true)} class="btn-secondary">Retry</button>
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
