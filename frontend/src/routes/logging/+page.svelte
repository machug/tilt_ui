<script lang="ts">
	import { onMount } from 'svelte';
	import { configState, updateConfig } from '$lib/stores/config.svelte';

	interface Stats {
		total_readings: number;
		oldest_reading: string | null;
		newest_reading: string | null;
		estimated_size_bytes: number;
	}

	let stats = $state<Stats | null>(null);
	let loading = $state(true);
	let saving = $state(false);

	// Local form state
	let loggingEnabled = $state(true);
	let intervalMinutes = $state(15);

	async function loadStats() {
		try {
			const response = await fetch('/api/stats');
			if (response.ok) {
				stats = await response.json();
			}
		} catch (e) {
			console.error('Failed to load stats:', e);
		} finally {
			loading = false;
		}
	}

	function syncFromConfig() {
		loggingEnabled = configState.config.local_logging_enabled;
		intervalMinutes = configState.config.local_interval_minutes;
	}

	async function saveSettings() {
		saving = true;
		try {
			await updateConfig({
				local_logging_enabled: loggingEnabled,
				local_interval_minutes: intervalMinutes
			});
		} finally {
			saving = false;
		}
	}

	function formatBytes(bytes: number): string {
		if (!Number.isFinite(bytes) || bytes < 0) return `${0} B`;
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}

	function formatDate(isoString: string | null): string {
		if (!isoString) return 'N/A';
		return new Date(isoString).toLocaleString();
	}

	function formatNumber(n: number): string {
		return n.toLocaleString();
	}

	onMount(() => {
		loadStats();
		syncFromConfig();
	});

	// Sync when config loads
	$effect(() => {
		if (configState.loaded) {
			syncFromConfig();
		}
	});
</script>

<svelte:head>
	<title>Logging | Tilt UI</title>
</svelte:head>

<div class="page-container">
	<div class="page-header">
		<h1 class="page-title">Logging</h1>
		<p class="page-description">Configure local data logging and export readings</p>
	</div>

	<div class="grid gap-6 md:grid-cols-2">
		<!-- Logging Settings -->
		<div class="card">
			<div class="card-header">
				<h2 class="card-title">Settings</h2>
			</div>
			<div class="card-body">
				<!-- Enable/Disable Toggle -->
				<div class="setting-row">
					<div class="setting-info">
						<span class="setting-label">Local Logging</span>
						<span class="setting-description">Store readings to database</span>
					</div>
					<button
						type="button"
						class="toggle"
						class:active={loggingEnabled}
						onclick={() => (loggingEnabled = !loggingEnabled)}
						aria-pressed={loggingEnabled}
						aria-label="Toggle local logging"
					>
						<span class="toggle-slider"></span>
					</button>
				</div>

				<!-- Logging Interval -->
				<div class="setting-row">
					<div class="setting-info">
						<span class="setting-label">Logging Interval</span>
						<span class="setting-description">How often to save readings</span>
					</div>
					<div class="interval-select">
						<select
							bind:value={intervalMinutes}
							class="select-input"
							disabled={!loggingEnabled}
						>
							<option value={1}>1 min</option>
							<option value={5}>5 min</option>
							<option value={10}>10 min</option>
							<option value={15}>15 min</option>
							<option value={30}>30 min</option>
							<option value={60}>60 min</option>
						</select>
					</div>
				</div>

				<!-- Save Button -->
				<div class="mt-6">
					<button
						type="button"
						class="btn-primary"
						onclick={saveSettings}
						disabled={saving}
					>
						{#if saving}
							<span class="loading-dot"></span>
							Saving...
						{:else}
							Save Settings
						{/if}
					</button>
				</div>
			</div>
		</div>

		<!-- Database Stats -->
		<div class="card">
			<div class="card-header">
				<h2 class="card-title">Database</h2>
			</div>
			<div class="card-body">
				{#if loading}
					<div class="loading-state">
						<div class="loading-spinner"></div>
						<span>Loading statistics...</span>
					</div>
				{:else if stats}
					<div class="stats-grid">
						<div class="stat-item">
							<span class="stat-value font-mono">{formatNumber(stats.total_readings)}</span>
							<span class="stat-label">Total Readings</span>
						</div>
						<div class="stat-item">
							<span class="stat-value font-mono">{formatBytes(stats.estimated_size_bytes)}</span>
							<span class="stat-label">Estimated Size</span>
						</div>
						<div class="stat-item full-width">
							<span class="stat-label">Data Range</span>
							<span class="stat-range font-mono">
								{formatDate(stats.oldest_reading)} — {formatDate(stats.newest_reading)}
							</span>
						</div>
					</div>
				{:else}
					<p class="text-muted">No statistics available</p>
				{/if}
			</div>
		</div>

		<!-- Export Section -->
		<div class="card md:col-span-2">
			<div class="card-header">
				<h2 class="card-title">Export Data</h2>
			</div>
			<div class="card-body">
				<div class="export-section">
					<div class="export-info">
						<p class="export-description">
							Download all recorded readings as a CSV file. The export includes timestamp,
							tilt ID, color, beer name, raw and calibrated values for SG and temperature,
							and signal strength.
						</p>
					</div>
					<a
						href="/log.csv"
						download="tilt_readings.csv"
						class="btn-secondary"
					>
						<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
						</svg>
						Download CSV
					</a>
				</div>
			</div>
		</div>
	</div>
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
		background: var(--accent-muted);
		border-color: var(--accent);
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
		background: var(--accent);
	}

	/* Select Input */
	.select-input {
		padding: 0.375rem 2rem 0.375rem 0.75rem;
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
		background-position: right 0.5rem center;
		background-size: 1rem;
	}

	.select-input:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.select-input:focus {
		outline: none;
		border-color: var(--accent);
	}

	/* Buttons */
	.btn-primary {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.625rem 1.25rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: white;
		background: var(--accent);
		border: none;
		border-radius: 0.5rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.btn-primary:hover {
		background: var(--accent-hover);
	}

	.btn-primary:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.btn-secondary {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.625rem 1.25rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--accent);
		background: var(--accent-muted);
		border: 1px solid var(--accent);
		border-radius: 0.5rem;
		cursor: pointer;
		text-decoration: none;
		transition: all 0.15s ease;
	}

	.btn-secondary:hover {
		background: var(--accent-hover);
		color: white;
		border-color: var(--accent-hover);
	}

	/* Stats */
	.stats-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 1rem;
	}

	.stat-item {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.stat-item.full-width {
		grid-column: span 2;
		padding-top: 0.75rem;
		border-top: 1px solid var(--bg-hover);
	}

	.stat-value {
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--accent);
	}

	.stat-label {
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.stat-range {
		font-size: 0.75rem;
		color: var(--text-secondary);
		margin-top: 0.25rem;
	}

	/* Export */
	.export-section {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1.5rem;
	}

	.export-description {
		font-size: 0.8125rem;
		color: var(--text-secondary);
		line-height: 1.5;
		max-width: 36rem;
	}

	/* Loading States */
	.loading-state {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		color: var(--text-muted);
		font-size: 0.8125rem;
	}

	.loading-spinner {
		width: 1.25rem;
		height: 1.25rem;
		border: 2px solid var(--bg-hover);
		border-top-color: var(--accent);
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

	@media (max-width: 640px) {
		.export-section {
			flex-direction: column;
			align-items: flex-start;
		}

		.stats-grid {
			grid-template-columns: 1fr;
		}

		.stat-item.full-width {
			grid-column: span 1;
		}
	}
</style>
