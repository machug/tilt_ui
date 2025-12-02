// Re-export fetchApi helper for convenience
const BASE_URL = '/api';

export async function fetchApi<T = any>(url: string, options?: RequestInit): Promise<T> {
	const response = await fetch(url.startsWith('/') ? url : `${BASE_URL}/${url}`, options);
	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: response.statusText }));
		throw new Error(error.detail || `Request failed: ${response.statusText}`);
	}
	return response.json();
}
