<script lang="ts">
	import type { RecipeResponse } from '$lib/api';
	import { formatGravity } from '$lib/stores/config.svelte';
	import BatchCard from './BatchCard.svelte';

	interface Props {
		recipe: RecipeResponse;
	}

	let { recipe }: Props = $props();

	function formatSG(value?: number | null): string {
		if (value === undefined || value === null) return '--';
		return formatGravity(value);
	}
</script>

<BatchCard title="Recipe Targets">
	<div class="targets-grid">
		<div class="target">
			<span class="target-label">OG</span>
			<span class="target-value">{formatSG(recipe.og_target)}</span>
		</div>
		<div class="target">
			<span class="target-label">FG</span>
			<span class="target-value">{formatSG(recipe.fg_target)}</span>
		</div>
		<div class="target">
			<span class="target-label">ABV</span>
			<span class="target-value">
				{recipe.abv_target != null ? `${recipe.abv_target.toFixed(1)}%` : '--'}
			</span>
		</div>
		{#if recipe.yeast_name}
			<div class="target wide">
				<span class="target-label">Yeast</span>
				<span class="target-value">{recipe.yeast_name}</span>
			</div>
		{/if}
	</div>
</BatchCard>

<style>
	.targets-grid {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 0.75rem;
	}

	.target {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.target.wide {
		grid-column: span 2;
	}

	.target-label {
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
	}

	.target-value {
		font-family: var(--font-mono);
		font-size: 1rem;
		font-weight: 500;
		color: var(--text-secondary);
	}

	@media (max-width: 640px) {
		.targets-grid {
			grid-template-columns: repeat(2, 1fr);
		}
	}
</style>
