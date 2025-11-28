<script lang="ts">
	import { onMount } from 'svelte';
	import { configState, formatTemp, getTempUnit } from '$lib/stores/config.svelte';

	interface Tilt {
		id: string;
		color: string;
		beer_name: string;
		mac: string | null;
		last_seen: string | null;
	}

	interface CalibrationPoint {
		id: number;
		type: 'sg' | 'temp';
		raw_value: number;
		actual_value: number;
	}

	let tilts = $state<Tilt[]>([]);
	let selectedTiltId = $state<string | null>(null);
	let calibrationPoints = $state<CalibrationPoint[]>([]);
	let loading = $state(true);
	let loadingPoints = $state(false);
	let saving = $state(false);

	// Form state for adding new points
	let sgRawValue = $state('');
	let sgActualValue = $state('');
	let tempRawValue = $state('');
	let tempActualValue = $state('');

	// Reactive temp unit
	let tempUnit = $derived(getTempUnit());
	let useCelsius = $derived(configState.config.temp_units === 'C');

	// Filter points by type
	let sgPoints = $derived(calibrationPoints.filter((p) => p.type === 'sg').sort((a, b) => a.raw_value - b.raw_value));
	let tempPoints = $derived(calibrationPoints.filter((p) => p.type === 'temp').sort((a, b) => a.raw_value - b.raw_value));

	// Selected tilt object
	let selectedTilt = $derived(tilts.find((t) => t.id === selectedTiltId));

	async function loadTilts() {
		try {
			const response = await fetch('/api/tilts');
			if (response.ok) {
				tilts = await response.json();
				if (tilts.length > 0 && !selectedTiltId) {
					selectedTiltId = tilts[0].id;
				}
			}
		} catch (e) {
			console.error('Failed to load tilts:', e);
		} finally {
			loading = false;
		}
	}

	async function loadCalibrationPoints() {
		if (!selectedTiltId) return;
		loadingPoints = true;
		try {
			const response = await fetch(`/api/tilts/${selectedTiltId}/calibration`);
			if (response.ok) {
				calibrationPoints = await response.json();
			}
		} catch (e) {
			console.error('Failed to load calibration points:', e);
		} finally {
			loadingPoints = false;
		}
	}

	async function addCalibrationPoint(type: 'sg' | 'temp', rawValue: string, actualValue: string) {
		if (!selectedTiltId) return;

		const raw = parseFloat(rawValue);
		const actual = parseFloat(actualValue);

		if (isNaN(raw) || isNaN(actual)) {
			return;
		}

		saving = true;
		try {
			const response = await fetch(`/api/tilts/${selectedTiltId}/calibration`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					type,
					raw_value: raw,
					actual_value: actual
				})
			});

			if (response.ok) {
				// Clear form and reload
				if (type === 'sg') {
					sgRawValue = '';
					sgActualValue = '';
				} else {
					tempRawValue = '';
					tempActualValue = '';
				}
				await loadCalibrationPoints();
			}
		} catch (e) {
			console.error('Failed to add calibration point:', e);
		} finally {
			saving = false;
		}
	}

	async function clearCalibration(type: 'sg' | 'temp') {
		if (!selectedTiltId) return;

		if (!confirm(`Clear all ${type === 'sg' ? 'gravity' : 'temperature'} calibration points?`)) {
			return;
		}

		saving = true;
		try {
			const response = await fetch(`/api/tilts/${selectedTiltId}/calibration/${type}`, {
				method: 'DELETE'
			});

			if (response.ok) {
				await loadCalibrationPoints();
			}
		} catch (e) {
			console.error('Failed to clear calibration:', e);
		} finally {
			saving = false;
		}
	}

	function formatSG(sg: number): string {
		return sg.toFixed(3);
	}

	function formatTempDisplay(temp: number): string {
		// Temp is stored as Fahrenheit in the database
		if (useCelsius) {
			return ((temp - 32) * (5 / 9)).toFixed(1);
		}
		return temp.toFixed(1);
	}

	onMount(() => {
		loadTilts();
	});

	// Load calibration when tilt changes
	$effect(() => {
		if (selectedTiltId) {
			loadCalibrationPoints();
		}
	});
</script>

<svelte:head>
	<title>Calibration | Tilt UI</title>
</svelte:head>

<div class="page-container">
	<div class="page-header">
		<h1 class="page-title">Calibration</h1>
		<p class="page-description">Fine-tune SG and temperature readings with calibration points</p>
	</div>

	{#if loading}
		<div class="loading-state">
			<div class="loading-spinner"></div>
			<span>Loading Tilts...</span>
		</div>
	{:else if tilts.length === 0}
		<div class="empty-state">
			<div class="empty-icon">📊</div>
			<h3 class="empty-title">No Tilts Found</h3>
			<p class="empty-description">
				Connect a Tilt hydrometer to start calibrating.
				Tilts will appear here once detected.
			</p>
		</div>
	{:else}
		<!-- Tilt Selector -->
		<div class="card mb-6">
			<div class="card-header">
				<h2 class="card-title">Select Tilt</h2>
			</div>
			<div class="card-body">
				<div class="tilt-selector">
					<select
						bind:value={selectedTiltId}
						class="select-input"
					>
						{#each tilts as tilt}
							<option value={tilt.id}>
								{tilt.color} — {tilt.beer_name}
							</option>
						{/each}
					</select>
					{#if selectedTilt}
						<div class="tilt-info">
							<span class="tilt-color-dot" style="background: var(--tilt-{selectedTilt.color.toLowerCase()});"></span>
							<span class="font-mono text-xs text-[var(--text-muted)]">{selectedTilt.id}</span>
						</div>
					{/if}
				</div>
			</div>
		</div>

		<div class="grid gap-6 md:grid-cols-2">
			<!-- SG Calibration -->
			<div class="card">
				<div class="card-header flex items-center justify-between">
					<h2 class="card-title">Gravity (SG)</h2>
					{#if sgPoints.length > 0}
						<button
							type="button"
							class="btn-danger-small"
							onclick={() => clearCalibration('sg')}
							disabled={saving}
						>
							Clear All
						</button>
					{/if}
				</div>
				<div class="card-body">
					<p class="section-description">
						Add calibration points by measuring with a reference hydrometer.
						The system will interpolate between points.
					</p>

					{#if loadingPoints}
						<div class="loading-inline">
							<div class="loading-spinner-small"></div>
							<span>Loading...</span>
						</div>
					{:else}
						<!-- Existing Points -->
						{#if sgPoints.length > 0}
							<div class="calibration-table">
								<div class="table-header">
									<span>Raw</span>
									<span>→</span>
									<span>Actual</span>
								</div>
								{#each sgPoints as point}
									<div class="table-row">
										<span class="font-mono">{formatSG(point.raw_value)}</span>
										<span class="text-[var(--text-muted)]">→</span>
										<span class="font-mono text-[var(--accent)]">{formatSG(point.actual_value)}</span>
									</div>
								{/each}
							</div>
						{:else}
							<div class="no-points">
								<span>No calibration points yet</span>
							</div>
						{/if}

						<!-- Add New Point Form -->
						<div class="add-point-form">
							<div class="form-row">
								<div class="form-group">
									<label for="sg-raw">Raw SG</label>
									<input
										id="sg-raw"
										type="number"
										step="0.001"
										placeholder="1.050"
										bind:value={sgRawValue}
										class="input-field"
									/>
								</div>
								<div class="form-arrow">→</div>
								<div class="form-group">
									<label for="sg-actual">Actual SG</label>
									<input
										id="sg-actual"
										type="number"
										step="0.001"
										placeholder="1.048"
										bind:value={sgActualValue}
										class="input-field"
									/>
								</div>
								<button
									type="button"
									class="btn-add"
									onclick={() => addCalibrationPoint('sg', sgRawValue, sgActualValue)}
									disabled={saving || !sgRawValue || !sgActualValue}
									aria-label="Add SG calibration point"
								>
									<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
										<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
									</svg>
								</button>
							</div>
						</div>
					{/if}
				</div>
			</div>

			<!-- Temperature Calibration -->
			<div class="card">
				<div class="card-header flex items-center justify-between">
					<h2 class="card-title">Temperature ({tempUnit})</h2>
					{#if tempPoints.length > 0}
						<button
							type="button"
							class="btn-danger-small"
							onclick={() => clearCalibration('temp')}
							disabled={saving}
						>
							Clear All
						</button>
					{/if}
				</div>
				<div class="card-body">
					<p class="section-description">
						Calibrate temperature by comparing with a reference thermometer.
						Values are stored in °F internally.
					</p>

					{#if loadingPoints}
						<div class="loading-inline">
							<div class="loading-spinner-small"></div>
							<span>Loading...</span>
						</div>
					{:else}
						<!-- Existing Points -->
						{#if tempPoints.length > 0}
							<div class="calibration-table">
								<div class="table-header">
									<span>Raw ({tempUnit})</span>
									<span>→</span>
									<span>Actual ({tempUnit})</span>
								</div>
								{#each tempPoints as point}
									<div class="table-row">
										<span class="font-mono">{formatTempDisplay(point.raw_value)}°</span>
										<span class="text-[var(--text-muted)]">→</span>
										<span class="font-mono text-[var(--accent)]">{formatTempDisplay(point.actual_value)}°</span>
									</div>
								{/each}
							</div>
						{:else}
							<div class="no-points">
								<span>No calibration points yet</span>
							</div>
						{/if}

						<!-- Add New Point Form -->
						<div class="add-point-form">
							<div class="form-row">
								<div class="form-group">
									<label for="temp-raw">Raw {tempUnit}</label>
									<input
										id="temp-raw"
										type="number"
										step="0.1"
										placeholder={useCelsius ? '20.0' : '68.0'}
										bind:value={tempRawValue}
										class="input-field"
									/>
								</div>
								<div class="form-arrow">→</div>
								<div class="form-group">
									<label for="temp-actual">Actual {tempUnit}</label>
									<input
										id="temp-actual"
										type="number"
										step="0.1"
										placeholder={useCelsius ? '19.5' : '67.5'}
										bind:value={tempActualValue}
										class="input-field"
									/>
								</div>
								<button
									type="button"
									class="btn-add"
									onclick={() => addCalibrationPoint('temp', tempRawValue, tempActualValue)}
									disabled={saving || !tempRawValue || !tempActualValue}
									aria-label="Add temperature calibration point"
								>
									<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
										<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
									</svg>
								</button>
							</div>
						</div>
					{/if}
				</div>
			</div>
		</div>

		<!-- Calibration Info -->
		<div class="info-section mt-6">
			<h3 class="info-title">How Calibration Works</h3>
			<p class="info-text">
				Add at least two calibration points for best results. The system uses linear interpolation
				between points to correct readings. For single-point calibration, only an offset is applied.
			</p>
			<div class="info-tips">
				<div class="tip">
					<span class="tip-label">Tip:</span>
					<span>For SG, use distilled water (1.000) and a known sugar solution for two-point calibration.</span>
				</div>
				<div class="tip">
					<span class="tip-label">Tip:</span>
					<span>For temperature, ice water (0°C/32°F) and room temp make good reference points.</span>
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

	/* Tilt Selector */
	.tilt-selector {
		display: flex;
		align-items: center;
		gap: 1rem;
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
		border-color: var(--accent);
	}

	.tilt-info {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.tilt-color-dot {
		width: 0.625rem;
		height: 0.625rem;
		border-radius: 50%;
	}

	/* Calibration Table */
	.calibration-table {
		margin-bottom: 1rem;
		border: 1px solid var(--bg-hover);
		border-radius: 0.5rem;
		overflow: hidden;
	}

	.table-header {
		display: grid;
		grid-template-columns: 1fr auto 1fr;
		gap: 0.5rem;
		padding: 0.625rem 1rem;
		background: var(--bg-elevated);
		font-size: 0.6875rem;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.table-row {
		display: grid;
		grid-template-columns: 1fr auto 1fr;
		gap: 0.5rem;
		padding: 0.625rem 1rem;
		font-size: 0.8125rem;
		border-top: 1px solid var(--bg-hover);
	}

	.no-points {
		padding: 1.5rem;
		text-align: center;
		color: var(--text-muted);
		font-size: 0.8125rem;
		background: var(--bg-elevated);
		border-radius: 0.5rem;
		margin-bottom: 1rem;
	}

	/* Add Point Form */
	.add-point-form {
		padding-top: 1rem;
		border-top: 1px solid var(--bg-hover);
	}

	.form-row {
		display: flex;
		align-items: flex-end;
		gap: 0.75rem;
	}

	.form-group {
		flex: 1;
	}

	.form-group label {
		display: block;
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin-bottom: 0.375rem;
	}

	.input-field {
		width: 100%;
		padding: 0.5rem 0.75rem;
		font-size: 0.8125rem;
		font-family: 'JetBrains Mono', monospace;
		color: var(--text-primary);
		background: var(--bg-elevated);
		border: 1px solid var(--bg-hover);
		border-radius: 0.375rem;
	}

	.input-field:focus {
		outline: none;
		border-color: var(--accent);
	}

	.input-field::placeholder {
		color: var(--text-muted);
		opacity: 0.5;
	}

	.form-arrow {
		padding-bottom: 0.625rem;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.btn-add {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 2.25rem;
		height: 2.25rem;
		color: white;
		background: var(--accent);
		border: 1px solid var(--accent);
		border-radius: 0.5rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.btn-add:hover:not(:disabled) {
		background: var(--accent-hover);
		border-color: var(--accent-hover);
	}

	.btn-add:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}

	.btn-danger-small {
		padding: 0.25rem 0.625rem;
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--tilt-red);
		background: rgba(244, 63, 94, 0.1);
		border: 1px solid rgba(244, 63, 94, 0.2);
		border-radius: 0.375rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.btn-danger-small:hover:not(:disabled) {
		background: rgba(244, 63, 94, 0.15);
		border-color: rgba(244, 63, 94, 0.3);
	}

	.btn-danger-small:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	/* Info Section */
	.info-section {
		background: var(--bg-card);
		border: 1px solid var(--bg-hover);
		border-radius: 0.75rem;
		padding: 1.25rem;
	}

	.info-title {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-primary);
		margin-bottom: 0.5rem;
	}

	.info-text {
		font-size: 0.8125rem;
		color: var(--text-secondary);
		line-height: 1.6;
		margin-bottom: 1rem;
	}

	.info-tips {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.tip {
		font-size: 0.75rem;
		color: var(--text-muted);
		line-height: 1.5;
	}

	.tip-label {
		font-weight: 600;
		color: var(--accent);
		margin-right: 0.25rem;
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
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	.loading-inline {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 1rem;
		color: var(--text-muted);
		font-size: 0.8125rem;
	}

	.loading-spinner-small {
		width: 1rem;
		height: 1rem;
		border: 2px solid var(--bg-hover);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	/* Empty State */
	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 4rem 2rem;
		text-align: center;
		background: var(--bg-card);
		border: 1px solid var(--bg-hover);
		border-radius: 0.75rem;
	}

	.empty-icon {
		font-size: 3rem;
		margin-bottom: 1rem;
		opacity: 0.6;
	}

	.empty-title {
		font-size: 1.125rem;
		font-weight: 600;
		color: var(--text-primary);
		margin-bottom: 0.5rem;
	}

	.empty-description {
		font-size: 0.875rem;
		color: var(--text-muted);
		max-width: 20rem;
		line-height: 1.6;
	}

	/* Grid utilities */
	.mb-6 {
		margin-bottom: 1.5rem;
	}

	.mt-6 {
		margin-top: 1.5rem;
	}

	@media (max-width: 768px) {
		.form-row {
			flex-wrap: wrap;
		}

		.form-group {
			flex: 1 1 40%;
		}

		.form-arrow {
			display: none;
		}

		.btn-add {
			flex: 0 0 100%;
			width: 100%;
			margin-top: 0.5rem;
		}
	}
</style>
