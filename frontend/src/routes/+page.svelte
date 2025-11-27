<script lang="ts">
	import { onMount } from 'svelte';
	import { tiltsState, connectWebSocket, disconnectWebSocket } from '$lib/stores/tilts.svelte';
	import TiltCard from '$lib/components/TiltCard.svelte';

	onMount(() => {
		connectWebSocket();
		return () => disconnectWebSocket();
	});

	let tiltsList = $derived(Array.from(tiltsState.tilts.values()));

	// Track which tilt card is expanded (only one at a time)
	let expandedTiltId = $state<string | null>(null);

	function toggleExpand(tiltId: string) {
		expandedTiltId = expandedTiltId === tiltId ? null : tiltId;
	}
</script>

<svelte:head>
	<title>Dashboard | Tilt UI</title>
</svelte:head>

{#if tiltsList.length === 0}
	<div class="empty-state">
		<div class="empty-icon">
			<span class="text-5xl">🍺</span>
		</div>
		<h2 class="empty-title">No Tilts Detected</h2>
		<p class="empty-description">
			{#if tiltsState.connected}
				Waiting for Tilt hydrometers to broadcast...
			{:else}
				<span class="connecting-dots">Connecting to server</span>
			{/if}
		</p>
		{#if tiltsState.connected}
			<div class="empty-hint">
				<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z"
					/>
				</svg>
				<span>Make sure your Tilt is floating in liquid and within Bluetooth range</span>
			</div>
		{/if}
	</div>
{:else}
	<div class="tilt-grid">
		{#each tiltsList as tilt (tilt.id)}
			<TiltCard
				{tilt}
				expanded={expandedTiltId === tilt.id}
				onToggleExpand={() => toggleExpand(tilt.id)}
			/>
		{/each}
	</div>
{/if}

<style>
	.tilt-grid {
		display: grid;
		grid-template-columns: repeat(1, 1fr);
		gap: 1.5rem;
	}

	@media (min-width: 768px) {
		.tilt-grid {
			grid-template-columns: repeat(2, 1fr);
		}
	}

	@media (min-width: 1024px) {
		.tilt-grid {
			grid-template-columns: repeat(3, 1fr);
		}
	}

	@media (min-width: 1280px) {
		.tilt-grid {
			grid-template-columns: repeat(4, 1fr);
		}
	}

	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		text-align: center;
		padding: 4rem 1.5rem;
		min-height: 50vh;
	}

	.empty-icon {
		width: 5rem;
		height: 5rem;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 1rem;
		background: var(--bg-card);
		border: 1px solid var(--bg-hover);
		margin-bottom: 1.5rem;
		animation: float 3s ease-in-out infinite;
	}

	@keyframes float {
		0%,
		100% {
			transform: translateY(0);
		}
		50% {
			transform: translateY(-8px);
		}
	}

	.empty-title {
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--text-primary);
		margin-bottom: 0.5rem;
	}

	.empty-description {
		color: var(--text-muted);
		font-size: 0.875rem;
		margin-bottom: 1.5rem;
	}

	.connecting-dots::after {
		content: '';
		animation: dots 1.5s steps(4, end) infinite;
	}

	@keyframes dots {
		0%,
		20% {
			content: '';
		}
		40% {
			content: '.';
		}
		60% {
			content: '..';
		}
		80%,
		100% {
			content: '...';
		}
	}

	.empty-hint {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.75rem 1rem;
		background: var(--bg-card);
		border: 1px solid var(--bg-hover);
		border-radius: 0.5rem;
		color: var(--text-muted);
		font-size: 0.75rem;
		max-width: 24rem;
	}

	.empty-hint svg {
		flex-shrink: 0;
		color: var(--amber-400);
	}
</style>
