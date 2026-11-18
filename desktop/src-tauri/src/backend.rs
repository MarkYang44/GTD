use reqwest::{redirect::Policy, Client, Method};
use serde_json::Value;
use std::ffi::OsString;
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::mpsc;
use std::time::{Duration, Instant};
use std::{env, thread};
use uuid::Uuid;

#[derive(Clone)]
pub struct Connection {
    addr: String,
    token: String,
    client: Client,
}

impl Connection {
    pub async fn api(&self, path: &str, body: Option<Value>) -> Result<Value, String> {
        if !allowed(path, body.is_some()) {
            return Err("Unsupported desktop operation.".into());
        }
        let method = if body.is_some() {
            Method::POST
        } else {
            Method::GET
        };
        let mut req = self
            .client
            .request(method, format!("{}{path}", self.addr))
            .bearer_auth(&self.token);
        if let Some(body) = body {
            req = req.json(&body);
        }
        let response = req
            .send()
            .await
            .map_err(|e| format!("Could not reach GTD: {e}"))?;
        let status = response.status();
        let data = response
            .json::<Value>()
            .await
            .map_err(|_| format!("GTD returned HTTP {status}."))?;
        if status.is_success() {
            Ok(data)
        } else {
            Err(data.to_string())
        }
    }
}

fn allowed(path: &str, post: bool) -> bool {
    fn id(value: &str) -> bool {
        value.len() == 32 && value.bytes().all(|c| c.is_ascii_hexdigit())
    }
    match (post, path.split('/').collect::<Vec<_>>().as_slice()) {
        (_, ["", "api", "desktop", "settings"]) => true,
        (true, ["", "api", "desktop", "cookies" | "extract" | "batch-action"]) => true,
        (true, ["", "api", "preview" | "download"]) => true,
        (false, ["", "api", "capabilities" | "batches"]) => true,
        (false, ["", "api", "batch", batch]) => id(batch),
        (true, ["", "api", "batch", batch, "retry-failed"]) => id(batch),
        (true, ["", "api", "batch", batch, "task", task, "cancel" | "retry" | "redownload"]) => {
            id(batch) && id(task)
        }
        _ => false,
    }
}

pub struct Backend {
    process: Process,
    pub connection: Connection,
}

impl Backend {
    pub fn launch(runtime: &Path, data: &Path, downloads: &Path) -> Result<Self, String> {
        std::fs::create_dir_all(data)
            .map_err(|e| format!("Could not create GTD data folder: {e}"))?;
        let client = Client::builder()
            .no_proxy()
            .redirect(Policy::none())
            .connect_timeout(Duration::from_secs(3))
            .timeout(Duration::from_secs(150))
            .build()
            .map_err(|e| e.to_string())?;

        let mut command = backend_command(runtime)?;
        command
            .arg("--data-dir")
            .arg(data)
            .arg("--download-dir")
            .arg(downloads)
            .current_dir(data)
            .env("PATH", runtime_path(runtime)?)
            .env("PYTHONUTF8", "1")
            .env_remove("PYTHONPATH")
            .env_remove("PYTHONHOME")
            .env_remove("NODE_OPTIONS")
            .env_remove("NODE_PATH")
            .env("NoDefaultCurrentDirectoryInExePath", "1")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit());
        let mut process = Process::spawn(command)?;
        let token = format!("{}{}", Uuid::new_v4().simple(), Uuid::new_v4().simple());
        let pipe = process
            .stdin
            .as_mut()
            .ok_or("GTD backend pipe is missing.")?;
        writeln!(pipe, "{token}").map_err(|e| format!("GTD backend could not start: {e}"))?;

        let stdout = process
            .child
            .stdout
            .take()
            .ok_or("GTD backend output is missing.")?;
        let (tx, rx) = mpsc::sync_channel(1);
        thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            let mut frame = String::new();
            let ready = reader
                .read_line(&mut frame)
                .ok()
                .and_then(|_| frame.trim().strip_prefix("GTD_READY ")?.parse::<u16>().ok());
            let _ = tx.send(ready.filter(|p| *p != 0));
            let _ = std::io::copy(&mut reader, &mut std::io::sink());
        });
        let port = rx
            .recv_timeout(Duration::from_secs(25))
            .map_err(|_| "GTD backend did not become ready within 25 seconds.".to_string())?
            .ok_or("GTD backend stopped during startup.")?;
        Ok(Self {
            process,
            connection: Connection {
                addr: format!("http://127.0.0.1:{port}"),
                token,
                client,
            },
        })
    }

    pub fn stop(self) {
        drop(self.process);
    }
}

fn backend_command(runtime: &Path) -> Result<Command, String> {
    #[cfg(debug_assertions)]
    if let Some(python) = env::var_os("GTD_DEV_PYTHON") {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let mut command = Command::new(python);
        command.arg(root.join("desktop_backend.py"));
        return Ok(command);
    }

    let executable = runtime.join("backend").join(exe_name("gtd-backend"));
    if !executable.is_file() {
        return Err("GTD’s bundled Python backend is missing. Reinstall the application.".into());
    }
    for tool in ["ffmpeg", "ffprobe", "node"] {
        if !media_tool(runtime, tool).is_file() {
            return Err(format!(
                "GTD’s bundled {tool} is missing. Reinstall the application."
            ));
        }
    }
    Ok(Command::new(executable))
}

pub fn media_tool(runtime: &Path, name: &str) -> PathBuf {
    runtime.join("bin").join(exe_name(name))
}

fn exe_name(name: &str) -> String {
    format!("{name}{}", env::consts::EXE_SUFFIX)
}

fn runtime_path(runtime: &Path) -> Result<OsString, String> {
    let bundled = runtime.join("bin");
    let host = env::var_os("PATH").unwrap_or_default();
    env::join_paths(std::iter::once(bundled).chain(env::split_paths(&host)))
        .map_err(|e| format!("Invalid GTD runtime path: {e}"))
}

struct Process {
    child: Child,
    stdin: Option<ChildStdin>,
    #[cfg(windows)]
    _job: windows_job::Job,
}

impl Process {
    fn spawn(mut command: Command) -> Result<Self, String> {
        #[cfg(unix)]
        {
            use std::os::unix::process::CommandExt;
            command.process_group(0).arg("--owned-process-group");
        }
        #[cfg(windows)]
        let job = {
            use std::os::windows::process::CommandExt;
            use windows_sys::Win32::System::Threading::CREATE_NO_WINDOW;
            command.creation_flags(CREATE_NO_WINDOW);
            windows_job::Job::new().map_err(|e| format!("Could not isolate GTD backend: {e}"))?
        };
        let mut child = command
            .spawn()
            .map_err(|e| format!("Could not launch GTD backend: {e}"))?;
        #[cfg(windows)]
        if let Err(e) = job.attach(&child) {
            let _ = child.kill();
            let _ = child.wait();
            return Err(format!("Could not isolate GTD backend: {e}"));
        }
        let stdin = child.stdin.take();
        Ok(Self {
            child,
            stdin,
            #[cfg(windows)]
            _job: job,
        })
    }

    #[cfg(unix)]
    fn has_exited(&mut self) -> bool {
        // Keep the group leader's PID reserved until the group has been killed.
        let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
        let status = unsafe {
            libc::waitid(
                libc::P_PID,
                self.child.id() as libc::id_t,
                &mut info,
                libc::WEXITED | libc::WNOHANG | libc::WNOWAIT,
            )
        };
        status == 0 && unsafe { info.si_pid() } != 0
    }

    #[cfg(windows)]
    fn has_exited(&mut self) -> bool {
        matches!(self.child.try_wait(), Ok(Some(_)))
    }
}

impl Drop for Process {
    fn drop(&mut self) {
        drop(self.stdin.take());
        let deadline = Instant::now() + Duration::from_millis(3_000);
        while Instant::now() < deadline && !self.has_exited() {
            thread::sleep(Duration::from_millis(30));
        }

        #[cfg(unix)]
        {
            // The sidecar leads a private group. FFmpeg and Node inherit it.
            unsafe { libc::killpg(self.child.id() as libc::pid_t, libc::SIGKILL) };
        }
        let _ = self.child.kill();
        let _ = self.child.wait();
        // Closing the Windows job handle kills any remaining descendants.
    }
}

#[cfg(windows)]
mod windows_job {
    use std::io;
    use std::os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle};
    use std::process::Child;
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
        SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };

    pub struct Job(OwnedHandle);

    impl Job {
        pub fn new() -> io::Result<Self> {
            let raw = unsafe { CreateJobObjectW(std::ptr::null(), std::ptr::null()) };
            if raw.is_null() {
                return Err(io::Error::last_os_error());
            }
            let handle = unsafe { OwnedHandle::from_raw_handle(raw) };
            let mut limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            let ok = unsafe {
                SetInformationJobObject(
                    handle.as_raw_handle(),
                    JobObjectExtendedLimitInformation,
                    (&limits as *const JOBOBJECT_EXTENDED_LIMIT_INFORMATION).cast(),
                    std::mem::size_of_val(&limits) as u32,
                )
            };
            if ok == 0 {
                return Err(io::Error::last_os_error());
            }
            Ok(Self(handle))
        }

        pub fn attach(&self, child: &Child) -> io::Result<()> {
            if unsafe { AssignProcessToJobObject(self.0.as_raw_handle(), child.as_raw_handle()) }
                == 0
            {
                return Err(io::Error::last_os_error());
            }
            Ok(())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::allowed;

    #[test]
    fn only_explicit_json_routes_are_forwarded() {
        let id = "37a9154304876b0bfefcfbc406021da7";
        assert!(allowed("/api/desktop/settings", false));
        assert!(allowed("/api/desktop/settings", true));
        assert!(allowed(&format!("/api/batch/{id}/task/{id}/cancel"), true));
        for path in [
            "//127.0.0.1",
            "/api/batches?key=secret",
            "/api/download",
            "/api/batch/../batches",
            "/api/desktop/%2fsettings",
            "/",
        ] {
            assert!(!allowed(path, false), "{path}");
        }
    }

    #[cfg(unix)]
    #[test]
    fn shutdown_reaps_group_even_when_its_leader_already_exited() {
        use super::*;

        let mut command = Command::new("/bin/sh");
        command
            .args(["-c", "sleep 30 & printf 'started\\n'; exit 1"])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped());
        let mut process = Process::spawn(command).unwrap();
        let mut stdout = BufReader::new(process.child.stdout.take().unwrap());
        let mut started = String::new();
        stdout.read_line(&mut started).unwrap();
        assert_eq!(started, "started\n");

        let (tx, rx) = mpsc::channel();
        thread::spawn(move || {
            let count = stdout.read_line(&mut String::new()).unwrap();
            let _ = tx.send(count);
        });
        drop(process);
        // The sleeping child also held the pipe open. EOF proves it was killed.
        assert_eq!(rx.recv_timeout(Duration::from_secs(2)).unwrap(), 0);
    }
}
