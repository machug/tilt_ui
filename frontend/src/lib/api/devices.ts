import { fetchApi } from './index';

export interface DeviceResponse {
	id: string;
	color: string;
	beer_name: string;
	paired: boolean;
	last_seen: string | null;
	mac: string | null;
}

export async function fetchAllDevices(pairedOnly: boolean = false): Promise<DeviceResponse[]> {
	const queryParam = pairedOnly ? '?paired_only=true' : '';
	return fetchApi(`/api/tilts${queryParam}`);
}

export async function pairDevice(deviceId: string): Promise<DeviceResponse> {
	return fetchApi(`/api/tilts/${deviceId}/pair`, {
		method: 'POST'
	});
}

export async function unpairDevice(deviceId: string): Promise<DeviceResponse> {
	return fetchApi(`/api/tilts/${deviceId}/unpair`, {
		method: 'POST'
	});
}
