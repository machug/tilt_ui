<script lang="ts">
	import { goto } from '$app/navigation';
	import type { BatchResponse } from '$lib/api';

	interface Props {
		batches: BatchResponse[];
	}

	let { batches }: Props = $props();

	// Status configuration
	const statusConfig: Record<string, { label: string; color: string }> = {
		planning: { label: 'Planning', color: 'var(--text-muted)' },
		fermenting: { label: 'Fermenting', color: '#f59e0b' },
		conditioning: { label: 'Conditioning', color: '#8b5cf6' },
		completed: { label: 'Completed', color: 'var(--positive)' },
		archived: { label: 'Archived', color: 'var(--text-muted)' }
	};

	// Count batches by status
	let statusCounts = $derived(
		batches.reduce(
			(acc, b) => {
				acc[b.status] = (acc[b.status] || 0) + 1;
				return acc;
			},
			{} as Record<string, number>
		)
	);

	// Active batches (fermenting + conditioning)
	let activeBatches = $derived(batches.filter((b) => b.status === 'fermenting' || b.status === 'conditioning'));

	// Most recent active batch
	let featuredBatch = $derived(activeBatches[0]);

	function formatDate(dateStr?: string): string {
		if (!dateStr) return '--';
		return new Date(dateStr).toLocaleDateString('en-US', {
			month: 'short',
			day: 'numeric'
		});
	}

	function daysSinceBrew(dateStr?: string): string {
		if (!dateStr) return '--';
		const brewDate = new Date(dateStr);
		const now = new Date();
		const days = Math.floor((now.getTime() - brewDate.getTime()) / (1000 * 60 * 60 * 24));
		if (days === 0) return 'Today';
		if (days === 1) return '1 day';
		return `${days} days`;
	}
</script>

<div class="batch-summary">
	<div class="summary-header">
		<div class="header-left">
			<h3 class="summary-title">Batches</h3>
			<span class="batch-count">{batches.length}</span>
		</div>
		<button type="button" class="view-all-btn" onclick={() => goto('/batches')}>
			View All
			<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
			</svg>
		</button>
	</div>

	{#if activeBatches.length > 0}
		<!-- Status pills row -->
		<div class="status-pills">
			{#each Object.entries(statusCounts) as [status, count]}
				{#if count > 0}
					<span
						class="status-pill"
						class:active={status === 'fermenting' || status === 'conditioning'}
						style="--status-color: {statusConfig[status]?.color || 'var(--text-muted)'}"
					>
						<span class="pill-count">{count}</span>
						{statusConfig[status]?.label || status}
					</span>
				{/if}
			{/each}
		</div>

		<!-- Featured active batch -->
		{#if featuredBatch}
			<button
				type="button"
				class="featured-batch"
				onclick={() => goto(`/batches/${featuredBatch.id}`)}
			>
				<div class="featured-left">
					<span class="batch-number">#{featuredBatch.batch_number || '?'}</span>
					<div class="batch-info">
						<span class="batch-name">{featuredBatch.name || featuredBatch.recipe?.name || 'Unnamed'}</span>
						<span class="batch-status" style="color: {statusConfig[featuredBatch.status]?.color}">
							{#if featuredBatch.status === 'fermenting'}
								<span class="status-dot"></span>
							{/if}
							{statusConfig[featuredBatch.status]?.label}
						</span>
					</div>
				</div>
				<div class="featured-right">
					<span class="days-label">{daysSinceBrew(featuredBatch.brew_date)}</span>
					<svg class="chevron" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
					</svg>
				</div>
			</button>
		{/if}

		<!-- Other active batches -->
		{#if activeBatches.length > 1}
			<div class="other-batches">
				{#each activeBatches.slice(1, 3) as batch}
					<button
						type="button"
						class="mini-batch"
						onclick={() => goto(`/batches/${batch.id}`)}
					>
						<span class="mini-name">{batch.name || batch.recipe?.name || 'Unnamed'}</span>
						<span class="mini-days">{daysSinceBrew(batch.brew_date)}</span>
					</button>
				{/each}
				{#if activeBatches.length > 3}
					<span class="more-count">+{activeBatches.length - 3} more</span>
				{/if}
			</div>
		{/if}
	{:else}
		<!-- No active batches -->
		<div class="no-active">
			<p class="no-active-text">No active fermentations</p>
			<button type="button" class="start-btn" onclick={() => goto('/batches/new')}>
				Start Batch
			</button>
		</div>
	{/if}
</div>

<style>
	.batch-summary {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.5rem;
		padding: 1rem 1.25rem;
	}

	.summary-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 0.75rem;
	}

	.header-left {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.summary-title {
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.batch-count {
		font-size: 0.625rem;
		font-weight: 600;
		color: var(--text-muted);
		background: var(--bg-elevated);
		padding: 0.125rem 0.375rem;
		border-radius: 9999px;
	}

	.view-all-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--accent);
		background: transparent;
		border: none;
		padding: 0.25rem 0.5rem;
		border-radius: 0.25rem;
		cursor: pointer;
		transition: background var(--transition);
	}

	.view-all-btn:hover {
		background: var(--accent-muted);
	}

	.btn-icon {
		width: 0.75rem;
		height: 0.75rem;
	}

	/* Status pills */
	.status-pills {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-bottom: 0.75rem;
	}

	.status-pill {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--status-color);
		background: var(--bg-elevated);
		padding: 0.25rem 0.5rem;
		border-radius: 9999px;
	}

	.status-pill.active {
		background: color-mix(in srgb, var(--status-color) 12%, transparent);
	}

	.pill-count {
		font-weight: 700;
	}

	/* Featured batch */
	.featured-batch {
		display: flex;
		align-items: center;
		justify-content: space-between;
		width: 100%;
		padding: 0.75rem;
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 0.375rem;
		cursor: pointer;
		transition: border-color var(--transition);
	}

	.featured-batch:hover {
		border-color: var(--border-default);
	}

	.featured-left {
		display: flex;
		align-items: center;
		gap: 0.625rem;
		min-width: 0;
	}

	.batch-number {
		font-family: var(--font-mono);
		font-size: 0.625rem;
		font-weight: 500;
		color: var(--text-muted);
		background: var(--bg-surface);
		padding: 0.125rem 0.375rem;
		border-radius: 0.125rem;
	}

	.batch-info {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}

	.batch-name {
		font-size: 0.8125rem;
		font-weight: 500;
		color: var(--text-primary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.batch-status {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		font-size: 0.6875rem;
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.02em;
	}

	.status-dot {
		width: 5px;
		height: 5px;
		border-radius: 50%;
		background: currentColor;
		animation: pulse 2s ease-in-out infinite;
	}

	@keyframes pulse {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.4; }
	}

	.featured-right {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex-shrink: 0;
	}

	.days-label {
		font-size: 0.6875rem;
		color: var(--text-muted);
	}

	.chevron {
		width: 0.875rem;
		height: 0.875rem;
		color: var(--text-muted);
	}

	/* Other active batches */
	.other-batches {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-top: 0.5rem;
	}

	.mini-batch {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		font-size: 0.6875rem;
		color: var(--text-secondary);
		background: transparent;
		border: 1px solid var(--border-subtle);
		padding: 0.25rem 0.5rem;
		border-radius: 0.25rem;
		cursor: pointer;
		transition: border-color var(--transition);
	}

	.mini-batch:hover {
		border-color: var(--border-default);
		color: var(--text-primary);
	}

	.mini-name {
		max-width: 8rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.mini-days {
		color: var(--text-muted);
	}

	.more-count {
		font-size: 0.6875rem;
		color: var(--text-muted);
		padding: 0.25rem 0.5rem;
	}

	/* No active batches */
	.no-active {
		text-align: center;
		padding: 1rem 0;
	}

	.no-active-text {
		font-size: 0.8125rem;
		color: var(--text-muted);
		margin: 0 0 0.75rem 0;
	}

	.start-btn {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--accent);
		background: var(--accent-muted);
		border: none;
		padding: 0.5rem 1rem;
		border-radius: 0.375rem;
		cursor: pointer;
		transition: background var(--transition);
	}

	.start-btn:hover {
		background: color-mix(in srgb, var(--accent) 20%, transparent);
	}
</style>
