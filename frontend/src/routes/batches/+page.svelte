<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import type { BatchResponse, BatchProgressResponse, BatchStatus } from '$lib/api';
	import { fetchBatches, fetchBatchProgress, deleteBatch } from '$lib/api';
	import BatchCard from '$lib/components/BatchCard.svelte';
	import { tiltsState } from '$lib/stores/tilts.svelte';

	// State
	let batches = $state<BatchResponse[]>([]);
	let progressMap = $state<Map<number, BatchProgressResponse>>(new Map());
	let loading = $state(true);
	let error = $state<string | null>(null);

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

	// Filters
	let statusFilter = $state<BatchStatus | ''>('');
	let searchQuery = $state('');

	const statusOptions: { value: BatchStatus | ''; label: string }[] = [
		{ value: '', label: 'All Batches' },
		{ value: 'planning', label: 'Planning' },
		{ value: 'fermenting', label: 'Fermenting' },
		{ value: 'conditioning', label: 'Conditioning' },
		{ value: 'completed', label: 'Completed' },
		{ value: 'archived', label: 'Archived' }
	];

	// Filtered batches
	let filteredBatches = $derived(
		batches.filter((b) => {
			const matchesStatus = !statusFilter || b.status === statusFilter;
			const matchesSearch =
				!searchQuery ||
				(b.name?.toLowerCase().includes(searchQuery.toLowerCase()) ?? false) ||
				(b.recipe?.name?.toLowerCase().includes(searchQuery.toLowerCase()) ?? false);
			return matchesStatus && matchesSearch;
		})
	);

	async function loadBatches() {
		loading = true;
		error = null;
		try {
			batches = await fetchBatches(statusFilter || undefined);
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

	async function handleDelete(batchId: number) {
		if (!confirm('Are you sure you want to delete this batch?')) return;
		try {
			await deleteBatch(batchId);
			batches = batches.filter((b) => b.id !== batchId);
		} catch (e) {
			alert('Failed to delete batch');
		}
	}

	onMount(() => {
		loadBatches();
	});

	// Reload when filter changes
	$effect(() => {
		if (statusFilter !== undefined) {
			loadBatches();
		}
	});
</script>

<svelte:head>
	<title>Batches | BrewSignal</title>
</svelte:head>

<div class="page-container">
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

	<!-- Filters -->
	<div class="filters-row">
		<div class="filter-chips">
			{#each statusOptions as option}
				<button
					type="button"
					class="filter-chip"
					class:active={statusFilter === option.value}
					onclick={() => (statusFilter = option.value)}
				>
					{option.label}
				</button>
			{/each}
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
				<h3>No batches yet</h3>
				<p>Create your first batch to start tracking fermentation</p>
				<button type="button" class="create-btn" onclick={() => goto('/batches/new')}>
					Create Batch
				</button>
			{:else}
				<div class="empty-icon">🔍</div>
				<h3>No matches</h3>
				<p>Try adjusting your filters or search query</p>
			{/if}
		</div>
	{:else}
		<div class="batches-grid">
			{#each filteredBatches as batch (batch.id)}
				<BatchCard
					{batch}
					progress={liveProgressMap.get(batch.id)}
					onViewDetails={() => handleViewDetails(batch.id)}
				/>
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

	/* Filters */
	.filters-row {
		display: flex;
		flex-wrap: wrap;
		gap: 1rem;
		margin-bottom: 1.5rem;
		align-items: center;
	}

	.filter-chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.filter-chip {
		padding: 0.5rem 0.875rem;
		font-size: 0.8125rem;
		font-weight: 500;
		color: var(--text-secondary);
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 9999px;
		cursor: pointer;
		transition: all var(--transition);
	}

	.filter-chip:hover {
		color: var(--text-primary);
		border-color: var(--border-default);
	}

	.filter-chip.active {
		color: var(--accent);
		background: var(--accent-muted);
		border-color: transparent;
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

		.filters-row {
			flex-direction: column;
			align-items: stretch;
		}

		.search-box {
			max-width: 100%;
			margin-left: 0;
		}

		.batches-grid {
			grid-template-columns: 1fr;
		}
	}
</style>
