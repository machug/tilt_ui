<script lang="ts">
	import { onMount } from 'svelte';
	import { configState, updateConfig } from '$lib/stores/config.svelte';

	interface SystemInfo {
		hostname: string;
		ip_addresses: string[];
		uptime_seconds: number | null;
		version: string;
	}

	interface StorageStats {
		total_readings: number;
		oldest_reading: string | null;
		newest_reading: string | null;
		estimated_size_bytes: number;
	}

	let systemInfo = $state<SystemInfo | null>(null);
	let storageStats = $state<StorageStats | null>(null);
	let timezones = $state<string[]>([]);
	let currentTimezone = $state('');
	let loading = $state(true);
	let actionInProgress = $state<string | null>(null);

	// Config form state
	let tempUnits = $state<'C' | 'F'>('C');
	let minRssi = $state(-100);
	let smoothingEnabled = $state(false);
	let smoothingSamples = $state(5);
	let idByMac = $state(false);
	let configSaving = $state(false);

	// Cleanup state
	let cleanupRetentionDays = $state(30);
	let cleanupPreview = $state<{ readings_to_delete: number } | null>(null);

	async function loadSystemInfo() {
		try {
			const response = await fetch('/api/system/info');
			if (response.ok) {
				systemInfo = await response.json();
			}
		} catch (e) {
			console.error('Failed to load system info:', e);
		}
	}

	async function loadStorageStats() {
		try {
			const response = await fetch('/api/system/storage');
			if (response.ok) {
				storageStats = await response.json();
			}
		} catch (e) {
			console.error('Failed to load storage stats:', e);
		}
	}

	async function loadTimezones() {
		try {
			const [tzListRes, tzCurrentRes] = await Promise.all([
				fetch('/api/system/timezones'),
				fetch('/api/system/timezone')
			]);
			if (tzListRes.ok) {
				const data = await tzListRes.json();
				timezones = data.timezones || [];
			}
			if (tzCurrentRes.ok) {
				const data = await tzCurrentRes.json();
				currentTimezone = data.timezone || 'UTC';
			}
		} catch (e) {
			console.error('Failed to load timezones:', e);
		}
	}

	function syncConfigFromStore() {
		tempUnits = configState.config.temp_units;
		minRssi = configState.config.min_rssi;
		smoothingEnabled = configState.config.smoothing_enabled;
		smoothingSamples = configState.config.smoothing_samples;
		idByMac = configState.config.id_by_mac;
	}

	async function saveConfig() {
		configSaving = true;
		try {
			await updateConfig({
				temp_units: tempUnits,
				min_rssi: minRssi,
				smoothing_enabled: smoothingEnabled,
				smoothing_samples: smoothingSamples,
				id_by_mac: idByMac
			});
		} finally {
			configSaving = false;
		}
	}

	async function setTimezone(tz: string) {
		actionInProgress = 'timezone';
		try {
			const response = await fetch('/api/system/timezone', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ timezone: tz })
			});
			if (response.ok) {
				currentTimezone = tz;
			}
		} catch (e) {
			console.error('Failed to set timezone:', e);
		} finally {
			actionInProgress = null;
		}
	}

	async function previewCleanup() {
		actionInProgress = 'cleanup-preview';
		try {
			const response = await fetch('/api/system/cleanup', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ retention_days: cleanupRetentionDays, confirm: false })
			});
			if (response.ok) {
				cleanupPreview = await response.json();
			}
		} catch (e) {
			console.error('Failed to preview cleanup:', e);
		} finally {
			actionInProgress = null;
		}
	}

	async function executeCleanup() {
		if (!cleanupPreview || cleanupPreview.readings_to_delete === 0) return;

		if (!confirm(`Delete ${cleanupPreview.readings_to_delete.toLocaleString()} readings older than ${cleanupRetentionDays} days?`)) {
			return;
		}

		actionInProgress = 'cleanup';
		try {
			const response = await fetch('/api/system/cleanup', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ retention_days: cleanupRetentionDays, confirm: true })
			});
			if (response.ok) {
				cleanupPreview = null;
				await loadStorageStats();
			}
		} catch (e) {
			console.error('Failed to execute cleanup:', e);
		} finally {
			actionInProgress = null;
		}
	}

	async function rebootSystem() {
		if (!confirm('Are you sure you want to reboot the system? The UI will be unavailable until restart completes.')) {
			return;
		}
		actionInProgress = 'reboot';
		try {
			await fetch('/api/system/reboot', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ confirm: true })
			});
		} catch (e) {
			console.error('Reboot command failed:', e);
		} finally {
			actionInProgress = null;
		}
	}

	async function shutdownSystem() {
		if (!confirm('Are you sure you want to shut down the system? You will need physical access to restart.')) {
			return;
		}
		actionInProgress = 'shutdown';
		try {
			await fetch('/api/system/shutdown', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ confirm: true })
			});
		} catch (e) {
			console.error('Shutdown command failed:', e);
		} finally {
			actionInProgress = null;
		}
	}

	function formatUptime(seconds: number | null): string {
		if (!seconds) return 'Unknown';
		const days = Math.floor(seconds / 86400);
		const hours = Math.floor((seconds % 86400) / 3600);
		const minutes = Math.floor((seconds % 3600) / 60);

		const parts = [];
		if (days > 0) parts.push(`${days}d`);
		if (hours > 0) parts.push(`${hours}h`);
		if (minutes > 0) parts.push(`${minutes}m`);
		return parts.length > 0 ? parts.join(' ') : '< 1m';
	}

	function formatBytes(bytes: number): string {
		if (!Number.isFinite(bytes) || bytes < 0) return '0 B';
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}

	function formatNumber(n: number): string {
		return n.toLocaleString();
	}

	onMount(async () => {
		await Promise.all([
			loadSystemInfo(),
			loadStorageStats(),
			loadTimezones()
		]);
		syncConfigFromStore();
		loading = false;
	});

	// Sync config when loaded
	$effect(() => {
		if (configState.loaded) {
			syncConfigFromStore();
		}
	});
</script>

<svelte:head>
	<title>System | Tilt UI</title>
</svelte:head>

<div class="page-container">
	<div class="page-header">
		<h1 class="page-title">System</h1>
		<p class="page-description">System settings, timezone configuration, and power controls</p>
	</div>

	{#if loading}
		<div class="loading-state">
			<div class="loading-spinner"></div>
			<span>Loading system information...</span>
		</div>
	{:else}
		<div class="grid gap-6">
			<!-- System Info Card -->
			<div class="card">
				<div class="card-header">
					<h2 class="card-title">System Information</h2>
				</div>
				<div class="card-body">
					{#if systemInfo}
						<div class="info-grid">
							<div class="info-item">
								<span class="info-label">Hostname</span>
								<span class="info-value font-mono">{systemInfo.hostname}</span>
							</div>
							<div class="info-item">
								<span class="info-label">Version</span>
								<span class="info-value font-mono">v{systemInfo.version}</span>
							</div>
							<div class="info-item">
								<span class="info-label">Uptime</span>
								<span class="info-value font-mono">{formatUptime(systemInfo.uptime_seconds)}</span>
							</div>
							<div class="info-item">
								<span class="info-label">IP Address</span>
								<span class="info-value font-mono">
									{systemInfo.ip_addresses.length > 0 ? systemInfo.ip_addresses[0] : 'Unknown'}
								</span>
							</div>
						</div>
					{:else}
						<p class="text-muted">Unable to load system information</p>
					{/if}
				</div>
			</div>

			<div class="grid gap-6 md:grid-cols-2">
				<!-- Application Settings -->
				<div class="card">
					<div class="card-header">
						<h2 class="card-title">Application Settings</h2>
					</div>
					<div class="card-body">
						<!-- Temperature Units -->
						<div class="setting-row">
							<div class="setting-info">
								<span class="setting-label">Temperature Units</span>
								<span class="setting-description">Display temperature in Celsius or Fahrenheit</span>
							</div>
							<div class="unit-toggle">
								<button
									type="button"
									class="unit-btn"
									class:active={tempUnits === 'C'}
									onclick={() => (tempUnits = 'C')}
								>°C</button>
								<button
									type="button"
									class="unit-btn"
									class:active={tempUnits === 'F'}
									onclick={() => (tempUnits = 'F')}
								>°F</button>
							</div>
						</div>

						<!-- Minimum RSSI -->
						<div class="setting-row">
							<div class="setting-info">
								<span class="setting-label">Minimum RSSI</span>
								<span class="setting-description">Ignore readings below this signal strength</span>
							</div>
							<div class="rssi-input">
								<input
									type="number"
									min="-100"
									max="0"
									bind:value={minRssi}
									class="input-field-sm"
								/>
								<span class="input-suffix">dBm</span>
							</div>
						</div>

						<!-- Smoothing -->
						<div class="setting-row">
							<div class="setting-info">
								<span class="setting-label">Reading Smoothing</span>
								<span class="setting-description">Average multiple readings to reduce noise</span>
							</div>
							<button
								type="button"
								class="toggle"
								class:active={smoothingEnabled}
								onclick={() => (smoothingEnabled = !smoothingEnabled)}
								aria-pressed={smoothingEnabled}
								aria-label="Toggle reading smoothing"
							>
								<span class="toggle-slider"></span>
							</button>
						</div>

						{#if smoothingEnabled}
							<div class="setting-row sub-setting">
								<div class="setting-info">
									<span class="setting-label">Smoothing Samples</span>
									<span class="setting-description">Number of readings to average</span>
								</div>
								<select bind:value={smoothingSamples} class="select-input-sm">
									<option value={3}>3</option>
									<option value={5}>5</option>
									<option value={10}>10</option>
									<option value={15}>15</option>
									<option value={20}>20</option>
								</select>
							</div>
						{/if}

						<!-- ID by MAC -->
						<div class="setting-row">
							<div class="setting-info">
								<span class="setting-label">Identify by MAC</span>
								<span class="setting-description">Use MAC address instead of broadcast ID</span>
							</div>
							<button
								type="button"
								class="toggle"
								class:active={idByMac}
								onclick={() => (idByMac = !idByMac)}
								aria-pressed={idByMac}
								aria-label="Toggle identify by MAC address"
							>
								<span class="toggle-slider"></span>
							</button>
						</div>

						<!-- Save Button -->
						<div class="mt-4">
							<button
								type="button"
								class="btn-primary"
								onclick={saveConfig}
								disabled={configSaving}
							>
								{#if configSaving}
									<span class="loading-dot"></span>
									Saving...
								{:else}
									Save Settings
								{/if}
							</button>
						</div>
					</div>
				</div>

				<!-- Timezone Settings -->
				<div class="card">
					<div class="card-header">
						<h2 class="card-title">Timezone</h2>
					</div>
					<div class="card-body">
						<p class="section-description">
							Current timezone: <span class="font-mono text-[var(--amber-400)]">{currentTimezone}</span>
						</p>
						<div class="timezone-selector">
							<select
								class="select-input"
								value={currentTimezone}
								onchange={(e) => setTimezone(e.currentTarget.value)}
								disabled={actionInProgress === 'timezone'}
							>
								{#each timezones as tz}
									<option value={tz}>{tz}</option>
								{/each}
							</select>
							{#if actionInProgress === 'timezone'}
								<div class="loading-spinner-small"></div>
							{/if}
						</div>
					</div>
				</div>
			</div>

			<!-- Storage & Cleanup -->
			<div class="card">
				<div class="card-header">
					<h2 class="card-title">Storage & Data Cleanup</h2>
				</div>
				<div class="card-body">
					<div class="storage-grid">
						<!-- Stats -->
						<div class="storage-stats">
							{#if storageStats}
								<div class="stat-item">
									<span class="stat-value font-mono">{formatNumber(storageStats.total_readings)}</span>
									<span class="stat-label">Total Readings</span>
								</div>
								<div class="stat-item">
									<span class="stat-value font-mono">{formatBytes(storageStats.estimated_size_bytes)}</span>
									<span class="stat-label">Estimated Size</span>
								</div>
							{:else}
								<p class="text-muted">Unable to load storage stats</p>
							{/if}
						</div>

						<!-- Cleanup Controls -->
						<div class="cleanup-section">
							<p class="section-description mb-3">
								Remove old readings to free up storage. Readings older than the specified days will be permanently deleted.
							</p>
							<div class="cleanup-controls">
								<div class="cleanup-input-group">
									<label for="retention-days">Keep readings from last</label>
									<input
										id="retention-days"
										type="number"
										min="1"
										max="365"
										bind:value={cleanupRetentionDays}
										class="input-field-sm"
									/>
									<span>days</span>
								</div>
								<div class="cleanup-actions">
									<button
										type="button"
										class="btn-secondary-sm"
										onclick={previewCleanup}
										disabled={actionInProgress !== null}
									>
										{actionInProgress === 'cleanup-preview' ? 'Checking...' : 'Preview'}
									</button>
									{#if cleanupPreview && cleanupPreview.readings_to_delete > 0}
										<button
											type="button"
											class="btn-danger-sm"
											onclick={executeCleanup}
											disabled={actionInProgress !== null}
										>
											{actionInProgress === 'cleanup' ? 'Deleting...' : `Delete ${formatNumber(cleanupPreview.readings_to_delete)} readings`}
										</button>
									{/if}
								</div>
							</div>
							{#if cleanupPreview && cleanupPreview.readings_to_delete === 0}
								<p class="cleanup-message">No readings older than {cleanupRetentionDays} days found.</p>
							{/if}
						</div>
					</div>
				</div>
			</div>

			<!-- Power Controls -->
			<div class="card danger-zone">
				<div class="card-header">
					<h2 class="card-title">Power Controls</h2>
				</div>
				<div class="card-body">
					<p class="section-description danger-text">
						These actions will affect the entire system. Make sure you have saved any pending work.
					</p>
					<div class="power-buttons">
						<button
							type="button"
							class="btn-warning"
							onclick={rebootSystem}
							disabled={actionInProgress !== null}
						>
							{#if actionInProgress === 'reboot'}
								<span class="loading-dot"></span>
								Rebooting...
							{:else}
								<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
								</svg>
								Reboot System
							{/if}
						</button>
						<button
							type="button"
							class="btn-danger"
							onclick={shutdownSystem}
							disabled={actionInProgress !== null}
						>
							{#if actionInProgress === 'shutdown'}
								<span class="loading-dot"></span>
								Shutting down...
							{:else}
								<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
								</svg>
								Shutdown System
							{/if}
						</button>
					</div>
				</div>
			</div>
		</div>
	{/if}
</div>

<style>
	.page-container {
		max-width: 56rem;
	}

	.page-header {
		margin-bottom: 1.5rem;
	}

	.page-title {
		font-size: 1.5rem;
		font-weight: 700;
		color: var(--text-primary);
		margin-bottom: 0.25rem;
	}

	.page-description {
		color: var(--text-secondary);
		font-size: 0.875rem;
	}

	.card {
		background: var(--bg-card);
		border: 1px solid var(--bg-hover);
		border-radius: 0.75rem;
		overflow: hidden;
	}

	.card.danger-zone {
		border-color: rgba(244, 63, 94, 0.2);
	}

	.card-header {
		padding: 1rem 1.25rem;
		border-bottom: 1px solid var(--bg-hover);
	}

	.card-title {
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--text-primary);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.card-body {
		padding: 1.25rem;
	}

	.section-description {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin-bottom: 1rem;
		line-height: 1.5;
	}

	/* Info Grid */
	.info-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 1rem;
	}

	.info-item {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.info-label {
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.info-value {
		font-size: 0.875rem;
		color: var(--text-primary);
	}

	/* Settings */
	.setting-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.875rem 0;
		border-bottom: 1px solid var(--bg-hover);
	}

	.setting-row:last-of-type {
		border-bottom: none;
	}

	.setting-row.sub-setting {
		padding-left: 1rem;
		opacity: 0.9;
	}

	.setting-info {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
	}

	.setting-label {
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--text-primary);
	}

	.setting-description {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	/* Toggle Switch */
	.toggle {
		position: relative;
		width: 2.75rem;
		height: 1.5rem;
		background: var(--bg-elevated);
		border: 1px solid var(--bg-hover);
		border-radius: 0.75rem;
		cursor: pointer;
		transition: all 0.2s ease;
	}

	.toggle.active {
		background: rgba(251, 191, 36, 0.2);
		border-color: var(--amber-400);
	}

	.toggle-slider {
		position: absolute;
		top: 2px;
		left: 2px;
		width: 1.125rem;
		height: 1.125rem;
		background: var(--text-muted);
		border-radius: 50%;
		transition: all 0.2s ease;
	}

	.toggle.active .toggle-slider {
		left: calc(100% - 1.125rem - 2px);
		background: var(--amber-400);
	}

	/* Unit Toggle */
	.unit-toggle {
		display: flex;
		background: var(--bg-elevated);
		border: 1px solid var(--bg-hover);
		border-radius: 0.5rem;
		overflow: hidden;
	}

	.unit-btn {
		padding: 0.375rem 0.75rem;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--text-muted);
		background: transparent;
		border: none;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.unit-btn.active {
		color: var(--amber-400);
		background: rgba(251, 191, 36, 0.1);
	}

	/* Inputs */
	.input-field-sm {
		width: 4rem;
		padding: 0.375rem 0.5rem;
		font-size: 0.8125rem;
		font-family: 'JetBrains Mono', monospace;
		color: var(--text-primary);
		background: var(--bg-elevated);
		border: 1px solid var(--bg-hover);
		border-radius: 0.375rem;
		text-align: center;
	}

	.input-field-sm:focus {
		outline: none;
		border-color: var(--amber-400);
	}

	.rssi-input {
		display: flex;
		align-items: center;
		gap: 0.375rem;
	}

	.input-suffix {
		font-size: 0.75rem;
		color: var(--text-muted);
		font-family: 'JetBrains Mono', monospace;
	}

	.select-input-sm {
		padding: 0.375rem 1.75rem 0.375rem 0.5rem;
		font-size: 0.8125rem;
		font-family: 'JetBrains Mono', monospace;
		color: var(--text-primary);
		background: var(--bg-elevated);
		border: 1px solid var(--bg-hover);
		border-radius: 0.375rem;
		cursor: pointer;
		appearance: none;
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2371717a'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'/%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: right 0.375rem center;
		background-size: 1rem;
	}

	/* Timezone */
	.timezone-selector {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.select-input {
		flex: 1;
		max-width: 20rem;
		padding: 0.625rem 2.5rem 0.625rem 1rem;
		font-size: 0.875rem;
		color: var(--text-primary);
		background: var(--bg-elevated);
		border: 1px solid var(--bg-hover);
		border-radius: 0.5rem;
		cursor: pointer;
		appearance: none;
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2371717a'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'/%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: right 0.75rem center;
		background-size: 1.25rem;
	}

	.select-input:focus {
		outline: none;
		border-color: var(--amber-400);
	}

	/* Storage */
	.storage-grid {
		display: grid;
		gap: 1.5rem;
	}

	.storage-stats {
		display: flex;
		gap: 2rem;
	}

	.stat-item {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.stat-value {
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--amber-400);
	}

	.stat-label {
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	/* Cleanup */
	.cleanup-section {
		padding-top: 1rem;
		border-top: 1px solid var(--bg-hover);
	}

	.cleanup-controls {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 1rem;
	}

	.cleanup-input-group {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.8125rem;
		color: var(--text-secondary);
	}

	.cleanup-actions {
		display: flex;
		gap: 0.5rem;
	}

	.cleanup-message {
		margin-top: 0.75rem;
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	/* Power Controls */
	.danger-text {
		color: var(--tilt-red);
	}

	.power-buttons {
		display: flex;
		gap: 0.75rem;
	}

	/* Buttons */
	.btn-primary {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.625rem 1.25rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--bg-deep);
		background: var(--amber-400);
		border: none;
		border-radius: 0.5rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.btn-primary:hover {
		background: var(--amber-500);
	}

	.btn-primary:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.btn-secondary-sm {
		padding: 0.375rem 0.75rem;
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--amber-400);
		background: rgba(251, 191, 36, 0.1);
		border: 1px solid rgba(251, 191, 36, 0.2);
		border-radius: 0.375rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.btn-secondary-sm:hover:not(:disabled) {
		background: rgba(251, 191, 36, 0.15);
	}

	.btn-secondary-sm:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.btn-danger-sm {
		padding: 0.375rem 0.75rem;
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--tilt-red);
		background: rgba(244, 63, 94, 0.1);
		border: 1px solid rgba(244, 63, 94, 0.2);
		border-radius: 0.375rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.btn-danger-sm:hover:not(:disabled) {
		background: rgba(244, 63, 94, 0.15);
	}

	.btn-danger-sm:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.btn-warning {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.625rem 1.25rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--tilt-orange);
		background: rgba(251, 146, 60, 0.1);
		border: 1px solid rgba(251, 146, 60, 0.2);
		border-radius: 0.5rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.btn-warning:hover:not(:disabled) {
		background: rgba(251, 146, 60, 0.15);
		border-color: rgba(251, 146, 60, 0.3);
	}

	.btn-warning:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.btn-danger {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.625rem 1.25rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--tilt-red);
		background: rgba(244, 63, 94, 0.1);
		border: 1px solid rgba(244, 63, 94, 0.2);
		border-radius: 0.5rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.btn-danger:hover:not(:disabled) {
		background: rgba(244, 63, 94, 0.15);
		border-color: rgba(244, 63, 94, 0.3);
	}

	.btn-danger:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	/* Loading States */
	.loading-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 1rem;
		padding: 4rem 2rem;
		color: var(--text-muted);
	}

	.loading-spinner {
		width: 2rem;
		height: 2rem;
		border: 2px solid var(--bg-hover);
		border-top-color: var(--amber-400);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	.loading-spinner-small {
		width: 1rem;
		height: 1rem;
		border: 2px solid var(--bg-hover);
		border-top-color: var(--amber-400);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	.loading-dot {
		width: 0.375rem;
		height: 0.375rem;
		background: currentColor;
		border-radius: 50%;
		animation: pulse 1s ease-in-out infinite;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	@keyframes pulse {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.4; }
	}

	.text-muted {
		color: var(--text-muted);
		font-size: 0.8125rem;
	}

	.mt-4 {
		margin-top: 1rem;
	}

	.mb-3 {
		margin-bottom: 0.75rem;
	}

	@media (max-width: 640px) {
		.info-grid {
			grid-template-columns: 1fr;
		}

		.storage-stats {
			flex-direction: column;
			gap: 1rem;
		}

		.cleanup-controls {
			flex-direction: column;
			align-items: flex-start;
		}

		.power-buttons {
			flex-direction: column;
		}
	}
</style>
