<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import type { BatchResponse, BatchProgressResponse, BatchUpdate, BatchStatus } from '$lib/api';
	import { fetchBatch, fetchBatchProgress, updateBatch, deleteBatch } from '$lib/api';
	import { formatGravity, getGravityUnit, formatTemp, getTempUnit } from '$lib/stores/config.svelte';
	import { tiltsState } from '$lib/stores/tilts.svelte';
	import BatchForm from '$lib/components/BatchForm.svelte';

	// State
	let batch = $state<BatchResponse | null>(null);
	let progress = $state<BatchProgressResponse | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let isEditing = $state(false);
	let statusUpdating = $state(false);

	let batchId = $derived(parseInt($page.params.id));

	// Status configuration
	const statusConfig: Record<string, { label: string; color: string; bg: string }> = {
		planning: { label: 'Planning', color: 'var(--text-secondary)', bg: 'var(--bg-elevated)' },
		fermenting: { label: 'Fermenting', color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.12)' },
		conditioning: { label: 'Conditioning', color: '#8b5cf6', bg: 'rgba(139, 92, 246, 0.12)' },
		completed: { label: 'Completed', color: 'var(--positive)', bg: 'rgba(34, 197, 94, 0.12)' },
		archived: { label: 'Archived', color: 'var(--text-muted)', bg: 'var(--bg-elevated)' }
	};

	const statusOptions: BatchStatus[] = ['planning', 'fermenting', 'conditioning', 'completed', 'archived'];

	let statusInfo = $derived(batch ? statusConfig[batch.status] : statusConfig.planning);
	let gravityUnit = $derived(getGravityUnit());
	let tempUnit = $derived(getTempUnit());

	// Get live readings from WebSocket if device is linked
	// device_id can be "tilt-{color}" (e.g., "tilt-red") or just "{COLOR}" (e.g., "RED")
	// tiltsState uses tilt.id as key, so we need to find by color match
	let liveReading = $derived.by(() => {
		if (!batch?.device_id) return null;
		// Extract color from device_id - handle both "tilt-red" and "RED" formats
		const colorMatch = batch.device_id.match(/^(?:tilt-)?(\w+)$/i);
		if (!colorMatch) return null;
		const targetColor = colorMatch[1].toUpperCase();
		// Find tilt with matching color
		for (const tilt of tiltsState.tilts.values()) {
			if (tilt.color.toUpperCase() === targetColor) {
				return tilt;
			}
		}
		return null;
	});

	async function loadBatch() {
		loading = true;
		error = null;
		try {
			batch = await fetchBatch(batchId);
			if (batch.status === 'fermenting' || batch.status === 'conditioning') {
				try {
					progress = await fetchBatchProgress(batchId);
				} catch {
					// Progress may not be available
				}
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load batch';
		} finally {
			loading = false;
		}
	}

	async function handleStatusChange(newStatus: BatchStatus) {
		if (!batch || statusUpdating) return;
		statusUpdating = true;
		try {
			batch = await updateBatch(batch.id, { status: newStatus });
			// Reload progress if needed
			if (newStatus === 'fermenting' || newStatus === 'conditioning') {
				progress = await fetchBatchProgress(batch.id);
			}
		} catch (e) {
			console.error('Failed to update status:', e);
		} finally {
			statusUpdating = false;
		}
	}

	async function handleFormSubmit(data: BatchUpdate) {
		if (!batch) return;
		batch = await updateBatch(batch.id, data);
		isEditing = false;
	}

	async function handleDelete() {
		if (!batch) return;
		if (!confirm(`Are you sure you want to delete "${batch.name || 'this batch'}"?`)) return;
		try {
			await deleteBatch(batch.id);
			goto('/batches');
		} catch (e) {
			alert('Failed to delete batch');
		}
	}

	function formatSG(value?: number | null): string {
		if (value === undefined || value === null) return '--';
		return formatGravity(value);
	}

	function formatTempValue(value?: number | null): string {
		if (value === undefined || value === null) return '--';
		return formatTemp(value);
	}

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

	onMount(() => {
		loadBatch();
	});
</script>

<svelte:head>
	<title>{batch?.name || 'Batch'} | BrewSignal</title>
</svelte:head>

<div class="page-container">
	<!-- Back link -->
	<div class="back-link">
		<a href="/batches" class="back-btn">
			<svg class="back-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
			</svg>
			Back to Batches
		</a>
	</div>

	{#if loading}
		<div class="loading-state">
			<div class="spinner"></div>
			<span>Loading batch...</span>
		</div>
	{:else if error}
		<div class="error-state">
			<span class="error-icon">!</span>
			<p>{error}</p>
			<button type="button" class="retry-btn" onclick={loadBatch}>Retry</button>
		</div>
	{:else if !batch}
		<div class="error-state">
			<p>Batch not found</p>
		</div>
	{:else if isEditing}
		<BatchForm
			{batch}
			onSubmit={handleFormSubmit}
			onCancel={() => (isEditing = false)}
		/>
	{:else}
		<!-- Batch Header -->
		<div class="batch-header">
			<div class="header-main">
				<div class="batch-number">#{batch.batch_number || '?'}</div>
				<div class="header-info">
					<h1 class="batch-name">{batch.name || batch.recipe?.name || 'Unnamed Batch'}</h1>
					{#if batch.recipe}
						<a href="/recipes/{batch.recipe.id}" class="recipe-link">
							{batch.recipe.name}
							{#if batch.recipe.type}
								<span class="recipe-type">({batch.recipe.type})</span>
							{/if}
						</a>
					{/if}
				</div>
			</div>
			<div class="header-actions">
				<!-- Status selector -->
				<div class="status-selector">
					<select
						class="status-select"
						value={batch.status}
						onchange={(e) => handleStatusChange(e.currentTarget.value as BatchStatus)}
						disabled={statusUpdating}
						style="color: {statusInfo.color}; background: {statusInfo.bg};"
					>
						{#each statusOptions as status}
							<option value={status}>{statusConfig[status].label}</option>
						{/each}
					</select>
				</div>
				<button type="button" class="edit-btn" onclick={() => (isEditing = true)}>
					<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
					</svg>
					Edit
				</button>
				<button type="button" class="delete-btn" onclick={handleDelete}>
					<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
					</svg>
				</button>
			</div>
		</div>

		<!-- Main content grid -->
		<div class="content-grid">
			<!-- Stats cards -->
			<div class="stats-section">
				<!-- Current/Live reading -->
				{#if liveReading || progress?.measured?.current_sg != null}
					<div class="stat-card live">
						<div class="stat-header">
							<span class="stat-title">Current</span>
							{#if liveReading}
								<span class="live-badge">
									<span class="live-dot"></span>
									Live
								</span>
							{/if}
						</div>
						<div class="stat-row">
							<div class="stat-item">
								<div class="stat-value">
									{formatSG(liveReading?.sg ?? progress?.measured?.current_sg)}
								</div>
								<div class="stat-label">{gravityUnit}</div>
							</div>
							{#if liveReading?.temp != null || progress?.temperature?.current != null}
								<div class="stat-item">
									<div class="stat-value temp">
										{formatTempValue(liveReading?.temp ?? progress?.temperature?.current)}
									</div>
									<div class="stat-label">{tempUnit}</div>
								</div>
							{/if}
						</div>
					</div>
				{/if}

				<!-- Progress -->
				{#if progress?.progress?.percent_complete != null}
					<div class="stat-card">
						<div class="stat-header">
							<span class="stat-title">Progress</span>
						</div>
						<div class="progress-display">
							<div class="progress-value">{progress.progress.percent_complete.toFixed(0)}%</div>
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
					</div>
				{/if}

				<!-- Measurements -->
				<div class="stat-card">
					<div class="stat-header">
						<span class="stat-title">Measurements</span>
					</div>
					<div class="measurements-grid">
						<div class="measurement">
							<span class="measurement-label">OG</span>
							<span class="measurement-value">{formatSG(batch.measured_og)}</span>
						</div>
						<div class="measurement">
							<span class="measurement-label">FG</span>
							<span class="measurement-value">{formatSG(batch.measured_fg)}</span>
						</div>
						<div class="measurement">
							<span class="measurement-label">ABV</span>
							<span class="measurement-value">
								{batch.measured_abv != null ? `${batch.measured_abv.toFixed(1)}%` : '--'}
							</span>
						</div>
						<div class="measurement">
							<span class="measurement-label">Atten</span>
							<span class="measurement-value">
								{batch.measured_attenuation != null ? `${batch.measured_attenuation.toFixed(0)}%` : '--'}
							</span>
						</div>
					</div>
				</div>

				<!-- Targets (from recipe) -->
				{#if batch.recipe}
					<div class="stat-card">
						<div class="stat-header">
							<span class="stat-title">Recipe Targets</span>
						</div>
						<div class="measurements-grid">
							<div class="measurement">
								<span class="measurement-label">OG</span>
								<span class="measurement-value target">{formatSG(batch.recipe.og_target)}</span>
							</div>
							<div class="measurement">
								<span class="measurement-label">FG</span>
								<span class="measurement-value target">{formatSG(batch.recipe.fg_target)}</span>
							</div>
							<div class="measurement">
								<span class="measurement-label">ABV</span>
								<span class="measurement-value target">
									{batch.recipe.abv_target != null ? `${batch.recipe.abv_target.toFixed(1)}%` : '--'}
								</span>
							</div>
							{#if batch.recipe.yeast_name}
								<div class="measurement wide">
									<span class="measurement-label">Yeast</span>
									<span class="measurement-value target">{batch.recipe.yeast_name}</span>
								</div>
							{/if}
						</div>
					</div>
				{/if}
			</div>

			<!-- Timeline & Device -->
			<div class="info-section">
				<!-- Timeline -->
				<div class="info-card">
					<h3 class="info-title">Timeline</h3>
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
				</div>

				<!-- Device -->
				<div class="info-card">
					<h3 class="info-title">Tracking Device</h3>
					{#if batch.device_id}
						<div class="device-info">
							{#if liveReading}
								<div class="device-status online">
									<span class="device-dot"></span>
									{liveReading.color} Tilt - Connected
								</div>
								<div class="device-last-seen">
									Updated just now
								</div>
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
							<button type="button" class="link-btn" onclick={() => (isEditing = true)}>
								Link a device
							</button>
						</div>
					{/if}
				</div>

				<!-- Notes -->
				{#if batch.notes}
					<div class="info-card">
						<h3 class="info-title">Notes</h3>
						<p class="notes-content">{batch.notes}</p>
					</div>
				{/if}
			</div>
		</div>
	{/if}
</div>

<style>
	.page-container {
		max-width: 1200px;
	}

	.back-link {
		margin-bottom: 1.5rem;
	}

	.back-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--text-secondary);
		text-decoration: none;
		transition: color var(--transition);
	}

	.back-btn:hover {
		color: var(--text-primary);
	}

	.back-icon {
		width: 1rem;
		height: 1rem;
	}

	/* Loading/Error states */
	.loading-state,
	.error-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 4rem 2rem;
		text-align: center;
		color: var(--text-secondary);
	}

	.spinner {
		width: 2rem;
		height: 2rem;
		border: 2px solid var(--bg-hover);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
		margin-bottom: 1rem;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	.error-icon {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 3rem;
		height: 3rem;
		font-size: 1.5rem;
		font-weight: 700;
		color: var(--negative);
		background: rgba(239, 68, 68, 0.1);
		border-radius: 50%;
		margin-bottom: 1rem;
	}

	.retry-btn {
		margin-top: 1rem;
		padding: 0.5rem 1rem;
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--text-primary);
		background: var(--bg-elevated);
		border: 1px solid var(--border-default);
		border-radius: 0.375rem;
		cursor: pointer;
	}

	/* Header */
	.batch-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 1.5rem;
		margin-bottom: 2rem;
		padding-bottom: 1.5rem;
		border-bottom: 1px solid var(--border-subtle);
	}

	.header-main {
		display: flex;
		align-items: flex-start;
		gap: 1rem;
	}

	.batch-number {
		flex-shrink: 0;
		font-family: var(--font-mono);
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--text-muted);
		background: var(--bg-elevated);
		padding: 0.375rem 0.75rem;
		border-radius: 0.375rem;
		margin-top: 0.25rem;
	}

	.header-info {
		min-width: 0;
	}

	.batch-name {
		font-size: 1.5rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0 0 0.25rem 0;
		line-height: 1.3;
	}

	.recipe-link {
		font-size: 0.875rem;
		color: var(--accent);
		text-decoration: none;
	}

	.recipe-link:hover {
		text-decoration: underline;
	}

	.recipe-type {
		color: var(--text-muted);
	}

	.header-actions {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex-shrink: 0;
	}

	.status-selector {
		position: relative;
	}

	.status-select {
		padding: 0.5rem 2rem 0.5rem 0.75rem;
		font-size: 0.8125rem;
		font-weight: 500;
		border: none;
		border-radius: 9999px;
		cursor: pointer;
		appearance: none;
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%239ca3af'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'/%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: right 0.5rem center;
		background-size: 1rem;
	}

	.edit-btn,
	.delete-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.5rem 0.75rem;
		font-size: 0.8125rem;
		font-weight: 500;
		border-radius: 0.375rem;
		cursor: pointer;
		transition: all var(--transition);
	}

	.edit-btn {
		color: var(--text-secondary);
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
	}

	.edit-btn:hover {
		color: var(--text-primary);
		border-color: var(--border-default);
	}

	.delete-btn {
		color: var(--text-muted);
		background: transparent;
		border: none;
		padding: 0.5rem;
	}

	.delete-btn:hover {
		color: var(--negative);
	}

	.btn-icon {
		width: 1rem;
		height: 1rem;
	}

	/* Content grid */
	.content-grid {
		display: grid;
		grid-template-columns: 2fr 1fr;
		gap: 1.5rem;
	}

	@media (max-width: 900px) {
		.content-grid {
			grid-template-columns: 1fr;
		}
	}

	/* Stats section */
	.stats-section {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.stat-card {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.75rem;
		padding: 1.25rem;
	}

	.stat-card.live {
		border-color: rgba(245, 158, 11, 0.3);
	}

	.stat-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 1rem;
	}

	.stat-title {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.live-badge {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		font-size: 0.6875rem;
		font-weight: 500;
		color: #f59e0b;
		text-transform: uppercase;
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

	.stat-row {
		display: flex;
		gap: 2rem;
	}

	.stat-item {
		text-align: center;
	}

	.stat-value {
		font-family: var(--font-mono);
		font-size: 2.5rem;
		font-weight: 500;
		color: var(--text-primary);
		line-height: 1;
	}

	.stat-value.temp {
		color: var(--positive);
	}

	.stat-label {
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		margin-top: 0.25rem;
	}

	/* Progress */
	.progress-display {
		text-align: center;
	}

	.progress-value {
		font-family: var(--font-mono);
		font-size: 2rem;
		font-weight: 500;
		color: var(--positive);
		margin-bottom: 0.75rem;
	}

	.progress-bar-container {
		height: 8px;
		background: var(--bg-elevated);
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
	}

	/* Measurements */
	.measurements-grid {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 0.75rem;
	}

	.measurement {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.measurement.wide {
		grid-column: span 2;
	}

	.measurement-label {
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
	}

	.measurement-value {
		font-family: var(--font-mono);
		font-size: 1rem;
		font-weight: 500;
		color: var(--text-primary);
	}

	.measurement-value.target {
		color: var(--text-secondary);
	}

	/* Info section */
	.info-section {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.info-card {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.75rem;
		padding: 1.25rem;
	}

	.info-title {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0 0 1rem 0;
	}

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
	}

	/* Device */
	.device-info {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
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

	.device-last-seen {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin-left: 1rem;
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

	/* Notes */
	.notes-content {
		font-size: 0.875rem;
		color: var(--text-secondary);
		line-height: 1.6;
		margin: 0;
		white-space: pre-wrap;
	}

	@media (max-width: 640px) {
		.batch-header {
			flex-direction: column;
			gap: 1rem;
		}

		.header-actions {
			width: 100%;
			justify-content: flex-start;
		}

		.measurements-grid {
			grid-template-columns: repeat(2, 1fr);
		}

		.stat-row {
			gap: 1.5rem;
		}

		.stat-value {
			font-size: 2rem;
		}
	}
</style>
