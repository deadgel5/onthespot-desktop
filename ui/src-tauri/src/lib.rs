use std::sync::Mutex;
use tauri::Manager;
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandChild;

struct AppState {
    backend_child: Mutex<Option<CommandChild>>,
}

fn kill_sidecar(state: &AppState) {
    if let Ok(mut lock) = state.backend_child.lock() {
        if let Some(child) = lock.take() {
            let _ = child.kill();
            log::info!("OnTheSpot backend sidecar terminated cleanly");
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
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
            let sidecar_result = shell
                .sidecar("binaries/ots-backend")
                .or_else(|_| shell.sidecar("ots-backend"));

            match sidecar_result {
                Ok(sidecar_command) => {
                    match sidecar_command.spawn() {
                        Ok((_rx, child)) => {
                            let state = app.state::<AppState>();
                            if let Ok(mut lock) = state.backend_child.lock() {
                                *lock = Some(child);
                            }
                            log::info!("OnTheSpot backend sidecar spawned successfully");
                        }
                        Err(err) => {
                            log::warn!("Could not spawn backend sidecar: {err}. If running in dev mode, start backend manually.");
                        }
                    }
                }
                Err(err) => {
                    log::warn!("Could not find backend sidecar: {err}. If running in dev mode, start backend manually.");
                }
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                let state = window.state::<AppState>();
                kill_sidecar(&state);
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building OnTheSpot desktop application");

    app.run(|app_handle, event| {
        if let tauri::RunEvent::Exit = event {
            let state = app_handle.state::<AppState>();
            kill_sidecar(&state);
        }
    });
}
