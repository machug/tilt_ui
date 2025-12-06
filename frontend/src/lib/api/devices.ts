import { fetchApi } from './index';

export interface DeviceResponse {
	id: string;
	device_type: string;
	name: string;
	display_name: string | null;
	beer_name: string | null;
	original_gravity: number | null;
	native_gravity_unit: string;
	native_temp_unit: string;
	calibration_type: string;
	calibration_data: Record<string, any> | null;
	auth_token: string | null;
	last_seen: string | null;
	battery_voltage: number | null;
	firmware_version: string | null;
	color: string | null;
	mac: string | null;
	created_at: string;
	paired: boolean;
	paired_at: string | null;
}

export async function fetchAllDevices(pairedOnly: boolean = false): Promise<DeviceResponse[]> {
	const queryParam = pairedOnly ? '?paired_only=true' : '';
	return fetchApi(`/api/devices${queryParam}`);
}

export async function pairDevice(deviceId: string): Promise<DeviceResponse> {
	// Use universal /api/devices endpoint for pairing (works for all device types)
	return fetchApi(`/api/devices/${deviceId}/pair`, {
		method: 'POST'
	});
}

export async function unpairDevice(deviceId: string): Promise<DeviceResponse> {
	// Use universal /api/devices endpoint for unpairing (works for all device types)
	return fetchApi(`/api/devices/${deviceId}/unpair`, {
		method: 'POST'
	});
}
