"""Stage the native programs and the frozen Python sidecar for Tauri."""

import argparse
from hashlib import file_digest
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import urllib.request
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "desktop" / "build"
RUNTIME = ROOT / "desktop" / "src-tauri" / "runtime"
TARGETS = {"Darwin": "aarch64-apple-darwin", "Windows": "x86_64-pc-windows-msvc"}
MACH_O_MAGIC = {
    b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xce",
    b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf", b"\xbe\xba\xfe\xca", b"\xbf\xba\xfe\xca",
}
NODE_VERSION = "24.22.3"
NODE_ARCHIVES = {
    "Darwin": ("darwin-arm64.tar.xz", "1d64136c8a43d648d1b3bad10797a4c995b1ca032d2bde8799de43b37f058fe5"),
    "Windows": ("win-x64.zip", "e612af99f626ab415ea225af6bce5c971feb448cb5cae250bb1c3fa50c5f7d9f"),
}


def download(url: str, path: Path, expected: str) -> None:
    if not path.is_file():
        partial = path.with_suffix(path.suffix + ".part")
        try:
            with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as output:
                shutil.copyfileobj(response, output)
            partial.replace(path)
        finally:
            partial.unlink(missing_ok=True)
    with path.open("rb") as downloaded:
        actual = file_digest(downloaded, "sha256").hexdigest()
    if actual != expected:
        raise ValueError(f"Incorrect SHA-256 for {path}. Remove it before retrying.")


def stage_node(system: str, runtime: Path) -> None:
    archive_name, checksum = NODE_ARCHIVES[system]
    name = f"node-v{NODE_VERSION}-{archive_name}"
    archive = BUILD / name
    download(f"https://nodejs.org/dist/v{NODE_VERSION}/{name}", archive, checksum)
    license_path = runtime / "licenses" / "Node.js.txt"
    if system == "Windows":
        directory = archive.stem
        with ZipFile(archive) as bundle:
            (runtime / "bin" / "node.exe").write_bytes(bundle.read(f"{directory}/node.exe"))
            license_path.write_bytes(bundle.read(f"{directory}/LICENSE"))
    else:
        directory = name.removesuffix(".tar.xz")
        binary = runtime / "bin" / "node"
        with tarfile.open(archive) as bundle:
            with bundle.extractfile(f"{directory}/bin/node") as node, binary.open("wb") as output:
                shutil.copyfileobj(node, output)
            with bundle.extractfile(f"{directory}/LICENSE") as license_file:
                license_path.write_bytes(license_file.read())
        binary.chmod(0o755)


def stage_system_media(runtime: Path) -> None:
    for command in ("ffmpeg", "ffprobe", "node", "aria2c"):
        binary = shutil.which(command)
        if binary is None:
            if command == "aria2c":
                continue
            raise FileNotFoundError(f"{command} is required on PATH for --system-media")
        shutil.copy2(binary, runtime / "bin" / Path(binary).name)
    (runtime / "DEVELOPMENT-TOOLS.txt").write_text(
        "Development bundle. Uses this build machine's system tools.\n", encoding="utf-8"
    )


def stage_python(runtime: Path) -> None:
    env = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(BUILD / "pyinstaller-cache"))
    command = [
        sys.executable, "-m", "PyInstaller", "--onedir", "--console",
        "--noconfirm", "--name", "gtd-backend", "--distpath", str(BUILD / "python-dist"),
        "--specpath", str(BUILD), "--workpath", str(BUILD / "python-work"),
        "--paths", str(ROOT), "--collect-submodules", "yt_dlp",
        "--collect-all", "yt_dlp_ejs", "--collect-all", "curl_cffi", "--collect-data", "certifi",
        "--add-data", f"{ROOT / 'assets' / 'fallback_covers'}:assets/fallback_covers",
        str(ROOT / "desktop_backend.py"),
    ]
    subprocess.run(command, check=True, env=env, cwd=ROOT)
    shutil.copytree(BUILD / "python-dist" / "gtd-backend", runtime / "backend", symlinks=True)


def stage_python_licenses(directory: Path) -> None:
    summaries = [f"CPython {platform.python_version()} — https://www.python.org/psf/license/"]
    candidates = (Path(sysconfig.get_path("stdlib")) / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE.txt")
    for candidate in candidates:
        if candidate.is_file():
            shutil.copyfile(candidate, directory / "CPython.txt")
            break
    else:
        raise FileNotFoundError("The CPython distribution must supply LICENSE.txt")
    for dist in sorted(metadata.distributions(), key=lambda item: item.metadata["Name"].lower()):
        name = dist.metadata["Name"]
        if name in ("pip", "wheel"):
            continue
        summaries.append(f"{name} {dist.version} — https://pypi.org/project/{name}/{dist.version}/")
        for entry in dist.files or ():
            if entry.name.lower().startswith(("license", "licence", "copying", "notice", "copyright")):
                target = directory / name / entry.name
                target.parent.mkdir(exist_ok=True)
                shutil.copyfile(dist.locate_file(entry), target)
    (directory / "Python-distributions.txt").write_text("\n".join(summaries) + "\n", encoding="utf-8")


def stage_rust_licenses(system: str, directory: Path) -> None:
    manifest = RUNTIME.parent / "Cargo.toml"
    command = ["cargo", "metadata", "--format-version", "1", "--locked", "--filter-platform",
               TARGETS[system], "--manifest-path", str(manifest)]
    packages = json.loads(subprocess.check_output(command, text=True, encoding="utf-8"))["packages"]
    summaries = []
    for package in sorted(packages, key=lambda item: (item["name"], item["version"])):
        if package["source"] is None:
            continue
        name, version = package["name"], package["version"]
        summaries.append(f"{name} {version} — {package['license'] or 'see license file'} — https://crates.io/crates/{name}/{version}")
        crate = Path(package["manifest_path"]).parent
        entries = [entry for entry in crate.iterdir() if entry.is_file() and entry.name.lower().startswith(
            ("license", "licence", "copying", "notice", "copyright"))]
        if package["license_file"]:
            entries.append(crate / package["license_file"])
        for entry in entries:
            target = directory / "rust" / f"{name}-{version}" / entry.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(entry, target)
    (directory / "Rust-crates.txt").write_text("\n".join(summaries) + "\n", encoding="utf-8")


def verify_macos_binaries(directory: Path) -> None:
    """Reject a package containing an arm64 binary built for a newer macOS."""
    def version_tuple(value):
        return tuple(int(part) for part in (value + ".0.0").split(".")[:3])

    config = json.loads((RUNTIME.parent / "tauri.conf.json").read_text(encoding="utf-8"))
    minimum = config["bundle"]["macOS"]["minimumSystemVersion"]
    accepted = version_tuple(minimum)
    invalid = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        with path.open("rb") as handle:
            if handle.read(4) not in MACH_O_MAGIC:
                continue
        try:
            headers = subprocess.check_output(["otool", "-arch", "arm64", "-l", str(path)],
                                              text=True, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError:
            invalid.append(f"{path.relative_to(directory)} (arm64 slice unavailable)")
            continue
        reported = re.search(r"^\s*minos\s+(\d+(?:\.\d+){0,2})\s*$", headers, re.MULTILINE)
        if reported is None:
            reported = re.search(r"cmd LC_VERSION_MIN_MACOSX\s+cmdsize \d+\s+version (\d+(?:\.\d+){0,2})", headers)
        if reported is None or version_tuple(reported[1]) > accepted:
            invalid.append(f"{path.relative_to(directory)} (minimum {reported[1] if reported else 'unknown'})")
    if invalid:
        raise ValueError(f"Binaries incompatible with macOS {minimum}:\n" + "\n".join(invalid)
                         + "\nUse the official python.org universal2 CPython and rebuild.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system-media", action="store_true", help="Use tools on PATH for local development only")
    args = parser.parse_args()
    system, machine = platform.system(), platform.machine().lower()
    if (system, machine) not in {("Darwin", "arm64"), ("Windows", "amd64")}:
        parser.error("Stage the runtime natively on macOS arm64 or Windows x64")

    candidate = BUILD / "runtime"
    if candidate.exists():
        shutil.rmtree(candidate)
    (candidate / "bin").mkdir(parents=True)
    (candidate / "licenses").mkdir()
    if args.system_media:
        stage_system_media(candidate)
    else:
        media = BUILD / "media"
        suffix = ".exe" if system == "Windows" else ""
        for name in ("ffmpeg", "ffprobe", "aria2c"):
            binary = media / "bin" / (name + suffix)
            if not binary.is_file():
                parser.error(f"Run desktop/scripts/build_media.sh first (missing {binary.name})")
            shutil.copy2(binary, candidate / "bin" / binary.name)
        shutil.copytree(media / "licenses", candidate / "licenses", dirs_exist_ok=True)
        stage_node(system, candidate)
    stage_python(candidate)
    stage_python_licenses(candidate / "licenses")
    stage_rust_licenses(system, candidate / "licenses")
    shutil.copyfile(ROOT / "desktop" / "scripts" / "third-party.md", candidate / "THIRD-PARTY.md")
    if system == "Darwin" and not args.system_media:
        verify_macos_binaries(candidate)
    if RUNTIME.exists():
        shutil.rmtree(RUNTIME)
    candidate.replace(RUNTIME)
    print(f"Staged {RUNTIME}")


if __name__ == "__main__":
    main()
