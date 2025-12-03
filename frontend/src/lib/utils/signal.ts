/**
 * Signal strength utility functions for RSSI-based diagnostics
 */

export interface SignalStrength {
	bars: number;
	color: string;
	label: string;
}

/**
 * Convert RSSI value to signal strength indicator
 * @param rssiValue - RSSI in dBm (typically -30 to -90)
 * @returns Signal strength with bars (1-4), color, and quality label
 */
export function getSignalStrength(rssiValue: number): SignalStrength {
	if (rssiValue >= -50) return { bars: 4, color: 'var(--positive)', label: 'Excellent' };
	if (rssiValue >= -60) return { bars: 3, color: 'var(--positive)', label: 'Good' };
	if (rssiValue >= -70) return { bars: 2, color: 'var(--warning)', label: 'Fair' };
	return { bars: 1, color: 'var(--negative)', label: 'Weak' };
}

/**
 * Convert ISO timestamp to human-readable relative time
 * @param isoString - ISO 8601 timestamp
 * @returns Human-readable time difference (e.g., "23s ago", "5m ago")
 */
export function timeSince(isoString: string): string {
	const seconds = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
	if (seconds < 10) return 'just now';
	if (seconds < 60) return `${seconds}s ago`;
	const minutes = Math.floor(seconds / 60);
	if (minutes < 60) return `${minutes}m ago`;
	const hours = Math.floor(minutes / 60);
	if (hours < 24) return `${hours}h ago`;
	const days = Math.floor(hours / 24);
	return `${days}d ago`;
}
