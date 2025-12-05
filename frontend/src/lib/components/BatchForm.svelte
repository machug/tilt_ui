<script lang="ts">
	import { onMount } from 'svelte';
	import type { BatchResponse, BatchCreate, BatchUpdate, RecipeResponse, BatchStatus, HeaterEntity } from '$lib/api';
	import { fetchRecipes, fetchHeaterEntities, fetchCoolerEntities } from '$lib/api';
	import { configState, getTempUnit, fahrenheitToCelsius, celsiusToFahrenheit } from '$lib/stores/config.svelte';
	import { fetchAllDevices, type DeviceResponse } from '$lib/api/devices';
	import RecipeSelector from './RecipeSelector.svelte';

	interface Props {
		batch?: BatchResponse;
		onSubmit: (data: BatchCreate | BatchUpdate) => Promise<void>;
		onCancel: () => void;
		initialRecipeId?: number;
	}

	let { batch, onSubmit, onCancel, initialRecipeId }: Props = $props();

	// Form state
	let name = $state(batch?.name || '');
	let recipeId = $state<number | null>(batch?.recipe_id || null);
	let deviceId = $state<string | null>(batch?.device_id || null);
	let status = $state<BatchStatus>(batch?.status || 'planning');
	let brewDate = $state(batch?.brew_date ? batch.brew_date.split('T')[0] : '');
	let measuredOg = $state(batch?.measured_og?.toString() || '');
	let measuredFg = $state(batch?.measured_fg?.toString() || '');
	let notes = $state(batch?.notes || '');

	// Temperature control fields
	// Backend stores temps in Celsius (standardized after ML integration)
	let heaterEntityId = $state(batch?.heater_entity_id || '');
	let coolerEntityId = $state(batch?.cooler_entity_id || '');

	// Helper to convert backend C value to display value (F or C based on preference)
	function tempToDisplay(tempC: number | null | undefined): string {
		if (tempC === null || tempC === undefined) return '';
		if (configState.config.temp_units === 'F') {
			return celsiusToFahrenheit(tempC).toFixed(1);
		}
		return tempC.toFixed(1);
	}

	// Helper to convert temperature DELTA (difference) from C to display unit
	// For deltas: ΔF = ΔC × 9/5 (no offset addition)
	function tempDeltaToDisplay(deltaC: number | null | undefined): string {
		if (deltaC === null || deltaC === undefined) return '';
		if (configState.config.temp_units === 'F') {
			return (deltaC * 9 / 5).toFixed(1);
		}
		return deltaC.toFixed(1);
	}

	// Helper to convert display value back to C for backend
	function displayToTempC(displayValue: string): number | undefined {
		if (!displayValue) return undefined;
		const num = parseFloat(displayValue);
		if (isNaN(num)) return undefined;
		if (configState.config.temp_units === 'F') {
			return fahrenheitToCelsius(num);
		}
		return num;
	}

	// Helper to convert display delta back to C delta for backend
	// For deltas: ΔC = ΔF × 5/9 (no offset subtraction)
	function displayToTempDeltaC(displayValue: string): number | undefined {
		if (!displayValue) return undefined;
		const num = parseFloat(displayValue);
		if (isNaN(num)) return undefined;
		if (configState.config.temp_units === 'F') {
			return num * 5 / 9;
		}
		return num;
	}

	let tempTarget = $state(tempToDisplay(batch?.temp_target));
	let tempHysteresis = $state(tempDeltaToDisplay(batch?.temp_hysteresis));

	let recipes = $state<RecipeResponse[]>([]);
	let heaterEntities = $state<HeaterEntity[]>([]);
	let coolerEntities = $state<HeaterEntity[]>([]);
	let availableDevices = $state<DeviceResponse[]>([]);
	let loadingRecipes = $state(true);
	let loadingHeaters = $state(false);
	let loadingCoolers = $state(false);
	let loadingDevices = $state(false);
	let saving = $state(false);

	// Reactive temperature unit and validation ranges
	let tempUnit = $derived(getTempUnit());

	// Temperature validation ranges (depend on unit preference)
	let tempTargetMin = $derived(configState.config.temp_units === 'C' ? 0 : 32);
	let tempTargetMax = $derived(configState.config.temp_units === 'C' ? 38 : 100);
	let tempHysteresisMin = $derived(configState.config.temp_units === 'C' ? 0.3 : 0.5);
	let tempHysteresisMax = $derived(configState.config.temp_units === 'C' ? 5.5 : 10);

	let error = $state<string | null>(null);
	let selectedRecipe = $state<RecipeResponse | null>(null);

	// Check if HA is enabled
	let haEnabled = $derived(configState.config.ha_enabled);

	const statusOptions: { value: BatchStatus; label: string }[] = [
		{ value: 'planning', label: 'Planning' },
		{ value: 'fermenting', label: 'Fermenting' },
		{ value: 'conditioning', label: 'Conditioning' },
		{ value: 'completed', label: 'Completed' },
		{ value: 'archived', label: 'Archived' }
	];

	let isEditMode = $derived(!!batch);

	async function loadRecipes() {
		loadingRecipes = true;
		try {
			recipes = await fetchRecipes();
		} catch (e) {
			console.error('Failed to load recipes:', e);
		} finally {
			loadingRecipes = false;
		}
	}

	async function loadDevices() {
		loadingDevices = true;
		try {
			// Fetch only paired devices for batch assignment
			availableDevices = await fetchAllDevices(true);
		} catch (e) {
			console.error('Failed to load devices:', e);
		} finally {
			loadingDevices = false;
		}
	}

	async function loadHeaterEntities() {
		if (!haEnabled) return;
		loadingHeaters = true;
		try {
			heaterEntities = await fetchHeaterEntities();
		} catch (e) {
			console.error('Failed to load heater entities:', e);
		} finally {
			loadingHeaters = false;
		}
	}

	async function loadCoolerEntities() {
		if (!haEnabled) return;
		loadingCoolers = true;
		try {
			coolerEntities = await fetchCoolerEntities();
		} catch (e) {
			console.error('Failed to load cooler entities:', e);
		} finally {
			loadingCoolers = false;
		}
	}

	function handleRecipeSelect(recipe: RecipeResponse | null) {
		selectedRecipe = recipe;
		if (recipe) {
			// Auto-fill form from recipe
			name = recipe.name;
			recipeId = recipe.id;
			if (recipe.og_target) {
				measuredOg = recipe.og_target.toString();
			}
		} else {
			recipeId = null;
		}
	}

	async function handleSubmit(e: Event) {
		e.preventDefault();
		if (saving) return;

		saving = true;
		error = null;

		try {
			const data: BatchCreate | BatchUpdate = {
				name: name || undefined,
				status,
				device_id: deviceId || undefined,
				brew_date: brewDate ? new Date(brewDate).toISOString() : undefined,
				measured_og: measuredOg ? parseFloat(measuredOg) : undefined,
				notes: notes || undefined,
				// Temperature control - convert display values back to C for backend
				heater_entity_id: heaterEntityId || undefined,
				cooler_entity_id: coolerEntityId || undefined,
				temp_target: displayToTempC(tempTarget),
				temp_hysteresis: displayToTempDeltaC(tempHysteresis)
			};

			// Set recipe_id for both create and update
			if (!isEditMode) {
				(data as BatchCreate).recipe_id = recipeId || undefined;
			} else {
				(data as BatchUpdate).recipe_id = recipeId || undefined;
			}

			if (isEditMode && measuredFg) {
				(data as BatchUpdate).measured_fg = parseFloat(measuredFg);
			}

			await onSubmit(data);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to save batch';
		} finally {
			saving = false;
		}
	}

	// Auto-fill name from recipe when recipe changes
	$effect(() => {
		if (!isEditMode && recipeId && !name) {
			const recipe = recipes.find((r) => r.id === recipeId);
			if (recipe) {
				name = recipe.name;
			}
		}
	});

	// Load heater entities when HA becomes enabled
	$effect(() => {
		if (haEnabled && heaterEntities.length === 0 && !loadingHeaters) {
			loadHeaterEntities();
		}
	});

	// Load cooler entities when HA becomes enabled
	$effect(() => {
		if (haEnabled && coolerEntities.length === 0 && !loadingCoolers) {
			loadCoolerEntities();
		}
	});

	// Auto-select recipe from query parameter
	$effect(() => {
		if (initialRecipeId && recipes.length > 0 && !selectedRecipe) {
			const recipe = recipes.find((r) => r.id === initialRecipeId);
			if (recipe) {
				handleRecipeSelect(recipe);
			}
		}
	});

	// Initialize selectedRecipe when editing batch with recipe
	$effect(() => {
		if (isEditMode && batch?.recipe && recipes.length > 0 && !selectedRecipe) {
			const recipe = recipes.find((r) => r.id === batch.recipe_id);
			if (recipe) {
				selectedRecipe = recipe;
			}
		}
	});

	onMount(() => {
		loadRecipes();
		loadDevices();
		loadHeaterEntities();
		loadCoolerEntities();
	});
</script>

<form class="batch-form" onsubmit={handleSubmit}>
	<div class="form-header">
		<h2 class="form-title">{isEditMode ? 'Edit Batch' : 'New Batch'}</h2>
		<p class="form-description">
			{isEditMode ? 'Update batch details and measurements' : 'Create a new fermentation batch'}
		</p>
	</div>

	{#if error}
		<div class="error-banner">
			<span class="error-icon">!</span>
			{error}
		</div>
	{/if}

	<div class="form-body">
		<!-- Recipe Selection -->
		<RecipeSelector
			selectedRecipeId={selectedRecipe?.id}
			onSelect={handleRecipeSelect}
		/>

			{#if selectedRecipe}
				<div class="recipe-reference">
					<p class="reference-label">From Recipe:</p>
					{#if selectedRecipe.yeast_name}
						<p class="reference-text">
							Yeast: {selectedRecipe.yeast_name}
							{#if selectedRecipe.yeast_temp_min && selectedRecipe.yeast_temp_max}
								({selectedRecipe.yeast_temp_min.toFixed(0)}-{selectedRecipe.yeast_temp_max.toFixed(
									0
								)}°C)
							{/if}
						</p>
					{/if}
				</div>
			{/if}

		<!-- Batch Name -->
		<div class="form-group">
			<label class="form-label" for="name">Batch Name</label>
			<input
				type="text"
				id="name"
				class="form-input"
				bind:value={name}
				placeholder="e.g., Summer IPA #3"
				maxlength="200"
			/>
			<span class="form-hint">Optional - defaults to recipe name</span>
		</div>

		<!-- Status -->
		<div class="form-group">
			<label class="form-label" for="status">Status</label>
			<select id="status" class="form-select" bind:value={status}>
				{#each statusOptions as option}
					<option value={option.value}>{option.label}</option>
				{/each}
			</select>
		</div>

		<!-- Device -->
		<div class="form-group">
			<label class="form-label" for="device">Tracking Device</label>
			{#if loadingDevices}
				<span class="form-hint">Loading devices...</span>
			{:else if availableDevices.length === 0}
				<div class="warning-message">
					<p>No paired devices available. Please <a href="/devices">pair a device</a> before creating a batch.</p>
				</div>
			{:else}
				<select id="device" class="form-select" bind:value={deviceId}>
					<option value={null}>No device assigned</option>
					{#each availableDevices as device}
						<option value={device.id}>
							{device.color} Tilt
							{#if device.beer_name && device.beer_name !== 'Untitled'}
								- {device.beer_name}
							{/if}
						</option>
					{/each}
				</select>
				<span class="form-hint">Link a Tilt to track live gravity and temperature</span>
			{/if}
		</div>

		<!-- Brew Date -->
		<div class="form-group">
			<label class="form-label" for="brewDate">Brew Date</label>
			<input
				type="date"
				id="brewDate"
				class="form-input date-input"
				bind:value={brewDate}
			/>
			<span class="form-hint">DD/MM/YYYY</span>
		</div>

		<!-- Gravity Measurements -->
		<div class="form-row">
			<div class="form-group">
				<label class="form-label" for="og">Measured OG</label>
				<input
					type="number"
					id="og"
					class="form-input"
					bind:value={measuredOg}
					placeholder="1.050"
					step="0.001"
					min="0.990"
					max="1.200"
				/>
			</div>
			{#if isEditMode}
				<div class="form-group">
					<label class="form-label" for="fg">Measured FG</label>
					<input
						type="number"
						id="fg"
						class="form-input"
						bind:value={measuredFg}
						placeholder="1.010"
						step="0.001"
						min="0.990"
						max="1.100"
					/>
				</div>
			{/if}
		</div>

		<!-- Temperature Control (only if HA is enabled) -->
		{#if haEnabled}
			<div class="form-section">
				<h3 class="section-title">Temperature Control</h3>
				<span class="section-hint">Link heater and/or cooler switches from Home Assistant to control fermentation temperature</span>
			</div>

			<div class="form-group">
				<label class="form-label" for="heaterEntity">Heater Switch</label>
				<select
					id="heaterEntity"
					class="form-select"
					bind:value={heaterEntityId}
					disabled={loadingHeaters}
				>
					<option value="">No heater assigned</option>
					{#each heaterEntities as entity}
						<option value={entity.entity_id}>
							{entity.friendly_name} ({entity.state})
						</option>
					{/each}
				</select>
				{#if loadingHeaters}
					<span class="form-hint">Loading available switches from Home Assistant...</span>
				{:else if heaterEntities.length === 0}
					<span class="form-hint">No switches found in Home Assistant</span>
				{:else}
					<span class="form-hint">Select a switch or input_boolean entity to control the heater</span>
				{/if}
			</div>

			<div class="form-group">
				<label class="form-label" for="coolerEntity">Cooler Switch</label>
				<select
					id="coolerEntity"
					class="form-select"
					bind:value={coolerEntityId}
					disabled={loadingCoolers}
				>
					<option value="">No cooler assigned</option>
					{#each coolerEntities as entity}
						<option value={entity.entity_id}>
							{entity.friendly_name} ({entity.state})
						</option>
					{/each}
				</select>
				{#if loadingCoolers}
					<span class="form-hint">Loading available switches from Home Assistant...</span>
				{:else if coolerEntities.length === 0}
					<span class="form-hint">No switches found in Home Assistant</span>
				{:else}
					<span class="form-hint">Select a switch or input_boolean entity to control the cooler</span>
				{/if}
			</div>

			{#if heaterEntityId || coolerEntityId}
				<div class="form-row">
					<div class="form-group">
						<label class="form-label" for="tempTarget">Target Temperature ({tempUnit})</label>
						<input
							type="number"
							id="tempTarget"
							class="form-input"
							bind:value={tempTarget}
							placeholder="68"
							step="0.5"
							min={tempTargetMin}
							max={tempTargetMax}
						/>
						<span class="form-hint">Leave empty to use global setting</span>
					</div>
					<div class="form-group">
						<label class="form-label" for="tempHysteresis">Hysteresis ({tempUnit})</label>
						<input
							type="number"
							id="tempHysteresis"
							class="form-input"
							bind:value={tempHysteresis}
							placeholder="1.0"
							step="0.5"
							min={tempHysteresisMin}
							max={tempHysteresisMax}
						/>
						<span class="form-hint">Leave empty to use global setting</span>
					</div>
				</div>
			{/if}
		{/if}

		<!-- Notes -->
		<div class="form-group">
			<label class="form-label" for="notes">Notes</label>
			<textarea
				id="notes"
				class="form-textarea"
				bind:value={notes}
				placeholder="Brewing notes, observations, etc."
				rows="3"
			></textarea>
		</div>
	</div>

	<div class="form-footer">
		<button type="button" class="btn-cancel" onclick={onCancel} disabled={saving}>
			Cancel
		</button>
		<button type="submit" class="btn-submit" disabled={saving}>
			{#if saving}
				<span class="spinner"></span>
				Saving...
			{:else}
				{isEditMode ? 'Save Changes' : 'Create Batch'}
			{/if}
		</button>
	</div>
</form>

<style>
	.batch-form {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.75rem;
		overflow: hidden;
	}

	.form-header {
		padding: 1.5rem;
		border-bottom: 1px solid var(--border-subtle);
	}

	.form-title {
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0 0 0.25rem 0;
	}

	.form-description {
		font-size: 0.875rem;
		color: var(--text-muted);
		margin: 0;
	}

	.form-body {
		padding: 1.5rem;
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
	}

	.form-section {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		padding-top: 1rem;
		border-top: 1px solid var(--border-subtle);
		margin-top: 0.5rem;
	}

	.section-title {
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.section-hint {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.form-group {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.form-row {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 1rem;
	}

	.form-label {
		font-size: 0.8125rem;
		font-weight: 500;
		color: var(--text-secondary);
	}

	.form-input,
	.form-select,
	.form-textarea {
		padding: 0.625rem 0.75rem;
		font-size: 0.875rem;
		color: var(--text-primary);
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 0.5rem;
		outline: none;
		transition: border-color var(--transition);
	}

	.form-input:focus,
	.form-select:focus,
	.form-textarea:focus {
		border-color: var(--accent);
	}

	.form-input::placeholder,
	.form-textarea::placeholder {
		color: var(--text-muted);
	}

	.form-select {
		cursor: pointer;
	}

	.form-textarea {
		resize: vertical;
		min-height: 80px;
	}

	.form-hint {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.form-footer {
		display: flex;
		justify-content: flex-end;
		gap: 0.75rem;
		padding: 1rem 1.5rem;
		background: var(--bg-elevated);
		border-top: 1px solid var(--border-subtle);
	}

	.btn-cancel,
	.btn-submit {
		padding: 0.625rem 1.25rem;
		font-size: 0.875rem;
		font-weight: 500;
		border-radius: 0.5rem;
		cursor: pointer;
		transition: all var(--transition);
	}

	.btn-cancel {
		color: var(--text-secondary);
		background: transparent;
		border: 1px solid var(--border-default);
	}

	.btn-cancel:hover:not(:disabled) {
		color: var(--text-primary);
		border-color: var(--text-muted);
	}

	.btn-submit {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		color: white;
		background: var(--accent);
		border: none;
	}

	.btn-submit:hover:not(:disabled) {
		background: var(--accent-hover);
	}

	.btn-cancel:disabled,
	.btn-submit:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.error-banner {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin: 1rem 1.5rem 0;
		padding: 0.75rem 1rem;
		font-size: 0.875rem;
		color: var(--negative);
		background: rgba(239, 68, 68, 0.1);
		border-radius: 0.5rem;
	}

	.error-icon {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 1.5rem;
		height: 1.5rem;
		font-size: 0.875rem;
		font-weight: 700;
		background: rgba(239, 68, 68, 0.2);
		border-radius: 50%;
	}

	.spinner {
		width: 1rem;
		height: 1rem;
		border: 2px solid rgba(255, 255, 255, 0.3);
		border-top-color: white;
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	.recipe-reference {
		padding: var(--space-3);
		background: var(--recipe-accent-muted);
		border: 1px solid var(--recipe-accent-border);
		border-radius: 6px;
	}

	.reference-label {
		font-size: 12px;
		font-weight: 500;
		color: var(--recipe-accent);
		margin: 0 0 var(--space-1) 0;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.reference-text {
		font-size: 13px;
		color: var(--text-secondary);
		font-family: var(--font-mono);
		margin: 0;
	}

	.warning-message {
		padding: 0.75rem 1rem;
		background: rgba(245, 158, 11, 0.1);
		border: 1px solid rgba(245, 158, 11, 0.3);
		border-radius: 0.5rem;
	}

	.warning-message p {
		margin: 0;
		font-size: 0.875rem;
		color: var(--warning);
	}

	.warning-message a {
		color: var(--accent);
		font-weight: 500;
		text-decoration: underline;
	}

	.warning-message a:hover {
		color: var(--accent-hover);
	}

	@media (max-width: 480px) {
		.form-row {
			grid-template-columns: 1fr;
		}
	}
</style>
