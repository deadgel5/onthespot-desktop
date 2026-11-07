use std::sync::Mutex;
use tauri::Manager;
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandChild;

enum BackendProcess {
    Tauri(CommandChild),
    Std(std::process::Child),
}

struct AppState {
    backend_child: Mutex<Option<BackendProcess>>,
}

fn kill_sidecar(state: &AppState) {
    if let Ok(mut lock) = state.backend_child.lock() {
        if let Some(child) = lock.take() {
            match child {
                BackendProcess::Tauri(c) => {
                    let _ = c.kill();
                }
                BackendProcess::Std(mut c) => {
                    let _ = c.kill();
                }
            }
            log::info!("OnTheSpot backend sidecar terminated cleanly");
        }
    }
}

fn try_spawn_direct_backend() -> Option<std::process::Child> {
    let current_exe = std::env::current_exe().ok()?;
    let exe_dir = current_exe.parent()?;

    let candidate_names = if cfg!(windows) {
        vec!["ots-backend.exe", "binaries/ots-backend.exe"]
    } else {
        vec!["ots-backend", "binaries/ots-backend"]
    };

    for name in candidate_names {
        let candidate_path = exe_dir.join(name);
        if candidate_path.is_file() {
            log::info!("Found backend binary at: {:?}", candidate_path);
            let mut cmd = std::process::Command::new(&candidate_path);

            #[cfg(windows)]
            {
                use std::os::windows::process::CommandExt;
                // CREATE_NO_WINDOW flag (0x08000000) prevents console popup
                cmd.creation_flags(0x08000000);
            }

            match cmd.spawn() {
                Ok(child) => {
                    log::info!("Spawned backend process directly via std::process");
                    return Some(child);
                }
                Err(err) => {
                    log::error!("Failed to spawn direct backend at {:?}: {}", candidate_path, err);
                }
            }
        }
    }

    None
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

            let mut spawned = false;

            if let Ok(sidecar_command) = sidecar_result {
                if let Ok((_rx, child)) = sidecar_command.spawn() {
                    let state = app.state::<AppState>();
                    if let Ok(mut lock) = state.backend_child.lock() {
                        *lock = Some(BackendProcess::Tauri(child));
                        spawned = true;
                    }
                    log::info!("OnTheSpot backend sidecar spawned successfully via Tauri shell");
                }
            }

            // Fallback: spawn direct binary next to the current executable (NSIS install directory)
            if !spawned {
                if let Some(child) = try_spawn_direct_backend() {
                    let state = app.state::<AppState>();
                    if let Ok(mut lock) = state.backend_child.lock() {
                        *lock = Some(BackendProcess::Std(child));
                    }
                } else {
                    log::warn!("Could not find backend binary. If running in dev mode, start backend manually.");
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
