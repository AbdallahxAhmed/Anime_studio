<script lang="ts">
  import { app } from "./state.svelte";

  let expanded = $state<Record<string, boolean>>({});

  function isOpen(path: string, hasSeasons: boolean): boolean {
    if (!hasSeasons) return false;
    return expanded[path] ?? app.folder?.startsWith(path) ?? false;
  }
</script>

<nav class="tree" aria-label="Library">
  <div class="root" title={app.config?.library_path}>
    <span class="mono">{app.config?.library_path || "No library folder"}</span>
  </div>
  <ul role="tree">
    {#each app.shows as show (show.path)}
      {@const open = isOpen(show.path, show.seasons.length > 0)}
      <li role="treeitem" aria-expanded={show.seasons.length ? open : undefined}
        aria-selected={app.folder === show.path}>
        <button class="item" class:selected={app.folder === show.path}
          disabled={app.running}
          onclick={() => {
            if (show.seasons.length) expanded[show.path] = !open;
            else app.openFolder(show.path);
          }}>
          <span class="arrow" class:open>{show.seasons.length ? "›" : ""}</span>
          <span class="name">{show.name}</span>
          <span class="count">{show.episodes}</span>
        </button>
        {#if open}
          <ul role="group">
            {#each show.seasons as season (season.path)}
              <li role="treeitem" aria-selected={app.folder === season.path}>
                <button class="item child" class:selected={app.folder === season.path}
                  disabled={app.running} onclick={() => app.openFolder(season.path)}>
                  <span class="name">{season.name}</span>
                  <span class="count">{season.episodes}</span>
                </button>
              </li>
            {/each}
          </ul>
        {/if}
      </li>
    {:else}
      <li class="empty muted">
        {#if app.config?.library_path}No folders with MKV files here.{:else}Choose a library folder to begin.{/if}
      </li>
    {/each}
  </ul>
</nav>

<style>
  .tree {
    width: 240px;
    flex: none;
    background: var(--window);
    border-right: 1px solid var(--border);
    padding: 8px 6px;
    overflow: auto;
  }
  .root {
    padding: 2px 8px 8px;
    color: var(--muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .item {
    position: relative;
    width: 100%;
    height: 30px;
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 0 8px;
    border: 0;
    border-radius: 4px;
    background: none;
    text-align: left;
  }
  .item:hover:not(:disabled) {
    background: var(--hover);
  }
  .item.selected {
    background: var(--nav-selected);
    font-weight: 600;
  }
  .item.selected::before {
    content: "";
    position: absolute;
    left: 0;
    top: 8px;
    width: 3px;
    height: 14px;
    border-radius: 2px;
    background: var(--accent);
  }
  .item.child {
    padding-left: 30px;
  }
  .arrow {
    width: 14px;
    color: var(--muted);
    transition: transform 0.1s;
  }
  .arrow.open {
    transform: rotate(90deg);
  }
  .name {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .count {
    font-size: 12px;
    color: var(--muted);
  }
  .empty {
    padding: 8px;
  }
</style>
