use portable_pty::{CommandBuilder, NativePtySystem, PtySize, PtySystem};
use std::io::{Read, Write};
use std::sync::{Arc, Mutex};
use std::thread;
use tauri::{AppHandle, Emitter, Manager, State};

struct AppState {
    pty_writer: Arc<Mutex<Option<Box<dyn Write + Send>>>>,
}

#[tauri::command]
fn spawn_pty(app: AppHandle, state: State<'_, AppState>) -> Result<(), String> {
    let pty_system = NativePtySystem::default();

    let pair = pty_system
        .openpty(PtySize {
            rows: 24,
            cols: 80,
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

    *state.pty_writer.lock().unwrap() = Some(writer);

    thread::spawn(move || {
        let mut reader = reader;
        let mut buf = [0u8; 1024];
        loop {
            match reader.read(&mut buf) {
                Ok(n) if n > 0 => {
                    let _ = app.emit("pty-output", buf[..n].to_vec());
                }
                _ => break,
            }
        }
    });

    Ok(())
}

#[tauri::command]
fn write_pty(data: String, state: State<'_, AppState>) -> Result<(), String> {
    if let Some(writer) = state.pty_writer.lock().unwrap().as_mut() {
        writer.write_all(data.as_bytes()).map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(AppState {
            pty_writer: Arc::new(Mutex::new(None)),
        })
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![spawn_pty, write_pty])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
