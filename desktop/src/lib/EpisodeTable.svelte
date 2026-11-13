<script lang="ts">
  import { app, type RowPhase } from "./state.svelte";
  import type { Episode } from "./types";

  const scanLabel: Record<Episode["status"], [string, string]> = {
    ready: ["Ready", "var(--ready)"],
    no_subtitle: ["No subtitle", "var(--idle)"],
    other_language: ["No Arabic track", "var(--warn)"],
  };
  const runColor: Record<RowPhase, string> = {
    queued: "var(--idle)",
    working: "var(--ready)",
    complete: "var(--ok)",
    partial: "var(--warn)",
    failed: "var(--bad)",
    skipped: "var(--idle)",
  };

  function subtitleText(e: Episode): string {
    if (!e.subtitle) return "None found";
    if (e.subtitle.kind === "external") return e.subtitle.name ?? "";
    const lang = app.config?.preferred_language ?? "ara";
    const track = e.subtitle.tracks?.find((t) => t.language === lang);
    return track ? `Inside file (track ${track.id})` : "Inside file, other languages";
  }

  function keydown(event: KeyboardEvent) {
    const list = app.visibleEpisodes;
    const index = list.findIndex((e) => e.path === app.focused);
    if (event.key === "ArrowDown" || event.key === "j") {
      app.focused = list[Math.min(index + 1, list.length - 1)]?.path ?? app.focused;
    } else if (event.key === "ArrowUp" || event.key === "k") {
      app.focused = list[Math.max(index - 1, 0)]?.path ?? app.focused;
    } else if (event.key === " " && app.focused && !app.running) {
      const episode = list[index];
      if (episode?.status === "ready") app.toggle(episode.path);
    } else {
      return;
    }
    event.preventDefault();
    document.getElementById(`row-${index}`)?.scrollIntoView({ block: "nearest" });
  }

  let allChecked = $derived(
    app.counts.ready > 0 &&
      (app.listing?.episodes ?? [])
        .filter((e) => e.status === "ready")
        .every((e) => app.checked.has(e.path)),
  );
</script>

<div class="wrap" tabindex="0" role="grid" aria-label="Episodes" onkeydown={keydown}>
  <table>
    <thead>
      <tr>
        <th class="c"><input type="checkbox" aria-label="Select all ready episodes"
          checked={allChecked} disabled={app.running || !app.counts.ready}
          onchange={() => app.toggleAll()} /></th>
        <th class="n">#</th>
        <th>Episode</th>
        <th>Arabic subtitle</th>
        <th class="s">Status</th>
      </tr>
    </thead>
    <tbody>
      {#each app.visibleEpisodes as e, i (e.path)}
        {@const run = app.runRows[e.path]}
        {@const [label, color] = run ? [run.note, runColor[run.phase]] : scanLabel[e.status]}
        <tr id={`row-${i}`} class:focused={app.focused === e.path}
          class:dim={e.status !== "ready"} onclick={() => (app.focused = e.path)}>
          <td class="c">
            <input type="checkbox" aria-label={`Select ${e.name}`}
              checked={app.checked.has(e.path)} disabled={e.status !== "ready" || app.running}
              onclick={(ev) => ev.stopPropagation()} onchange={() => app.toggle(e.path)} />
          </td>
          <td class="n">{e.number ?? "–"}</td>
          <td class="ep" title={e.path}>{e.name}</td>
          <td class:none={!e.subtitle}>{subtitleText(e)}</td>
          <td class="s">
            <span class="status" style:color={color}>
              <span class="mark" class:ring={!run && e.status === "no_subtitle"}
                class:spin={run?.phase === "working"} style:background={run?.phase === "working" ? "transparent" : color}
                style:border-color={color}></span>
              <span class="label">{label}</span>
            </span>
            {#if run?.phase === "working"}<span class="bar"><span></span></span>{/if}
          </td>
        </tr>
      {:else}
        <tr><td colspan="5" class="empty muted">
          {app.loading ? "Reading the folder…" : app.listing ? "No episodes match." : "Pick a show on the left."}
        </td></tr>
      {/each}
    </tbody>
  </table>
</div>

<style>
  .wrap {
    flex: 1;
    overflow: auto;
    background: var(--view);
  }
  .wrap:focus-visible {
    outline-offset: -2px;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
  }
  th {
    position: sticky;
    top: 0;
    z-index: 1;
    text-align: left;
    font-weight: 400;
    font-size: 12px;
    color: var(--muted);
    background: var(--header);
    padding: 6px 8px;
    border-bottom: 1px solid var(--border);
  }
  th + th {
    border-left: 1px solid var(--rule);
  }
  td {
    height: 30px;
    padding: 0 8px;
    border-bottom: 1px solid var(--rule);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .c {
    width: 40px;
    text-overflow: clip;
  }
  .n {
    width: 40px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  .s {
    width: 220px;
  }
  tr.focused td {
    background: var(--selected);
  }
  tr.dim td.ep {
    color: var(--muted);
  }
  td.none {
    color: var(--muted);
    font-style: italic;
  }
  .status {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    max-width: 100%;
  }
  .label {
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .mark {
    flex: none;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    border: 1.5px solid;
  }
  .mark.ring {
    background: transparent !important;
  }
  .mark.spin {
    width: 10px;
    height: 10px;
    border-right-color: transparent !important;
    animation: spin 0.8s linear infinite;
  }
  .bar {
    display: block;
    height: 3px;
    margin-top: 3px;
    background: var(--rule);
    border-radius: 2px;
    overflow: hidden;
  }
  .bar span {
    display: block;
    width: 40%;
    height: 100%;
    background: var(--ready);
    animation: slide 1.2s ease-in-out infinite;
  }
  .empty {
    text-align: center;
    height: 80px;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  @keyframes slide {
    from {
      transform: translateX(-100%);
    }
    to {
      transform: translateX(250%);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .mark.spin,
    .bar span {
      animation: none;
    }
  }
</style>
