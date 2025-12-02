// Svelte 5 runes-based store for Tilt readings

export interface TiltReading {
	id: string;
	color: string;
	beer_name: string;
	original_gravity: number | null;
	sg: number;
	sg_raw: number;
	temp: number;
	temp_raw: number;
	rssi: number;
	last_seen: string;
	paired: boolean;
}

export interface AmbientReading {
	temperature: number | null;
	humidity: number | null;
	timestamp: string;
}

export interface HeaterState {
	state: 'on' | 'off' | null;
	entity_id: string | null;
	last_changed: string | null;
	available: boolean;
	loading: boolean;
}

// Shared reactive state using Svelte 5 $state rune
export const tiltsState = $state<{
	tilts: Map<string, TiltReading>;
	connected: boolean;
	ambient: AmbientReading | null;
	heater: HeaterState;
}>({
	tilts: new Map(),
	connected: false,
	ambient: null,
	heater: {
		state: null,
		entity_id: null,
		last_changed: null,
		available: false,
		loading: false
	}
});

let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

export function connectWebSocket() {
	if (ws?.readyState === WebSocket.OPEN) return;

	const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
	const wsUrl = `${protocol}//${window.location.host}/ws`;

	console.log('Connecting to WebSocket:', wsUrl);
	ws = new WebSocket(wsUrl);

	ws.onopen = () => {
		console.log('WebSocket connected');
		tiltsState.connected = true;
		if (reconnectTimer) {
			clearTimeout(reconnectTimer);
			reconnectTimer = null;
		}
	};

	ws.onmessage = (event) => {
		try {
			const data = JSON.parse(event.data);

			// Handle ambient readings
			if (data.type === 'ambient') {
				tiltsState.ambient = {
					temperature: data.temperature,
					humidity: data.humidity,
					timestamp: data.timestamp
				};
				return;
			}

			// Handle control events (heater on/off)
			if (data.type === 'control_event') {
				// Update heater state based on action
				if (data.action === 'heat_on') {
					tiltsState.heater.state = 'on';
					tiltsState.heater.last_changed = data.timestamp;
				} else if (data.action === 'heat_off') {
					tiltsState.heater.state = 'off';
					tiltsState.heater.last_changed = data.timestamp;
				}
				return;
			}

			// Handle tilt readings
			const reading: TiltReading = data;
			tiltsState.tilts.set(reading.id, reading);
			// Trigger reactivity by reassigning
			tiltsState.tilts = new Map(tiltsState.tilts);
		} catch (e) {
			console.error('Failed to parse WebSocket message:', e);
		}
	};

	ws.onclose = () => {
		console.log('WebSocket disconnected');
		tiltsState.connected = false;
		ws = null;
		// Reconnect after 3 seconds
		reconnectTimer = setTimeout(connectWebSocket, 3000);
	};

	ws.onerror = (error) => {
		console.error('WebSocket error:', error);
		ws?.close();
	};
}

export function disconnectWebSocket() {
	if (reconnectTimer) {
		clearTimeout(reconnectTimer);
		reconnectTimer = null;
	}
	ws?.close();
	ws = null;
}

// Heater state polling interval
let heaterPollTimer: ReturnType<typeof setInterval> | null = null;

export async function fetchHeaterState(): Promise<void> {
	try {
		tiltsState.heater.loading = true;
		const response = await fetch('/api/control/heater');
		if (response.ok) {
			const data = await response.json();
			tiltsState.heater.state = data.state;
			tiltsState.heater.entity_id = data.entity_id;
			tiltsState.heater.last_changed = data.last_changed;
			tiltsState.heater.available = data.available;
		}
	} catch (e) {
		console.error('Failed to fetch heater state:', e);
	} finally {
		tiltsState.heater.loading = false;
	}
}

export async function toggleHeater(state: 'on' | 'off'): Promise<boolean> {
	try {
		tiltsState.heater.loading = true;
		const response = await fetch('/api/control/heater', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ state })
		});
		if (response.ok) {
			const data = await response.json();
			if (data.success) {
				tiltsState.heater.state = data.new_state;
				tiltsState.heater.last_changed = new Date().toISOString();
				return true;
			}
		}
		return false;
	} catch (e) {
		console.error('Failed to toggle heater:', e);
		return false;
	} finally {
		tiltsState.heater.loading = false;
	}
}

export function startHeaterPolling(intervalMs: number = 30000): void {
	// Initial fetch
	fetchHeaterState();
	// Poll at interval
	if (heaterPollTimer) {
		clearInterval(heaterPollTimer);
	}
	heaterPollTimer = setInterval(fetchHeaterState, intervalMs);
}

export function stopHeaterPolling(): void {
	if (heaterPollTimer) {
		clearInterval(heaterPollTimer);
		heaterPollTimer = null;
	}
}

export async function updateTiltBeerName(tiltId: string, beerName: string): Promise<boolean> {
	try {
		const response = await fetch(`/api/tilts/${tiltId}`, {
			method: 'PUT',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ beer_name: beerName })
		});
		if (response.ok) {
			// Update local state immediately
			const existing = tiltsState.tilts.get(tiltId);
			if (existing) {
				existing.beer_name = beerName;
				tiltsState.tilts = new Map(tiltsState.tilts);
			}
			return true;
		}
	} catch (e) {
		console.error('Failed to update beer name:', e);
	}
	return false;
}

export async function updateTiltOriginalGravity(tiltId: string, og: number | null): Promise<boolean> {
	try {
		const response = await fetch(`/api/tilts/${tiltId}`, {
			method: 'PUT',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ original_gravity: og })
		});
		if (response.ok) {
			// Update local state immediately
			const existing = tiltsState.tilts.get(tiltId);
			if (existing) {
				existing.original_gravity = og;
				tiltsState.tilts = new Map(tiltsState.tilts);
			}
			return true;
		}
	} catch (e) {
		console.error('Failed to update original gravity:', e);
	}
	return false;
}
