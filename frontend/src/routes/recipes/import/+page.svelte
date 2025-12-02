<script lang="ts">
	import { goto } from '$app/navigation';
	import { importBeerXML } from '$lib/api';

	const MAX_FILE_SIZE = 1_000_000; // 1MB in bytes

	let uploading = $state(false);
	let error = $state<string | null>(null);
	let dragActive = $state(false);

	async function handleFileUpload(file: File) {
		error = null;

		// Validate file
		if (!file.name.endsWith('.xml')) {
			error = 'Please upload a .xml BeerXML file';
			return;
		}

		if (file.size > MAX_FILE_SIZE) {
			error = 'File must be smaller than 1MB';
			return;
		}

		uploading = true;

		try {
			const recipes = await importBeerXML(file);
			// Redirect to first imported recipe or back to list
			if (recipes.length === 1) {
				goto(`/recipes/${recipes[0].id}`);
			} else {
				goto('/recipes');
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to import recipe';
		} finally {
			uploading = false;
		}
	}

	function handleDrop(e: DragEvent) {
		e.preventDefault();
		dragActive = false;

		const file = e.dataTransfer?.files[0];
		if (file) {
			handleFileUpload(file);
		}
	}

	function handleDragOver(e: DragEvent) {
		e.preventDefault();
		dragActive = true;
	}

	function handleDragLeave() {
		dragActive = false;
	}

	function handleFileInput(e: Event) {
		const input = e.target as HTMLInputElement;
		const file = input.files?.[0];
		if (file) {
			handleFileUpload(file);
		}
	}

	function handleKeyDown(e: KeyboardEvent) {
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			const fileInput = document.querySelector('.file-input') as HTMLInputElement;
			fileInput?.click();
		}
	}
</script>

<svelte:head>
	<title>Import Recipe | BrewSignal</title>
</svelte:head>

<div class="page-container">
	<div class="back-link">
		<a href="/recipes" class="back-btn">
			<svg class="back-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
			</svg>
			Back to Recipes
		</a>
	</div>

	<div class="import-container">
		<h1 class="page-title">Import Recipe</h1>
		<p class="page-description">
			Upload BeerXML files from Brewfather, BeerSmith, Brewer's Friend, or any brewing software
		</p>

		<div
			class="drop-zone"
			class:active={dragActive}
			class:uploading
			ondrop={handleDrop}
			ondragover={handleDragOver}
			ondragleave={handleDragLeave}
			onkeydown={handleKeyDown}
			role="button"
			tabindex="0"
			aria-label="Upload BeerXML file by dropping or clicking"
		>
			{#if uploading}
				<div class="spinner"></div>
				<p class="drop-text">Importing recipe...</p>
			{:else}
				<div class="upload-icon">📄</div>
				<p class="drop-text">Drop BeerXML file here</p>
				<p class="drop-subtext">or click to browse</p>
				<input
					type="file"
					accept=".xml"
					onchange={handleFileInput}
					class="file-input"
					disabled={uploading}
				/>
			{/if}
		</div>

		<div class="file-info">
			<p class="info-text">Supported: .xml files (max 1MB)</p>
		</div>

		{#if error}
			<div class="error-box">
				<svg class="error-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
					/>
				</svg>
				<p class="error-text">{error}</p>
			</div>
		{/if}
	</div>
</div>

<style>
	.page-container {
		max-width: 600px;
		margin: 0 auto;
		padding: var(--space-6);
	}

	.back-link {
		margin-bottom: var(--space-6);
	}

	.back-btn {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		font-size: 14px;
		font-weight: 500;
		color: var(--text-secondary);
		text-decoration: none;
		transition: color var(--transition);
	}

	.back-btn:hover {
		color: var(--text-primary);
	}

	.back-icon {
		width: 16px;
		height: 16px;
	}

	.import-container {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}

	.page-title {
		font-size: 28px;
		font-weight: 600;
		margin: 0;
		color: var(--text-primary);
	}

	.page-description {
		font-size: 14px;
		color: var(--text-secondary);
		margin: 0;
	}

	.drop-zone {
		position: relative;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: var(--space-3);
		padding: var(--space-12) var(--space-6);
		background: var(--bg-surface);
		border: 2px dashed var(--border-default);
		border-radius: 8px;
		cursor: pointer;
		transition: all var(--transition);
	}

	.drop-zone:hover:not(.uploading) {
		border-color: var(--recipe-accent-border);
		background: var(--bg-elevated);
	}

	.drop-zone.active {
		border-color: var(--recipe-accent);
		background: var(--recipe-accent-muted);
	}

	.drop-zone.uploading {
		cursor: wait;
		opacity: 0.7;
	}

	.upload-icon {
		font-size: 48px;
	}

	.drop-text {
		font-size: 16px;
		font-weight: 500;
		color: var(--text-primary);
		margin: 0;
	}

	.drop-subtext {
		font-size: 14px;
		color: var(--text-secondary);
		margin: 0;
	}

	.file-input {
		position: absolute;
		inset: 0;
		opacity: 0;
		cursor: pointer;
	}

	.file-input:disabled {
		cursor: wait;
	}

	.file-info {
		display: flex;
		justify-content: center;
	}

	.info-text {
		font-size: 12px;
		color: var(--text-muted);
		margin: 0;
		font-family: var(--font-mono);
	}

	.spinner {
		width: 32px;
		height: 32px;
		border: 3px solid var(--gray-700);
		border-top-color: var(--recipe-accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	.error-box {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-4);
		background: rgba(239, 68, 68, 0.1);
		border: 1px solid var(--negative);
		border-radius: 6px;
	}

	.error-icon {
		width: 20px;
		height: 20px;
		color: var(--negative);
		flex-shrink: 0;
	}

	.error-text {
		font-size: 14px;
		color: var(--negative);
		margin: 0;
	}
</style>
