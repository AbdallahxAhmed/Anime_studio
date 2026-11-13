export interface Tool {
  name: string;
  required: boolean;
  found: boolean;
  path: string;
  hint: string;
}

export interface Config {
  library_path: string;
  preferred_language: string;
  strict_language: boolean;
  set_default: boolean;
  sync_by_default: boolean;
  proxy: string;
  trash_max_age_days: number;
}

export interface AppInfo {
  version: string;
  platform: string;
  data_dir: string;
  tools: Tool[];
  missing_required_tools: string[];
  config: Config;
}

export interface Season {
  name: string;
  path: string;
  episodes: number;
}

export interface Show {
  name: string;
  path: string;
  episodes: number;
  seasons: Season[];
}

export interface EmbeddedTrack {
  id: number;
  language: string;
  default: boolean;
}

export interface SubtitleInfo {
  kind: "external" | "embedded";
  path?: string;
  name?: string;
  tracks?: EmbeddedTrack[];
}

export type ScanStatus = "ready" | "no_subtitle" | "other_language";

export interface Episode {
  path: string;
  name: string;
  number: number | null;
  subtitle: SubtitleInfo | null;
  status: ScanStatus;
}

export interface EpisodeListing {
  path: string;
  name: string;
  episodes: Episode[];
}

export interface EpisodeResult {
  path: string;
  status: "complete" | "partial" | "failed" | "skipped";
  fonts_attached: number;
  missing_fonts: string[];
  messages: string[];
}

export interface HistoryEpisode {
  path: string;
  show: string;
  status: string;
  restorable: boolean;
}

export interface HistoryRun {
  run_id: string;
  timestamp: string;
  library_path: string;
  shows: string[];
  episodes: HistoryEpisode[];
}

export type BackendEvent =
  | { type: "ready" }
  | { type: "progress"; stage: string; current: number | null; total: number | null; message: string }
  | { type: "log"; level: string; message: string; details: Record<string, string> }
  | { type: "run.started"; run_id: string }
  | { type: "run.finished"; run_id: string; duration_ms: number; episodes: EpisodeResult[] }
  | { type: "run.stopped"; run_id: string }
  | { type: "run.failed"; run_id: string; error: string };
