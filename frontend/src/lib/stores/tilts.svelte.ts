// Svelte 5 runes-based store for Tilt readings

export interface TiltReading {
	id: string;
	color: string;
	beer_name: string;
	sg: number;
	sg_raw: number;
	temp: number;
	temp_raw: number;
	rssi: number;
	last_seen: string;
}

export interface AmbientReading {
	temperature: number | null;
	humidity: number | null;
	timestamp: string;
}

// Shared reactive state using Svelte 5 $state rune
export const tiltsState = $state<{
	tilts: Map<string, TiltReading>;
	connected: boolean;
	ambient: AmbientReading | null;
}>({
	tilts: new Map(),
	connected: false,
	ambient: null
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
