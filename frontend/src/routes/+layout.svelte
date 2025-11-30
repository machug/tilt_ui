<script lang="ts">
	import '../app.css';
	import { onMount, onDestroy } from 'svelte';
	import { slide } from 'svelte/transition';
	import { page } from '$app/stores';
	import { tiltsState, connectWebSocket, disconnectWebSocket, startHeaterPolling, stopHeaterPolling } from '$lib/stores/tilts.svelte';
	import { loadConfig, configState, getTempUnit } from '$lib/stores/config.svelte';
	import { weatherState, startWeatherPolling, stopWeatherPolling, getWeatherIcon, formatDayName } from '$lib/stores/weather.svelte';

	// Format ambient temp based on user's unit preference
	function formatAmbientTemp(tempC: number): string {
		if (configState.config.temp_units === 'F') {
			return ((tempC * 9) / 5 + 32).toFixed(1);
		}
		return tempC.toFixed(1);
	}

	// Format forecast temp
	function formatForecastTemp(temp: number | null): string {
		if (temp === null) return '--';
		return Math.round(temp).toString();
	}

	let { children } = $props();
	let mobileMenuOpen = $state(false);
	let weatherDropdownOpen = $state(false);

	// Derived: show heater indicator only when HA is enabled and heater entity is configured
	let showHeaterIndicator = $derived(
		configState.config.ha_enabled && configState.config.ha_heater_entity_id
	);

	// Get today's forecast
	let todayForecast = $derived(weatherState.forecast[0] || null);

	onMount(() => {
		loadConfig();
		// Connect WebSocket for live updates (persists across navigation)
		connectWebSocket();
		// Start polling heater state every 30 seconds
		startHeaterPolling(30000);
		// Start polling weather every 30 minutes
		startWeatherPolling(30 * 60 * 1000);
	});

	onDestroy(() => {
		disconnectWebSocket();
		stopHeaterPolling();
		stopWeatherPolling();
	});

	function toggleWeatherDropdown() {
		weatherDropdownOpen = !weatherDropdownOpen;
	}

	function closeWeatherDropdown() {
		weatherDropdownOpen = false;
	}

	const navLinks = [
		{ href: '/', label: 'Dashboard' },
		{ href: '/batches', label: 'Batches' },
		{ href: '/logging', label: 'Logging' },
		{ href: '/calibration', label: 'Calibration' },
		{ href: '/system', label: 'System' }
	];

	function isActive(href: string, pathname: string): boolean {
		if (href === '/') return pathname === '/';
		return pathname.startsWith(href);
	}

	function closeMobileMenu() {
		mobileMenuOpen = false;
	}
</script>

<svelte:head>
	<title>BrewSignal</title>
	<meta name="viewport" content="width=device-width, initial-scale=1" />
</svelte:head>

<div class="min-h-screen" style="background: var(--bg-deep);">
	<!-- Navigation -->
	<nav
		class="sticky top-0 z-50 backdrop-blur-md"
		style="background: rgba(15, 17, 21, 0.85); border-bottom: 1px solid var(--bg-hover);"
	>
		<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
			<div class="flex items-center justify-between h-16">
				<!-- Logo -->
				<a href="/" class="flex items-center gap-3 group">
					<div
						class="w-9 h-9 rounded-lg flex items-center justify-center transition-all group-hover:scale-105"
						style="background: var(--accent);"
					>
						<span class="text-lg">🍺</span>
					</div>
					<span class="text-lg font-semibold tracking-tight" style="color: var(--text-primary);">
						Brew<span style="color: var(--accent);">Signal</span>
					</span>
				</a>

				<!-- Desktop navigation -->
				<div class="hidden md:flex items-center gap-1">
					{#each navLinks as link}
						{@const active = isActive(link.href, $page.url.pathname)}
						<a
							href={link.href}
							class="nav-link {active ? 'active' : ''}"
						>
							{link.label}
						</a>
					{/each}
				</div>

				<!-- Right side: weather + ambient + heater indicator + connection status + mobile menu -->
				<div class="flex items-center gap-3">
					<!-- Weather indicator with dropdown -->
					{#if todayForecast}
						<div class="weather-indicator-wrapper">
							<button
								type="button"
								class="weather-indicator"
								onclick={toggleWeatherDropdown}
								aria-label="Toggle weather forecast"
								aria-expanded={weatherDropdownOpen}
							>
								<span class="text-sm">{getWeatherIcon(todayForecast.condition)}</span>
								<span class="text-xs font-medium font-mono" style="color: var(--text-secondary);">
									{formatForecastTemp(todayForecast.temperature)}°
								</span>
							</button>

							{#if weatherDropdownOpen}
								<!-- svelte-ignore a11y_no_static_element_interactions -->
								<!-- svelte-ignore a11y_click_events_have_key_events -->
								<div class="weather-backdrop" onclick={closeWeatherDropdown}></div>
								<div class="weather-dropdown" transition:slide={{ duration: 150 }}>
									<div class="weather-dropdown-header">
										<span>5-Day Forecast</span>
									</div>
									<div class="weather-dropdown-days">
										{#each weatherState.forecast.slice(0, 5) as day}
											<div class="weather-day">
												<span class="weather-day-name">{formatDayName(day.datetime)}</span>
												<span class="weather-day-icon">{getWeatherIcon(day.condition)}</span>
												<div class="weather-day-temps">
													<span class="weather-temp-high">{formatForecastTemp(day.temperature)}°</span>
													<span class="weather-temp-low">{formatForecastTemp(day.templow)}°</span>
												</div>
											</div>
										{/each}
									</div>
								</div>
							{/if}
						</div>
					{/if}

					<!-- Ambient temperature/humidity -->
					{#if tiltsState.ambient && (tiltsState.ambient.temperature !== null || tiltsState.ambient.humidity !== null)}
						<div
							class="hidden sm:flex items-center gap-3 px-3 py-1.5 rounded-full"
							style="background: var(--bg-elevated);"
						>
							{#if tiltsState.ambient.temperature !== null}
								<div class="flex items-center gap-1.5">
									<span class="text-sm opacity-60">🌡️</span>
									<span class="text-xs font-medium font-mono" style="color: var(--text-secondary);">
										{formatAmbientTemp(tiltsState.ambient.temperature)}{getTempUnit()}
									</span>
								</div>
							{/if}
							{#if tiltsState.ambient.humidity !== null}
								<div class="flex items-center gap-1.5">
									<span class="text-sm opacity-60">💧</span>
									<span class="text-xs font-medium font-mono" style="color: var(--text-secondary);">
										{tiltsState.ambient.humidity.toFixed(0)}%
									</span>
								</div>
							{/if}
						</div>
					{/if}

					<!-- Heater indicator -->
					{#if showHeaterIndicator && tiltsState.heater.available}
						<div
							class="flex items-center gap-2 px-3 py-1.5 rounded-full"
							style="background: {tiltsState.heater.state === 'on' ? 'rgba(239, 68, 68, 0.1)' : 'var(--bg-elevated)'};"
						>
							<span class="text-sm" style="opacity: {tiltsState.heater.state === 'on' ? 1 : 0.4};">🔥</span>
							<span
								class="text-xs font-medium uppercase tracking-wide hidden sm:inline"
								style="color: {tiltsState.heater.state === 'on' ? 'var(--negative)' : 'var(--text-muted)'};"
							>
								{tiltsState.heater.state === 'on' ? 'Heating' : 'Off'}
							</span>
						</div>
					{/if}

					<!-- Connection status -->
					<div
						class="flex items-center gap-2 px-3 py-1.5 rounded-full"
						style="background: var(--bg-elevated);"
					>
						<span
							class="w-2 h-2 rounded-full"
							style="background: {tiltsState.connected ? 'var(--positive)' : 'var(--text-muted)'};"
						></span>
						<span class="text-xs font-medium hidden sm:inline" style="color: var(--text-muted);">
							{tiltsState.connected ? 'Live' : 'Offline'}
						</span>
					</div>

					<!-- Mobile menu button -->
					<button
						type="button"
						class="md:hidden p-2 rounded-lg transition-colors"
						style="color: var(--text-secondary);"
						onclick={() => (mobileMenuOpen = !mobileMenuOpen)}
						aria-label="Toggle menu"
					>
						{#if mobileMenuOpen}
							<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
							</svg>
						{:else}
							<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h16" />
							</svg>
						{/if}
					</button>
				</div>
			</div>
		</div>

		<!-- Mobile menu -->
		{#if mobileMenuOpen}
			<div class="md:hidden" style="background: var(--bg-primary); border-top: 1px solid var(--bg-hover);" transition:slide={{ duration: 150 }}>
				<div class="px-3 py-3 space-y-1">
					{#each navLinks as link}
						{@const active = isActive(link.href, $page.url.pathname)}
						<a
							href={link.href}
							onclick={closeMobileMenu}
							class="block px-4 py-3 rounded-lg text-base font-medium transition-colors"
							style="color: {active ? 'var(--text-primary)' : 'var(--text-secondary)'}; background: {active ? 'var(--bg-elevated)' : 'transparent'};"
						>
							{link.label}
						</a>
					{/each}
				</div>
			</div>
		{/if}
	</nav>

	<!-- Main content -->
	<main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
		{@render children()}
	</main>
</div>

<style>
	.nav-link {
		position: relative;
		padding: 0.5rem 1rem;
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--text-secondary);
		background: transparent;
		border-radius: 0.375rem;
		transition: color var(--transition), background var(--transition);
	}

	.nav-link:hover {
		color: var(--text-primary);
	}

	.nav-link.active {
		color: var(--text-primary);
		background: var(--bg-elevated);
	}

	.nav-link.active::after {
		content: '';
		position: absolute;
		bottom: 0;
		left: 50%;
		transform: translateX(-50%);
		width: 1.5rem;
		height: 2px;
		background: var(--accent);
		border-radius: 1px;
	}

	/* Weather indicator */
	.weather-indicator-wrapper {
		position: relative;
	}

	.weather-indicator {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.375rem 0.75rem;
		background: var(--bg-elevated);
		border: none;
		border-radius: 9999px;
		cursor: pointer;
		transition: background var(--transition);
	}

	.weather-indicator:hover {
		background: var(--bg-hover);
	}

	.weather-backdrop {
		position: fixed;
		inset: 0;
		z-index: 40;
	}

	.weather-dropdown {
		position: absolute;
		top: calc(100% + 0.5rem);
		right: 0;
		z-index: 50;
		min-width: 16rem;
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.5rem;
		box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
		overflow: hidden;
	}

	.weather-dropdown-header {
		padding: 0.75rem 1rem;
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		border-bottom: 1px solid var(--border-subtle);
	}

	.weather-dropdown-days {
		padding: 0.5rem;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.weather-day {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.5rem 0.75rem;
		border-radius: 0.375rem;
		background: var(--bg-elevated);
	}

	.weather-day-name {
		flex: 0 0 4rem;
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-secondary);
	}

	.weather-day-icon {
		font-size: 1.25rem;
	}

	.weather-day-temps {
		margin-left: auto;
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.weather-temp-high {
		font-size: 0.875rem;
		font-weight: 500;
		font-family: var(--font-mono);
		color: var(--text-primary);
	}

	.weather-temp-low {
		font-size: 0.75rem;
		font-family: var(--font-mono);
		color: var(--text-muted);
	}
</style>
