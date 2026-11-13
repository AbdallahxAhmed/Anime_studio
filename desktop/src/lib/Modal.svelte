<script lang="ts">
  import type { Snippet } from "svelte";
  import { onMount } from "svelte";

  let {
    title,
    width = 560,
    onclose,
    children,
    footer,
  }: {
    title: string;
    width?: number;
    onclose: () => void;
    children: Snippet;
    footer: Snippet;
  } = $props();

  let panel: HTMLElement;

  onMount(() => {
    const body = panel.querySelector(".body");
    const first =
      panel.querySelector<HTMLElement>("footer button.primary:not(:disabled)") ??
      body?.querySelector<HTMLElement>("input, select, button") ??
      null;
    first?.focus();
  });

  function keydown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      event.stopPropagation();
      onclose();
    }
  }
</script>

<div class="scrim" role="presentation" onkeydown={keydown}>
  <div bind:this={panel} class="dialog" role="dialog" aria-modal="true"
    aria-label={title} style:width="min({width}px, calc(100vw - 48px))">
    <header>
      <span>{title}</span>
      <button class="close" aria-label="Close" onclick={onclose}>×</button>
    </header>
    <div class="body">{@render children()}</div>
    <footer>{@render footer()}</footer>
  </div>
</div>

<style>
  .scrim {
    position: fixed;
    inset: 0;
    background: var(--scrim);
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding-top: 9vh;
    z-index: 10;
  }
  .dialog {
    max-height: 82vh;
    display: flex;
    flex-direction: column;
    background: var(--view);
    border: 1px solid var(--border);
    border-radius: 8px;
    box-shadow: var(--shadow);
    overflow: hidden;
  }
  header {
    display: flex;
    align-items: center;
    height: 38px;
    padding-left: 16px;
    font-weight: 600;
    border-bottom: 1px solid var(--border);
    background: var(--window);
  }
  header span {
    flex: 1;
  }
  .close {
    width: 44px;
    height: 38px;
    border: 0;
    background: none;
    font-size: 20px;
    color: var(--muted);
  }
  .close:hover {
    background: var(--hover);
  }
  .body {
    padding: 18px 20px;
    overflow: auto;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  footer {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 16px;
    border-top: 1px solid var(--border);
    background: var(--window);
  }
</style>
