use std::sync::Mutex;
use tauri::Manager;
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandChild;

struct AppState {
    backend_child: Mutex<Option<CommandChild>>,
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(AppState {
            backend_child: Mutex::new(None),
        })
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            // Spawn the python backend sidecar in release mode or if present
            let shell = app.shell();
            if let Ok(sidecar_command) = shell.sidecar("ots-backend") {
                match sidecar_command.spawn() {
                    Ok((_rx, child)) => {
                        let state = app.state::<AppState>();
                        *state.backend_child.lock().unwrap() = Some(child);
                        log::info!("OnTheSpot backend sidecar spawned successfully");
                    }
                    Err(err) => {
                        log::warn!("Could not spawn backend sidecar: {err}. If running in dev mode, start backend manually.");
                    }
                }
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                let state = window.state::<AppState>();
                if let Ok(mut lock) = state.backend_child.lock() {
                    if let Some(child) = lock.take() {
                        let _ = child.kill();
                        log::info!("OnTheSpot backend sidecar terminated cleanly");
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running OnTheSpot desktop application");
}
