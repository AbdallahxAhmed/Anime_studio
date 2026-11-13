<script lang="ts">
  import Modal from "./Modal.svelte";
  import Icon from "./Icon.svelte";
  import { app } from "./state.svelte";
  import { primaryFirst } from "./platform";

  let setDefault = $state(app.config?.set_default ?? true);
  let sync = $state(app.config?.sync_by_default ?? false);
  let dryRun = $state(false);

  let episodes = $derived(app.selected);
  let fromFiles = $derived(episodes.filter((e) => e.subtitle?.kind === "external").length);
  let fromVideo = $derived(episodes.length - fromFiles);
  let skipped = $derived((app.listing?.episodes.length ?? 0) - episodes.length);

  const close = () => (app.dialog = null);
  const apply = () => app.apply({ sync, dryRun, setDefault });
</script>

<Modal title="Apply changes" onclose={close}>
  <div class="lead">
    <span class="icon"><Icon name="play" size={18} /></span>
    <div>
      <h2>Add Arabic subtitles to {episodes.length} episode{episodes.length === 1 ? "" : "s"}?</h2>
      <p class="muted">Each new file is checked before it replaces the original. Originals are kept
        for {app.config?.trash_max_age_days ?? 30} days, so you can undo from History.</p>
    </div>
  </div>

  <ul class="summary">
    {#if fromFiles}<li><Icon name="check" size={14} /> {fromFiles} from subtitle files in the folder</li>{/if}
    {#if fromVideo}<li><Icon name="check" size={14} /> {fromVideo} already inside the video (styles repaired, fonts added)</li>{/if}
    <li><Icon name="check" size={14} /> Fonts the subtitles use are attached to each video</li>
    <li><Icon name="check" size={14} /> Other subtitle tracks stay in the files</li>
    {#if skipped > 0}<li class="muted"><Icon name="dot" size={14} /> {skipped} episode{skipped === 1 ? "" : "s"} in this folder not included</li>{/if}
  </ul>

  <fieldset>
    <legend>Options</legend>
    <label><input type="checkbox" bind:checked={setDefault} /> Make Arabic the default subtitle</label>
    <label><input type="checkbox" bind:checked={sync} /> Sync timing to the audio
      <span class="muted">(slow; only for subtitles made for another release)</span></label>
    <label><input type="checkbox" bind:checked={dryRun} /> Preview only, change nothing</label>
  </fieldset>

  {#snippet footer()}
    <span class="muted grow">Space toggles an episode · Ctrl+Enter opens this dialog</span>
    {#if primaryFirst}
      <button class="btn primary" onclick={apply}>{dryRun ? "Preview" : "Apply"}</button>
      <button class="btn" onclick={close}>Cancel</button>
    {:else}
      <button class="btn" onclick={close}>Cancel</button>
      <button class="btn primary" onclick={apply}>{dryRun ? "Preview" : "Apply"}</button>
    {/if}
  {/snippet}
</Modal>

<style>
  .lead {
    display: flex;
    gap: 14px;
  }
  .icon {
    flex: none;
    width: 34px;
    height: 34px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    background: var(--selected);
    color: var(--accent);
  }
  h2 {
    margin: 4px 0 6px;
    font-size: 17px;
  }
  p {
    margin: 0;
    line-height: 1.5;
  }
  .summary {
    list-style: none;
    margin: 0;
    padding: 6px 0;
    border: 1px solid var(--border);
    border-radius: 6px;
  }
  .summary li {
    display: flex;
    gap: 10px;
    align-items: center;
    padding: 6px 12px;
  }
  .summary li :global(svg) {
    color: var(--ok);
    flex: none;
  }
  .summary li.muted :global(svg) {
    color: var(--idle);
  }
  fieldset {
    border: 0;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  legend {
    font-weight: 600;
    padding: 0 0 8px;
  }
  label {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .grow {
    flex: 1;
    font-size: 12px;
  }
</style>
