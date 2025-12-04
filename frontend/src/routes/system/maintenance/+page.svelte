<script lang="ts">
	import { onMount } from 'svelte';
	import type { OrphanedDataReport, CleanupPreview } from '$lib/api';
	import { fetchOrphanedData, previewCleanup, executeCleanup } from '$lib/api';

	// State
	let loading = $state(true);
	let refreshing = $state(false);
	let previewing = $state(false);
	let executing = $state(false);
	let orphanedReport = $state<OrphanedDataReport | null>(null);
	let cleanupPreviewData = $state<CleanupPreview | null>(null);
	let selectedBatches = $state<Set<number>>(new Set());
	let error = $state<string | null>(null);
	let successMessage = $state<string | null>(null);

	// Derived
	let hasOrphanedData = $derived(orphanedReport && orphanedReport.orphaned_readings_count > 0);
	let batchIds = $derived(
		orphanedReport ? Object.keys(orphanedReport.batches_with_orphans).map(Number) : []
	);
	let allSelected = $derived(batchIds.length > 0 && selectedBatches.size === batchIds.length);
	let canPreview = $derived(selectedBatches.size > 0);
	let canExecute = $derived(cleanupPreviewData !== null && cleanupPreviewData.total_count > 0);

	async function loadOrphanedData() {
		try {
			error = null;
			orphanedReport = await fetchOrphanedData();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load orphaned data';
			console.error('Failed to load orphaned data:', e);
		}
	}

	async function refreshReport() {
		refreshing = true;
		error = null;
		successMessage = null;
		cleanupPreviewData = null;
		selectedBatches.clear();
		try {
			await loadOrphanedData();
		} finally {
			refreshing = false;
		}
	}

	async function handlePreview() {
		if (!canPreview) return;

		previewing = true;
		error = null;
		successMessage = null;
		try {
			cleanupPreviewData = await previewCleanup(Array.from(selectedBatches));
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to preview cleanup';
			console.error('Failed to preview cleanup:', e);
		} finally {
			previewing = false;
		}
	}

	async function handleExecute() {
		if (!canExecute || !cleanupPreviewData) return;

		const confirmed = confirm(
			`Are you sure you want to permanently delete ${cleanupPreviewData.total_count.toLocaleString()} readings?\n\nThis action cannot be undone.`
		);

		if (!confirmed) return;

		executing = true;
		error = null;
		successMessage = null;
		try {
			const result = await executeCleanup(Array.from(selectedBatches));
			successMessage = `Successfully deleted ${result.total_count.toLocaleString()} readings`;
			cleanupPreviewData = null;
			selectedBatches.clear();
			// Refresh report to show updated counts
			await loadOrphanedData();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to execute cleanup';
			console.error('Failed to execute cleanup:', e);
		} finally {
			executing = false;
		}
	}

	function toggleBatch(batchId: number) {
		if (selectedBatches.has(batchId)) {
			selectedBatches.delete(batchId);
		} else {
			selectedBatches.add(batchId);
		}
		// Clear preview when selection changes
		cleanupPreviewData = null;
	}

	function toggleAll() {
		if (allSelected) {
			selectedBatches.clear();
		} else {
			selectedBatches = new Set(batchIds);
		}
		// Clear preview when selection changes
		cleanupPreviewData = null;
	}

	onMount(async () => {
		await loadOrphanedData();
		loading = false;
	});
</script>

<svelte:head>
	<title>Data Maintenance | BrewSignal</title>
</svelte:head>

<div class="page-container">
	<div class="page-header">
		<h1 class="page-title">Data Maintenance</h1>
		<p class="page-description">
			Manage orphaned data and clean up readings linked to deleted batches
		</p>
	</div>

	{#if loading}
		<div class="loading-state">
			<div class="loading-spinner"></div>
			<span>Loading maintenance data...</span>
		</div>
	{:else}
		<div class="grid gap-6">
			<!-- Orphaned Data Report -->
			<div class="card">
				<div class="card-header">
					<div class="flex items-center justify-between">
						<h2 class="card-title">Orphaned Data Report</h2>
						<button
							type="button"
							class="btn-secondary-sm"
							onclick={refreshReport}
							disabled={refreshing}
						>
							{#if refreshing}
								<span class="loading-dot"></span>
								Refreshing...
							{:else}
								<svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
								</svg>
								Refresh Report
							{/if}
						</button>
					</div>
				</div>
				<div class="card-body">
					{#if hasOrphanedData}
						<div class="orphaned-summary">
							<div class="stat-item">
								<span class="stat-value font-mono text-orange-400">
									{orphanedReport.orphaned_readings_count.toLocaleString()}
								</span>
								<span class="stat-label">Orphaned Readings</span>
							</div>
							<div class="stat-item">
								<span class="stat-value font-mono text-orange-400">
									{Object.keys(orphanedReport.batches_with_orphans).length}
								</span>
								<span class="stat-label">Deleted Batches</span>
							</div>
						</div>

						<!-- Batch breakdown -->
						<div class="batch-breakdown">
							<h3 class="breakdown-title">Breakdown by Deleted Batch</h3>
							<div class="batch-list">
								{#each Object.entries(orphanedReport.batches_with_orphans) as [batchId, count]}
									<div class="batch-item">
										<span class="batch-id font-mono">Batch #{batchId}</span>
										<span class="batch-count font-mono">{count.toLocaleString()} readings</span>
									</div>
								{/each}
							</div>
						</div>
					{:else}
						<div class="empty-state">
							<svg class="w-12 h-12 text-green-500 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
							</svg>
							<p class="empty-state-title">No Orphaned Data</p>
							<p class="empty-state-description">
								All readings are properly linked to active batches. No cleanup needed.
							</p>
						</div>
					{/if}
				</div>
			</div>

			<!-- Cleanup Preview Section -->
			{#if hasOrphanedData}
				<div class="card">
					<div class="card-header">
						<h2 class="card-title">Cleanup Preview</h2>
					</div>
					<div class="card-body">
						<p class="section-description mb-4">
							Select which deleted batches you want to clean up. Preview the operation before executing.
						</p>

						<!-- Batch selection -->
						<div class="batch-selection">
							<div class="selection-header">
								<label class="checkbox-label">
									<input
										type="checkbox"
										checked={allSelected}
										onchange={toggleAll}
										class="checkbox-input"
									/>
									<span class="checkbox-text">Select All Batches</span>
								</label>
							</div>

							<div class="selection-list">
								{#each batchIds as batchId}
									<label class="checkbox-label batch-checkbox">
										<input
											type="checkbox"
											checked={selectedBatches.has(batchId)}
											onchange={() => toggleBatch(batchId)}
											class="checkbox-input"
										/>
										<span class="checkbox-text">
											Batch #{batchId}
											<span class="batch-reading-count">
												({orphanedReport.batches_with_orphans[batchId].toLocaleString()} readings)
											</span>
										</span>
									</label>
								{/each}
							</div>
						</div>

						<!-- Preview button -->
						<div class="action-row">
							<button
								type="button"
								class="btn-warning"
								onclick={handlePreview}
								disabled={!canPreview || previewing}
							>
								{#if previewing}
									<span class="loading-dot"></span>
									Previewing...
								{:else}
									<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
										<path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
										<path stroke-linecap="round" stroke-linejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
									</svg>
									Preview Cleanup
								{/if}
							</button>

							{#if !canPreview}
								<p class="text-muted">Select at least one batch to preview cleanup</p>
							{/if}
						</div>

						<!-- Preview results -->
						{#if cleanupPreviewData}
							<div class="preview-results">
								<div class="preview-header">
									<svg class="w-5 h-5 text-orange-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
										<path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
									</svg>
									<span class="preview-title">Preview Results</span>
								</div>
								<div class="preview-stats">
									<div class="preview-stat">
										<span class="preview-label">Total Readings to Delete</span>
										<span class="preview-value font-mono">{cleanupPreviewData.total_count.toLocaleString()}</span>
									</div>
									<div class="preview-stat">
										<span class="preview-label">Batches Affected</span>
										<span class="preview-value font-mono">{Object.keys(cleanupPreviewData.batch_breakdown).length}</span>
									</div>
								</div>
							</div>
						{/if}
					</div>
				</div>

				<!-- Execute Cleanup Section -->
				<div class="card danger-zone">
					<div class="card-header">
						<h2 class="card-title">Execute Cleanup</h2>
					</div>
					<div class="card-body">
						<p class="section-description danger-text mb-4">
							<svg class="w-4 h-4 inline-block mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
							</svg>
							This action permanently deletes readings and cannot be undone. Preview the cleanup first.
						</p>

						<button
							type="button"
							class="btn-danger"
							onclick={handleExecute}
							disabled={!canExecute || executing}
						>
							{#if executing}
								<span class="loading-dot"></span>
								Deleting...
							{:else}
								<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
								</svg>
								Execute Cleanup
							{/if}
						</button>

						{#if !canExecute}
							<p class="text-muted mt-3">Preview cleanup first to enable execution</p>
						{/if}
					</div>
				</div>
			{/if}

			<!-- Feedback Messages -->
			{#if error}
				<div class="alert alert-error">
					<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
					</svg>
					<span>{error}</span>
				</div>
			{/if}

			{#if successMessage}
				<div class="alert alert-success">
					<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
					</svg>
					<span>{successMessage}</span>
				</div>
			{/if}
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
		background: rgba(244, 63, 94, 0.02);
	}

	.card-header {
		padding: 1rem 1.25rem;
		border-bottom: 1px solid var(--bg-hover);
	}

	.card-title {
		font-size: 0.75rem;
		font-weight: 600;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	.card-body {
		padding: 1.25rem;
	}

	.section-description {
		font-size: 0.8125rem;
		color: var(--text-muted);
		line-height: 1.5;
	}

	.danger-text {
		color: var(--tilt-red);
		font-weight: 500;
	}

	/* Loading State */
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

	/* Orphaned Summary */
	.orphaned-summary {
		display: flex;
		gap: 2rem;
		margin-bottom: 1.5rem;
	}

	.stat-item {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.stat-value {
		font-size: 1.5rem;
		font-weight: 600;
	}

	.stat-label {
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	/* Batch Breakdown */
	.batch-breakdown {
		padding-top: 1.5rem;
		border-top: 1px solid var(--bg-hover);
	}

	.breakdown-title {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-secondary);
		margin-bottom: 0.75rem;
	}

	.batch-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.batch-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.75rem;
		background: var(--bg-elevated);
		border-radius: 0.375rem;
	}

	.batch-id {
		font-size: 0.8125rem;
		color: var(--text-primary);
	}

	.batch-count {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	/* Empty State */
	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 3rem 2rem;
		text-align: center;
	}

	.empty-state-title {
		font-size: 1rem;
		font-weight: 600;
		color: var(--text-primary);
		margin-bottom: 0.5rem;
	}

	.empty-state-description {
		font-size: 0.875rem;
		color: var(--text-muted);
		max-width: 24rem;
	}

	/* Batch Selection */
	.batch-selection {
		padding: 1rem;
		background: var(--bg-elevated);
		border-radius: 0.5rem;
		margin-bottom: 1rem;
	}

	.selection-header {
		padding-bottom: 0.75rem;
		border-bottom: 1px solid var(--bg-hover);
		margin-bottom: 0.75rem;
	}

	.selection-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.checkbox-label {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		cursor: pointer;
		font-size: 0.875rem;
		color: var(--text-primary);
	}

	.batch-checkbox {
		padding: 0.5rem;
		border-radius: 0.375rem;
		transition: background var(--transition);
	}

	.batch-checkbox:hover {
		background: var(--bg-hover);
	}

	.checkbox-input {
		width: 1rem;
		height: 1rem;
		cursor: pointer;
		accent-color: var(--accent);
	}

	.checkbox-text {
		flex: 1;
	}

	.batch-reading-count {
		color: var(--text-muted);
		font-size: 0.75rem;
		margin-left: 0.5rem;
	}

	/* Action Row */
	.action-row {
		display: flex;
		align-items: center;
		gap: 1rem;
		flex-wrap: wrap;
	}

	/* Preview Results */
	.preview-results {
		margin-top: 1.5rem;
		padding: 1rem;
		background: rgba(251, 146, 60, 0.05);
		border: 1px solid rgba(251, 146, 60, 0.2);
		border-radius: 0.5rem;
	}

	.preview-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-bottom: 0.75rem;
	}

	.preview-title {
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--text-primary);
	}

	.preview-stats {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 1rem;
	}

	.preview-stat {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.preview-label {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.preview-value {
		font-size: 1.125rem;
		font-weight: 600;
		color: var(--tilt-orange);
	}

	/* Buttons */
	.btn-secondary-sm {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.375rem 0.75rem;
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--accent);
		background: var(--accent-muted);
		border: 1px solid var(--accent-muted);
		border-radius: 0.375rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.btn-secondary-sm:hover:not(:disabled) {
		background: rgba(59, 130, 246, 0.2);
	}

	.btn-secondary-sm:disabled {
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
		color: white;
		background: var(--tilt-red);
		border: 1px solid var(--tilt-red);
		border-radius: 0.5rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.btn-danger:hover:not(:disabled) {
		background: rgba(244, 63, 94, 0.9);
	}

	.btn-danger:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	/* Alerts */
	.alert {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 1rem 1.25rem;
		border-radius: 0.5rem;
		font-size: 0.875rem;
		font-weight: 500;
	}

	.alert-error {
		background: rgba(244, 63, 94, 0.1);
		border: 1px solid rgba(244, 63, 94, 0.2);
		color: var(--tilt-red);
	}

	.alert-success {
		background: rgba(16, 185, 129, 0.1);
		border: 1px solid rgba(16, 185, 129, 0.2);
		color: var(--tilt-green);
	}

	.text-muted {
		color: var(--text-muted);
		font-size: 0.8125rem;
	}

	.mt-3 {
		margin-top: 0.75rem;
	}

	.mb-3 {
		margin-bottom: 0.75rem;
	}

	.mb-4 {
		margin-bottom: 1rem;
	}

	@media (max-width: 640px) {
		.orphaned-summary {
			flex-direction: column;
			gap: 1rem;
		}

		.preview-stats {
			grid-template-columns: 1fr;
		}
	}
</style>
