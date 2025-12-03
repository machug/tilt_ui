<script lang="ts">
	import type { BatchResponse, BatchProgressResponse } from '$lib/api';
	import { formatGravity } from '$lib/stores/config.svelte';
	import BatchCard from './BatchCard.svelte';

	interface Props {
		batch: BatchResponse;
		currentSg?: number | null;
		progress?: BatchProgressResponse | null;
	}

	let { batch, currentSg, progress }: Props = $props();

	// Calculate real-time metrics
	let metrics = $derived.by(() => {
		if (!batch.measured_og) return null;

		const sg = currentSg ?? progress?.measured?.current_sg;
		if (!sg) return null;

		// ABV: (OG - Current SG) × 131.25
		const abv = (batch.measured_og - sg) * 131.25;

		// Attenuation: ((OG - Current SG) / (OG - 1.000)) × 100
		const attenuation = ((batch.measured_og - sg) / (batch.measured_og - 1.0)) * 100;

		return {
			currentSg: sg,
			abv: Math.max(0, abv),
			attenuation: Math.max(0, Math.min(100, attenuation)),
			isFermenting: batch.status === 'fermenting' || batch.status === 'conditioning'
		};
	});

	// Show live calculations or final measurements
	let showLive = $derived(metrics?.isFermenting ?? false);

	function formatSG(value?: number | null): string {
		if (value === undefined || value === null) return '--';
		return formatGravity(value);
	}

	function formatPercent(value?: number | null): string {
		if (value === undefined || value === null) return '--';
		return `${value.toFixed(1)}%`;
	}
</script>

<BatchCard title={showLive ? 'Fermentation Progress' : 'Fermentation Measurements'}>
	{#if metrics && showLive}
		<!-- Active fermentation with live calculations -->
		<div class="current-sg">
			<div class="sg-label">Current Specific Gravity</div>
			<div class="sg-value">
				{formatSG(metrics.currentSg)}
				<span class="fermenting-badge">
					<span class="pulse-dot"></span>
					Fermenting
				</span>
			</div>
		</div>

		<div class="gravity-timeline">
			<div class="timeline-line"></div>
			<div class="gravity-point start">
				<div class="point-marker"></div>
				<div class="point-label">Original Gravity</div>
				<div class="point-value">{formatSG(batch.measured_og)}</div>
			</div>
			{#if batch.recipe?.fg_target}
				<div class="gravity-point target">
					<div class="point-marker"></div>
					<div class="point-label">Target FG</div>
					<div class="point-value">{formatSG(batch.recipe.fg_target)}</div>
				</div>
			{/if}
			<div class="gravity-point current">
				<div class="point-marker pulsing"></div>
				<div class="point-label">Current FG</div>
				<div class="point-value">{formatSG(metrics.currentSg)}</div>
			</div>
		</div>

		<div class="metrics-grid">
			<div class="metric abv-metric">
				<div class="metric-icon">%</div>
				<div class="metric-content">
					<div class="metric-label">Alcohol by Volume</div>
					<div class="metric-value">
						{formatPercent(metrics.abv)}
						<span class="live-indicator">LIVE</span>
					</div>
				</div>
			</div>
			<div class="metric attenuation-metric">
				<div class="metric-icon">↓</div>
				<div class="metric-content">
					<div class="metric-label">Apparent Attenuation</div>
					<div class="metric-value">
						{formatPercent(metrics.attenuation)}
						<span class="live-indicator">LIVE</span>
					</div>
				</div>
			</div>
		</div>

		{#if progress?.progress?.percent_complete != null}
			<div class="progress-section">
				<div class="progress-header">
					<span class="progress-label">Fermentation Progress</span>
					<span class="progress-percent">{progress.progress.percent_complete.toFixed(0)}%</span>
				</div>
				<div class="progress-bar-container">
					<div class="progress-bar-bg"></div>
					<div
						class="progress-bar-fill"
						style="width: {progress.progress.percent_complete}%"
					></div>
					<div class="progress-bar-shine"></div>
				</div>
				{#if progress.progress.sg_remaining != null}
					<div class="progress-remaining">
						{progress.progress.sg_remaining.toFixed(3)} gravity points remaining
					</div>
				{/if}
			</div>
		{/if}

	{:else if batch.measured_og}
		<!-- Completed batch or no current readings -->
		<div class="measurements-grid">
			<div class="measurement">
				<div class="measurement-label">Original Gravity</div>
				<div class="measurement-value">{formatSG(batch.measured_og)}</div>
			</div>
			<div class="measurement">
				<div class="measurement-label">Final Gravity</div>
				<div class="measurement-value">{formatSG(batch.measured_fg)}</div>
			</div>
			<div class="measurement">
				<div class="measurement-label">ABV</div>
				<div class="measurement-value">
					{batch.measured_abv != null ? formatPercent(batch.measured_abv) : '--'}
				</div>
			</div>
			<div class="measurement">
				<div class="measurement-label">Attenuation</div>
				<div class="measurement-value">
					{batch.measured_attenuation != null ? formatPercent(batch.measured_attenuation) : '--'}
				</div>
			</div>
		</div>
	{:else}
		<!-- No OG set -->
		<div class="no-data">
			<div class="no-data-icon">○</div>
			<p class="no-data-text">Set Original Gravity to begin tracking fermentation metrics</p>
		</div>
	{/if}
</BatchCard>

<style>
	/* Import distinctive fonts */
	@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Work+Sans:wght@400;500;600&display=swap');

	/* Current SG - Hero Display */
	.current-sg {
		text-align: center;
		margin-bottom: 2rem;
		padding: 1.75rem 1.5rem;
		background:
			linear-gradient(135deg, rgba(251, 191, 36, 0.03) 0%, rgba(217, 119, 6, 0.03) 100%),
			repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0, 0, 0, 0.02) 2px, rgba(0, 0, 0, 0.02) 4px);
		border-radius: 0.75rem;
		border: 1px solid rgba(251, 191, 36, 0.15);
		position: relative;
		overflow: hidden;
	}

	.current-sg::before {
		content: '';
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		height: 1px;
		background: linear-gradient(90deg, transparent, rgba(251, 191, 36, 0.4), transparent);
	}

	.sg-label {
		font-family: 'Work Sans', sans-serif;
		font-size: 0.6875rem;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.1em;
		margin-bottom: 0.75rem;
	}

	.sg-value {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 2.5rem;
		font-weight: 500;
		color: var(--text-primary);
		line-height: 1;
		letter-spacing: -0.02em;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 1rem;
	}

	.fermenting-badge {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		font-family: 'Work Sans', sans-serif;
		font-size: 0.75rem;
		font-weight: 600;
		color: #d97706;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		padding: 0.375rem 0.75rem;
		background: rgba(251, 191, 36, 0.1);
		border: 1px solid rgba(251, 191, 36, 0.3);
		border-radius: 2rem;
	}

	.pulse-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: #f59e0b;
		animation: pulse 2s ease-in-out infinite;
	}

	@keyframes pulse {
		0%, 100% {
			opacity: 1;
			transform: scale(1);
		}
		50% {
			opacity: 0.5;
			transform: scale(1.3);
		}
	}

	/* Gravity Timeline */
	.gravity-timeline {
		position: relative;
		display: flex;
		justify-content: space-between;
		gap: 1rem;
		margin-bottom: 2rem;
		padding: 2rem 1.5rem;
		background: var(--bg-elevated);
		border-radius: 0.75rem;
		border: 1px solid rgba(0, 0, 0, 0.06);
	}

	.timeline-line {
		position: absolute;
		top: 2.75rem;
		left: 2rem;
		right: 2rem;
		height: 2px;
		background: linear-gradient(
			90deg,
			#84cc16 0%,
			#f59e0b 50%,
			rgba(251, 191, 36, 0.3) 100%
		);
		z-index: 0;
	}

	.gravity-point {
		position: relative;
		text-align: center;
		flex: 1;
		z-index: 1;
		animation: slideUp 0.6s ease-out backwards;
	}

	.gravity-point:nth-child(2) { animation-delay: 0.1s; }
	.gravity-point:nth-child(3) { animation-delay: 0.2s; }
	.gravity-point:nth-child(4) { animation-delay: 0.3s; }

	@keyframes slideUp {
		from {
			opacity: 0;
			transform: translateY(10px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	.point-marker {
		width: 14px;
		height: 14px;
		margin: 0 auto 1rem;
		border-radius: 50%;
		background: var(--bg-surface);
		border: 3px solid #84cc16;
		box-shadow: 0 0 0 3px var(--bg-elevated);
	}

	.gravity-point.target .point-marker {
		border-color: #94a3b8;
		background: var(--bg-elevated);
	}

	.gravity-point.current .point-marker {
		border-color: #f59e0b;
		background: #fef3c7;
		box-shadow:
			0 0 0 3px var(--bg-elevated),
			0 0 12px rgba(245, 158, 11, 0.4);
	}

	.point-marker.pulsing {
		animation: markerPulse 2s ease-in-out infinite;
	}

	@keyframes markerPulse {
		0%, 100% {
			transform: scale(1);
			box-shadow:
				0 0 0 3px var(--bg-elevated),
				0 0 12px rgba(245, 158, 11, 0.4);
		}
		50% {
			transform: scale(1.15);
			box-shadow:
				0 0 0 3px var(--bg-elevated),
				0 0 20px rgba(245, 158, 11, 0.6);
		}
	}

	.point-label {
		font-family: 'Work Sans', sans-serif;
		font-size: 0.6875rem;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin-bottom: 0.375rem;
	}

	.point-value {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.125rem;
		font-weight: 600;
		color: var(--text-primary);
		letter-spacing: -0.01em;
	}

	/* Metrics Grid */
	.metrics-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 1rem;
		margin-bottom: 2rem;
	}

	.metric {
		display: flex;
		align-items: center;
		gap: 1rem;
		padding: 1.25rem;
		background: var(--bg-elevated);
		border-radius: 0.75rem;
		border: 1px solid rgba(0, 0, 0, 0.06);
		transition: all 0.3s ease;
		animation: fadeIn 0.6s ease-out backwards;
	}

	.metric:nth-child(1) { animation-delay: 0.4s; }
	.metric:nth-child(2) { animation-delay: 0.5s; }

	@keyframes fadeIn {
		from {
			opacity: 0;
			transform: translateY(10px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	.metric:hover {
		transform: translateY(-2px);
		box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
		border-color: rgba(251, 191, 36, 0.3);
	}

	.metric-icon {
		flex-shrink: 0;
		width: 44px;
		height: 44px;
		display: flex;
		align-items: center;
		justify-content: center;
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.5rem;
		font-weight: 600;
		color: #d97706;
		background: rgba(251, 191, 36, 0.1);
		border: 1px solid rgba(251, 191, 36, 0.3);
		border-radius: 0.5rem;
	}

	.metric-content {
		flex: 1;
		min-width: 0;
	}

	.metric-label {
		font-family: 'Work Sans', sans-serif;
		font-size: 0.6875rem;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin-bottom: 0.375rem;
	}

	.metric-value {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.5rem;
		font-weight: 600;
		color: var(--text-primary);
		line-height: 1;
		letter-spacing: -0.02em;
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.live-indicator {
		font-family: 'Work Sans', sans-serif;
		font-size: 0.625rem;
		font-weight: 600;
		color: #f59e0b;
		background: rgba(251, 191, 36, 0.15);
		padding: 0.125rem 0.375rem;
		border-radius: 0.25rem;
		letter-spacing: 0.05em;
		animation: liveBlink 3s ease-in-out infinite;
	}

	@keyframes liveBlink {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.6; }
	}

	/* Progress Section */
	.progress-section {
		padding: 1.5rem;
		background:
			linear-gradient(135deg, rgba(132, 204, 22, 0.03) 0%, rgba(251, 191, 36, 0.03) 100%),
			var(--bg-elevated);
		border-radius: 0.75rem;
		border: 1px solid rgba(132, 204, 22, 0.2);
		animation: fadeIn 0.6s ease-out 0.6s backwards;
	}

	.progress-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 1rem;
	}

	.progress-label {
		font-family: 'Work Sans', sans-serif;
		font-size: 0.6875rem;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.1em;
	}

	.progress-percent {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.75rem;
		font-weight: 600;
		color: #84cc16;
		letter-spacing: -0.02em;
	}

	.progress-bar-container {
		position: relative;
		height: 12px;
		background: rgba(0, 0, 0, 0.05);
		border-radius: 6px;
		overflow: hidden;
		margin-bottom: 0.75rem;
		box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.06);
	}

	.progress-bar-bg {
		position: absolute;
		inset: 0;
		background: repeating-linear-gradient(
			45deg,
			transparent,
			transparent 10px,
			rgba(0, 0, 0, 0.02) 10px,
			rgba(0, 0, 0, 0.02) 20px
		);
	}

	.progress-bar-fill {
		position: absolute;
		top: 0;
		left: 0;
		height: 100%;
		background: linear-gradient(90deg, #f59e0b 0%, #fbbf24 50%, #84cc16 100%);
		border-radius: 6px;
		transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1);
		box-shadow: 0 0 8px rgba(245, 158, 11, 0.4);
	}

	.progress-bar-shine {
		position: absolute;
		top: 0;
		left: -100%;
		width: 100%;
		height: 100%;
		background: linear-gradient(
			90deg,
			transparent,
			rgba(255, 255, 255, 0.3),
			transparent
		);
		animation: shine 3s ease-in-out infinite;
	}

	@keyframes shine {
		0% { left: -100%; }
		50%, 100% { left: 200%; }
	}

	.progress-remaining {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 0.75rem;
		color: var(--text-muted);
		text-align: center;
		letter-spacing: 0.01em;
	}

	/* Measurements Grid (Completed Batches) */
	.measurements-grid {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 1rem;
	}

	.measurement {
		text-align: center;
		padding: 1rem;
		background: var(--bg-elevated);
		border-radius: 0.5rem;
		border: 1px solid rgba(0, 0, 0, 0.06);
		transition: all 0.2s ease;
	}

	.measurement:hover {
		border-color: rgba(0, 0, 0, 0.12);
		transform: translateY(-1px);
	}

	.measurement-label {
		font-family: 'Work Sans', sans-serif;
		font-size: 0.6875rem;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin-bottom: 0.5rem;
	}

	.measurement-value {
		font-family: 'IBM Plex Mono', monospace;
		font-size: 1.125rem;
		font-weight: 600;
		color: var(--text-primary);
		letter-spacing: -0.01em;
	}

	/* No Data State */
	.no-data {
		text-align: center;
		padding: 3rem 1.5rem;
	}

	.no-data-icon {
		font-size: 3rem;
		color: var(--text-muted);
		opacity: 0.3;
		margin-bottom: 1rem;
		font-family: 'IBM Plex Mono', monospace;
	}

	.no-data-text {
		font-family: 'Work Sans', sans-serif;
		font-size: 0.875rem;
		color: var(--text-muted);
		margin: 0;
		line-height: 1.5;
	}

	/* Responsive Design */
	@media (max-width: 640px) {
		.sg-value {
			font-size: 2rem;
			flex-direction: column;
			gap: 0.75rem;
		}

		.gravity-timeline {
			flex-direction: column;
			gap: 1.5rem;
			padding: 1.5rem 1rem;
		}

		.timeline-line {
			top: 1rem;
			bottom: 1rem;
			left: 2rem;
			width: 2px;
			height: auto;
			right: auto;
			background: linear-gradient(
				180deg,
				#84cc16 0%,
				#f59e0b 50%,
				rgba(251, 191, 36, 0.3) 100%
			);
		}

		.gravity-point {
			display: flex;
			align-items: center;
			text-align: left;
			gap: 1rem;
		}

		.point-marker {
			margin: 0;
			flex-shrink: 0;
		}

		.point-label {
			margin-bottom: 0.25rem;
		}

		.measurements-grid {
			grid-template-columns: repeat(2, 1fr);
		}

		.metrics-grid {
			grid-template-columns: 1fr;
		}

		.metric-value {
			font-size: 1.25rem;
		}
	}
</style>
