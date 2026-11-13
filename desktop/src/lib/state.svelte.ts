import { backendPromise, isDesktop, type Backend } from "./backend";
import type {
  AppInfo,
  BackendEvent,
  Config,
  Episode,
  EpisodeListing,
  EpisodeResult,
  HistoryRun,
  Show,
} from "./types";

export type RowPhase = "queued" | "working" | "complete" | "partial" | "failed" | "skipped";

export interface RowRun {
  phase: RowPhase;
  note: string;
}

export interface LogLine {
  time: string;
  level: string;
  message: string;
}

type Dialog = null | "apply" | "history" | "preferences" | "setup" | "about";

function now(): string {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

class AppState {
  backend: Backend | null = null;
  info = $state<AppInfo | null>(null);
  shows = $state<Show[]>([]);
  folder = $state<string | null>(null);
  listing = $state<EpisodeListing | null>(null);
  loading = $state(false);
  checked = $state<Set<string>>(new Set());
  focused = $state<string | null>(null);
  filter = $state("");
  view = $state<"all" | "attention" | "ready">("all");
  running = $state(false);
  stopping = $state(false);
  runRows = $state<Record<string, RowRun>>({});
  stageText = $state("");
  done = $state(0);
  total = $state(0);
  log = $state<LogLine[]>([]);
  dialog = $state<Dialog>(null);
  history = $state<HistoryRun[]>([]);
  error = $state<string | null>(null);
  backendDown = $state(false);

  get config(): Config | null {
    return this.info?.config ?? null;
  }

  get visibleEpisodes(): Episode[] {
    const list = this.listing?.episodes ?? [];
    const needle = this.filter.trim().toLowerCase();
    return list.filter((episode) => {
      if (needle && !episode.name.toLowerCase().includes(needle)) return false;
      if (this.view === "ready") return episode.status === "ready";
      if (this.view === "attention") return episode.status !== "ready";
      return true;
    });
  }

  get selected(): Episode[] {
    return (this.listing?.episodes ?? []).filter(
      (e) => this.checked.has(e.path) && e.status === "ready",
    );
  }

  get focusedEpisode(): Episode | null {
    return this.listing?.episodes.find((e) => e.path === this.focused) ?? null;
  }

  get counts() {
    const list = this.listing?.episodes ?? [];
    return {
      ready: list.filter((e) => e.status === "ready").length,
      none: list.filter((e) => e.status === "no_subtitle").length,
      other: list.filter((e) => e.status === "other_language").length,
    };
  }

  async init() {
    this.backend = await backendPromise;
    this.backend.onEvent((event) => this.handleEvent(event));
    this.backend.onExit(() => {
      this.backendDown = true;
      this.running = false;
    });
    try {
      this.info = await this.backend.call<AppInfo>("app.info");
    } catch (error) {
      this.error = String(error);
      return;
    }
    if (this.info.missing_required_tools.length || !this.info.config.library_path) {
      this.dialog = "setup";
    }
    await this.loadShows();
  }

  async refreshInfo() {
    if (!this.backend) return;
    this.info = await this.backend.call<AppInfo>("app.info");
  }

  async loadShows() {
    if (!this.backend || !this.info?.config.library_path) return;
    this.shows = await this.backend.call<Show[]>("library.shows");
    if (!this.folder && this.shows.length) {
      const first = this.shows[0];
      await this.openFolder(first.seasons[0]?.path ?? first.path);
    }
  }

  async openFolder(path: string) {
    if (!this.backend || this.running) return;
    this.folder = path;
    this.loading = true;
    this.runRows = {};
    try {
      this.listing = await this.backend.call<EpisodeListing>("library.episodes", { path });
      this.checked = new Set(
        this.listing.episodes.filter((e) => e.status === "ready").map((e) => e.path),
      );
      this.focused = this.listing.episodes[0]?.path ?? null;
    } catch (error) {
      this.error = String(error);
    } finally {
      this.loading = false;
    }
  }

  async rescan() {
    await this.loadShows();
    if (this.folder) await this.openFolder(this.folder);
  }

  toggle(path: string) {
    const next = new Set(this.checked);
    if (next.has(path)) next.delete(path);
    else next.add(path);
    this.checked = next;
  }

  toggleAll() {
    const ready = (this.listing?.episodes ?? []).filter((e) => e.status === "ready");
    const allOn = ready.every((e) => this.checked.has(e.path));
    this.checked = new Set(allOn ? [] : ready.map((e) => e.path));
  }

  async chooseLibrary() {
    let picked: string | null = null;
    if (isDesktop) {
      const { open } = await import("@tauri-apps/plugin-dialog");
      const result = await open({ directory: true, title: "Choose your anime library folder" });
      picked = typeof result === "string" ? result : null;
    } else {
      picked = window.prompt("Library folder", this.config?.library_path ?? "") ?? null;
    }
    if (!picked) return;
    await this.updateConfig({ library_path: picked });
    this.folder = null;
    this.listing = null;
    await this.loadShows();
  }

  async updateConfig(patch: Partial<Config>) {
    if (!this.backend || !this.info) return;
    const config = await this.backend.call<Config>("config.update", patch);
    this.info = { ...this.info, config };
  }

  async importFonts() {
    if (!this.backend || !isDesktop) return;
    const { open, message } = await import("@tauri-apps/plugin-dialog");
    const files = await open({
      multiple: true,
      title: "Import fonts",
      filters: [{ name: "Fonts", extensions: ["ttf", "otf", "ttc", "otc"] }],
    });
    const paths = Array.isArray(files) ? files : files ? [files] : [];
    if (!paths.length) return;
    const result = await this.backend.call<{ added: number; skipped: number; failed: number }>(
      "fonts.import",
      { paths },
    );
    await message(
      `${result.added} added, ${result.skipped} already in the cache, ${result.failed} could not be read.`,
      { title: "Import fonts" },
    );
  }

  async apply(options: { sync: boolean; dryRun: boolean; setDefault: boolean }) {
    if (!this.backend || !this.listing || !this.folder) return;
    const episodes = this.selected;
    if (!episodes.length) return;
    if (this.config && options.setDefault !== this.config.set_default) {
      await this.updateConfig({ set_default: options.setDefault });
    }
    this.dialog = null;
    this.runRows = Object.fromEntries(
      episodes.map((e) => [e.path, { phase: "queued" as RowPhase, note: "Waiting" }]),
    );
    this.done = 0;
    this.total = episodes.length;
    this.stageText = "Checking subtitles and finding fonts…";
    this.log = [];
    this.running = true;
    this.stopping = false;
    try {
      await this.backend.call("run.start", {
        show_path: this.folder,
        episodes: episodes.map((e) => e.path),
        sync: options.sync,
        dry_run: options.dryRun,
      });
    } catch (error) {
      this.running = false;
      this.error = String(error);
    }
  }

  async stop() {
    if (!this.backend || !this.running) return;
    this.stopping = true;
    await this.backend.call("run.stop");
  }

  private rowByName(name: string): string | null {
    const episode = this.listing?.episodes.find((e) => e.name === name);
    return episode?.path ?? null;
  }

  private setRow(path: string | null, phase: RowPhase, note: string) {
    if (!path || !(path in this.runRows)) return;
    this.runRows = { ...this.runRows, [path]: { phase, note } };
  }

  private handleEvent(event: BackendEvent) {
    switch (event.type) {
      case "progress": {
        if (event.stage === "mux") {
          const [verb, ...rest] = event.message.split(": ");
          const path = this.rowByName(rest.join(": "));
          if (verb === "Muxing episode") {
            this.stageText = "Writing files";
            this.setRow(path, "working", "Writing new file and checking it");
          } else if (verb === "Mux completed" || verb === "Mux failed") {
            this.done = event.current ?? this.done;
            this.setRow(
              path,
              verb === "Mux failed" ? "failed" : "complete",
              verb === "Mux failed" ? "Failed · original kept" : "Done · checked and replaced",
            );
          }
        }
        break;
      }
      case "log": {
        if (event.level !== "info" || this.log.length < 400) {
          this.log = [...this.log.slice(-399), { time: now(), level: event.level, message: event.message }];
        }
        break;
      }
      case "run.finished":
        this.finish(event.episodes);
        break;
      case "run.stopped":
        this.running = false;
        this.stopping = false;
        this.stageText = "Stopped. Finished episodes stay applied and can be undone.";
        for (const [path, row] of Object.entries(this.runRows)) {
          if (row.phase === "queued" || row.phase === "working") this.setRow(path, "skipped", "Not started");
        }
        break;
      case "run.failed":
        this.running = false;
        this.error = event.error;
        break;
    }
  }

  private finish(results: EpisodeResult[]) {
    for (const result of results) {
      const note =
        result.status === "complete"
          ? `Done · ${result.fonts_attached} fonts`
          : result.status === "partial"
            ? result.missing_fonts.length
              ? `Done · missing ${result.missing_fonts.join(", ")}`
              : "Done with warnings"
            : result.status === "failed"
              ? result.messages[0] ?? "Failed · original kept"
              : "Skipped";
      this.setRow(result.path, result.status, note);
    }
    const applied = results.filter((r) => r.status === "complete" || r.status === "partial");
    const ok = applied.length;
    // Applied episodes are done: leave them unselected so a second click on
    // Apply never processes them again.
    const next = new Set(this.checked);
    for (const result of applied) next.delete(result.path);
    this.checked = next;
    this.running = false;
    this.done = this.total;
    this.stageText = `${ok} of ${this.total} episodes applied.`;
  }

  async openHistory() {
    if (!this.backend) return;
    this.history = await this.backend.call<HistoryRun[]>("history.list");
    this.dialog = "history";
  }

  async undo(runId: string, episodes: string[]) {
    if (!this.backend) return null;
    const result = await this.backend.call<{ restored: number; failed: number; missing: number }>(
      "history.undo",
      { run_id: runId, episodes },
    );
    this.history = await this.backend.call<HistoryRun[]>("history.list");
    if (this.folder) await this.openFolder(this.folder);
    return result;
  }
}

export const app = new AppState();
