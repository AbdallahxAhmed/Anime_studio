<script lang="ts">
  import { onMount } from "svelte";
  import { app } from "./lib/state.svelte";
  import { isDesktop } from "./lib/backend";
  import Icon from "./lib/Icon.svelte";
  import ShowTree from "./lib/ShowTree.svelte";
  import EpisodeTable from "./lib/EpisodeTable.svelte";
  import Details from "./lib/Details.svelte";
  import ApplyDialog from "./lib/ApplyDialog.svelte";
  import HistoryDialog from "./lib/HistoryDialog.svelte";
  import SetupDialog from "./lib/SetupDialog.svelte";
  import PreferencesDialog from "./lib/PreferencesDialog.svelte";

  let activityOpen = $state(false);

  function openApply() {
    if (!app.running && app.selected.length) app.dialog = "apply";
  }

  const actions: Record<string, () => void> = {
    "add-folder": () => void app.chooseLibrary(),
    "import-fonts": () => void app.importFonts(),
    preferences: () => (app.dialog = "preferences"),
    rescan: () => void app.rescan(),
    apply: openApply,
    stop: () => void app.stop(),
    history: () => void app.openHistory(),
    about: () => (app.dialog = "about"),
  };

  onMount(() => {
    void app.init().then(() => {
      // Browser preview only: ?demo=apply|history|setup|run opens that state.
      const demo = isDesktop ? null : new URLSearchParams(location.search).get("demo");
      if (demo === "run") setTimeout(() => void app.apply({ sync: false, dryRun: false, setDefault: true }), 300);
      else if (demo === "history") void app.openHistory();
      else if (demo === "apply" || demo === "setup" || demo === "preferences")
        setTimeout(() => (app.dialog = demo), 300);
    });
    if (isDesktop) {
      void import("@tauri-apps/api/event").then(({ listen }) =>
        listen<string>("menu://action", ({ payload }) => actions[payload]?.()),
      );
    }
  });

  $effect(() => {
    if (app.running) activityOpen = true;
  });

  function keydown(event: KeyboardEvent) {
    if (app.dialog) return;
    const mod = event.ctrlKey || event.metaKey;
    if (mod && event.key === "Enter") openApply();
    else if (event.key === "F5") void app.rescan();
    else if (mod && event.key.toLowerCase() === "h") void app.openHistory();
    else if (mod && event.key === ",") app.dialog = "preferences";
    else return;
    event.preventDefault();
  }

  let percent = $derived(app.total ? Math.round((app.done / app.total) * 100) : 0);
</script>

<svelte:window onkeydown={keydown} />

<div class="window">
  <div class="toolbar" role="toolbar" aria-label="Main toolbar">
    <button class="btn flat" disabled={app.running} onclick={() => app.chooseLibrary()}>
      <Icon name="folder" /> Library…</button>
    <button class="btn flat" disabled={app.running} onclick={() => app.rescan()} title="F5">
      <Icon name="refresh" /> Rescan</button>
    <span class="sep"></span>
    {#if app.running}
      <button class="btn danger" disabled={app.stopping} onclick={() => app.stop()}>
        <Icon name="stop" size={14} /> {app.stopping ? "Stopping after this episode…" : "Stop After This Episode"}</button>
    {:else}
      <button class="btn primary" disabled={!app.selected.length} onclick={openApply} title="Ctrl+Enter">
        <Icon name="play" size={14} /> Apply to {app.selected.length} Episode{app.selected.length === 1 ? "" : "s"}…</button>
    {/if}
    <span class="sep"></span>
    <button class="btn flat" disabled={app.running} onclick={() => app.openHistory()} title="Ctrl+H">
      <Icon name="history" /> History</button>
    <button class="btn flat" disabled={app.running || !isDesktop} onclick={() => app.importFonts()}>
      <Icon name="font" /> Import Fonts</button>
    <span class="grow"></span>
    <label class="search">
      <Icon name="search" size={14} />
      <span class="sr-only">Filter episodes</span>
      <input placeholder="Filter episodes" bind:value={app.filter} />
    </label>
    <button class="btn flat icon" aria-label="Preferences" title="Preferences (Ctrl+,)"
      onclick={() => (app.dialog = "preferences")}><Icon name="settings" /></button>
  </div>

  {#if app.backendDown}
    <div class="banner bad">The background service stopped. Restart Anime Studio; your files are safe.</div>
  {:else if app.error}
    <div class="banner bad">{app.error}
      <button class="btn link" onclick={() => (app.error = null)}>Dismiss</button></div>
  {/if}

  <div class="body">
    <ShowTree />
    <main>
      <div class="head">
        <h1>{app.listing?.name ?? "Anime Studio"}</h1>
        {#if app.listing}<span class="muted">{app.listing.episodes.length} episodes</span>{/if}
        <span class="grow"></span>
        <label class="muted">Show
          <select class="field" bind:value={app.view}>
            <option value="all">All episodes</option>
            <option value="ready">Ready</option>
            <option value="attention">Needs attention</option>
          </select>
        </label>
      </div>
      <EpisodeTable />
      <section class="activity" class:open={activityOpen} aria-label="Activity">
        <button class="activity-head" aria-expanded={activityOpen}
          onclick={() => (activityOpen = !activityOpen)}>
          <span class="chev" class:open={activityOpen}><Icon name="chevron" size={12} /></span>
          <b>Activity</b>
          <span class="muted">{app.stageText}</span>
        </button>
        {#if activityOpen}
          <ul>
            {#each app.log.slice(-200) as line, i (i)}
              <li class={line.level}><span class="t">{line.time}</span>{line.message}</li>
            {:else}
              <li class="muted">Nothing yet.</li>
            {/each}
          </ul>
        {/if}
      </section>
    </main>
    <Details />
  </div>

  <footer class="status" role="status">
    {#if app.running}
      <span>{app.done} of {app.total} done</span>
      <span class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100"
        aria-valuenow={percent}><span style:width="{percent}%"></span></span>
    {:else if app.listing}
      <span>{app.selected.length} selected</span>
      <span>{app.counts.ready} ready</span>
      {#if app.counts.none}<span class="warn">{app.counts.none} without subtitles</span>{/if}
      {#if app.counts.other}<span class="warn">{app.counts.other} without an Arabic track</span>{/if}
    {/if}
    <span class="grow"></span>
    {#if app.info}
      {#if app.info.missing_required_tools.length}
        <button class="btn link warn" onclick={() => (app.dialog = "setup")}>Missing: {app.info.missing_required_tools.join(", ")}</button>
      {:else}
        <span class="ok"><Icon name="check" size={12} /> Tools ready</span>
      {/if}
      <span>v{app.info.version}</span>
    {/if}
  </footer>
</div>

{#if app.dialog === "apply"}<ApplyDialog />{/if}
{#if app.dialog === "history"}<HistoryDialog />{/if}
{#if app.dialog === "setup"}<SetupDialog />{/if}
{#if app.dialog === "preferences" && app.config}<PreferencesDialog />{/if}

<style>
  .window {
    height: 100%;
    display: flex;
    flex-direction: column;
  }
  .toolbar {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 6px 8px;
    background: var(--pane);
    border-bottom: 1px solid var(--border);
    flex-wrap: wrap;
  }
  .sep {
    width: 1px;
    height: 20px;
    background: var(--border);
    margin: 0 6px;
  }
  .grow {
    flex: 1;
  }
  .icon {
    width: 32px;
    padding: 0;
    justify-content: center;
  }
  .search {
    display: flex;
    align-items: center;
    gap: 6px;
    width: 220px;
    height: 30px;
    padding: 0 8px;
    border: 1px solid var(--control-border);
    border-bottom-color: var(--control-bottom);
    border-radius: 4px;
    background: var(--control);
    color: var(--muted);
  }
  .search input {
    flex: 1;
    min-width: 0;
    border: 0;
    outline: none;
    background: transparent;
    color: var(--text);
  }
  .banner {
    padding: 8px 14px;
    border-bottom: 1px solid var(--warn-border);
    background: var(--warn-bg);
  }
  .body {
    flex: 1;
    min-height: 0;
    display: flex;
  }
  main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    background: var(--view);
  }
  .head {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
  }
  .head h1 {
    margin: 0;
    font-size: 15px;
  }
  .head label {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .activity {
    flex: none;
    border-top: 1px solid var(--border);
    background: var(--pane);
  }
  .activity.open {
    height: 170px;
    display: flex;
    flex-direction: column;
  }
  .activity-head {
    width: 100%;
    height: 30px;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0 10px;
    border: 0;
    background: none;
    text-align: left;
    white-space: nowrap;
    overflow: hidden;
  }
  .chev {
    display: grid;
    transition: transform 0.1s;
  }
  .chev.open {
    transform: rotate(90deg);
  }
  .activity ul {
    flex: 1;
    overflow: auto;
    list-style: none;
    margin: 0;
    padding: 4px 10px 8px;
    font-size: 12px;
    background: var(--view);
    user-select: text;
  }
  .activity li {
    padding: 2px 0;
  }
  .activity li.warning {
    color: var(--warn);
  }
  .activity li.error {
    color: var(--bad);
  }
  .t {
    display: inline-block;
    width: 48px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  .status {
    display: flex;
    align-items: center;
    gap: 16px;
    height: 26px;
    padding: 0 12px;
    font-size: 12px;
    color: var(--muted);
    background: var(--window);
    border-top: 1px solid var(--border);
  }
  .status .ok {
    color: var(--ok);
    display: inline-flex;
    gap: 4px;
    align-items: center;
  }
  .warn {
    color: var(--warn);
  }
  .progress {
    width: 220px;
    height: 6px;
    border-radius: 3px;
    background: var(--rule);
    overflow: hidden;
  }
  .progress span {
    display: block;
    height: 100%;
    background: var(--accent);
    transition: width 0.3s;
  }
</style>
