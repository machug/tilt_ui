<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import type { RecipeResponse } from '$lib/api';
	import { fetchRecipe, deleteRecipe } from '$lib/api';

	let recipe = $state<RecipeResponse | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let showDeleteConfirm = $state(false);
	let deleting = $state(false);

	let recipeId = $derived(() => {
		const id = parseInt($page.params.id || '', 10);
		return isNaN(id) || id <= 0 ? null : id;
	});

	onMount(async () => {
		if (!recipeId) {
			error = 'Invalid recipe ID';
			loading = false;
			return;
		}

		try {
			recipe = await fetchRecipe(recipeId);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load recipe';
		} finally {
			loading = false;
		}
	});

	async function handleDelete() {
		if (!recipe) return;

		deleting = true;
		try {
			await deleteRecipe(recipe.id);
			goto('/recipes');
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to delete recipe';
			deleting = false;
			showDeleteConfirm = false;
		}
	}

	function handleBrewThis() {
		if (!recipe) return;
		goto(`/batches/new?recipe_id=${recipe.id}`);
	}
</script>

<svelte:head>
	<title>{recipe?.name || 'Recipe'} | BrewSignal</title>
</svelte:head>

<div class="page-container">
	<div class="back-link">
		<a href="/recipes" class="back-btn">
			<svg class="back-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
			</svg>
			Back to Recipes
		</a>
	</div>

	{#if loading}
		<div class="loading-state">
			<div class="spinner"></div>
			<p>Loading recipe...</p>
		</div>
	{:else if error}
		<div class="error-state">
			<p class="error-message">{error}</p>
		</div>
	{:else if recipe}
		<div class="recipe-container">
			<div class="recipe-header">
				<div class="header-left">
					<h1 class="recipe-title">{recipe.name}</h1>
					{#if recipe.author}
						<p class="recipe-author">by {recipe.author}</p>
					{/if}
					{#if recipe.type}
						<p class="recipe-type">{recipe.type}</p>
					{/if}
				</div>
				<button type="button" class="delete-btn" onclick={() => (showDeleteConfirm = true)}>
					<svg class="icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
						/>
					</svg>
					Delete
				</button>
			</div>

			<div class="section">
				<h2 class="section-title">Fermentation Parameters</h2>
				<div class="param-grid">
					{#if recipe.og_target}
						<div class="param">
							<span class="param-label">Original Gravity</span>
							<span class="param-value">{recipe.og_target.toFixed(3)}</span>
						</div>
					{/if}
					{#if recipe.fg_target}
						<div class="param">
							<span class="param-label">Final Gravity</span>
							<span class="param-value">{recipe.fg_target.toFixed(3)}</span>
						</div>
					{/if}
					{#if recipe.abv_target}
						<div class="param">
							<span class="param-label">ABV</span>
							<span class="param-value">{recipe.abv_target.toFixed(1)}%</span>
						</div>
					{/if}
					{#if recipe.yeast_attenuation}
						<div class="param">
							<span class="param-label">Attenuation</span>
							<span class="param-value">{recipe.yeast_attenuation.toFixed(0)}%</span>
						</div>
					{/if}
				</div>
			</div>

			{#if recipe.yeast_name || recipe.yeast_temp_min || recipe.yeast_temp_max}
				<div class="section">
					<h2 class="section-title">Yeast</h2>
					<div class="yeast-info">
						{#if recipe.yeast_name}
							<p class="yeast-name">{recipe.yeast_name}</p>
						{/if}
						{#if recipe.yeast_lab}
							<p class="yeast-lab">{recipe.yeast_lab}</p>
						{/if}
						{#if recipe.yeast_temp_min != null && recipe.yeast_temp_max != null}
							<p class="yeast-temp">
								Temperature: {recipe.yeast_temp_min.toFixed(0)}-{recipe.yeast_temp_max.toFixed(0)}°C
							</p>
						{/if}
					</div>
				</div>
			{/if}

			<div class="section">
				<h2 class="section-title">Batch Details</h2>
				<div class="details-grid">
					{#if recipe.batch_size}
						<div class="detail">
							<span class="detail-label">Batch Size</span>
							<span class="detail-value">{recipe.batch_size.toFixed(1)} L</span>
						</div>
					{/if}
					{#if recipe.ibu_target}
						<div class="detail">
							<span class="detail-label">IBU</span>
							<span class="detail-value">{recipe.ibu_target.toFixed(0)}</span>
						</div>
					{/if}
					{#if recipe.srm_target}
						<div class="detail">
							<span class="detail-label">SRM</span>
							<span class="detail-value">{recipe.srm_target.toFixed(1)}</span>
						</div>
					{/if}
				</div>
			</div>

			{#if recipe.notes}
				<div class="section">
					<h2 class="section-title">Notes</h2>
					<p class="notes">{recipe.notes}</p>
				</div>
			{/if}

			<div class="section">
				<p class="created-date">Created {new Date(recipe.created_at).toLocaleDateString()}</p>
			</div>

			<div class="actions">
				<button type="button" class="brew-btn" onclick={handleBrewThis}>
					<svg class="icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M12 6v6m0 0v6m0-6h6m-6 0H6"
						/>
					</svg>
					Brew This Recipe
				</button>
			</div>
		</div>
	{/if}
</div>

{#if showDeleteConfirm}
	<div class="modal-overlay" onclick={() => (showDeleteConfirm = false)}>
		<div class="modal" onclick={(e) => e.stopPropagation()}>
			<h2 class="modal-title">Delete Recipe?</h2>
			<p class="modal-text">
				Are you sure you want to delete "{recipe?.name}"? This cannot be undone.
			</p>
			<div class="modal-actions">
				<button
					type="button"
					class="modal-btn cancel"
					onclick={() => (showDeleteConfirm = false)}
					disabled={deleting}
				>
					Cancel
				</button>
				<button type="button" class="modal-btn delete" onclick={handleDelete} disabled={deleting}>
					{deleting ? 'Deleting...' : 'Delete Recipe'}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.page-container {
		max-width: 800px;
		margin: 0 auto;
		padding: var(--space-6);
	}

	.back-link {
		margin-bottom: var(--space-6);
	}

	.back-btn {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		font-size: 14px;
		font-weight: 500;
		color: var(--text-secondary);
		text-decoration: none;
		transition: color var(--transition);
	}

	.back-btn:hover {
		color: var(--text-primary);
	}

	.back-icon {
		width: 16px;
		height: 16px;
	}

	.loading-state,
	.error-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: var(--space-12) var(--space-6);
		text-align: center;
	}

	.spinner {
		width: 32px;
		height: 32px;
		border: 3px solid var(--gray-700);
		border-top-color: var(--recipe-accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	.error-message {
		color: var(--negative);
		font-size: 14px;
	}

	.recipe-container {
		display: flex;
		flex-direction: column;
		gap: var(--space-6);
	}

	.recipe-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: var(--space-4);
		padding-bottom: var(--space-6);
		border-bottom: 1px solid var(--border-subtle);
	}

	.header-left {
		flex: 1;
	}

	.recipe-title {
		font-family: var(--font-recipe-name);
		font-size: 32px;
		font-weight: 600;
		letter-spacing: -0.02em;
		color: var(--text-primary);
		margin: 0 0 var(--space-2) 0;
	}

	.recipe-author {
		font-size: 14px;
		color: var(--text-secondary);
		margin: 0 0 var(--space-1) 0;
	}

	.recipe-type {
		font-size: 13px;
		color: var(--text-muted);
		font-family: var(--font-mono);
		margin: 0;
	}

	.delete-btn {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-2) var(--space-3);
		background: transparent;
		border: 1px solid var(--border-default);
		border-radius: 6px;
		color: var(--text-secondary);
		font-size: 14px;
		cursor: pointer;
		transition: all var(--transition);
	}

	.delete-btn:hover {
		border-color: var(--negative);
		color: var(--negative);
	}

	.icon {
		width: 16px;
		height: 16px;
	}

	.section {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}

	.section-title {
		font-size: 16px;
		font-weight: 600;
		color: var(--recipe-accent);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0;
	}

	.param-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
		gap: var(--space-4);
		padding: var(--space-4);
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 6px;
	}

	.param {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.param-label {
		font-size: 12px;
		color: var(--text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.param-value {
		font-family: var(--font-measurement);
		font-size: 20px;
		color: var(--text-primary);
	}

	.yeast-info {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		padding: var(--space-4);
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 6px;
	}

	.yeast-name {
		font-size: 16px;
		font-weight: 500;
		color: var(--text-primary);
		margin: 0;
	}

	.yeast-lab {
		font-size: 14px;
		color: var(--text-secondary);
		margin: 0;
	}

	.yeast-temp {
		font-family: var(--font-mono);
		font-size: 13px;
		color: var(--text-secondary);
		margin: 0;
	}

	.details-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
		gap: var(--space-4);
	}

	.detail {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.detail-label {
		font-size: 12px;
		color: var(--text-secondary);
	}

	.detail-value {
		font-family: var(--font-measurement);
		font-size: 16px;
		color: var(--text-primary);
	}

	.notes {
		font-size: 14px;
		color: var(--text-secondary);
		line-height: 1.6;
		margin: 0;
	}

	.created-date {
		font-size: 12px;
		color: var(--text-muted);
		font-family: var(--font-mono);
		margin: 0;
	}

	.actions {
		display: flex;
		justify-content: center;
		padding-top: var(--space-6);
		border-top: 1px solid var(--border-subtle);
	}

	.brew-btn {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-3) var(--space-6);
		background: var(--recipe-accent);
		color: white;
		border: none;
		border-radius: 6px;
		font-size: 16px;
		font-weight: 600;
		cursor: pointer;
		transition: background var(--transition);
	}

	.brew-btn:hover {
		background: var(--recipe-accent-hover);
	}

	.modal-overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.6);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
	}

	.modal {
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 8px;
		padding: var(--space-6);
		max-width: 400px;
		width: 90%;
	}

	.modal-title {
		font-size: 20px;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0 0 var(--space-3) 0;
	}

	.modal-text {
		font-size: 14px;
		color: var(--text-secondary);
		line-height: 1.5;
		margin: 0 0 var(--space-6) 0;
	}

	.modal-actions {
		display: flex;
		gap: var(--space-3);
		justify-content: flex-end;
	}

	.modal-btn {
		padding: var(--space-2) var(--space-4);
		border-radius: 6px;
		font-size: 14px;
		font-weight: 500;
		cursor: pointer;
		transition: all var(--transition);
	}

	.modal-btn.cancel {
		background: transparent;
		border: 1px solid var(--border-default);
		color: var(--text-primary);
	}

	.modal-btn.cancel:hover {
		background: var(--bg-hover);
	}

	.modal-btn.delete {
		background: var(--negative);
		border: none;
		color: white;
	}

	.modal-btn.delete:hover {
		background: #dc2626;
	}

	.modal-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
</style>
