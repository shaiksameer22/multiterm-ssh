use portable_pty::{CommandBuilder, MasterPty, NativePtySystem, PtySize, PtySystem};
use std::collections::HashMap;
use std::io::{Read, Write};
use std::sync::{Arc, Mutex};
use std::thread;
use tauri::{AppHandle, Emitter, Manager, State};
use uuid::Uuid;
use serde::Serialize;

#[derive(Clone, Serialize)]
struct PtyPayload {
    id: String,
    data: Vec<u8>,
}

struct AppState {
    pty_writers: Arc<Mutex<HashMap<String, Box<dyn Write + Send>>>>,
    pty_masters: Arc<Mutex<HashMap<String, Box<dyn MasterPty + Send>>>>,
}

#[tauri::command]
fn spawn_pty(
    app: AppHandle,
    state: State<'_, AppState>,
    rows: u16,
    cols: u16,
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
    let cmd = CommandBuilder::new("cmd.exe");

    #[cfg(not(target_os = "windows"))]
    let mut cmd = CommandBuilder::new("bash");

    #[cfg(not(target_os = "windows"))]
    cmd.env("TERM", "xterm-256color");

    let _child = pair.slave.spawn_command(cmd).map_err(|e| e.to_string())?;

    let reader = pair.master.try_clone_reader().map_err(|e| e.to_string())?;
    let writer = pair.master.take_writer().map_err(|e| e.to_string())?;
    
    let id = Uuid::new_v4().to_string();

    state.pty_writers.lock().unwrap().insert(id.clone(), writer);
    state.pty_masters.lock().unwrap().insert(id.clone(), pair.master);

    let thread_id = id.clone();
    thread::spawn(move || {
        let mut reader = reader;
        let mut buf = [0u8; 1024];
        loop {
            match reader.read(&mut buf) {
                Ok(n) if n > 0 => {
                    let _ = app.emit("pty-output", PtyPayload {
                        id: thread_id.clone(),
                        data: buf[..n].to_vec(),
                    });
                }
                _ => break,
            }
        }
    });

    Ok(id)
}

#[tauri::command]
fn write_pty(id: String, data: String, state: State<'_, AppState>) -> Result<(), String> {
    if let Some(writer) = state.pty_writers.lock().unwrap().get_mut(&id) {
        writer.write_all(data.as_bytes()).map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
fn resize_pty(id: String, rows: u16, cols: u16, state: State<'_, AppState>) -> Result<(), String> {
    if let Some(master) = state.pty_masters.lock().unwrap().get_mut(&id) {
        master.resize(PtySize {
            rows,
            cols,
            pixel_width: 0,
            pixel_height: 0,
        }).map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(AppState {
            pty_writers: Arc::new(Mutex::new(HashMap::new())),
            pty_masters: Arc::new(Mutex::new(HashMap::new())),
        })
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![spawn_pty, write_pty, resize_pty])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
