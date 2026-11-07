use std::process::Child;
use std::sync::Mutex;
use tauri::Manager;

struct AppState {
    backend_child: Mutex<Option<Child>>,
}

fn kill_sidecar(state: &AppState) {
    if let Ok(mut lock) = state.backend_child.lock() {
        if let Some(mut child) = lock.take() {
            let _ = child.kill();
            log::info!("OnTheSpot backend sidecar terminated cleanly");
        }
    }
}

fn spawn_backend_sidecar() -> Option<Child> {
    let current_exe = std::env::current_exe().ok()?;
    let exe_dir = current_exe.parent()?;

    let binary_name = if cfg!(windows) {
        "ots-backend.exe"
    } else {
        "ots-backend"
    };

    // 1. Direct path (where NSIS on Windows and .app bundle on macOS place the external binary)
    let direct_path = exe_dir.join(binary_name);
    // 2. Binaries subdirectory fallback
    let sub_path = exe_dir.join("binaries").join(binary_name);

    let target_path = if direct_path.is_file() {
        Some(direct_path)
    } else if sub_path.is_file() {
        Some(sub_path)
    } else {
        None
    };

    if let Some(path) = target_path {
        log::info!("Spawning backend from: {:?}", path);
        let mut cmd = std::process::Command::new(path);

        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            // CREATE_NO_WINDOW (0x08000000) prevents command prompt window from showing
            cmd.creation_flags(0x08000000);
        }

        match cmd.spawn() {
            Ok(child) => {
                log::info!("Backend process spawned successfully");
                return Some(child);
            }
            Err(err) => {
                log::error!("Failed to spawn backend: {}", err);
            }
        }
    } else {
        log::warn!("Backend binary not found. If running in dev mode, start backend manually.");
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

            // Spawn the python backend process automatically
            if let Some(child) = spawn_backend_sidecar() {
                let state = app.state::<AppState>();
                if let Ok(mut lock) = state.backend_child.lock() {
                    *lock = Some(child);
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
