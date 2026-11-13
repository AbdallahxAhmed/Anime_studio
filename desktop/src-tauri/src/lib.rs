//! Thin native shell: starts the Python backend, relays its JSON-RPC
//! messages to the web UI, and owns the native menu.

use std::sync::Mutex;

use tauri::menu::{Menu, MenuItem, PredefinedMenuItem, Submenu};
use tauri::{AppHandle, Emitter, Manager, RunEvent, State};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

#[derive(Default)]
struct Backend(Mutex<Option<CommandChild>>);

/// Send one JSON-RPC line to the backend.
#[tauri::command]
fn backend_send(line: String, backend: State<'_, Backend>) -> Result<(), String> {
    let mut guard = backend.0.lock().map_err(|e| e.to_string())?;
    let child = guard.as_mut().ok_or("The backend is not running")?;
    let mut bytes = line.into_bytes();
    bytes.push(b'\n');
    child.write(&bytes).map_err(|e| e.to_string())
}

/// Bundled builds run the packaged `anime-studio-core` sidecar.  During
/// development set ANIME_STUDIO_BACKEND_DIR to the repository root to run
/// `python -m src.sidecar` (ANIME_STUDIO_PYTHON picks the interpreter).
fn spawn_backend(app: &AppHandle) -> Result<(), String> {
    let shell = app.shell();
    let command = match std::env::var("ANIME_STUDIO_BACKEND_DIR") {
        Ok(dir) => {
            let python =
                std::env::var("ANIME_STUDIO_PYTHON").unwrap_or_else(|_| "python3".into());
            shell
                .command(python)
                .args(["-m", "src.sidecar"])
                .current_dir(dir)
        }
        Err(_) => shell.sidecar("anime-studio-core").map_err(|e| e.to_string())?,
    };
    let (mut rx, child) = command
        .env("PYTHONIOENCODING", "utf-8")
        .set_raw_out(true)
        .spawn()
        .map_err(|e| e.to_string())?;
    app.state::<Backend>()
        .0
        .lock()
        .map_err(|e| e.to_string())?
        .replace(child);

    let handle = app.clone();
    tauri::async_runtime::spawn(async move {
        let mut pending: Vec<u8> = Vec::new();
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(bytes) => {
                    pending.extend_from_slice(&bytes);
                    while let Some(pos) = pending.iter().position(|b| *b == b'\n') {
                        let line: Vec<u8> = pending.drain(..=pos).collect();
                        let text = String::from_utf8_lossy(&line).trim().to_string();
                        if !text.is_empty() {
                            let _ = handle.emit("backend://message", text);
                        }
                    }
                }
                CommandEvent::Stderr(bytes) => {
                    eprint!("{}", String::from_utf8_lossy(&bytes));
                }
                CommandEvent::Terminated(status) => {
                    let _ = handle.emit("backend://exit", status.code);
                }
                _ => {}
            }
        }
    });
    Ok(())
}

fn build_menu(app: &AppHandle) -> tauri::Result<Menu<tauri::Wry>> {
    let item = |id: &str, label: &str, accel: Option<&str>| {
        MenuItem::with_id(app, id, label, true, accel)
    };
    let file = Submenu::with_items(
        app,
        "File",
        true,
        &[
            &item("add-folder", "Add Folder…", Some("CmdOrCtrl+O"))?,
            &item("import-fonts", "Import Fonts…", None)?,
            &PredefinedMenuItem::separator(app)?,
            &item("preferences", "Preferences…", Some("CmdOrCtrl+,"))?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::quit(app, Some("Quit"))?,
        ],
    )?;
    let library = Submenu::with_items(
        app,
        "Library",
        true,
        &[
            &item("rescan", "Rescan", Some("F5"))?,
            &item("apply", "Apply to Selected…", Some("CmdOrCtrl+Return"))?,
            &item("stop", "Stop After This Episode", None)?,
            &PredefinedMenuItem::separator(app)?,
            &item("history", "History and Undo…", Some("CmdOrCtrl+H"))?,
        ],
    )?;
    let help = Submenu::with_items(app, "Help", true, &[&item("about", "About Anime Studio", None)?])?;
    Menu::with_items(app, &[&file, &library, &help])
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(Backend::default())
        .invoke_handler(tauri::generate_handler![backend_send])
        .menu(build_menu)
        .on_menu_event(|app, event| {
            let _ = app.emit("menu://action", event.id().0.as_str());
        })
        .setup(|app| {
            if let Err(error) = spawn_backend(app.handle()) {
                eprintln!("failed to start backend: {error}");
                let _ = app.handle().emit("backend://exit", Option::<i32>::None);
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Anime Studio");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            // Closing stdin lets the backend finish the current episode and exit.
            if let Ok(mut guard) = handle.state::<Backend>().0.lock() {
                if let Some(child) = guard.take() {
                    drop(child);
                }
            }
        }
    });
}
