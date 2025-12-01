<script lang="ts">
	import { onMount } from 'svelte';
	import { configState, updateConfig, fahrenheitToCelsius, celsiusToFahrenheit } from '$lib/stores/config.svelte';

	interface SystemInfo {
		hostname: string;
		ip_addresses: string[];
		uptime_seconds: number | null;
		version: string;
	}

	interface StorageStats {
		total_readings: number;
		oldest_reading: string | null;
		newest_reading: string | null;
		estimated_size_bytes: number;
	}

	let systemInfo = $state<SystemInfo | null>(null);
	let storageStats = $state<StorageStats | null>(null);
	let timezones = $state<string[]>([]);
	let currentTimezone = $state('');
	let loading = $state(true);
	let actionInProgress = $state<string | null>(null);

	// Config form state
	let tempUnits = $state<'C' | 'F'>('C');
	let sgUnits = $state<'sg' | 'plato' | 'brix'>('sg');
	let minRssi = $state(-100);
	let smoothingEnabled = $state(false);
	let smoothingSamples = $state(5);
	let idByMac = $state(false);
	let configSaving = $state(false);
	let configError = $state<string | null>(null);
	let configSuccess = $state(false);

	// Cleanup state
	let cleanupRetentionDays = $state(30);
	let cleanupPreview = $state<{ readings_to_delete: number } | null>(null);

	// Home Assistant state
	let haEnabled = $state(false);
	let haUrl = $state('');
	let haToken = $state('');
	let haAmbientTempEntityId = $state('');
	let haAmbientHumidityEntityId = $state('');
	let haWeatherEntityId = $state('');
	let haTesting = $state(false);
	let haTestResult = $state<{ success: boolean; message: string } | null>(null);
	let haStatus = $state<{ enabled: boolean; connected: boolean; url: string } | null>(null);
	let haSaving = $state(false);
	let haError = $state<string | null>(null);
	let haSuccess = $state(false);

	// Temperature Control state
	let tempControlEnabled = $state(false);
	let tempTarget = $state(68.0);
	let tempHysteresis = $state(1.0);
	let controlSaving = $state(false);
	let controlError = $state<string | null>(null);
	let controlSuccess = $state(false);

	// Weather Alerts state
	let weatherAlertsEnabled = $state(false);
	let alertTempThreshold = $state(3.0);
	let alertsSaving = $state(false);
	let alertsError = $state<string | null>(null);
	let alertsSuccess = $state(false);

	// Derived unit helpers
	let useCelsius = $derived(configState.config.temp_units === 'C');
	let tempUnitSymbol = $derived(useCelsius ? '°C' : '°F');

	// Convert temperature from display units to Fahrenheit for storage
	function toFahrenheit(temp: number): number {
		if (useCelsius) {
			return celsiusToFahrenheit(temp);
		}
		return temp;
	}

	// Convert temperature from Fahrenheit to display units
	function fromFahrenheit(tempF: number): number {
		if (useCelsius) {
			return fahrenheitToCelsius(tempF);
		}
		return tempF;
	}

	async function loadSystemInfo() {
		try {
			const response = await fetch('/api/system/info');
			if (response.ok) {
				systemInfo = await response.json();
			}
		} catch (e) {
			console.error('Failed to load system info:', e);
		}
	}

	async function loadStorageStats() {
		try {
			const response = await fetch('/api/system/storage');
			if (response.ok) {
				storageStats = await response.json();
			}
		} catch (e) {
			console.error('Failed to load storage stats:', e);
		}
	}

	async function loadTimezones() {
		try {
			const [tzListRes, tzCurrentRes] = await Promise.all([
				fetch('/api/system/timezones'),
				fetch('/api/system/timezone')
			]);
			if (tzListRes.ok) {
				const data = await tzListRes.json();
				timezones = data.timezones || [];
			}
			if (tzCurrentRes.ok) {
				const data = await tzCurrentRes.json();
				currentTimezone = data.timezone || 'UTC';
			}
		} catch (e) {
			console.error('Failed to load timezones:', e);
		}
	}

	function syncConfigFromStore() {
		tempUnits = configState.config.temp_units;
		sgUnits = configState.config.sg_units;
		minRssi = configState.config.min_rssi;
		smoothingEnabled = configState.config.smoothing_enabled;
		smoothingSamples = configState.config.smoothing_samples;
		idByMac = configState.config.id_by_mac;
		// Home Assistant
		haEnabled = configState.config.ha_enabled;
		haUrl = configState.config.ha_url;
		haToken = configState.config.ha_token;
		haAmbientTempEntityId = configState.config.ha_ambient_temp_entity_id;
		haAmbientHumidityEntityId = configState.config.ha_ambient_humidity_entity_id;
		haWeatherEntityId = configState.config.ha_weather_entity_id;
		// Temperature Control - convert from Fahrenheit to display units
		tempControlEnabled = configState.config.temp_control_enabled;
		tempTarget = Math.round(fromFahrenheit(configState.config.temp_target) * 2) / 2; // Round to nearest 0.5
		// Hysteresis: convert delta (°F delta to °C delta uses same ratio), round to 2 decimal places
		tempHysteresis = configState.config.temp_units === 'C'
			? Math.round(configState.config.temp_hysteresis * (5 / 9) * 100) / 100
			: configState.config.temp_hysteresis;
		// Weather Alerts
		weatherAlertsEnabled = configState.config.weather_alerts_enabled;
		alertTempThreshold = configState.config.alert_temp_threshold;
	}

	async function saveConfig() {
		configSaving = true;
		configError = null;
		configSuccess = false;
		try {
			const result = await updateConfig({
				temp_units: tempUnits,
				sg_units: sgUnits,
				min_rssi: minRssi,
				smoothing_enabled: smoothingEnabled,
				smoothing_samples: smoothingSamples,
				id_by_mac: idByMac
			});
			if (result.success) {
				configSuccess = true;
				setTimeout(() => (configSuccess = false), 3000);
			} else {
				configError = result.error || 'Failed to save settings';
			}
		} finally {
			configSaving = false;
		}
	}

	async function saveHAConfig() {
		haSaving = true;
		haError = null;
		haSuccess = false;
		try {
			const result = await updateConfig({
				ha_enabled: haEnabled,
				ha_url: haUrl,
				ha_token: haToken,
				ha_ambient_temp_entity_id: haAmbientTempEntityId,
				ha_ambient_humidity_entity_id: haAmbientHumidityEntityId,
				ha_weather_entity_id: haWeatherEntityId
			});
			if (result.success) {
				haSuccess = true;
				setTimeout(() => (haSuccess = false), 3000);
				// Reload HA status after saving
				await loadHAStatus();
			} else {
				haError = result.error || 'Failed to save settings';
			}
		} finally {
			haSaving = false;
		}
	}

	async function saveControlConfig() {
		controlSaving = true;
		controlError = null;
		controlSuccess = false;
		try {
			// Convert from display units back to Fahrenheit for storage
			const targetF = toFahrenheit(tempTarget);
			// Hysteresis delta: convert from display units to Fahrenheit
			const hysteresisF = useCelsius ? tempHysteresis * (9 / 5) : tempHysteresis;

			const result = await updateConfig({
				temp_control_enabled: tempControlEnabled,
				temp_target: targetF,
				temp_hysteresis: hysteresisF
			});
			if (result.success) {
				controlSuccess = true;
				setTimeout(() => (controlSuccess = false), 3000);
			} else {
				controlError = result.error || 'Failed to save settings';
			}
		} finally {
			controlSaving = false;
		}
	}

	async function saveAlertsConfig() {
		alertsSaving = true;
		alertsError = null;
		alertsSuccess = false;
		try {
			const result = await updateConfig({
				weather_alerts_enabled: weatherAlertsEnabled,
				alert_temp_threshold: alertTempThreshold
			});
			if (result.success) {
				alertsSuccess = true;
				setTimeout(() => (alertsSuccess = false), 3000);
			} else {
				alertsError = result.error || 'Failed to save settings';
			}
		} finally {
			alertsSaving = false;
		}
	}

	async function setTimezone(tz: string) {
		actionInProgress = 'timezone';
		try {
			const response = await fetch('/api/system/timezone', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ timezone: tz })
			});
			if (response.ok) {
				currentTimezone = tz;
			}
		} catch (e) {
			console.error('Failed to set timezone:', e);
		} finally {
			actionInProgress = null;
		}
	}

	async function previewCleanup() {
		actionInProgress = 'cleanup-preview';
		try {
			const response = await fetch('/api/system/cleanup', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ retention_days: cleanupRetentionDays, confirm: false })
			});
			if (response.ok) {
				cleanupPreview = await response.json();
			}
		} catch (e) {
			console.error('Failed to preview cleanup:', e);
		} finally {
			actionInProgress = null;
		}
	}

	async function executeCleanup() {
		if (!cleanupPreview || cleanupPreview.readings_to_delete === 0) return;

		if (!confirm(`Delete ${cleanupPreview.readings_to_delete.toLocaleString()} readings older than ${cleanupRetentionDays} days?`)) {
			return;
		}

		actionInProgress = 'cleanup';
		try {
			const response = await fetch('/api/system/cleanup', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ retention_days: cleanupRetentionDays, confirm: true })
			});
			if (response.ok) {
				cleanupPreview = null;
				await loadStorageStats();
			}
		} catch (e) {
			console.error('Failed to execute cleanup:', e);
		} finally {
			actionInProgress = null;
		}
	}

	async function rebootSystem() {
		if (!confirm('Are you sure you want to reboot the system? The UI will be unavailable until restart completes.')) {
			return;
		}
		actionInProgress = 'reboot';
		try {
			await fetch('/api/system/reboot', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ confirm: true })
			});
		} catch (e) {
			console.error('Reboot command failed:', e);
		} finally {
			actionInProgress = null;
		}
	}

	async function shutdownSystem() {
		if (!confirm('Are you sure you want to shut down the system? You will need physical access to restart.')) {
			return;
		}
		actionInProgress = 'shutdown';
		try {
			await fetch('/api/system/shutdown', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ confirm: true })
			});
		} catch (e) {
			console.error('Shutdown command failed:', e);
		} finally {
			actionInProgress = null;
		}
	}

	function formatUptime(seconds: number | null): string {
		if (!seconds) return 'Unknown';
		const days = Math.floor(seconds / 86400);
		const hours = Math.floor((seconds % 86400) / 3600);
		const minutes = Math.floor((seconds % 3600) / 60);

		const parts = [];
		if (days > 0) parts.push(`${days}d`);
		if (hours > 0) parts.push(`${hours}h`);
		if (minutes > 0) parts.push(`${minutes}m`);
		return parts.length > 0 ? parts.join(' ') : '< 1m';
	}

	function formatBytes(bytes: number): string {
		if (!Number.isFinite(bytes) || bytes < 0) return '0 B';
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}

	function formatNumber(n: number): string {
		return n.toLocaleString();
	}

	async function testHAConnection() {
		haTesting = true;
		haTestResult = null;
		try {
			const response = await fetch('/api/ha/test', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ url: haUrl, token: haToken })
			});
			if (response.ok) {
				haTestResult = await response.json();
			} else {
				haTestResult = { success: false, message: 'Request failed' };
			}
		} catch (e) {
			haTestResult = { success: false, message: 'Network error' };
		} finally {
			haTesting = false;
		}
	}

	async function loadHAStatus() {
		try {
			const response = await fetch('/api/ha/status');
			if (response.ok) {
				haStatus = await response.json();
			}
		} catch (e) {
			console.error('Failed to load HA status:', e);
		}
	}

	onMount(async () => {
		await Promise.all([
			loadSystemInfo(),
			loadStorageStats(),
			loadTimezones(),
			loadHAStatus()
		]);
		syncConfigFromStore();
		loading = false;
	});

	// Sync config when loaded
	$effect(() => {
		if (configState.loaded) {
			syncConfigFromStore();
		}
	});
</script>

<svelte:head>
	<title>System | BrewSignal</title>
</svelte:head>

<div class="page-container">
	<div class="page-header">
		<h1 class="page-title">System</h1>
		<p class="page-description">System settings, timezone configuration, and power controls</p>
	</div>

	{#if loading}
		<div class="loading-state">
			<div class="loading-spinner"></div>
			<span>Loading system information...</span>
		</div>
	{:else}
		<div class="grid gap-6">
			<!-- System Info Card -->
			<div class="card">
				<div class="card-header">
					<h2 class="card-title">System Information</h2>
				</div>
				<div class="card-body">
					{#if systemInfo}
						<div class="info-grid">
							<div class="info-item">
								<span class="info-label">Hostname</span>
								<span class="info-value font-mono">{systemInfo.hostname}</span>
							</div>
							<div class="info-item">
								<span class="info-label">Version</span>
								<span class="info-value font-mono">v{systemInfo.version}</span>
							</div>
							<div class="info-item">
								<span class="info-label">Uptime</span>
								<span class="info-value font-mono">{formatUptime(systemInfo.uptime_seconds)}</span>
							</div>
							<div class="info-item">
								<span class="info-label">IP Address</span>
								<span class="info-value font-mono">
									{systemInfo.ip_addresses.length > 0 ? systemInfo.ip_addresses[0] : 'Unknown'}
								</span>
							</div>
						</div>
					{:else}
						<p class="text-muted">Unable to load system information</p>
					{/if}
				</div>
			</div>

			<div class="grid gap-6 md:grid-cols-2">
				<!-- Application Settings -->
				<div class="card">
					<div class="card-header">
						<h2 class="card-title">Application Settings</h2>
					</div>
					<div class="card-body">
						<!-- Temperature Units -->
						<div class="setting-row">
							<div class="setting-info">
								<span class="setting-label">Temperature Units</span>
								<span class="setting-description">Display temperature in Celsius or Fahrenheit</span>
							</div>
							<div class="unit-toggle">
								<button
									type="button"
									class="unit-btn"
									class:active={tempUnits === 'C'}
									onclick={() => (tempUnits = 'C')}
								>°C</button>
								<button
									type="button"
									class="unit-btn"
									class:active={tempUnits === 'F'}
									onclick={() => (tempUnits = 'F')}
								>°F</button>
							</div>
						</div>

						<!-- Gravity Units -->
						<div class="setting-row">
							<div class="setting-info">
								<span class="setting-label">Gravity Units</span>
								<span class="setting-description">Display gravity as SG, Plato, or Brix</span>
							</div>
							<div class="unit-toggle">
								<button
									type="button"
									class="unit-btn"
									class:active={sgUnits === 'sg'}
									onclick={() => (sgUnits = 'sg')}
								>SG</button>
								<button
									type="button"
									class="unit-btn"
									class:active={sgUnits === 'plato'}
									onclick={() => (sgUnits = 'plato')}
								>°P</button>
								<button
									type="button"
									class="unit-btn"
									class:active={sgUnits === 'brix'}
									onclick={() => (sgUnits = 'brix')}
								>°Bx</button>
							</div>
						</div>

						<!-- Minimum RSSI -->
						<div class="setting-row">
							<div class="setting-info">
								<span class="setting-label">Minimum RSSI</span>
								<span class="setting-description">Ignore readings below this signal strength</span>
							</div>
							<div class="rssi-input">
								<input
									type="number"
									min="-100"
									max="0"
									bind:value={minRssi}
									class="input-field-sm"
								/>
								<span class="input-suffix">dBm</span>
							</div>
						</div>

						<!-- Smoothing -->
						<div class="setting-row">
							<div class="setting-info">
								<span class="setting-label">Reading Smoothing</span>
								<span class="setting-description">Average multiple readings to reduce noise</span>
							</div>
							<button
								type="button"
								class="toggle"
								class:active={smoothingEnabled}
								onclick={() => (smoothingEnabled = !smoothingEnabled)}
								aria-pressed={smoothingEnabled}
								aria-label="Toggle reading smoothing"
							>
								<span class="toggle-slider"></span>
							</button>
						</div>

						{#if smoothingEnabled}
							<div class="setting-row sub-setting">
								<div class="setting-info">
									<span class="setting-label">Smoothing Samples</span>
									<span class="setting-description">Number of readings to average</span>
								</div>
								<select bind:value={smoothingSamples} class="select-input-sm">
									<option value={3}>3</option>
									<option value={5}>5</option>
									<option value={10}>10</option>
									<option value={15}>15</option>
									<option value={20}>20</option>
								</select>
							</div>
						{/if}

						<!-- ID by MAC -->
						<div class="setting-row">
							<div class="setting-info">
								<span class="setting-label">Identify by MAC</span>
								<span class="setting-description">Use MAC address instead of broadcast ID</span>
							</div>
							<button
								type="button"
								class="toggle"
								class:active={idByMac}
								onclick={() => (idByMac = !idByMac)}
								aria-pressed={idByMac}
								aria-label="Toggle identify by MAC address"
							>
								<span class="toggle-slider"></span>
							</button>
						</div>

						<!-- Save Button & Feedback -->
						<div class="mt-4 config-actions">
							<button
								type="button"
								class="btn-primary"
								onclick={saveConfig}
								disabled={configSaving}
							>
								{#if configSaving}
									<span class="loading-dot"></span>
									Saving...
								{:else}
									Save Settings
								{/if}
							</button>
							{#if configError}
								<p class="config-error">{configError}</p>
							{/if}
							{#if configSuccess}
								<p class="config-success">Settings saved</p>
							{/if}
						</div>
					</div>
				</div>

				<!-- Timezone Settings -->
				<div class="card">
					<div class="card-header">
						<h2 class="card-title">Timezone</h2>
					</div>
					<div class="card-body">
						<p class="section-description">
							Current timezone: <span class="font-mono text-[var(--accent)]">{currentTimezone}</span>
						</p>
						<div class="timezone-selector">
							<select
								class="select-input"
								value={currentTimezone}
								onchange={(e) => setTimezone(e.currentTarget.value)}
								disabled={actionInProgress === 'timezone'}
							>
								{#each timezones as tz}
									<option value={tz}>{tz}</option>
								{/each}
							</select>
							{#if actionInProgress === 'timezone'}
								<div class="loading-spinner-small"></div>
							{/if}
						</div>
					</div>
				</div>
			</div>

			<!-- Home Assistant Integration -->
			<div class="card">
				<div class="card-header">
					<h2 class="card-title">Home Assistant</h2>
				</div>
				<div class="card-body">
					<!-- Enable/Disable -->
					<div class="setting-row">
						<div class="setting-info">
							<span class="setting-label">Enable Integration</span>
							<span class="setting-description">Connect to Home Assistant for ambient temp and control</span>
						</div>
						<button
							type="button"
							class="toggle"
							class:active={haEnabled}
							onclick={() => (haEnabled = !haEnabled)}
							aria-pressed={haEnabled}
							aria-label="Enable Home Assistant integration"
						>
							<span class="toggle-slider"></span>
						</button>
					</div>

					{#if haEnabled}
						<!-- Connection Status -->
						{#if haStatus}
							<div class="setting-row">
								<div class="setting-info">
									<span class="setting-label">Connection Status</span>
								</div>
								<span class="status-badge" class:connected={haStatus.connected}>
									{haStatus.connected ? 'Connected' : 'Disconnected'}
								</span>
							</div>
						{/if}

						<!-- HA URL -->
						<div class="setting-row">
							<div class="setting-info">
								<span class="setting-label">Home Assistant URL</span>
								<span class="setting-description">e.g., http://192.168.1.100:8123</span>
							</div>
							<input
								type="url"
								bind:value={haUrl}
								placeholder="http://homeassistant.local:8123"
								class="input-field"
							/>
						</div>

						<!-- HA Token -->
						<div class="setting-row">
							<div class="setting-info">
								<span class="setting-label">Access Token</span>
								<span class="setting-description">Long-lived access token from HA profile</span>
							</div>
							<input
								type="password"
								bind:value={haToken}
								placeholder="Enter token..."
								class="input-field"
							/>
						</div>

						<!-- Test Connection -->
						<div class="setting-row">
							<div class="setting-info">
								<span class="setting-label">Test Connection</span>
							</div>
							<div class="test-connection">
								<button
									type="button"
									class="btn-secondary-sm"
									onclick={testHAConnection}
									disabled={haTesting || !haUrl || !haToken}
								>
									{haTesting ? 'Testing...' : 'Test'}
								</button>
								{#if haTestResult}
									<span class="test-result" class:success={haTestResult.success}>
										{haTestResult.message}
									</span>
								{/if}
							</div>
						</div>

						<!-- Ambient Temp Entity -->
						<div class="setting-row">
							<div class="setting-info">
								<span class="setting-label">Ambient Temp Entity</span>
								<span class="setting-description">e.g., sensor.fermenter_room_temperature</span>
							</div>
							<input
								type="text"
								bind:value={haAmbientTempEntityId}
								placeholder="sensor.xxx_temperature"
								class="input-field"
							/>
						</div>

						<!-- Ambient Humidity Entity -->
						<div class="setting-row">
							<div class="setting-info">
								<span class="setting-label">Ambient Humidity Entity</span>
								<span class="setting-description">Optional humidity sensor</span>
							</div>
							<input
								type="text"
								bind:value={haAmbientHumidityEntityId}
								placeholder="sensor.xxx_humidity"
								class="input-field"
							/>
						</div>

						<!-- Weather Entity -->
						<div class="setting-row">
							<div class="setting-info">
								<span class="setting-label">Weather Entity</span>
								<span class="setting-description">For forecast display, e.g., weather.home</span>
							</div>
							<input
								type="text"
								bind:value={haWeatherEntityId}
								placeholder="weather.home"
								class="input-field"
							/>
						</div>

						<!-- Save Button & Feedback -->
						<div class="mt-4 config-actions">
							<button
								type="button"
								class="btn-primary"
								onclick={saveHAConfig}
								disabled={haSaving}
							>
								{#if haSaving}
									<span class="loading-dot"></span>
									Saving...
								{:else}
									Save HA Settings
								{/if}
							</button>
							{#if haError}
								<p class="config-error">{haError}</p>
							{/if}
							{#if haSuccess}
								<p class="config-success">Settings saved</p>
							{/if}
						</div>
					{/if}
				</div>
			</div>

			<!-- Temperature Control -->
			{#if haEnabled}
				<div class="card">
					<div class="card-header">
						<h2 class="card-title">Temperature Control</h2>
					</div>
					<div class="card-body">
						<!-- Enable/Disable Control -->
						<div class="setting-row">
							<div class="setting-info">
								<span class="setting-label">Enable Temperature Control</span>
								<span class="setting-description">Automatically control heaters for batches</span>
							</div>
							<button
								type="button"
								class="toggle"
								class:active={tempControlEnabled}
								onclick={() => (tempControlEnabled = !tempControlEnabled)}
								aria-pressed={tempControlEnabled}
								aria-label="Toggle temperature control"
							>
								<span class="toggle-slider"></span>
							</button>
						</div>

						{#if tempControlEnabled}
							<p class="section-note">
								Configure heater switches per batch. These are the default settings used when a batch doesn't specify its own.
							</p>

							<!-- Default Target Temperature -->
							<div class="setting-row">
								<div class="setting-info">
									<span class="setting-label">Default Target Temperature</span>
									<span class="setting-description">Desired fermentation temperature ({tempUnitSymbol})</span>
								</div>
								<div class="input-with-unit">
									<input
										type="number"
										bind:value={tempTarget}
										min={useCelsius ? 0 : 32}
										max={useCelsius ? 38 : 100}
										step="0.5"
										class="input-field input-number"
									/>
									<span class="unit">{tempUnitSymbol}</span>
								</div>
							</div>

							<!-- Default Hysteresis -->
							<div class="setting-row">
								<div class="setting-info">
									<span class="setting-label">Default Hysteresis</span>
									<span class="setting-description">± tolerance before triggering ({tempUnitSymbol})</span>
								</div>
								<div class="input-with-unit">
									<input
										type="number"
										bind:value={tempHysteresis}
										min={useCelsius ? 0.3 : 0.5}
										max={useCelsius ? 5.5 : 10}
										step={useCelsius ? 0.25 : 0.5}
										class="input-field input-number"
									/>
									<span class="unit">{tempUnitSymbol}</span>
								</div>
							</div>

							<!-- Save Button -->
							<div class="mt-4 config-actions">
								<button
									type="button"
									class="btn-primary"
									onclick={saveControlConfig}
									disabled={controlSaving}
								>
									{#if controlSaving}
										<span class="loading-dot"></span>
										Saving...
									{:else}
										Save Control Settings
									{/if}
								</button>
								{#if controlError}
									<p class="config-error">{controlError}</p>
								{/if}
								{#if controlSuccess}
									<p class="config-success">Settings saved</p>
								{/if}
							</div>
						{/if}
					</div>
				</div>
			{/if}

			<!-- Weather Alerts -->
			{#if haEnabled && haWeatherEntityId}
				<div class="card">
					<div class="card-header">
						<h2 class="card-title">Weather Alerts</h2>
					</div>
					<div class="card-body">
						<!-- Enable Alerts -->
						<div class="setting-row">
							<div class="setting-info">
								<span class="setting-label">Enable Weather Alerts</span>
								<span class="setting-description">Get alerts when forecast temps may affect fermentation</span>
							</div>
							<button
								type="button"
								class="toggle"
								class:active={weatherAlertsEnabled}
								onclick={() => (weatherAlertsEnabled = !weatherAlertsEnabled)}
								aria-pressed={weatherAlertsEnabled}
								aria-label="Toggle weather alerts"
							>
								<span class="toggle-slider"></span>
							</button>
						</div>

						{#if weatherAlertsEnabled}
							<!-- Alert Threshold -->
							<div class="setting-row">
								<div class="setting-info">
									<span class="setting-label">Alert Threshold</span>
									<span class="setting-description">Alert when forecast differs from target by this amount (°C)</span>
								</div>
								<div class="input-with-unit">
									<input
										type="number"
										min="1"
										max="15"
										step="0.5"
										bind:value={alertTempThreshold}
										class="input-field-sm"
									/>
									<span class="unit">°C</span>
								</div>
							</div>

							<p class="setting-hint mt-2">
								Alerts are generated when the forecast high or low temperatures differ from your target fermentation temperature by more than the threshold.
							</p>
						{/if}

						<!-- Save Button -->
						<div class="mt-4 config-actions">
							<button
								type="button"
								class="btn-primary"
								onclick={saveAlertsConfig}
								disabled={alertsSaving}
							>
								{#if alertsSaving}
									<span class="loading-dot"></span>
									Saving...
								{:else}
									Save Alert Settings
								{/if}
							</button>
							{#if alertsError}
								<p class="config-error">{alertsError}</p>
							{/if}
							{#if alertsSuccess}
								<p class="config-success">Settings saved</p>
							{/if}
						</div>
					</div>
				</div>
			{/if}

			<!-- Storage & Cleanup -->
			<div class="card">
				<div class="card-header">
					<h2 class="card-title">Storage & Data Cleanup</h2>
				</div>
				<div class="card-body">
					<div class="storage-grid">
						<!-- Stats -->
						<div class="storage-stats">
							{#if storageStats}
								<div class="stat-item">
									<span class="stat-value font-mono">{formatNumber(storageStats.total_readings)}</span>
									<span class="stat-label">Total Readings</span>
								</div>
								<div class="stat-item">
									<span class="stat-value font-mono">{formatBytes(storageStats.estimated_size_bytes)}</span>
									<span class="stat-label">Estimated Size</span>
								</div>
							{:else}
								<p class="text-muted">Unable to load storage stats</p>
							{/if}
						</div>

						<!-- Cleanup Controls -->
						<div class="cleanup-section">
							<p class="section-description mb-3">
								Remove old readings to free up storage. Readings older than the specified days will be permanently deleted.
							</p>
							<div class="cleanup-controls">
								<div class="cleanup-input-group">
									<label for="retention-days">Keep readings from last</label>
									<input
										id="retention-days"
										type="number"
										min="1"
										max="365"
										bind:value={cleanupRetentionDays}
										class="input-field-sm"
									/>
									<span>days</span>
								</div>
								<div class="cleanup-actions">
									<button
										type="button"
										class="btn-secondary-sm"
										onclick={previewCleanup}
										disabled={actionInProgress !== null}
									>
										{actionInProgress === 'cleanup-preview' ? 'Checking...' : 'Preview'}
									</button>
									{#if cleanupPreview && cleanupPreview.readings_to_delete > 0}
										<button
											type="button"
											class="btn-danger-sm"
											onclick={executeCleanup}
											disabled={actionInProgress !== null}
										>
											{actionInProgress === 'cleanup' ? 'Deleting...' : `Delete ${formatNumber(cleanupPreview.readings_to_delete)} readings`}
										</button>
									{/if}
								</div>
							</div>
							{#if cleanupPreview && cleanupPreview.readings_to_delete === 0}
								<p class="cleanup-message">No readings older than {cleanupRetentionDays} days found.</p>
							{/if}
						</div>
					</div>
				</div>
			</div>

			<!-- Power Controls -->
			<div class="card danger-zone">
				<div class="card-header">
					<h2 class="card-title">Power Controls</h2>
				</div>
				<div class="card-body">
					<p class="section-description danger-text">
						These actions will affect the entire system. Make sure you have saved any pending work.
					</p>
					<div class="power-buttons">
						<button
							type="button"
							class="btn-warning"
							onclick={rebootSystem}
							disabled={actionInProgress !== null}
						>
							{#if actionInProgress === 'reboot'}
								<span class="loading-dot"></span>
								Rebooting...
							{:else}
								<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
								</svg>
								Reboot System
							{/if}
						</button>
						<button
							type="button"
							class="btn-danger"
							onclick={shutdownSystem}
							disabled={actionInProgress !== null}
						>
							{#if actionInProgress === 'shutdown'}
								<span class="loading-dot"></span>
								Shutting down...
							{:else}
								<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
								</svg>
								Shutdown System
							{/if}
						</button>
					</div>
				</div>
			</div>
		</div>
	{/if}
</div>

<style>
	.page-container {
		max-width: 56rem;
	}

	.page-header {
		margin-bottom: 1.5rem;
	}

	.page-title {
		font-size: 1.5rem;
		font-weight: 700;
		color: var(--text-primary);
		margin-bottom: 0.25rem;
	}

	.page-description {
		color: var(--text-secondary);
		font-size: 0.875rem;
	}

	.card {
		background: var(--bg-card);
		border: 1px solid var(--bg-hover);
		border-radius: 0.75rem;
		overflow: hidden;
	}

	.card.danger-zone {
		border-color: rgba(244, 63, 94, 0.2);
	}

	.card-header {
		padding: 1rem 1.25rem;
		border-bottom: 1px solid var(--bg-hover);
	}

	.card-title {
		font-size: 0.75rem;
		font-weight: 600;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	.card-body {
		padding: 1.25rem;
	}

	.section-description {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin-bottom: 1rem;
		line-height: 1.5;
	}

	/* Info Grid */
	.info-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 1rem;
	}

	.info-item {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.info-label {
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.info-value {
		font-size: 0.875rem;
		color: var(--text-primary);
	}

	/* Settings */
	.setting-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.875rem 0;
		border-bottom: 1px solid var(--bg-hover);
	}

	.setting-row:last-of-type {
		border-bottom: none;
	}

	.setting-row.sub-setting {
		padding-left: 1rem;
		opacity: 0.9;
	}

	.setting-info {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
	}

	.setting-label {
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--text-primary);
	}

	.setting-description {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	/* Toggle Switch */
	.toggle {
		position: relative;
		width: 2.75rem;
		height: 1.5rem;
		background: var(--bg-elevated);
		border: 1px solid var(--bg-hover);
		border-radius: 0.75rem;
		cursor: pointer;
		transition: all 0.2s ease;
	}

	.toggle.active {
		background: var(--accent);
	}

	.toggle-slider {
		position: absolute;
		top: 2px;
		left: 2px;
		width: 1.125rem;
		height: 1.125rem;
		background: var(--text-muted);
		border-radius: 50%;
		transition: all 0.2s ease;
	}

	.toggle.active .toggle-slider {
		left: calc(100% - 1.125rem - 2px);
		background: white;
	}

	/* Unit Toggle */
	.unit-toggle {
		display: flex;
		gap: 0.25rem;
	}

	.unit-btn {
		min-width: 2.75rem;
		min-height: 2.75rem;
		padding: 0.5rem 0.75rem;
		font-size: 0.75rem;
		font-weight: 500;
		border-radius: 0.375rem;
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		color: var(--text-secondary);
		cursor: pointer;
		transition: all var(--transition);
	}

	.unit-btn:hover {
		border-color: var(--border-default);
		color: var(--text-primary);
	}

	.unit-btn.active {
		background: var(--accent);
		border-color: var(--accent);
		color: white;
	}

	/* Inputs */
	.input-field-sm {
		width: 4rem;
		padding: 0.375rem 0.5rem;
		font-size: 0.8125rem;
		font-family: 'JetBrains Mono', monospace;
		color: var(--text-primary);
		background: var(--bg-elevated);
		border: 1px solid var(--bg-hover);
		border-radius: 0.375rem;
		text-align: center;
	}

	.input-field-sm:focus {
		outline: none;
		border-color: var(--accent);
	}

	.rssi-input {
		display: flex;
		align-items: center;
		gap: 0.375rem;
	}

	.input-suffix {
		font-size: 0.75rem;
		color: var(--text-muted);
		font-family: 'JetBrains Mono', monospace;
	}

	.input-with-unit {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.input-with-unit .unit {
		font-size: 0.75rem;
		color: var(--text-muted);
		font-family: 'JetBrains Mono', monospace;
		min-width: 2rem;
	}

	.select-input-sm {
		padding: 0.375rem 1.75rem 0.375rem 0.5rem;
		font-size: 0.8125rem;
		font-family: 'JetBrains Mono', monospace;
		color: var(--text-primary);
		background: var(--bg-elevated);
		border: 1px solid var(--bg-hover);
		border-radius: 0.375rem;
		cursor: pointer;
		appearance: none;
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2371717a'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'/%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: right 0.375rem center;
		background-size: 1rem;
	}

	/* Timezone */
	.timezone-selector {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.select-input {
		flex: 1;
		max-width: 20rem;
		padding: 0.625rem 2.5rem 0.625rem 1rem;
		font-size: 0.875rem;
		color: var(--text-primary);
		background: var(--bg-elevated);
		border: 1px solid var(--bg-hover);
		border-radius: 0.5rem;
		cursor: pointer;
		appearance: none;
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2371717a'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'/%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: right 0.75rem center;
		background-size: 1.25rem;
	}

	.select-input:focus {
		outline: none;
		border-color: var(--accent);
	}

	/* Storage */
	.storage-grid {
		display: grid;
		gap: 1.5rem;
	}

	.storage-stats {
		display: flex;
		gap: 2rem;
	}

	.stat-item {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.stat-value {
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--accent);
	}

	.stat-label {
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	/* Cleanup */
	.cleanup-section {
		padding-top: 1rem;
		border-top: 1px solid var(--bg-hover);
	}

	.cleanup-controls {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 1rem;
	}

	.cleanup-input-group {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.8125rem;
		color: var(--text-secondary);
	}

	.cleanup-actions {
		display: flex;
		gap: 0.5rem;
	}

	.cleanup-message {
		margin-top: 0.75rem;
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	/* Power Controls */
	.danger-text {
		color: var(--tilt-red);
	}

	.power-buttons {
		display: flex;
		gap: 0.75rem;
	}

	/* Buttons */
	.btn-primary {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.625rem 1.25rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: white;
		background: var(--accent);
		border: none;
		border-radius: 0.5rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.btn-primary:hover {
		background: var(--accent-hover);
	}

	.btn-primary:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.btn-secondary-sm {
		padding: 0.375rem 0.75rem;
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--accent);
		background: var(--accent-muted);
		border: 1px solid var(--accent-muted);
		border-radius: 0.375rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.btn-secondary-sm:hover:not(:disabled) {
		background: rgba(59, 130, 246, 0.2);
	}

	.btn-secondary-sm:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.btn-danger-sm {
		padding: 0.375rem 0.75rem;
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--tilt-red);
		background: rgba(244, 63, 94, 0.1);
		border: 1px solid rgba(244, 63, 94, 0.2);
		border-radius: 0.375rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.btn-danger-sm:hover:not(:disabled) {
		background: rgba(244, 63, 94, 0.15);
	}

	.btn-danger-sm:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.btn-warning {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.625rem 1.25rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--tilt-orange);
		background: rgba(251, 146, 60, 0.1);
		border: 1px solid rgba(251, 146, 60, 0.2);
		border-radius: 0.5rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.btn-warning:hover:not(:disabled) {
		background: rgba(251, 146, 60, 0.15);
		border-color: rgba(251, 146, 60, 0.3);
	}

	.btn-warning:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.btn-danger {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.625rem 1.25rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--tilt-red);
		background: rgba(244, 63, 94, 0.1);
		border: 1px solid rgba(244, 63, 94, 0.2);
		border-radius: 0.5rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.btn-danger:hover:not(:disabled) {
		background: rgba(244, 63, 94, 0.15);
		border-color: rgba(244, 63, 94, 0.3);
	}

	.btn-danger:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	/* Loading States */
	.loading-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 1rem;
		padding: 4rem 2rem;
		color: var(--text-muted);
	}

	.loading-spinner {
		width: 2rem;
		height: 2rem;
		border: 2px solid var(--bg-hover);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	.loading-spinner-small {
		width: 1rem;
		height: 1rem;
		border: 2px solid var(--bg-hover);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	.loading-dot {
		width: 0.375rem;
		height: 0.375rem;
		background: currentColor;
		border-radius: 50%;
		animation: pulse 1s ease-in-out infinite;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	@keyframes pulse {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.4; }
	}

	.text-muted {
		color: var(--text-muted);
		font-size: 0.8125rem;
	}

	.mt-4 {
		margin-top: 1rem;
	}

	.mb-3 {
		margin-bottom: 0.75rem;
	}

	/* Config feedback */
	.config-actions {
		display: flex;
		align-items: center;
		gap: 1rem;
		flex-wrap: wrap;
	}

	.config-error {
		font-size: 0.75rem;
		color: var(--tilt-red);
	}

	.config-success {
		font-size: 0.75rem;
		color: var(--tilt-green);
	}

	/* Home Assistant Inputs */
	.input-field {
		width: 16rem;
		padding: 0.5rem 0.75rem;
		font-size: 0.8125rem;
		color: var(--text-primary);
		background: var(--bg-elevated);
		border: 1px solid var(--bg-hover);
		border-radius: 0.375rem;
	}

	.input-field:focus {
		outline: none;
		border-color: var(--accent);
	}

	.input-field::placeholder {
		color: var(--text-muted);
	}

	.status-badge {
		padding: 0.25rem 0.75rem;
		font-size: 0.75rem;
		font-weight: 500;
		border-radius: 9999px;
		background: rgba(244, 63, 94, 0.1);
		color: var(--tilt-red);
	}

	.status-badge.connected {
		background: rgba(16, 185, 129, 0.1);
		color: var(--tilt-green);
	}

	.test-connection {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.test-result {
		font-size: 0.75rem;
		color: var(--tilt-red);
	}

	.test-result.success {
		color: var(--tilt-green);
	}

	/* Temperature Control */
	.section-note {
		font-size: 0.8125rem;
		color: var(--text-muted);
		margin-bottom: 1rem;
		line-height: 1.5;
	}

	.input-number {
		width: 6rem;
		text-align: right;
	}

	@media (max-width: 640px) {
		.info-grid {
			grid-template-columns: 1fr;
		}

		.storage-stats {
			flex-direction: column;
			gap: 1rem;
		}

		.cleanup-controls {
			flex-direction: column;
			align-items: flex-start;
		}

		.power-buttons {
			flex-direction: column;
		}
	}
</style>
