<script lang="ts">
  import Modal from "./Modal.svelte";
  import { app } from "./state.svelte";
  import { primaryFirst } from "./platform";

  const config = app.config!;
  let language = $state(config.preferred_language);
  let strict = $state(config.strict_language);
  let setDefault = $state(config.set_default);
  let sync = $state(config.sync_by_default);
  let proxy = $state(config.proxy);

  const languages = [
    ["ara", "Arabic"],
    ["eng", "English"],
    ["fre", "French"],
    ["spa", "Spanish"],
    ["por", "Portuguese"],
    ["ind", "Indonesian"],
    ["tur", "Turkish"],
  ];

  const close = () => (app.dialog = null);
  async function save() {
    await app.updateConfig({
      preferred_language: language,
      strict_language: strict,
      set_default: setDefault,
      sync_by_default: sync,
      proxy,
    });
    close();
  }
</script>

<Modal title="Preferences" width={600} onclose={close}>
  <div class="grid">
    <label for="lang">Subtitle language</label>
    <select id="lang" class="field" bind:value={language}>
      {#each languages as [code, name] (code)}<option value={code}>{name} ({code})</option>{/each}
    </select>
    <label for="lib">Library folder</label>
    <div class="pick">
      <span id="lib" class="mono path">{app.config?.library_path || "Not chosen"}</span>
      <button class="btn" onclick={() => app.chooseLibrary()}>Change…</button>
    </div>
    <label for="proxy">Proxy for font downloads</label>
    <input id="proxy" class="field" placeholder="socks5://127.0.0.1:1080" bind:value={proxy} />
  </div>

  <fieldset>
    <legend>When applying</legend>
    <label><input type="checkbox" bind:checked={setDefault} /> Make the new subtitle the default track</label>
    <label><input type="checkbox" bind:checked={sync} /> Sync timing to the audio by default</label>
    <label><input type="checkbox" bind:checked={strict} /> Skip videos whose built-in subtitles are in another language</label>
  </fieldset>

  {#snippet footer()}
    <span class="grow"></span>
    {#if primaryFirst}
      <button class="btn primary" onclick={save}>OK</button>
      <button class="btn" onclick={close}>Cancel</button>
    {:else}
      <button class="btn" onclick={close}>Cancel</button>
      <button class="btn primary" onclick={save}>OK</button>
    {/if}
  {/snippet}
</Modal>

<style>
  .grid {
    display: grid;
    grid-template-columns: 180px minmax(0, 1fr);
    gap: 10px 14px;
    align-items: center;
  }
  .pick {
    display: flex;
    gap: 8px;
    min-width: 0;
  }
  .path {
    flex: 1;
    min-width: 0;
    padding: 6px 8px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--window);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
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
  fieldset label {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .grow {
    flex: 1;
  }
</style>
