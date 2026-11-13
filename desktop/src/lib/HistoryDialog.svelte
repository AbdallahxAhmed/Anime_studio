<script lang="ts">
  import Modal from "./Modal.svelte";
  import { app } from "./state.svelte";
  import { primaryFirst } from "./platform";

  let runId = $state(app.history[0]?.run_id ?? null);
  let picked = $state<Set<string>>(new Set());
  let busy = $state(false);
  let result = $state<string | null>(null);

  let run = $derived(app.history.find((r) => r.run_id === runId) ?? null);
  let restorable = $derived(run?.episodes.filter((e) => e.restorable) ?? []);

  function when(timestamp: string): string {
    const date = new Date(timestamp);
    return Number.isNaN(date.getTime())
      ? timestamp
      : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  }

  function base(path: string): string {
    return path.split(/[\\/]/).pop() ?? path;
  }

  function toggle(path: string) {
    const next = new Set(picked);
    if (next.has(path)) next.delete(path);
    else next.add(path);
    picked = next;
  }

  async function restore() {
    if (!run || !picked.size) return;
    busy = true;
    const outcome = await app.undo(run.run_id, [...picked]);
    busy = false;
    picked = new Set();
    if (outcome) {
      result = `${outcome.restored} restored` +
        (outcome.missing ? `, ${outcome.missing} backups already deleted` : "") +
        (outcome.failed ? `, ${outcome.failed} failed` : "");
    }
  }

  const close = () => (app.dialog = null);
</script>

<Modal title="History and undo" width={780} onclose={close}>
  {#if !app.history.length}
    <p class="muted">Nothing applied yet. Every applied episode shows up here and can be restored.</p>
  {:else}
    <div class="split">
      <div class="runs" role="listbox" aria-label="Runs">
        {#each app.history as item (item.run_id)}
          <button role="option" aria-selected={item.run_id === runId}
            class:selected={item.run_id === runId}
            onclick={() => { runId = item.run_id; picked = new Set(); result = null; }}>
            <b>{item.shows.join(", ") || "Run"}</b>
            <span class="muted">{when(item.timestamp)} · {item.episodes.length} episodes</span>
          </button>
        {/each}
      </div>
      <div class="episodes">
        {#if run}
          {#each run.episodes as ep (ep.path)}
            <label class:off={!ep.restorable}>
              <input type="checkbox" checked={picked.has(ep.path)} disabled={!ep.restorable}
                onchange={() => toggle(ep.path)} />
              <span class="name" title={ep.path}>{base(ep.path)}</span>
              <span class="muted">{ep.restorable ? "Original in backup" : "Restored"}</span>
            </label>
          {/each}
        {/if}
      </div>
    </div>
  {/if}
  {#if result}<p class="ok">{result}.</p>{/if}

  {#snippet footer()}
    <button class="btn link" disabled={!restorable.length}
      onclick={() => (picked = new Set(restorable.map((e) => e.path)))}>Select all</button>
    <span class="grow"></span>
    {#if primaryFirst}
      <button class="btn primary" disabled={!picked.size || busy} onclick={restore}>Restore {picked.size || ""}</button>
      <button class="btn" onclick={close}>Close</button>
    {:else}
      <button class="btn" onclick={close}>Close</button>
      <button class="btn primary" disabled={!picked.size || busy} onclick={restore}>Restore {picked.size || ""}</button>
    {/if}
  {/snippet}
</Modal>

<style>
  .split {
    display: flex;
    gap: 12px;
    min-height: 300px;
  }
  .runs {
    width: 240px;
    flex: none;
    display: flex;
    flex-direction: column;
    gap: 2px;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 4px;
    overflow: auto;
  }
  .runs button {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
    padding: 8px 10px;
    border: 0;
    border-radius: 4px;
    background: none;
    text-align: left;
  }
  .runs button:hover {
    background: var(--hover);
  }
  .runs button.selected {
    background: var(--nav-selected);
  }
  .runs span {
    font-size: 12px;
  }
  .episodes {
    flex: 1;
    min-width: 0;
    border: 1px solid var(--border);
    border-radius: 6px;
    overflow: auto;
  }
  .episodes label {
    display: flex;
    align-items: center;
    gap: 8px;
    height: 30px;
    padding: 0 10px;
    border-bottom: 1px solid var(--rule);
  }
  .episodes label.off {
    color: var(--muted);
  }
  .name {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .grow {
    flex: 1;
  }
  .ok {
    color: var(--ok);
    margin: 0;
  }
</style>
