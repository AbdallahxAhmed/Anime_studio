<script lang="ts">
  import { app } from "./state.svelte";
  import Icon from "./Icon.svelte";

  let episode = $derived(app.focusedEpisode);
  let run = $derived(episode ? app.runRows[episode.path] : undefined);
  let language = $derived(app.config?.preferred_language ?? "ara");
  let embeddedMatch = $derived(
    episode?.subtitle?.kind === "embedded"
      ? episode.subtitle.tracks?.find((t) => t.language === language)
      : undefined,
  );
</script>

<aside class="details" aria-label="Episode details">
  {#if episode}
    <div class="head">
      <div class="title">{episode.number != null ? `Episode ${episode.number}` : "Episode"}</div>
      <div class="file muted" title={episode.path}>{episode.name}</div>
    </div>

    <section class="card">
      <h3>Subtitle</h3>
      {#if episode.subtitle?.kind === "external"}
        <p>From the file <b>{episode.subtitle.name}</b> in the same folder.</p>
      {:else if embeddedMatch}
        <p>Already inside the video (track {embeddedMatch.id}). Its styles are repaired and its fonts added.</p>
      {:else if episode.subtitle?.kind === "embedded"}
        <p class="warn"><Icon name="warn" size={14} /> The video has subtitles, but none in
          <b>{language}</b>: {episode.subtitle.tracks?.map((t) => t.language || "unknown").join(", ")}.</p>
      {:else}
        <p class="warn"><Icon name="warn" size={14} /> No subtitle found.</p>
        <p class="muted small">Put the .ass file next to the video with the same name or episode number, then press Rescan (F5).</p>
      {/if}
    </section>

    {#if episode.status === "ready"}
      <section class="card">
        <h3>After apply</h3>
        <div class="row"><span class="muted">Arabic</span><span class="tag">new · {app.config?.set_default ? "default" : "not default"}</span></div>
        <div class="row"><span class="muted">Other subtitles</span><span>kept{app.config?.set_default ? ", not default" : ""}</span></div>
        <div class="row"><span class="muted">Video and audio</span><span>unchanged</span></div>
        <div class="row"><span class="muted">Original file</span><span>kept {app.config?.trash_max_age_days ?? 30} days</span></div>
      </section>

      <section class="card">
        <h3>Fonts</h3>
        <p class="muted small">Found while applying, in this order: font cache, the video itself, a Fonts folder next to it, system fonts, then the web.</p>
      </section>
    {/if}

    {#if run}
      <section class="card">
        <h3>Result</h3>
        <p>{run.note}</p>
      </section>
    {/if}
  {:else}
    <p class="muted pad">Select an episode to see what will change.</p>
  {/if}
</aside>

<style>
  .details {
    width: 300px;
    flex: none;
    background: var(--pane);
    border-left: 1px solid var(--border);
    overflow: auto;
    padding-bottom: 10px;
  }
  .head {
    padding: 12px 14px 10px;
  }
  .title {
    font-size: 15px;
    font-weight: 600;
  }
  .file {
    font-size: 12px;
    margin-top: 2px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .card {
    margin: 0 10px 10px;
    padding: 10px 12px;
    background: var(--view);
    border: 1px solid var(--border);
    border-radius: 6px;
  }
  h3 {
    margin: 0 0 6px;
    font-size: 13px;
  }
  p {
    margin: 0 0 6px;
    line-height: 1.45;
    user-select: text;
  }
  p:last-child {
    margin-bottom: 0;
  }
  .small {
    font-size: 12px;
  }
  .warn {
    color: var(--warn);
    display: flex;
    gap: 6px;
    align-items: flex-start;
  }
  .row {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    padding: 2px 0;
  }
  .tag {
    color: var(--accent);
    font-weight: 600;
  }
  .pad {
    padding: 14px;
  }
</style>
