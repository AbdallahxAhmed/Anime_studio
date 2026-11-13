import type { BackendEvent } from "./types";
import { createMockBackend } from "./mock";

type Listener = (event: BackendEvent) => void;

export interface Backend {
  call<T>(method: string, params?: Record<string, unknown>): Promise<T>;
  onEvent(listener: Listener): void;
  onExit(listener: (code: number | null) => void): void;
}

interface Pending {
  resolve: (value: unknown) => void;
  reject: (error: Error) => void;
}

const inTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

/** JSON-RPC client over the Tauri shell that relays the Python backend's stdio. */
async function createTauriBackend(): Promise<Backend> {
  const { invoke } = await import("@tauri-apps/api/core");
  const { listen } = await import("@tauri-apps/api/event");
  const pending = new Map<number, Pending>();
  const listeners: Listener[] = [];
  const exitListeners: ((code: number | null) => void)[] = [];
  let nextId = 0;

  await listen<string>("backend://message", ({ payload }) => {
    let message: { id?: number; result?: unknown; error?: { message: string }; params?: BackendEvent };
    try {
      message = JSON.parse(payload);
    } catch {
      return;
    }
    if (typeof message.id === "number" && pending.has(message.id)) {
      const entry = pending.get(message.id)!;
      pending.delete(message.id);
      if (message.error) entry.reject(new Error(message.error.message));
      else entry.resolve(message.result);
    } else if (message.params) {
      for (const listener of listeners) listener(message.params);
    }
  });
  await listen<number | null>("backend://exit", ({ payload }) => {
    for (const [, entry] of pending) entry.reject(new Error("The backend stopped"));
    pending.clear();
    for (const listener of exitListeners) listener(payload);
  });

  return {
    call<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
      const id = ++nextId;
      return new Promise<T>((resolve, reject) => {
        pending.set(id, { resolve: resolve as (v: unknown) => void, reject });
        const line = JSON.stringify({ jsonrpc: "2.0", id, method, params });
        invoke("backend_send", { line }).catch((error: unknown) => {
          pending.delete(id);
          reject(new Error(String(error)));
        });
      });
    },
    onEvent(listener) {
      listeners.push(listener);
    },
    onExit(listener) {
      exitListeners.push(listener);
    },
  };
}

export const backendPromise: Promise<Backend> = inTauri
  ? createTauriBackend()
  : Promise.resolve(createMockBackend());

export const isDesktop = inTauri;
