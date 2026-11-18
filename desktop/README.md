# GTD desktop development

Build each target on its native OS. macOS builds require Apple Silicon, macOS 13.5 or later, and the Xcode command-line tools. Windows builds require x64 Windows, Visual Studio Build Tools with the Desktop development with C++ workload and Windows SDK, Microsoft Edge WebView2, and MSYS2 with the UCRT64 toolchain. Both require CPython 3.14, Node.js 24, and stable Rust. Use the python.org universal2 installer on macOS so the Python libraries support the declared macOS deployment target. Use native x64 Python on Windows.

## Build on macOS

From the repository root in an active Python 3.14 virtual environment:

```sh
python -m pip install -r desktop/requirements-build.txt
bash desktop/scripts/build_media.sh
python desktop/scripts/stage_runtime.py
cd desktop
npx --yes --package @tauri-apps/cli@2.12.4 tauri build --target aarch64-apple-darwin --bundles app,dmg -- --locked
cd ..
python desktop/scripts/package_release.py
```

The build produces `GTD.app` and the DMG under `desktop/src-tauri/target/aarch64-apple-darwin/release/bundle`. The last command verifies the packages and writes the distributable DMG, app ZIP, matching media sources, and checksums to `desktop/build/dist`.

## Build on Windows

From the project root in the **MSYS2 UCRT64** shell:

```sh
pacman -S --needed curl make diffutils mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-nasm mingw-w64-ucrt-x86_64-pkgconf
bash desktop/scripts/build_media.sh
```

Then open PowerShell in the project root with an active Python 3.14 virtual environment:

```powershell
python -m pip install -r desktop/requirements-build.txt
python desktop/scripts/stage_runtime.py
Set-Location desktop
npx --yes --package @tauri-apps/cli@2.12.4 tauri build --target x86_64-pc-windows-msvc --bundles nsis -- --locked
Set-Location ..
python desktop/scripts/package_release.py
```

The NSIS installer is built under `desktop/src-tauri/target/x86_64-pc-windows-msvc/release/bundle/nsis`. The last command smoke-tests the portable app and writes the installer, portable ZIP, matching media sources, and checksums to `desktop/build/dist`. On a clean Windows test machine, add `--test-installer` to exercise silent NSIS installation, startup, and removal. CI performs that check on a fresh runner.

## Development and tests

The Tauri window serves the files in `desktop/ui` from its embedded origin. Rust forwards selected operations to the Python process on an OS-assigned loopback port. It hands the process a per-launch token over stdin and keeps the pipe open until exit. Both the direct Web interface and CLI continue to use the same download modules. Desktop task state is stored separately from a source checkout.

After staging the runtime, launch the debug window with `npx --yes --package @tauri-apps/cli@2.12.4 tauri dev` from `desktop`. For rapid Python development, set `GTD_DEV_PYTHON` to the absolute path of a virtual environment's Python executable and create an empty `desktop/src-tauri/runtime` before invoking the debug command. This mode uses the source backend and media tools on `PATH`. Production packages require the bundled runtime.

```sh
python -m unittest discover -s tests -p 'test_*.py'
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python -m unittest discover -s tests/browser -p 'test_*.py'
cargo test --locked --manifest-path desktop/src-tauri/Cargo.toml
```

The native executable supports `--smoke-test`, which initializes the WebView, starts the packaged backend, generates a video using bundled FFmpeg, extracts MP3 through the task queue, and shuts the process down. The package collector invokes it with a minimal system `PATH` and a temporary profile that includes Unicode and spaces. Platform downloads can be checked separately against public URLs or with user-provided cookies in Settings.

## GitHub Actions and versioning

The **Desktop packages** workflow supports manual dispatch from Actions. A manual run produces test artifacts for both architectures. A push of a tag matching `v*` runs the same builds and publishes a GitHub Release after both builds and smoke tests pass. Artifact checksums are verified before publication.

Keep the version in `src-tauri/tauri.conf.json` and `src-tauri/Cargo.toml` identical, refresh `Cargo.lock` using `cargo update --workspace` in `src-tauri`, and use the exact `v<version>` for a release tag. Optional release-specific notes go in `docs/releases/v<version>.md` at the repository root. GitHub also generates change notes. The workflow uses ad-hoc signing on macOS and distributes Windows packages unsigned.

[Third-party components and source archives](scripts/third-party.md)
