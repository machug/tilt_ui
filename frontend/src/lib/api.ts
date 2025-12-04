// API helper functions for BrewSignal

const BASE_URL = '/api';

export interface HistoricalReading {
	id: number;
	timestamp: string;
	sg_raw: number | null;
	sg_calibrated: number | null;
	temp_raw: number | null;
	temp_calibrated: number | null;
	rssi: number | null;
	status?: string; // 'valid', 'invalid', 'uncalibrated', 'incomplete'
}

export interface TimeRangeOption {
	label: string;
	hours: number;
}

export const TIME_RANGES: TimeRangeOption[] = [
	{ label: '1H', hours: 1 },
	{ label: '6H', hours: 6 },
	{ label: '24H', hours: 24 },
	{ label: '7D', hours: 168 },
	{ label: '30D', hours: 720 }
];

export async function fetchReadings(
	tiltId: string,
	hours: number = 24
): Promise<HistoricalReading[]> {
	const response = await fetch(`${BASE_URL}/tilts/${tiltId}/readings?hours=${hours}&limit=5000`);
	if (!response.ok) {
		throw new Error(`Failed to fetch readings: ${response.statusText}`);
	}
	return response.json();
}

export async function updateTiltBeerName(tiltId: string, beerName: string): Promise<void> {
	const response = await fetch(`${BASE_URL}/tilts/${tiltId}`, {
		method: 'PUT',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ beer_name: beerName })
	});
	if (!response.ok) {
		throw new Error(`Failed to update tilt: ${response.statusText}`);
	}
}

export interface AmbientHistoricalReading {
	id: number;
	timestamp: string;
	temperature: number | null;
	humidity: number | null;
}

export async function fetchAmbientHistory(hours: number = 24): Promise<AmbientHistoricalReading[]> {
	const response = await fetch(`${BASE_URL}/ambient/history?hours=${hours}`);
	if (!response.ok) {
		throw new Error('Failed to fetch ambient history');
	}
	return response.json();
}

// ============================================================================
// Batch Types & API
// ============================================================================

export type BatchStatus = 'planning' | 'fermenting' | 'conditioning' | 'completed' | 'archived';

export interface FermentableResponse {
	id: number;
	name: string;
	type?: string;
	amount_kg?: number;
	yield_percent?: number;
	color_lovibond?: number;
	origin?: string;
	supplier?: string;
}

export interface HopResponse {
	id: number;
	name: string;
	alpha_percent?: number;
	amount_kg?: number;
	use?: string;
	time_min?: number;
	form?: string;
	type?: string;
}

export interface YeastResponse {
	id: number;
	name: string;
	lab?: string;
	product_id?: string;
	type?: string;
	attenuation_percent?: number;
	temp_min_c?: number;
	temp_max_c?: number;
	flocculation?: string;
}

export interface MiscResponse {
	id: number;
	name: string;
	type?: string;
	use?: string;
	time_min?: number;
	amount_kg?: number;
	amount_is_weight?: boolean;
}

export interface RecipeResponse {
	id: number;
	name: string;
	author?: string;
	style_id?: string;
	type?: string;
	og_target?: number;
	fg_target?: number;
	yeast_name?: string;
	yeast_lab?: string;
	yeast_product_id?: string;
	yeast_temp_min?: number;
	yeast_temp_max?: number;
	yeast_attenuation?: number;
	ibu_target?: number;
	srm_target?: number;
	abv_target?: number;
	batch_size?: number;
	notes?: string;
	created_at: string;
	// Ingredient lists (only in detail response)
	fermentables?: FermentableResponse[];
	hops?: HopResponse[];
	yeasts?: YeastResponse[];
	miscs?: MiscResponse[];
}

export interface BatchResponse {
	id: number;
	recipe_id?: number;
	device_id?: string;
	batch_number?: number;
	name?: string;
	status: BatchStatus;
	brew_date?: string;
	start_time?: string;
	end_time?: string;
	measured_og?: number;
	measured_fg?: number;
	measured_abv?: number;
	measured_attenuation?: number;
	notes?: string;
	created_at: string;
	recipe?: RecipeResponse;
	// Temperature control
	heater_entity_id?: string;
	temp_target?: number;
	temp_hysteresis?: number;
	// Soft delete
	deleted_at?: string;
}

export interface BatchCreate {
	recipe_id?: number;
	device_id?: string;
	name?: string;
	status?: BatchStatus;
	brew_date?: string;
	measured_og?: number;
	notes?: string;
	// Temperature control
	heater_entity_id?: string;
	temp_target?: number;
	temp_hysteresis?: number;
}

export interface BatchUpdate {
	name?: string;
	status?: BatchStatus;
	device_id?: string;
	brew_date?: string;
	start_time?: string;
	end_time?: string;
	measured_og?: number;
	measured_fg?: number;
	notes?: string;
	// Temperature control
	heater_entity_id?: string;
	temp_target?: number;
	temp_hysteresis?: number;
}

export interface BatchProgressResponse {
	batch_id: number;
	recipe_name?: string;
	status: BatchStatus;
	targets: {
		og?: number;
		fg?: number;
		attenuation?: number;
		abv?: number;
	};
	measured: {
		og?: number;
		current_sg?: number;
		attenuation?: number;
		abv?: number;
	};
	progress: {
		percent_complete?: number;
		sg_remaining?: number;
		estimated_days_remaining?: number;
	};
	temperature: {
		current?: number;
		yeast_min?: number;
		yeast_max?: number;
		status: 'unknown' | 'in_range' | 'too_cold' | 'too_hot';
	};
}

export interface BatchControlStatus {
	batch_id: number;
	enabled: boolean;
	heater_state?: string;
	heater_entity?: string;
	override_active: boolean;
	override_state?: string;
	override_until?: string;
	target_temp?: number;
	hysteresis?: number;
	wort_temp?: number;
}

/**
 * Heater entity from Home Assistant
 */
export interface HeaterEntity {
	entity_id: string;
	friendly_name: string;
	state: string | null;
}

/**
 * Fetch available heater entities from Home Assistant
 */
export async function fetchHeaterEntities(): Promise<HeaterEntity[]> {
	const response = await fetch(`${BASE_URL}/control/heater-entities`);
	if (!response.ok) {
		throw new Error(`Failed to fetch heater entities: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Fetch batch control status
 */
export async function fetchBatchControlStatus(batchId: number): Promise<BatchControlStatus> {
	const response = await fetch(`${BASE_URL}/control/batch/${batchId}/status`);
	if (!response.ok) {
		throw new Error(`Failed to fetch batch control status: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Toggle heater for a specific batch
 */
export async function toggleBatchHeater(batchId: number, state: 'on' | 'off'): Promise<{ success: boolean; message: string; new_state?: string }> {
	const response = await fetch(`${BASE_URL}/control/heater`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ state, batch_id: batchId })
	});
	return response.json();
}

/**
 * Set heater override for a batch
 */
export async function setBatchHeaterOverride(
	batchId: number,
	state: 'on' | 'off' | null,
	durationMinutes: number = 60
): Promise<{ success: boolean; message: string; override_state?: string; override_until?: string }> {
	const response = await fetch(`${BASE_URL}/control/override`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ state, duration_minutes: durationMinutes, batch_id: batchId })
	});
	return response.json();
}

/**
 * Fetch batches with optional filtering
 */
export async function fetchBatches(
	status?: BatchStatus,
	deviceId?: string,
	limit: number = 50,
	offset: number = 0,
	deletedOnly: boolean = false
): Promise<BatchResponse[]> {
	const params = new URLSearchParams();
	if (status) params.append('status', status);
	if (deviceId) params.append('device_id', deviceId);
	if (deletedOnly) params.append('deleted_only', 'true');
	params.append('limit', String(limit));
	params.append('offset', String(offset));

	const response = await fetch(`${BASE_URL}/batches?${params}`);
	if (!response.ok) {
		throw new Error(`Failed to fetch batches: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Fetch active batches (planning or fermenting)
 */
export async function fetchActiveBatches(limit: number = 50, offset: number = 0): Promise<BatchResponse[]> {
	const params = new URLSearchParams();
	params.append('limit', String(limit));
	params.append('offset', String(offset));

	const response = await fetch(`${BASE_URL}/batches/active?${params}`);
	if (!response.ok) {
		throw new Error(`Failed to fetch active batches: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Fetch completed batches (completed or conditioning)
 */
export async function fetchCompletedBatches(limit: number = 50, offset: number = 0): Promise<BatchResponse[]> {
	const params = new URLSearchParams();
	params.append('limit', String(limit));
	params.append('offset', String(offset));

	const response = await fetch(`${BASE_URL}/batches/completed?${params}`);
	if (!response.ok) {
		throw new Error(`Failed to fetch completed batches: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Fetch deleted batches
 */
export async function fetchDeletedBatches(limit: number = 50, offset: number = 0): Promise<BatchResponse[]> {
	return fetchBatches(undefined, undefined, limit, offset, true);
}

/**
 * Fetch a single batch by ID
 */
export async function fetchBatch(batchId: number): Promise<BatchResponse> {
	const response = await fetch(`${BASE_URL}/batches/${batchId}`);
	if (!response.ok) {
		throw new Error(`Failed to fetch batch: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Create a new batch
 */
export async function createBatch(batch: BatchCreate): Promise<BatchResponse> {
	const response = await fetch(`${BASE_URL}/batches`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(batch)
	});
	if (!response.ok) {
		throw new Error(`Failed to create batch: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Update an existing batch
 */
export async function updateBatch(batchId: number, update: BatchUpdate): Promise<BatchResponse> {
	const response = await fetch(`${BASE_URL}/batches/${batchId}`, {
		method: 'PUT',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(update)
	});
	if (!response.ok) {
		throw new Error(`Failed to update batch: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Delete a batch (soft delete)
 */
export async function deleteBatch(batchId: number): Promise<void> {
	const response = await fetch(`${BASE_URL}/batches/${batchId}`, {
		method: 'DELETE'
	});
	if (!response.ok) {
		throw new Error(`Failed to delete batch: ${response.statusText}`);
	}
}

/**
 * Restore a soft-deleted batch
 */
export async function restoreBatch(batchId: number): Promise<BatchResponse> {
	const response = await fetch(`${BASE_URL}/batches/${batchId}/restore`, {
		method: 'POST'
	});
	if (!response.ok) {
		throw new Error(`Failed to restore batch: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Fetch fermentation progress for a batch
 */
export async function fetchBatchProgress(batchId: number): Promise<BatchProgressResponse> {
	const response = await fetch(`${BASE_URL}/batches/${batchId}/progress`);
	if (!response.ok) {
		throw new Error(`Failed to fetch batch progress: ${response.statusText}`);
	}
	return response.json();
}

// ============================================================================
// Recipe Types & API
// ============================================================================

export async function fetchRecipes(limit = 50, offset = 0): Promise<RecipeResponse[]> {
	const response = await fetch(`${BASE_URL}/recipes?limit=${limit}&offset=${offset}`);
	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: response.statusText }));
		throw new Error(error.detail || 'Failed to fetch recipes');
	}
	return response.json();
}

export async function fetchRecipe(id: number): Promise<RecipeResponse> {
	const response = await fetch(`${BASE_URL}/recipes/${id}`);
	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: response.statusText }));
		throw new Error(error.detail || 'Failed to fetch recipe');
	}
	return response.json();
}

export async function importBeerXML(file: File): Promise<RecipeResponse[]> {
	const formData = new FormData();
	formData.append('file', file);

	const response = await fetch(`${BASE_URL}/recipes/import`, {
		method: 'POST',
		body: formData
	});

	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: response.statusText }));
		throw new Error(error.detail || 'Failed to import recipe');
	}

	return response.json();
}

export async function deleteRecipe(id: number): Promise<void> {
	const response = await fetch(`${BASE_URL}/recipes/${id}`, {
		method: 'DELETE'
	});

	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: response.statusText }));
		throw new Error(error.detail || 'Failed to delete recipe');
	}
}

// ============================================================================
// Maintenance Types & API
// ============================================================================

export interface OrphanedDataReport {
	orphaned_readings_count: number;
	orphaned_readings: number[]; // Reading IDs
	batches_with_orphans: Record<number, number>; // batch_id -> count
}

export interface CleanupPreview {
	readings_to_delete: number[]; // Reading IDs
	total_count: number;
	batch_breakdown: Record<number, number>; // batch_id -> count
}

/**
 * Fetch orphaned data report (readings linked to deleted batches)
 */
export async function fetchOrphanedData(): Promise<OrphanedDataReport> {
	const response = await fetch(`${BASE_URL}/maintenance/orphaned-data`);
	if (!response.ok) {
		throw new Error(`Failed to fetch orphaned data: ${response.statusText}`);
	}
	return response.json();
}

/**
 * Preview cleanup of readings for deleted batches
 */
export async function previewCleanup(batchIds: number[]): Promise<CleanupPreview> {
	const response = await fetch(`${BASE_URL}/maintenance/cleanup-readings`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ deleted_batch_ids: batchIds, dry_run: true })
	});
	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: response.statusText }));
		throw new Error(error.detail || 'Failed to preview cleanup');
	}
	return response.json();
}

/**
 * Execute cleanup of readings for deleted batches
 */
export async function executeCleanup(batchIds: number[]): Promise<CleanupPreview> {
	const response = await fetch(`${BASE_URL}/maintenance/cleanup-readings`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ deleted_batch_ids: batchIds, dry_run: false })
	});
	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: response.statusText }));
		throw new Error(error.detail || 'Failed to execute cleanup');
	}
	return response.json();
}
