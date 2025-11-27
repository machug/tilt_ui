// Svelte 5 runes-based store for app configuration

export interface AppConfig {
	temp_units: 'C' | 'F';
	sg_units: 'sg' | 'plato' | 'brix';
	local_logging_enabled: boolean;
	local_interval_minutes: number;
	min_rssi: number;
	smoothing_enabled: boolean;
	smoothing_samples: number;
	id_by_mac: boolean;
}

const DEFAULT_CONFIG: AppConfig = {
	temp_units: 'C',
	sg_units: 'sg',
	local_logging_enabled: true,
	local_interval_minutes: 15,
	min_rssi: -100,
	smoothing_enabled: false,
	smoothing_samples: 5,
	id_by_mac: false
};

export const configState = $state<{ config: AppConfig; loaded: boolean }>({
	config: DEFAULT_CONFIG,
	loaded: false
});

export async function loadConfig(): Promise<void> {
	try {
		const response = await fetch('/api/config');
		if (response.ok) {
			const data = await response.json();
			configState.config = { ...DEFAULT_CONFIG, ...data };
		}
	} catch (e) {
		console.error('Failed to load config:', e);
	} finally {
		configState.loaded = true;
	}
}

export async function updateConfig(updates: Partial<AppConfig>): Promise<boolean> {
	try {
		const response = await fetch('/api/config', {
			method: 'PATCH',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(updates)
		});
		if (response.ok) {
			const data = await response.json();
			configState.config = { ...DEFAULT_CONFIG, ...data };
			return true;
		}
	} catch (e) {
		console.error('Failed to update config:', e);
	}
	return false;
}

// Temperature conversion utilities
export function fahrenheitToCelsius(f: number): number {
	return (f - 32) * (5 / 9);
}

export function celsiusToFahrenheit(c: number): number {
	return c * (9 / 5) + 32;
}

export function formatTemp(tempF: number, units: 'C' | 'F' = configState.config.temp_units): string {
	if (units === 'C') {
		return fahrenheitToCelsius(tempF).toFixed(1);
	}
	return tempF.toFixed(1);
}

export function getTempUnit(): string {
	return configState.config.temp_units === 'C' ? '°C' : '°F';
}
