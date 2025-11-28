<script lang="ts">
	import '../app.css';
	import { onMount, onDestroy } from 'svelte';
	import { slide } from 'svelte/transition';
	import { page } from '$app/stores';
	import { tiltsState, startHeaterPolling, stopHeaterPolling } from '$lib/stores/tilts.svelte';
	import { loadConfig, configState } from '$lib/stores/config.svelte';

	let { children } = $props();
	let mobileMenuOpen = $state(false);

	// Derived: show heater indicator only when HA is enabled and heater entity is configured
	let showHeaterIndicator = $derived(
		configState.config.ha_enabled && configState.config.ha_heater_entity_id
	);

	onMount(() => {
		loadConfig();
		// Start polling heater state every 30 seconds
		startHeaterPolling(30000);
	});

	onDestroy(() => {
		stopHeaterPolling();
	});

	const navLinks = [
		{ href: '/', label: 'Dashboard' },
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
	<title>Tilt UI</title>
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
						Tilt<span style="color: var(--accent);">UI</span>
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

				<!-- Right side: heater indicator + connection status + mobile menu -->
				<div class="flex items-center gap-3">
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
</style>
