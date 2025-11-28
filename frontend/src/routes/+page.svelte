<script lang="ts">
	import { onMount } from 'svelte';
	import { tiltsState, connectWebSocket, disconnectWebSocket } from '$lib/stores/tilts.svelte';
	import { configState, formatTemp, getTempUnit } from '$lib/stores/config.svelte';
	import TiltCard from '$lib/components/TiltCard.svelte';

	// Weather/Alerts types
	interface WeatherForecast {
		datetime: string;
		condition: string;
		temperature: number | null;
		templow: number | null;
	}

	interface Alert {
		level: string;
		message: string;
		day: string;
	}

	interface AlertsResponse {
		forecast: WeatherForecast[];
		alerts: Alert[];
		weather_entity: string | null;
		alerts_enabled: boolean;
	}

	let alertsData = $state<AlertsResponse | null>(null);
	let alertsLoading = $state(false);
	let alertsDismissed = $state(false);
	let alertsCollapsed = $state(false);

	async function loadAlerts() {
		alertsLoading = true;
		try {
			const response = await fetch('/api/alerts');
			if (response.ok) {
				alertsData = await response.json();
			}
		} catch (e) {
			console.error('Failed to load alerts:', e);
		} finally {
			alertsLoading = false;
		}
	}

	onMount(() => {
		// Load alert dismissal state from localStorage
		const dismissed = localStorage.getItem('tiltui_alerts_dismissed');
		const dismissedTime = localStorage.getItem('tiltui_alerts_dismissed_time');
		if (dismissed === 'true' && dismissedTime) {
			const elapsed = Date.now() - parseInt(dismissedTime, 10);
			// Auto-restore alerts after 6 hours
			if (elapsed < 6 * 60 * 60 * 1000) {
				alertsDismissed = true;
			}
		}

		connectWebSocket();
		loadAlerts();
		// Refresh alerts every 30 minutes
		const interval = setInterval(loadAlerts, 30 * 60 * 1000);
		return () => {
			disconnectWebSocket();
			clearInterval(interval);
		};
	});

	let tiltsList = $derived(Array.from(tiltsState.tilts.values()));

	// Track which tilt card is expanded (only one at a time)
	let expandedTiltId = $state<string | null>(null);

	function toggleExpand(tiltId: string) {
		expandedTiltId = expandedTiltId === tiltId ? null : tiltId;
	}

	// Format ambient temp based on user's unit preference
	// Ambient temp from HA is typically in Celsius, convert if needed
	function formatAmbientTemp(tempC: number): string {
		if (configState.config.temp_units === 'F') {
			return ((tempC * 9) / 5 + 32).toFixed(1);
		}
		return tempC.toFixed(1);
	}

	// Format forecast temp (HA provides temps in Celsius)
	function formatForecastTemp(temp: number | null): string {
		if (temp === null) return '--';
		return Math.round(temp).toString();
	}

	// Get weather icon based on condition
	function getWeatherIcon(condition: string): string {
		const icons: Record<string, string> = {
			'sunny': '☀️',
			'clear-night': '🌙',
			'partlycloudy': '⛅',
			'cloudy': '☁️',
			'rainy': '🌧️',
			'pouring': '🌧️',
			'snowy': '❄️',
			'fog': '🌫️',
			'windy': '💨',
			'lightning': '⚡',
			'lightning-rainy': '⛈️',
			'hail': '🌨️',
		};
		return icons[condition] || '🌡️';
	}

	// Format day name from datetime
	function formatDayName(datetime: string): string {
		try {
			const date = new Date(datetime);
			const today = new Date();
			const tomorrow = new Date(today);
			tomorrow.setDate(tomorrow.getDate() + 1);

			if (date.toDateString() === today.toDateString()) return 'Today';
			if (date.toDateString() === tomorrow.toDateString()) return 'Tomorrow';
			return date.toLocaleDateString('en-US', { weekday: 'short' });
		} catch {
			return 'Day';
		}
	}

	function dismissAlerts() {
		alertsDismissed = true;
		localStorage.setItem('tiltui_alerts_dismissed', 'true');
		localStorage.setItem('tiltui_alerts_dismissed_time', Date.now().toString());
	}

	function toggleAlertsCollapse() {
		alertsCollapsed = !alertsCollapsed;
	}
</script>

<svelte:head>
	<title>Dashboard | Tilt UI</title>
</svelte:head>

<!-- Alerts Banner -->
{#if alertsData && alertsData.alerts.length > 0 && !alertsDismissed}
	<div class="alerts-banner">
		<div class="alerts-header">
			<div class="alerts-title">
				<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
				</svg>
				<span>Weather Alerts</span>
				<span class="alerts-count">{alertsData.alerts.length}</span>
			</div>
			<button type="button" class="dismiss-btn" onclick={dismissAlerts} aria-label="Dismiss alerts">
				<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
				</svg>
			</button>
		</div>
		{#if !alertsCollapsed}
			<div class="alerts-list">
				{#each alertsData.alerts as alert}
					<div class="alert-item" class:warning={alert.level === 'warning'} class:critical={alert.level === 'critical'}>
						<span class="alert-day">{alert.day}:</span>
						<span class="alert-message">{alert.message}</span>
					</div>
				{/each}
			</div>
		{/if}
		{#if alertsData.alerts.length > 3}
			<button type="button" class="show-more-btn" onclick={toggleAlertsCollapse}>
				{alertsCollapsed ? `Show ${alertsData.alerts.length} alerts` : 'Show less'}
			</button>
		{/if}
	</div>
{/if}

{#if tiltsList.length === 0}
	<div class="empty-state">
		<div class="empty-icon">
			<span class="text-5xl">🍺</span>
		</div>
		<h2 class="empty-title">No Tilts Detected</h2>
		<p class="empty-description">
			{#if tiltsState.connected}
				Waiting for Tilt hydrometers to broadcast...
			{:else}
				<span class="connecting-dots">Connecting to server</span>
			{/if}
		</p>
		{#if tiltsState.connected}
			<div class="empty-hint">
				<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z"
					/>
				</svg>
				<span>Make sure your Tilt is floating in liquid and within Bluetooth range</span>
			</div>
		{/if}
	</div>
{:else}
	<div class="tilt-grid">
		{#each tiltsList as tilt (tilt.id)}
			<TiltCard
				{tilt}
				expanded={expandedTiltId === tilt.id}
				onToggleExpand={() => toggleExpand(tilt.id)}
			/>
		{/each}
	</div>

	<!-- Ambient Temperature -->
	{#if tiltsState.ambient && (tiltsState.ambient.temperature !== null || tiltsState.ambient.humidity !== null)}
		<div class="ambient-card">
			<div class="ambient-header">
				<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z" />
				</svg>
				<span>Room Ambient</span>
			</div>
			<div class="ambient-values">
				{#if tiltsState.ambient.temperature !== null}
					<div class="ambient-value">
						<span class="value">{formatAmbientTemp(tiltsState.ambient.temperature)}</span>
						<span class="unit">{getTempUnit()}</span>
						<span class="label">Temp</span>
					</div>
				{/if}
				{#if tiltsState.ambient.humidity !== null}
					<div class="ambient-value">
						<span class="value">{tiltsState.ambient.humidity.toFixed(0)}</span>
						<span class="unit">%</span>
						<span class="label">Humidity</span>
					</div>
				{/if}
			</div>
		</div>
	{/if}

	<!-- Weather Forecast -->
	{#if alertsData && alertsData.forecast.length > 0}
		<div class="forecast-card">
			<div class="forecast-header">
				<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z" />
				</svg>
				<span>Weather Forecast</span>
			</div>
			<div class="forecast-days">
				{#each alertsData.forecast.slice(0, 5) as day}
					<div class="forecast-day">
						<span class="day-name">{formatDayName(day.datetime)}</span>
						<span class="day-icon">{getWeatherIcon(day.condition)}</span>
						<div class="day-temps">
							<span class="temp-high">{formatForecastTemp(day.temperature)}°</span>
							<span class="temp-low">{formatForecastTemp(day.templow)}°</span>
						</div>
					</div>
				{/each}
			</div>
		</div>
	{/if}
{/if}

<style>
	.tilt-grid {
		display: grid;
		grid-template-columns: repeat(1, 1fr);
		gap: 1.5rem;
	}

	@media (min-width: 768px) {
		.tilt-grid {
			grid-template-columns: repeat(2, 1fr);
		}
	}

	@media (min-width: 1024px) {
		.tilt-grid {
			grid-template-columns: repeat(3, 1fr);
		}
	}

	@media (min-width: 1280px) {
		.tilt-grid {
			grid-template-columns: repeat(4, 1fr);
		}
	}

	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		text-align: center;
		padding: 4rem 1.5rem;
		min-height: 50vh;
	}

	.empty-icon {
		width: 5rem;
		height: 5rem;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 1rem;
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		margin-bottom: 1.5rem;
		animation: float 3s ease-in-out infinite;
	}

	@keyframes float {
		0%,
		100% {
			transform: translateY(0);
		}
		50% {
			transform: translateY(-8px);
		}
	}

	.empty-title {
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--text-primary);
		margin-bottom: 0.5rem;
	}

	.empty-description {
		color: var(--text-muted);
		font-size: 0.875rem;
		margin-bottom: 1.5rem;
	}

	.connecting-dots::after {
		content: '';
		animation: dots 1.5s steps(4, end) infinite;
	}

	@keyframes dots {
		0%,
		20% {
			content: '';
		}
		40% {
			content: '.';
		}
		60% {
			content: '..';
		}
		80%,
		100% {
			content: '...';
		}
	}

	.empty-hint {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.75rem 1rem;
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.375rem;
		color: var(--text-muted);
		font-size: 0.75rem;
		max-width: 24rem;
	}

	.empty-hint svg {
		flex-shrink: 0;
		color: var(--text-secondary);
	}

	/* Ambient Card */
	.ambient-card {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.375rem;
		padding: 1rem 1.25rem;
		margin-top: 1.5rem;
	}

	.ambient-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin-bottom: 0.75rem;
	}

	.ambient-header svg {
		width: 1rem;
		height: 1rem;
		color: var(--text-secondary);
	}

	.ambient-values {
		display: flex;
		gap: 2rem;
	}

	.ambient-value {
		display: flex;
		align-items: baseline;
		gap: 0.25rem;
	}

	.ambient-value .value {
		font-size: 1.5rem;
		font-weight: 500;
		font-family: var(--font-mono);
		color: var(--text-primary);
	}

	.ambient-value .unit {
		font-size: 0.875rem;
		color: var(--text-secondary);
	}

	.ambient-value .label {
		font-size: 0.625rem;
		color: var(--text-muted);
		text-transform: uppercase;
		margin-left: 0.5rem;
	}

	/* Alerts Banner */
	.alerts-banner {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-left: 3px solid var(--warning);
		border-radius: 0.375rem;
		padding: 1rem 1.25rem;
		margin-bottom: 1.5rem;
	}

	.alerts-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 0.75rem;
	}

	.alerts-title {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--text-primary);
	}

	.alerts-title svg {
		width: 1.25rem;
		height: 1.25rem;
		color: var(--warning);
	}

	.alerts-count {
		background: var(--warning);
		color: var(--gray-950);
		font-size: 0.625rem;
		font-weight: 700;
		padding: 0.125rem 0.375rem;
		border-radius: 9999px;
		margin-left: 0.5rem;
	}

	.dismiss-btn {
		padding: 0.25rem;
		background: transparent;
		border: none;
		color: var(--text-muted);
		cursor: pointer;
		border-radius: 0.25rem;
	}

	.dismiss-btn:hover {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.dismiss-btn svg {
		width: 1rem;
		height: 1rem;
	}

	.alerts-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.alert-item {
		font-size: 0.8125rem;
		color: var(--text-secondary);
		padding-left: 0.5rem;
		border-left: 2px solid var(--gray-700);
	}

	.alert-item.warning {
		border-left-color: var(--warning);
	}

	.alert-item.critical {
		border-left-color: var(--negative);
	}

	.alert-day {
		font-weight: 600;
		color: var(--text-primary);
		margin-right: 0.25rem;
	}

	.show-more-btn {
		font-size: 0.75rem;
		color: var(--accent);
		background: none;
		border: none;
		padding: 0.25rem 0.5rem;
		cursor: pointer;
		margin-top: 0.25rem;
	}

	.show-more-btn:hover {
		text-decoration: underline;
	}

	/* Weather Forecast */
	.forecast-card {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.375rem;
		padding: 1rem 1.25rem;
		margin-top: 1.5rem;
	}

	.forecast-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin-bottom: 1rem;
	}

	.forecast-header svg {
		width: 1rem;
		height: 1rem;
		color: var(--text-secondary);
	}

	.forecast-days {
		display: flex;
		gap: 1rem;
		overflow-x: auto;
	}

	.forecast-day {
		flex: 0 0 auto;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.5rem;
		padding: 0.75rem;
		min-width: 4.5rem;
		background: var(--bg-elevated);
		border-radius: 0.375rem;
	}

	.day-name {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-secondary);
	}

	.day-icon {
		font-size: 1.5rem;
	}

	.day-temps {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.125rem;
	}

	.temp-high {
		font-size: 0.875rem;
		font-weight: 500;
		font-family: var(--font-mono);
		color: var(--text-primary);
	}

	.temp-low {
		font-size: 0.75rem;
		font-family: var(--font-mono);
		color: var(--text-muted);
	}
</style>
