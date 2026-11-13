<script lang="ts">
  import Modal from "./Modal.svelte";
  import Icon from "./Icon.svelte";
  import { app } from "./state.svelte";

  let checking = $state(false);
  let copied = $state<string | null>(null);

  let missing = $derived(app.info?.tools.filter((t) => t.required && !t.found) ?? []);
  let hints = $derived([...new Set(missing.map((t) => t.hint))]);
  let ready = $derived(!missing.length && !!app.config?.library_path);

  async function copy(text: string) {
    await navigator.clipboard.writeText(text);
    copied = text;
  }

  async function recheck() {
    checking = true;
    await app.refreshInfo();
    checking = false;
  }

  function finish() {
    app.dialog = null;
    void app.loadShows();
  }
</script>

<Modal title="Set up Anime Studio" width={620} onclose={finish}>
  <ol class="steps">
    <li class:done={!!app.config?.library_path}>
      <span class="num">{#if app.config?.library_path}<Icon name="check" size={12} />{:else}1{/if}</span>
      <div>
        <b>Library folder</b>
        <p class="muted">Each folder inside it is one show.</p>
        <div class="pick">
          <span class="path mono">{app.config?.library_path || "Not chosen"}</span>
          <button class="btn" onclick={() => app.chooseLibrary()}>Choose…</button>
        </div>
      </div>
    </li>
    <li class:done={!missing.length}>
      <span class="num">{#if !missing.length}<Icon name="check" size={12} />{:else}2{/if}</span>
      <div>
        <b>Tools</b>
        {#if missing.length}
          <p class="muted">MKVToolNix and FFmpeg read and write the video files. Run this, then check again:</p>
          {#each hints as hint (hint)}
            <div class="cmd">
              <span class="mono">{hint}</span>
              <button class="btn" onclick={() => copy(hint)}>{copied === hint ? "Copied" : "Copy"}</button>
            </div>
          {/each}
          <button class="btn" disabled={checking} onclick={recheck}>Check again</button>
        {/if}
        <ul class="tools">
          {#each app.info?.tools ?? [] as tool (tool.name)}
            <li>
              <span class:ok={tool.found} class:bad={!tool.found && tool.required} class="mark">
                <Icon name={tool.found ? "check" : "x"} size={12} />
              </span>
              <span class="tool">{tool.name}</span>
              <span class="muted">{tool.found ? "Found" : tool.required ? "Required" : "Optional"}</span>
            </li>
          {/each}
        </ul>
      </div>
    </li>
  </ol>

  {#snippet footer()}
    <span class="grow"></span>
    <button class="btn primary" disabled={!ready} onclick={finish}>Start</button>
  {/snippet}
</Modal>

<style>
  .steps {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 18px;
  }
  .steps > li {
    display: flex;
    gap: 12px;
  }
  .steps > li > div {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .num {
    flex: none;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    font-size: 12px;
    font-weight: 700;
    background: var(--selected);
    color: var(--accent);
  }
  .done .num {
    color: var(--ok);
  }
  p {
    margin: 0;
  }
  .pick,
  .cmd {
    display: flex;
    gap: 8px;
    align-items: center;
  }
  .path,
  .cmd .mono {
    flex: 1;
    min-width: 0;
    padding: 7px 10px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--window);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    user-select: text;
  }
  .tools {
    list-style: none;
    margin: 0;
    padding: 0;
    border: 1px solid var(--border);
    border-radius: 6px;
  }
  .tools li {
    display: flex;
    gap: 10px;
    align-items: center;
    height: 30px;
    padding: 0 10px;
    border-bottom: 1px solid var(--rule);
  }
  .tools li:last-child {
    border-bottom: 0;
  }
  .tool {
    width: 110px;
    font-weight: 600;
  }
  .mark {
    color: var(--idle);
    display: grid;
  }
  .mark.ok {
    color: var(--ok);
  }
  .mark.bad {
    color: var(--bad);
  }
  .grow {
    flex: 1;
  }
</style>
