#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod backend;

use backend::{media_tool, Backend, Connection};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tauri::webview::NewWindowResponse;
use tauri::{AppHandle, Manager, RunEvent, State, WebviewWindowBuilder};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_opener::OpenerExt;

type Service = Mutex<Result<Backend, String>>;

#[tauri::command]
fn renderer_ready(ready: State<'_, Arc<AtomicBool>>) {
    ready.store(true, Ordering::Release);
}

#[tauri::command]
async fn api(
    state: State<'_, Service>,
    path: String,
    body: Option<Value>,
) -> Result<Value, String> {
    let connection = {
        let service = state
            .lock()
            .map_err(|_| "GTD backend state is unavailable.")?;
        service.as_ref().map_err(Clone::clone)?.connection.clone()
    };
    connection.api(&path, body).await
}

#[tauri::command]
async fn pick_path(
    app: AppHandle,
    kind: String,
    initial_dir: Option<PathBuf>,
) -> Result<Option<PathBuf>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let mut chooser = app.dialog().file();
        if let Some(directory) = initial_dir.filter(|dir| dir.is_absolute() && dir.is_dir()) {
            chooser = chooser.set_directory(directory);
        }
        let selection = match kind.as_str() {
            "folder" => chooser.blocking_pick_folder(),
            "video" => chooser
                .add_filter(
                    "Video",
                    &[
                        "mp4", "m4v", "mov", "mkv", "webm", "avi", "ts", "mpg", "mpeg", "flv",
                        "wmv", "ogv",
                    ],
                )
                .blocking_pick_file(),
            "cookie" => chooser.add_filter("Cookies", &["txt"]).blocking_pick_file(),
            _ => return Err("Unknown file selection mode.".into()),
        };
        selection
            .map(|path| path.into_path().map_err(|e| e.to_string()))
            .transpose()
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
fn reveal_path(app: AppHandle, path: PathBuf) -> Result<(), String> {
    if !path.is_absolute() {
        return Err("Expected an absolute path.".into());
    }
    let metadata = path
        .metadata()
        .map_err(|e| format!("Could not find the file or folder: {e}"))?;
    let opener = app.opener();
    if metadata.is_dir() {
        opener.open_path(path.to_string_lossy(), None::<&str>)
    } else if metadata.is_file() {
        opener.reveal_item_in_dir(path)
    } else {
        return Err("Expected a file or folder.".into());
    }
    .map_err(|e| e.to_string())
}

fn stop_backend(app: &AppHandle) {
    if let Some(state) = app.try_state::<Service>() {
        if let Ok(mut guard) = state.lock() {
            let old = std::mem::replace(&mut *guard, Err("GTD is shutting down.".into()));
            if let Ok(backend) = old {
                backend.stop();
            }
        }
    }
}

async fn smoke_test(connection: Connection, runtime: &Path, root: &Path) -> Result<(), String> {
    let capabilities = connection.api("/api/capabilities", None).await?;
    if capabilities["default_download_dir"].as_str().is_none() {
        return Err("Backend did not report a download folder.".into());
    }
    let input = root.join("媒体 smoke test.mp4");
    let ffmpeg = media_tool(runtime, "ffmpeg");
    #[cfg(debug_assertions)]
    let ffmpeg = if ffmpeg.is_file() {
        ffmpeg
    } else {
        PathBuf::from("ffmpeg")
    };
    let mut command = Command::new(ffmpeg);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(windows_sys::Win32::System::Threading::CREATE_NO_WINDOW);
    }
    let status = command
        .args([
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=s=64x64:r=8",
            "-f",
            "lavfi",
            "-i",
            "sine",
            "-t",
            "0.5",
            "-c:v",
            "mpeg4",
            "-c:a",
            "aac",
        ])
        .arg(&input)
        .stdin(Stdio::null())
        .status()
        .map_err(|e| format!("Could not run FFmpeg: {e}"))?;
    if !status.success() {
        return Err("FFmpeg failed to generate a test clip.".into());
    }
    let batch = connection
        .api(
            "/api/desktop/extract",
            Some(json!({
                "path": input, "audio_format": "mp3",
            })),
        )
        .await?;
    let batch_id = batch["batch_id"]
        .as_str()
        .ok_or("Backend did not create an extraction job.")?;
    for _ in 0..75 {
        let batch = connection
            .api(&format!("/api/batch/{batch_id}"), None)
            .await?;
        let task = &batch["tasks"][0];
        if batch["all_done"] == true {
            if task["status"] == "completed"
                && task["result"]["filepath"]
                    .as_str()
                    .is_some_and(|path| Path::new(path).is_file())
            {
                return Ok(());
            }
            return Err(format!("Extraction smoke test failed: {}", task["error"]));
        }
        tokio::time::sleep(Duration::from_millis(200)).await;
    }
    Err("Extraction smoke test timed out.".into())
}

fn main() {
    let smoke = std::env::args_os().any(|arg| arg == "--smoke-test");
    let mut builder = tauri::Builder::default();
    if !smoke {
        builder = builder.plugin(tauri_plugin_single_instance::init(|app, _, _| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.unminimize();
                let _ = window.show();
                let _ = window.set_focus();
            }
        }));
    }

    builder
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            api,
            pick_path,
            reveal_path,
            renderer_ready
        ])
        .setup(move |app| {
            let runtime = app.path().resource_dir()?.join("runtime");
            let smoke_data = smoke.then(tempfile::tempdir).transpose()?;
            let (data, downloads) = if let Some(folder) = &smoke_data {
                (
                    folder.path().join("App Data 应用"),
                    folder.path().join("Downloads 下载"),
                )
            } else {
                let data = app.path().app_local_data_dir()?;
                let downloads = app
                    .path()
                    .download_dir()
                    .unwrap_or_else(|_| data.clone())
                    .join("GTD");
                (data, downloads)
            };

            let backend = Backend::launch(&runtime, &data, &downloads);
            let connection = backend
                .as_ref()
                .map(|b| b.connection.clone())
                .map_err(Clone::clone);
            app.manage(Service::new(backend));
            let ready = Arc::new(AtomicBool::new(false));
            app.manage(ready.clone());
            let window = WebviewWindowBuilder::from_config(app, &app.config().app.windows[0])?
                .on_navigation(|url| {
                    matches!(
                        (url.scheme(), url.host_str()),
                        ("tauri", Some("localhost")) | ("http" | "https", Some("tauri.localhost"))
                    )
                })
                .on_new_window(|_, _| NewWindowResponse::Deny)
                .visible(!smoke)
                .build()?;
            if let Some(folder) = smoke_data {
                let app = window.app_handle().clone();
                tauri::async_runtime::spawn(async move {
                    let result = match connection {
                        Ok(connection) => {
                            let loaded = tokio::time::timeout(Duration::from_secs(15), async {
                                while !ready.load(Ordering::Acquire) {
                                    tokio::time::sleep(Duration::from_millis(100)).await;
                                }
                            })
                            .await;
                            match loaded {
                                Ok(()) => smoke_test(connection, &runtime, folder.path()).await,
                                Err(_) => {
                                    Err("The GTD window could not initialize the renderer.".into())
                                }
                            }
                        }
                        Err(err) => Err(err),
                    };
                    stop_backend(&app);
                    drop(folder);
                    match result {
                        Ok(()) => {
                            println!("GTD desktop smoke test passed");
                            app.exit(0);
                        }
                        Err(err) => {
                            eprintln!("{err}");
                            app.exit(1);
                        }
                    }
                });
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("could not initialize GTD")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                stop_backend(app);
            }
        });
}
