use portable_pty::{CommandBuilder, MasterPty, NativePtySystem, PtySize, PtySystem, Child};
use dashmap::DashMap;
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

struct PtyContext {
    writer: Box<dyn Write + Send>,
    master: Box<dyn MasterPty + Send>,
    child: Box<dyn Child + Send + Sync>,
}

struct AppState {
    ptys: DashMap<String, Arc<Mutex<PtyContext>>>,
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
    
    // Setup Auto-Logging
    let log_file = if let Some(home) = dirs::home_dir() {
        let log_dir = home.join(".multiterm-logs");
        if std::fs::create_dir_all(&log_dir).is_ok() {
            let log_path = log_dir.join(format!("{}.log", thread_id));
            std::fs::OpenOptions::new().create(true).append(true).open(log_path).ok()
        } else {
            None
        }
    } else {
        None
    };
    
    thread::spawn(move || {
        let mut reader = reader;
        let mut buf = [0u8; 1024];
        let mut buf_writer = log_file.map(std::io::BufWriter::new);

        loop {
            match reader.read(&mut buf) {
                Ok(n) if n > 0 => {
                    let chunk = &buf[..n];
                    if let Some(f) = &mut buf_writer {
                        let _ = f.write_all(chunk);
                    }
                    
                    let _ = app.emit("pty-output", PtyPayload {
                        id: thread_id.clone(),
                        data: chunk.to_vec(),
                    });
                }
                _ => {
                    // Flush log file
                    if let Some(mut f) = buf_writer {
                        let _ = f.flush();
                    }
                    // Clean up map when process dies naturally
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
    }
    Ok(())
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
        .invoke_handler(tauri::generate_handler![spawn_pty, write_pty, resize_pty, close_pty])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
