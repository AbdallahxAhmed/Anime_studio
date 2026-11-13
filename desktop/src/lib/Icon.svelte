<script lang="ts">
  type Name =
    | "folder" | "refresh" | "play" | "stop" | "history" | "font" | "search"
    | "settings" | "check" | "x" | "warn" | "chevron" | "dot";
  let { name, size = 16 }: { name: Name; size?: number } = $props();
</script>

<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  {#if name === "folder"}<path d="M3 7h6l2 2h10v10H3z" /><path d="M12 12v5M9.5 14.5h5" />
  {:else if name === "refresh"}<path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5" />
  {:else if name === "play"}<path d="M7 4l12 8-12 8z" fill="currentColor" stroke="none" />
  {:else if name === "stop"}<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" stroke="none" />
  {:else if name === "history"}<path d="M9 14L4 9l5-5" /><path d="M4 9h10a6 6 0 0 1 0 12h-3" />
  {:else if name === "font"}<path d="M4 20l6-16h1l6 16M7 14h8" />
  {:else if name === "search"}<circle cx="11" cy="11" r="7" /><path d="M20 20l-4-4" />
  {:else if name === "settings"}<circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1" />
  {:else if name === "check"}<path d="M5 12l5 5L20 7" stroke-width="2.6" />
  {:else if name === "x"}<path d="M6 6l12 12M18 6L6 18" stroke-width="2.4" />
  {:else if name === "warn"}<path d="M12 3l10 18H2z" /><path d="M12 10v4M12 17v.5" />
  {:else if name === "chevron"}<path d="M9 6l6 6-6 6" />
  {:else if name === "dot"}<circle cx="12" cy="12" r="4" fill="currentColor" stroke="none" />
  {/if}
</svg>
