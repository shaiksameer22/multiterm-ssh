use portable_pty::{CommandBuilder, MasterPty, NativePtySystem, PtySize, PtySystem, Child};
use dashmap::DashMap;
use std::io::{Read, Write};
use std::sync::{Arc, Mutex};
use std::thread;
use std::path::PathBuf;
use std::process::Command;
use tauri::{AppHandle, Emitter, Manager, State};
use uuid::Uuid;
use serde::Serialize;

#[derive(Clone, Serialize)]
struct PtyPayload {
    id: String,
    data: Vec<u8>,
}

struct PtyContext {
    writer: Box<dyn Write + Send>,
    master: Box<dyn MasterPty + Send>,
    child: Box<dyn Child + Send + Sync>,
}

struct AppState {
    ptys: DashMap<String, Arc<Mutex<PtyContext>>>,
}

fn ensure_ghost_venv() -> Option<PathBuf> {
    if let Some(home) = dirs::home_dir() {
        let venv_dir = home.join(".multiterm-sandbox").join("venv");
        if !venv_dir.exists() {
            let python_cmd = if cfg!(target_os = "windows") { "python" } else { "python3" };
            let status = Command::new(python_cmd)
                .arg("-m").arg("venv").arg(&venv_dir)
                .status();
            
            if status.is_err() || !status.unwrap().success() {
                return None;
            }
        }
        Some(venv_dir)
    } else {
        None
    }
}

#[tauri::command]
fn spawn_pty(
    app: AppHandle,
    state: State<'_, AppState>,
    rows: u16,
    cols: u16,
    command: Option<String>,
    args: Option<Vec<String>>,
) -> Result<String, String> {
    let pty_system = NativePtySystem::default();

    let pair = pty_system
        .openpty(PtySize {
            rows,
            cols,
            pixel_width: 0,
            pixel_height: 0,
        })
        .map_err(|e| e.to_string())?;

    #[cfg(target_os = "windows")]
    let mut cmd = CommandBuilder::new(command.unwrap_or_else(|| "powershell.exe".to_string()));

    #[cfg(not(target_os = "windows"))]
    let mut cmd = CommandBuilder::new(command.unwrap_or_else(|| "bash".to_string()));

    if let Some(a) = args {
        cmd.args(&a);
    }

    #[cfg(not(target_os = "windows"))]
    cmd.env("TERM", "xterm-256color");

    // Ghost Venv Injection
    if let Some(venv_dir) = ensure_ghost_venv() {
        let bin_dir = if cfg!(target_os = "windows") {
            venv_dir.join("Scripts")
        } else {
            venv_dir.join("bin")
        };
        
        let mut paths = vec![bin_dir];
        if let Some(current_path) = std::env::var_os("PATH") {
            paths.extend(std::env::split_paths(&current_path));
        }
        if let Ok(new_path) = std::env::join_paths(paths) {
            cmd.env("PATH", new_path);
        }
        cmd.env("VIRTUAL_ENV", venv_dir);
    }

    let child = pair.slave.spawn_command(cmd).map_err(|e| e.to_string())?;

    let reader = pair.master.try_clone_reader().map_err(|e| e.to_string())?;
    let writer = pair.master.take_writer().map_err(|e| e.to_string())?;
    
    let id = Uuid::new_v4().to_string();

    let context = PtyContext {
        writer,
        master: pair.master,
        child,
    };

    state.ptys.insert(id.clone(), Arc::new(Mutex::new(context)));

    let thread_id = id.clone();
    let ptys = state.ptys.clone();
    
    thread::spawn(move || {
        let mut reader = reader;
        let mut buf = [0u8; 1024];

        loop {
            match reader.read(&mut buf) {
                Ok(n) if n > 0 => {
                    let chunk = &buf[..n];
                    let _ = app.emit("pty-output", PtyPayload {
                        id: thread_id.clone(),
                        data: chunk.to_vec(),
                    });
                }
                _ => {
                    ptys.remove(&thread_id);
                    break;
                }
            }
        }
    });

    Ok(id)
}

#[tauri::command]
fn write_pty(id: String, data: String, state: State<'_, AppState>) -> Result<(), String> {
    if let Some(pty) = state.ptys.get(&id) {
        let mut pty_guard = pty.lock().unwrap();
        pty_guard.writer.write_all(data.as_bytes()).map_err(|e| e.to_string())?;
        Ok(())
    } else {
        Err("PTY not found or already closed".to_string())
    }
}

#[tauri::command]
fn resize_pty(id: String, rows: u16, cols: u16, state: State<'_, AppState>) -> Result<(), String> {
    if let Some(pty) = state.ptys.get(&id) {
        let mut pty_guard = pty.lock().unwrap();
        pty_guard.master.resize(PtySize {
            rows,
            cols,
            pixel_width: 0,
            pixel_height: 0,
        }).map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
fn close_pty(id: String, state: State<'_, AppState>) -> Result<(), String> {
    if let Some((_, pty)) = state.ptys.remove(&id) {
        let mut pty_guard = pty.lock().unwrap();
        let _ = pty_guard.child.kill();
        let _ = pty_guard.child.wait();
    }
    Ok(())
}

#[tauri::command]
fn append_log(id: String, data: String) -> Result<(), String> {
    if let Some(mut data_dir) = dirs::data_local_dir() {
        data_dir.push("multiterm");
        data_dir.push("logs");
        let _ = std::fs::create_dir_all(&data_dir);
        let log_path = data_dir.join(format!("{}.log", id));
        if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(log_path) {
            let _ = f.write_all(data.as_bytes());
        }
    }
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(AppState {
            ptys: DashMap::new(),
        })
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![spawn_pty, write_pty, resize_pty, close_pty, append_log])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
