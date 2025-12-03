<script lang="ts">
	import BatchCard from './BatchCard.svelte';

	interface Props {
		notes: string;
	}

	let { notes }: Props = $props();
</script>

<BatchCard title="Notes">
	<p class="notes-content">{notes}</p>
</BatchCard>

<style>
	.notes-content {
		font-size: 0.875rem;
		color: var(--text-secondary);
		line-height: 1.6;
		margin: 0;
		white-space: pre-wrap;
	}
</style>
