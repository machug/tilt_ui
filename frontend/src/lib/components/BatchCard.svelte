<script lang="ts">
	import type { BatchResponse, BatchProgressResponse } from '$lib/api';
	import { formatGravity, getGravityUnit, formatTemp, getTempUnit } from '$lib/stores/config.svelte';

	interface Props {
		batch: BatchResponse;
		progress?: BatchProgressResponse;
		expanded?: boolean;
		onToggleExpand?: () => void;
		onStatusChange?: (status: string) => void;
		onViewDetails?: () => void;
	}

	let { batch, progress, expanded = false, onToggleExpand, onStatusChange, onViewDetails }: Props = $props();

	// Status configuration
	const statusConfig: Record<string, { label: string; color: string; bg: string }> = {
		planning: { label: 'Planning', color: 'var(--text-secondary)', bg: 'var(--bg-elevated)' },
		fermenting: { label: 'Fermenting', color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.12)' },
		conditioning: { label: 'Conditioning', color: '#8b5cf6', bg: 'rgba(139, 92, 246, 0.12)' },
		completed: { label: 'Completed', color: 'var(--positive)', bg: 'rgba(34, 197, 94, 0.12)' },
		archived: { label: 'Archived', color: 'var(--text-muted)', bg: 'var(--bg-elevated)' }
	};

	// Temperature status indicators
	const tempStatusConfig: Record<string, { icon: string; color: string }> = {
		in_range: { icon: '✓', color: 'var(--positive)' },
		too_cold: { icon: '↓', color: '#3b82f6' },
		too_hot: { icon: '↑', color: 'var(--negative)' },
		unknown: { icon: '?', color: 'var(--text-muted)' }
	};

	let statusInfo = $derived(statusConfig[batch.status] || statusConfig.planning);
	let tempStatus = $derived(progress?.temperature?.status ? tempStatusConfig[progress.temperature.status] : tempStatusConfig.unknown);
	let gravityUnit = $derived(getGravityUnit());
	let tempUnit = $derived(getTempUnit());

	// Format gravity for display
	function formatSG(value?: number): string {
		if (value === undefined || value === null) return '--';
		return formatGravity(value);
	}

	// Format temperature for display
	function formatTempValue(value?: number): string {
		if (value === undefined || value === null) return '--';
		return formatTemp(value);
	}

	// Calculate days since brew date
	function daysSinceBrew(): string {
		if (!batch.brew_date) return '--';
		const brewDate = new Date(batch.brew_date);
		const now = new Date();
		const days = Math.floor((now.getTime() - brewDate.getTime()) / (1000 * 60 * 60 * 24));
		if (days === 0) return 'Today';
		if (days === 1) return '1 day';
		return `${days} days`;
	}

	// Format date for display
	function formatDate(dateStr?: string): string {
		if (!dateStr) return '--';
		return new Date(dateStr).toLocaleDateString('en-US', {
			month: 'short',
			day: 'numeric'
		});
	}

	let brewDays = $derived(daysSinceBrew());
	let displayName = $derived(batch.name || batch.recipe?.name || 'Unnamed Batch');
</script>

<div
	class="batch-card"
	class:expanded
	class:fermenting={batch.status === 'fermenting'}
>
	<!-- Status accent stripe -->
	<div class="accent-stripe" style="background: {statusInfo.color};"></div>

	<div class="card-content">
		<!-- Header -->
		<div class="header">
			<div class="header-left">
				<div class="batch-number">#{batch.batch_number || '?'}</div>
				<div class="title-group">
					<h3 class="batch-name">{displayName}</h3>
					{#if batch.recipe?.name && batch.name && batch.name !== batch.recipe.name}
						<span class="recipe-name">{batch.recipe.name}</span>
					{/if}
				</div>
			</div>
			<button
				type="button"
				class="status-pill"
				style="color: {statusInfo.color}; background: {statusInfo.bg};"
				onclick={() => onStatusChange?.(batch.status)}
			>
				{#if batch.status === 'fermenting'}
					<span class="status-dot"></span>
				{/if}
				{statusInfo.label}
			</button>
		</div>

		<!-- Main metrics row -->
		<div class="metrics-row">
			<!-- Gravity -->
			<div class="metric">
				<div class="metric-value">
					{formatSG(progress?.measured?.current_sg ?? batch.measured_og)}
					<span class="metric-unit">{gravityUnit !== 'SG' ? gravityUnit : ''}</span>
				</div>
				<div class="metric-label">
					{progress?.measured?.current_sg ? 'Current' : 'OG'}
				</div>
			</div>

			<!-- Temperature -->
			{#if progress?.temperature?.current}
				<div class="metric">
					<div class="metric-value temp" style="color: {tempStatus.color};">
						{formatTempValue(progress.temperature.current)}
						<span class="metric-unit">{tempUnit}</span>
						<span class="temp-indicator">{tempStatus.icon}</span>
					</div>
					<div class="metric-label">Temp</div>
				</div>
			{/if}

			<!-- Progress -->
			{#if progress?.progress?.percent_complete !== undefined && progress.progress.percent_complete !== null}
				<div class="metric">
					<div class="metric-value progress-value">
						{progress.progress.percent_complete.toFixed(0)}
						<span class="metric-unit">%</span>
					</div>
					<div class="metric-label">Progress</div>
				</div>
			{/if}
		</div>

		<!-- Progress bar (only for fermenting/conditioning) -->
		{#if batch.status === 'fermenting' || batch.status === 'conditioning'}
			<div class="progress-bar-container">
				<div
					class="progress-bar"
					style="width: {progress?.progress?.percent_complete ?? 0}%;"
				></div>
				<div class="progress-markers">
					<span>0%</span>
					<span>50%</span>
					<span>100%</span>
				</div>
			</div>
		{/if}

		<!-- Stats row -->
		<div class="stats-row">
			{#if batch.measured_og && progress?.measured?.current_sg}
				<div class="stat">
					<span class="stat-label">ABV</span>
					<span class="stat-value">{progress.measured.abv?.toFixed(1) ?? '--'}%</span>
				</div>
				<div class="stat">
					<span class="stat-label">Atten</span>
					<span class="stat-value">{progress.measured.attenuation?.toFixed(0) ?? '--'}%</span>
				</div>
			{/if}
			{#if progress?.targets?.fg}
				<div class="stat">
					<span class="stat-label">Target FG</span>
					<span class="stat-value">{formatSG(progress.targets.fg)}</span>
				</div>
			{/if}
			<div class="stat">
				<span class="stat-label">Brewed</span>
				<span class="stat-value">{brewDays}</span>
			</div>
		</div>

		<!-- Footer -->
		<div class="footer">
			<span class="brew-date">{formatDate(batch.brew_date)}</span>
			<div class="footer-actions">
				{#if onViewDetails}
					<button type="button" class="action-btn" onclick={onViewDetails}>
						View
						<svg class="action-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
						</svg>
					</button>
				{/if}
				{#if onToggleExpand}
					<button
						type="button"
						class="expand-btn"
						onclick={onToggleExpand}
						aria-label={expanded ? 'Collapse' : 'Expand'}
					>
						<svg
							class="expand-icon"
							class:rotate-180={expanded}
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
							stroke-width="2"
						>
							<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
						</svg>
					</button>
				{/if}
			</div>
		</div>
	</div>
</div>

<style>
	.batch-card {
		position: relative;
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.5rem;
		overflow: hidden;
		transition: border-color var(--transition), box-shadow var(--transition);
	}

	.batch-card:hover {
		border-color: var(--border-default);
	}

	.batch-card.fermenting {
		box-shadow: 0 0 0 1px rgba(245, 158, 11, 0.1);
	}

	.batch-card.expanded {
		grid-column: span 2;
	}

	@media (max-width: 768px) {
		.batch-card.expanded {
			grid-column: span 1;
		}
	}

	.accent-stripe {
		height: 3px;
	}

	.card-content {
		padding: 1.25rem;
	}

	/* Header */
	.header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 1rem;
		margin-bottom: 1rem;
	}

	.header-left {
		display: flex;
		align-items: flex-start;
		gap: 0.75rem;
		min-width: 0;
	}

	.batch-number {
		flex-shrink: 0;
		font-family: var(--font-mono);
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
		background: var(--bg-elevated);
		padding: 0.25rem 0.5rem;
		border-radius: 0.25rem;
		margin-top: 0.125rem;
	}

	.title-group {
		min-width: 0;
	}

	.batch-name {
		font-size: 1.125rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
		line-height: 1.3;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.recipe-name {
		font-size: 0.75rem;
		color: var(--text-muted);
		display: block;
		margin-top: 0.125rem;
	}

	/* Status pill */
	.status-pill {
		flex-shrink: 0;
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		font-size: 0.75rem;
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.025em;
		padding: 0.375rem 0.75rem;
		border-radius: 9999px;
		border: none;
		cursor: pointer;
		transition: opacity var(--transition);
	}

	.status-pill:hover {
		opacity: 0.85;
	}

	.status-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: currentColor;
		animation: pulse 2s ease-in-out infinite;
	}

	@keyframes pulse {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.4; }
	}

	/* Metrics */
	.metrics-row {
		display: flex;
		gap: 1.5rem;
		margin-bottom: 1rem;
	}

	.metric {
		text-align: center;
	}

	.metric-value {
		font-family: var(--font-mono);
		font-size: 1.75rem;
		font-weight: 500;
		color: var(--text-primary);
		line-height: 1.1;
		display: flex;
		align-items: baseline;
		justify-content: center;
		gap: 0.125rem;
	}

	.metric-value.temp {
		font-size: 1.5rem;
	}

	.metric-value.progress-value {
		color: var(--positive);
	}

	.metric-unit {
		font-size: 0.875rem;
		color: var(--text-secondary);
	}

	.temp-indicator {
		font-size: 0.875rem;
		margin-left: 0.25rem;
	}

	.metric-label {
		font-size: 0.625rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin-top: 0.25rem;
	}

	/* Progress bar */
	.progress-bar-container {
		position: relative;
		height: 6px;
		background: var(--bg-elevated);
		border-radius: 3px;
		margin-bottom: 0.75rem;
		overflow: hidden;
	}

	.progress-bar {
		position: absolute;
		top: 0;
		left: 0;
		height: 100%;
		background: linear-gradient(90deg, #f59e0b, #84cc16);
		border-radius: 3px;
		transition: width 0.5s ease-out;
	}

	.progress-markers {
		display: flex;
		justify-content: space-between;
		font-size: 0.5rem;
		color: var(--text-muted);
		margin-top: 0.25rem;
	}

	/* Stats row */
	.stats-row {
		display: flex;
		flex-wrap: wrap;
		gap: 1rem;
		padding: 0.75rem 0;
		border-top: 1px solid var(--bg-hover);
		border-bottom: 1px solid var(--bg-hover);
		margin-bottom: 0.75rem;
	}

	.stat {
		display: flex;
		align-items: center;
		gap: 0.375rem;
	}

	.stat-label {
		font-size: 0.6875rem;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}

	.stat-value {
		font-family: var(--font-mono);
		font-size: 0.8125rem;
		font-weight: 500;
		color: var(--text-secondary);
	}

	/* Footer */
	.footer {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.brew-date {
		font-size: 0.6875rem;
		color: var(--text-muted);
	}

	.footer-actions {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.action-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--accent);
		background: transparent;
		border: none;
		padding: 0.375rem 0.5rem;
		border-radius: 0.25rem;
		cursor: pointer;
		transition: background var(--transition);
	}

	.action-btn:hover {
		background: var(--accent-muted);
	}

	.action-icon {
		width: 0.875rem;
		height: 0.875rem;
	}

	.expand-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 1.75rem;
		height: 1.75rem;
		background: var(--bg-elevated);
		border: 1px solid var(--bg-hover);
		border-radius: 0.375rem;
		color: var(--text-muted);
		cursor: pointer;
		transition: all var(--transition);
	}

	.expand-btn:hover {
		color: var(--accent);
		border-color: var(--accent-muted);
		background: var(--accent-muted);
	}

	.expand-icon {
		width: 1rem;
		height: 1rem;
		transition: transform 0.2s ease;
	}

	.expand-icon.rotate-180 {
		transform: rotate(180deg);
	}
</style>
