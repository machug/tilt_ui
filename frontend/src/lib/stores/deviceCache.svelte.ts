import { fetchAllDevices, type DeviceResponse } from '$lib/api/devices';

interface CacheEntry {
	data: DeviceResponse[];
	timestamp: number;
}

const CACHE_DURATION = 5 * 60 * 1000; // 5 minutes

class DeviceCache {
	private cache = $state<CacheEntry | null>(null);

	async getDevices(forceRefresh = false): Promise<DeviceResponse[]> {
		const now = Date.now();

		if (!forceRefresh && this.cache && now - this.cache.timestamp < CACHE_DURATION) {
			return this.cache.data;
		}

		const devices = await fetchAllDevices();
		this.cache = {
			data: devices,
			timestamp: now
		};

		return devices;
	}

	invalidate() {
		this.cache = null;
	}

	getCachedDevices(): DeviceResponse[] | null {
		const now = Date.now();
		if (this.cache && now - this.cache.timestamp < CACHE_DURATION) {
			return this.cache.data;
		}
		return null;
	}
}

export const deviceCache = new DeviceCache();
