<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import type { BatchResponse, BatchProgressResponse } from '$lib/api';
	import { fetchActiveBatches, fetchCompletedBatches, fetchDeletedBatches, fetchBatchProgress, deleteBatch, restoreBatch } from '$lib/api';
	import BatchCard from '$lib/components/BatchCard.svelte';
	import { tiltsState } from '$lib/stores/tilts.svelte';

	type TabType = 'active' | 'completed' | 'deleted';

	// State
	let batches = $state<BatchResponse[]>([]);
	let progressMap = $state<Map<number, BatchProgressResponse>>(new Map());
	let loading = $state(true);
	let error = $state<string | null>(null);
	let activeTab = $state<TabType>('active');
	let searchQuery = $state('');
	let notification = $state<{ message: string; type: 'success' | 'error' } | null>(null);

	// Map device_id to batch_id for live updates
	let deviceToBatch = $derived(
		new Map(
			batches
				.filter((b) => b.device_id && (b.status === 'fermenting' || b.status === 'conditioning'))
				.map((b) => [b.device_id!, b.id])
		)
	);

	// Enhance progress with live WebSocket data
	let liveProgressMap = $derived.by(() => {
		const enhanced = new Map(progressMap);
		for (const [deviceId, batchId] of deviceToBatch) {
			const tiltReading = tiltsState.tilts.get(deviceId);
			if (tiltReading) {
				const existing = enhanced.get(batchId) || {
					batch_id: batchId,
					measured: {},
					temperature: {},
					progress: {},
					targets: {}
				};
				// Update with live data
				enhanced.set(batchId, {
					...existing,
					measured: {
						...existing.measured,
						current_sg: tiltReading.sg
					},
					temperature: {
						...existing.temperature,
						current: tiltReading.temp,
						// Determine temperature status based on yeast thresholds (if available)
						status: existing.temperature?.yeast_min !== undefined && existing.temperature?.yeast_max !== undefined
							? (tiltReading.temp < existing.temperature.yeast_min ? 'too_cold' :
							   tiltReading.temp > existing.temperature.yeast_max ? 'too_hot' : 'in_range')
							: existing.temperature?.status
					}
				});
			}
		}
		return enhanced;
	});

	// Filtered batches
	let filteredBatches = $derived(
		batches.filter((b) => {
			const matchesSearch =
				!searchQuery ||
				(b.name?.toLowerCase().includes(searchQuery.toLowerCase()) ?? false) ||
				(b.recipe?.name?.toLowerCase().includes(searchQuery.toLowerCase()) ?? false);
			return matchesSearch;
		})
	);

	async function loadBatches() {
		loading = true;
		error = null;
		try {
			// Load batches based on active tab
			switch (activeTab) {
				case 'active':
					batches = await fetchActiveBatches();
					break;
				case 'completed':
					batches = await fetchCompletedBatches();
					break;
				case 'deleted':
					batches = await fetchDeletedBatches();
					break;
			}

			// Load progress for fermenting/conditioning batches
			const activeStatuses = ['fermenting', 'conditioning'];
			const activeBatches = batches.filter((b) => activeStatuses.includes(b.status));
			const progressPromises = activeBatches.map(async (b) => {
				try {
					const progress = await fetchBatchProgress(b.id);
					return [b.id, progress] as const;
				} catch {
					return null;
				}
			});
			const results = await Promise.all(progressPromises);
			const newMap = new Map<number, BatchProgressResponse>();
			for (const result of results) {
				if (result) {
					newMap.set(result[0], result[1]);
				}
			}
			progressMap = newMap;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load batches';
		} finally {
			loading = false;
		}
	}

	function handleViewDetails(batchId: number) {
		goto(`/batches/${batchId}`);
	}

	async function handleDelete(batchId: number, batchName: string) {
		const confirmMessage = activeTab === 'deleted'
			? 'This will permanently delete this batch. This cannot be undone. Are you sure?'
			: `Soft delete "${batchName}"? You can restore it later from the Deleted tab.`;

		if (!confirm(confirmMessage)) return;

		try {
			await deleteBatch(batchId);
			showNotification('Batch deleted successfully', 'success');
			await loadBatches();
		} catch (e) {
			showNotification('Failed to delete batch', 'error');
		}
	}

	async function handleRestore(batchId: number, batchName: string) {
		try {
			await restoreBatch(batchId);
			showNotification(`"${batchName}" restored successfully`, 'success');
			await loadBatches();
		} catch (e) {
			showNotification('Failed to restore batch', 'error');
		}
	}

	function showNotification(message: string, type: 'success' | 'error') {
		notification = { message, type };
		setTimeout(() => {
			notification = null;
		}, 3000);
	}

	onMount(() => {
		loadBatches();
	});

	// Reload when tab changes
	$effect(() => {
		if (activeTab !== undefined) {
			loadBatches();
		}
	});
</script>

<svelte:head>
	<title>Batches | BrewSignal</title>
</svelte:head>

<div class="page-container">
	<!-- Notification -->
	{#if notification}
		<div class="notification" class:success={notification.type === 'success'} class:error={notification.type === 'error'}>
			<span>{notification.message}</span>
			<button type="button" class="notification-close" onclick={() => (notification = null)}>×</button>
		</div>
	{/if}

	<!-- Header -->
	<div class="page-header">
		<div class="header-content">
			<h1 class="page-title">Batches</h1>
			<p class="page-description">Track your fermentation batches</p>
		</div>
		<button type="button" class="create-btn" onclick={() => goto('/batches/new')}>
			<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
			</svg>
			New Batch
		</button>
	</div>

	<!-- Tabs -->
	<div class="tabs-container">
		<div class="tabs">
			<button
				type="button"
				class="tab"
				class:active={activeTab === 'active'}
				onclick={() => (activeTab = 'active')}
			>
				Active
			</button>
			<button
				type="button"
				class="tab"
				class:active={activeTab === 'completed'}
				onclick={() => (activeTab = 'completed')}
			>
				Completed
			</button>
			<button
				type="button"
				class="tab"
				class:active={activeTab === 'deleted'}
				onclick={() => (activeTab = 'deleted')}
			>
				Deleted
			</button>
		</div>
		<div class="search-box">
			<svg class="search-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
			</svg>
			<input
				type="text"
				placeholder="Search batches..."
				bind:value={searchQuery}
				class="search-input"
			/>
		</div>
	</div>

	<!-- Content -->
	{#if loading}
		<div class="loading-state">
			<div class="spinner"></div>
			<span>Loading batches...</span>
		</div>
	{:else if error}
		<div class="error-state">
			<span class="error-icon">!</span>
			<p>{error}</p>
			<button type="button" class="retry-btn" onclick={loadBatches}>Retry</button>
		</div>
	{:else if filteredBatches.length === 0}
		<div class="empty-state">
			{#if batches.length === 0}
				<div class="empty-icon">🍺</div>
				<h3>No {activeTab} batches yet</h3>
				<p>
					{#if activeTab === 'active'}
						Create your first batch to start tracking fermentation
					{:else if activeTab === 'completed'}
						Complete a batch to see it here
					{:else}
						Deleted batches will appear here
					{/if}
				</p>
				{#if activeTab === 'active'}
					<button type="button" class="create-btn" onclick={() => goto('/batches/new')}>
						Create Batch
					</button>
				{/if}
			{:else}
				<div class="empty-icon">🔍</div>
				<h3>No matches</h3>
				<p>Try adjusting your search query</p>
			{/if}
		</div>
	{:else}
		<div class="batches-grid">
			{#each filteredBatches as batch (batch.id)}
				<div class="batch-wrapper">
					<!-- Deleted badge -->
					{#if batch.deleted_at}
						<div class="deleted-badge">
							<svg class="badge-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
							</svg>
							Deleted {new Date(batch.deleted_at).toLocaleDateString()}
						</div>
					{/if}

					<BatchCard
						{batch}
						progress={liveProgressMap.get(batch.id)}
						onViewDetails={() => handleViewDetails(batch.id)}
					/>

					<!-- Action buttons for deleted batches -->
					{#if batch.deleted_at}
						<div class="batch-actions">
							<button
								type="button"
								class="action-restore"
								onclick={() => handleRestore(batch.id, batch.name || batch.recipe?.name || 'Unnamed Batch')}
							>
								<svg class="action-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
								</svg>
								Restore
							</button>
							<button
								type="button"
								class="action-delete"
								onclick={() => handleDelete(batch.id, batch.name || batch.recipe?.name || 'Unnamed Batch')}
							>
								<svg class="action-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
								</svg>
								Permanent Delete
							</button>
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.page-container {
		max-width: 100%;
	}

	/* Header */
	.page-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 1rem;
		margin-bottom: 1.5rem;
	}

	.header-content {
		flex: 1;
	}

	.page-title {
		font-size: 1.75rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0 0 0.25rem 0;
		letter-spacing: -0.02em;
	}

	.page-description {
		font-size: 0.875rem;
		color: var(--text-muted);
		margin: 0;
	}

	.create-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.625rem 1rem;
		font-size: 0.875rem;
		font-weight: 500;
		color: white;
		background: var(--accent);
		border: none;
		border-radius: 0.5rem;
		cursor: pointer;
		transition: background var(--transition);
	}

	.create-btn:hover {
		background: var(--accent-hover);
	}

	.btn-icon {
		width: 1rem;
		height: 1rem;
	}

	/* Notification */
	.notification {
		position: fixed;
		top: 1rem;
		right: 1rem;
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.875rem 1rem;
		border-radius: 0.5rem;
		font-size: 0.875rem;
		font-weight: 500;
		box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
		z-index: 1000;
		animation: slideIn 0.2s ease-out;
	}

	@keyframes slideIn {
		from {
			transform: translateX(100%);
			opacity: 0;
		}
		to {
			transform: translateX(0);
			opacity: 1;
		}
	}

	.notification.success {
		background: var(--positive);
		color: white;
	}

	.notification.error {
		background: var(--negative);
		color: white;
	}

	.notification-close {
		background: none;
		border: none;
		color: inherit;
		font-size: 1.5rem;
		cursor: pointer;
		padding: 0;
		line-height: 1;
		opacity: 0.8;
		transition: opacity var(--transition);
	}

	.notification-close:hover {
		opacity: 1;
	}

	/* Tabs */
	.tabs-container {
		display: flex;
		flex-wrap: wrap;
		gap: 1rem;
		margin-bottom: 1.5rem;
		align-items: center;
		border-bottom: 1px solid var(--border-subtle);
	}

	.tabs {
		display: flex;
		gap: 0;
	}

	.tab {
		position: relative;
		padding: 0.75rem 1.5rem;
		font-size: 0.9375rem;
		font-weight: 500;
		color: var(--text-secondary);
		background: transparent;
		border: none;
		border-bottom: 2px solid transparent;
		cursor: pointer;
		transition: all var(--transition);
	}

	.tab:hover {
		color: var(--text-primary);
		background: var(--bg-hover);
	}

	.tab.active {
		color: var(--accent);
		border-bottom-color: var(--accent);
	}

	.search-box {
		position: relative;
		flex: 1;
		max-width: 20rem;
		margin-left: auto;
	}

	.search-icon {
		position: absolute;
		left: 0.75rem;
		top: 50%;
		transform: translateY(-50%);
		width: 1rem;
		height: 1rem;
		color: var(--text-muted);
		pointer-events: none;
	}

	.search-input {
		width: 100%;
		padding: 0.5rem 0.75rem 0.5rem 2.25rem;
		font-size: 0.875rem;
		color: var(--text-primary);
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 0.5rem;
		outline: none;
		transition: border-color var(--transition);
	}

	.search-input::placeholder {
		color: var(--text-muted);
	}

	.search-input:focus {
		border-color: var(--accent);
	}

	/* Grid */
	.batches-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
		gap: 1rem;
	}

	.batch-wrapper {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	/* Deleted badge */
	.deleted-badge {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.375rem 0.75rem;
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--negative);
		background: rgba(239, 68, 68, 0.1);
		border: 1px solid rgba(239, 68, 68, 0.2);
		border-radius: 0.375rem;
		width: fit-content;
	}

	.badge-icon {
		width: 0.875rem;
		height: 0.875rem;
	}

	/* Batch actions */
	.batch-actions {
		display: flex;
		gap: 0.5rem;
		margin-top: 0.5rem;
	}

	.action-restore,
	.action-delete {
		flex: 1;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.375rem;
		padding: 0.625rem 1rem;
		font-size: 0.875rem;
		font-weight: 500;
		border: 1px solid;
		border-radius: 0.375rem;
		cursor: pointer;
		transition: all var(--transition);
	}

	.action-restore {
		color: var(--positive);
		background: transparent;
		border-color: var(--positive);
	}

	.action-restore:hover {
		background: rgba(34, 197, 94, 0.1);
	}

	.action-delete {
		color: var(--negative);
		background: transparent;
		border-color: var(--negative);
	}

	.action-delete:hover {
		background: rgba(239, 68, 68, 0.1);
	}

	.action-icon {
		width: 1rem;
		height: 1rem;
	}

	/* Loading/Error/Empty states */
	.loading-state,
	.error-state,
	.empty-state {
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
		to {
			transform: rotate(360deg);
		}
	}

	.error-state {
		color: var(--negative);
	}

	.error-icon {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 3rem;
		height: 3rem;
		font-size: 1.5rem;
		font-weight: 700;
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

	.empty-state h3 {
		margin: 0 0 0.5rem 0;
		font-size: 1.125rem;
		font-weight: 600;
		color: var(--text-primary);
	}

	.empty-state p {
		margin: 0 0 1.5rem 0;
		color: var(--text-muted);
	}

	.empty-icon {
		font-size: 3rem;
		margin-bottom: 1rem;
		opacity: 0.5;
	}

	@media (max-width: 640px) {
		.page-header {
			flex-direction: column;
		}

		.tabs-container {
			flex-direction: column;
			align-items: stretch;
		}

		.tabs {
			width: 100%;
			justify-content: space-around;
		}

		.tab {
			flex: 1;
			text-align: center;
			padding: 0.75rem 1rem;
		}

		.search-box {
			max-width: 100%;
			margin-left: 0;
		}

		.batches-grid {
			grid-template-columns: 1fr;
		}

		.notification {
			left: 1rem;
			right: 1rem;
		}
	}
</style>
