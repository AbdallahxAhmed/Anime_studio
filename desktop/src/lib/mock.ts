// Browser-only stand-in for the Python backend so the UI can be developed and
// reviewed with `npm run dev` without Tauri.  Never used in the desktop app.
import type { Backend } from "./backend";
import type { AppInfo, BackendEvent, Episode, HistoryRun, Show } from "./types";

const ROOT = "D:/Anime";
const SHOW = `${ROOT}/Frieren`;

function episodes(): Episode[] {
  const list: Episode[] = [];
  for (let n = 1; n <= 12; n += 1) {
    const num = String(n).padStart(2, "0");
    const path = `${SHOW}/Season 1/[SubsPlease] Frieren - ${num} (1080p).mkv`;
    const base: Episode = { path, name: path.split("/").pop()!, number: n, subtitle: null, status: "no_subtitle" };
    if (n === 4) {
      base.subtitle = { kind: "embedded", tracks: [{ id: 3, language: "ara", default: false }, { id: 2, language: "eng", default: true }] };
      base.status = "ready";
    } else if (n !== 6 && n !== 11) {
      base.subtitle = { kind: "external", name: `Frieren - ${num}.ass`, path: `${SHOW}/Season 1/Frieren - ${num}.ass` };
      base.status = "ready";
    }
    list.push(base);
  }
  return list;
}

export function createMockBackend(): Backend {
  const listeners: ((e: BackendEvent) => void)[] = [];
  const emit = (event: BackendEvent) => listeners.forEach((l) => l(event));
  let stopping = false;
  const info: AppInfo = {
    version: "3.0.0-dev",
    platform: "Browser preview",
    data_dir: "~/.config/AnimeStudio",
    tools: [
      { name: "ffmpeg", required: true, found: true, path: "/usr/bin/ffmpeg", hint: "" },
      { name: "mkvmerge", required: true, found: true, path: "/usr/bin/mkvmerge", hint: "" },
      { name: "mkvextract", required: true, found: true, path: "/usr/bin/mkvextract", hint: "" },
      { name: "alass", required: false, found: false, path: "", hint: "sudo pacman -S alass" },
    ],
    missing_required_tools: [],
    config: {
      library_path: ROOT,
      preferred_language: "ara",
      strict_language: false,
      set_default: true,
      sync_by_default: false,
      proxy: "",
      trash_max_age_days: 30,
    },
  };
  const shows: Show[] = [
    { name: "Frieren", path: SHOW, episodes: 22, seasons: [
      { name: "Season 1", path: `${SHOW}/Season 1`, episodes: 12 },
      { name: "Season 2", path: `${SHOW}/Season 2`, episodes: 10 },
    ] },
    { name: "Dandadan", path: `${ROOT}/Dandadan`, episodes: 12, seasons: [] },
    { name: "Serial Experiments Lain", path: `${ROOT}/Serial Experiments Lain`, episodes: 13, seasons: [] },
    { name: "Mob Psycho 100", path: `${ROOT}/Mob Psycho 100`, episodes: 25, seasons: [] },
  ];
  const history: HistoryRun[] = [
    { run_id: "r2", timestamp: "2026-10-03T19:40:00+00:00", library_path: ROOT, shows: ["Serial Experiments Lain"],
      episodes: Array.from({ length: 13 }, (_, i) => ({ path: `${ROOT}/Serial Experiments Lain/Lain - ${String(i + 1).padStart(2, "0")}.mkv`, show: "Serial Experiments Lain", status: "success", restorable: true })) },
  ];

  async function run(paths: string[]) {
    emit({ type: "run.started", run_id: "mock" });
    const results = [];
    for (const [index, path] of paths.entries()) {
      if (stopping) break;
      const name = path.split("/").pop()!;
      emit({ type: "progress", stage: "mux", current: index + 1, total: paths.length, message: `Muxing episode: ${name}` });
      emit({ type: "log", level: "info", message: `Attaching fonts to ${name}`, details: {} });
      await new Promise((r) => setTimeout(r, 700));
      emit({ type: "progress", stage: "mux", current: index + 1, total: paths.length, message: `Mux completed: ${name}` });
      results.push({ path, status: index === 2 ? "partial" as const : "complete" as const, fonts_attached: 10, missing_fonts: index === 2 ? ["Hacen Maghreb"] : [], messages: [] });
    }
    if (stopping) emit({ type: "run.stopped", run_id: "mock" });
    else emit({ type: "run.finished", run_id: "mock", duration_ms: 4200, episodes: results });
    stopping = false;
  }

  return {
    async call<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
      await new Promise((r) => setTimeout(r, 80));
      switch (method) {
        case "app.info": return info as T;
        case "config.update": Object.assign(info.config, params); return info.config as T;
        case "library.shows": return shows as T;
        case "library.episodes": return { path: params.path, name: String(params.path).split("/").pop(), episodes: episodes() } as T;
        case "run.start": void run(params.episodes as string[]); return { run_id: "mock" } as T;
        case "run.stop": stopping = true; return { stopping: true } as T;
        case "history.list": return history as T;
        case "history.undo": return { restored: (params.episodes as string[] | undefined)?.length ?? 13, failed: 0, missing: 0 } as T;
        case "fonts.import": return { added: 1, skipped: 0, failed: 0 } as T;
        default: throw new Error(`unknown method ${method}`);
      }
    },
    onEvent(listener) { listeners.push(listener); },
    onExit() {},
  };
}
