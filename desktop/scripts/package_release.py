"""Smoke-test native bundles and copy validated release assets to desktop/build/dist."""

import argparse
from hashlib import file_digest
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
from tempfile import TemporaryDirectory
import tomllib
from zipfile import ZIP_DEFLATED, ZipFile

from stage_runtime import BUILD, ROOT, RUNTIME, TARGETS, verify_macos_binaries

TAURI = ROOT / "desktop" / "src-tauri"


def version_for(tag: str | None) -> str:
    version = json.loads((TAURI / "tauri.conf.json").read_text(encoding="utf-8"))["version"]
    manifest = tomllib.loads((TAURI / "Cargo.toml").read_text(encoding="utf-8"))
    if manifest["package"]["version"] != version:
        raise ValueError("The Tauri and Cargo versions must match")
    if tag and tag != f"v{version}":
        raise ValueError(f"Tag {tag!r} must match v{version}")
    return version


def one_file(directory: Path, pattern: str) -> Path:
    matches = list(directory.glob(pattern))
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected one {pattern} in {directory}, found {len(matches)}")
    return matches[0]


def smoke(executable: Path, runtime: Path) -> None:
    is_windows = executable.suffix == ".exe"
    if is_windows:
        with executable.open("rb") as binary:
            binary.seek(0x3C)
            binary.seek(struct.unpack("<I", binary.read(4))[0])
            if binary.read(6) != b"PE\0\0\x64\x86":
                raise ValueError(f"Expected an x64 PE executable at {executable}")
        clean_path = os.pathsep.join((str(Path(os.environ["SystemRoot"]) / "System32"), os.environ["SystemRoot"]))
    else:
        subprocess.run(["lipo", "-verify_arch", "arm64", str(executable)], check=True)
        clean_path = "/usr/bin:/bin:/usr/sbin:/sbin"
    clean_environment = dict(os.environ, PATH=clean_path)
    print(f"Smoke-testing {executable}", flush=True)
    for tool in ("node", "aria2c"):
        program = runtime / "bin" / (tool + executable.suffix)
        subprocess.run([str(program), "--version"], env=clean_environment, timeout=30, check=True)
    subprocess.run([str(executable), "--smoke-test"], env=clean_environment,
                   cwd=executable.parent, timeout=180, check=True)


def zip_directory(directory: Path, output: Path) -> None:
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for entry in sorted(directory.rglob("*")):
            if entry.is_file():
                archive.write(entry, entry.relative_to(directory.parent))


def collect_windows(release: Path, dist: Path, prefix: str, *, test_installer: bool) -> None:
    installer = one_file(release / "bundle" / "nsis", "*.exe")
    shutil.copy2(installer, dist / f"{prefix}-windows-x64-setup.exe")
    with TemporaryDirectory(prefix="GTD Package ", dir=os.environ.get("RUNNER_TEMP")) as temporary:
        temp = Path(temporary).resolve()
        portable = temp / "验证 with spaces" / "GTD"
        portable.mkdir(parents=True)
        shutil.copy2(release / "gtd.exe", portable / "gtd.exe")
        shutil.copytree(RUNTIME, portable / "runtime")
        smoke(portable / "gtd.exe", portable / "runtime")
        zip_directory(portable, dist / f"{prefix}-windows-x64-portable.zip")

        if not test_installer:
            return
        installed = temp / "GTD Installed 测试"
        # NSIS reads the unquoted remainder after /D as the path, including spaces.
        command = f'"{installer}" /S /D={installed}'
        subprocess.run(command, timeout=180, check=True)
        try:
            smoke(installed / "gtd.exe", installed / "runtime")
        finally:
            uninstaller = installed / "uninstall.exe"
            if uninstaller.is_file():
                subprocess.run(f'"{uninstaller}" /S _?={installed}', timeout=60, check=False)


def collect_macos(release: Path, dist: Path, prefix: str) -> None:
    dmg = one_file(release / "bundle" / "dmg", "*.dmg")
    shutil.copy2(dmg, dist / f"{prefix}-macos-arm64.dmg")
    with TemporaryDirectory(prefix="GTD Package ") as temporary:
        temp = Path(temporary).resolve()
        mounted = temp / "mount"
        mounted.mkdir()
        subprocess.run(["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", str(mounted), str(dmg)],
                       check=True, timeout=120)
        try:
            app = temp / "验证 with spaces" / "GTD.app"
            subprocess.run(["ditto", str(mounted / "GTD.app"), str(app)], check=True)
            verify_macos_binaries(app)
            subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
            smoke(app / "Contents" / "MacOS" / "gtd", app / "Contents" / "Resources" / "runtime")
            subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app),
                            str(dist / f"{prefix}-macos-arm64-app.zip")], check=True)
        finally:
            subprocess.run(["hdiutil", "detach", str(mounted)], check=True, timeout=60)


def media_source_archive(dist: Path, prefix: str, system: str) -> None:
    suffix = "macos-arm64" if system == "Darwin" else "windows-x64"
    names = ("ffmpeg-*.tar.xz", "lame-*.tar.gz", "aria2-*.tar.xz")
    if system == "Windows":
        names += ("zlib-*.tar.xz",)
    with ZipFile(dist / f"{prefix}-{suffix}-media-sources.zip", "w") as archive:
        for pattern in names:
            source = one_file(BUILD / "media" / "sources", pattern)
            archive.write(source, f"build/media/sources/{source.name}")
        # Keep the source layout expected by the standalone media build script.
        archive.write(Path(__file__).with_name("build_media.sh"), "scripts/build_media.sh")
        archive.write(Path(__file__).with_name("third-party.md"), "THIRD-PARTY.md")


def write_checksums(dist: Path) -> None:
    lines = []
    for asset in sorted(dist.iterdir()):
        if asset.name == "SHA256SUMS.txt" or not asset.is_file():
            continue
        with asset.open("rb") as file:
            digest = file_digest(file, "sha256").hexdigest()
        lines.append(f"{digest}  {asset.name}")
    if not lines:
        raise ValueError(f"No assets found in {dist}")
    (dist / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-version", action="store_true", help="Print and validate the app version, then exit")
    parser.add_argument("--tag", help="Validate an optional release tag against the app version")
    parser.add_argument("--target-dir", type=Path, default=TAURI / "target")
    parser.add_argument("--test-installer", action="store_true",
                        help="Also install and uninstall GTD while testing on a disposable Windows machine")
    args = parser.parse_args()
    version = version_for(args.tag)
    if args.verify_version:
        print(version)
        return
    system = platform.system()
    if system not in TARGETS:
        parser.error("Package the app natively on macOS arm64 or Windows x64")
    if (RUNTIME / "DEVELOPMENT-TOOLS.txt").exists():
        parser.error("Re-stage the self-contained runtime without --system-media before packaging")
    release = args.target_dir.resolve() / TARGETS[system] / "release"
    dist = BUILD / "dist"
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir(parents=True)
    prefix = f"GTD-{version}"
    if system == "Windows":
        collect_windows(release, dist, prefix, test_installer=args.test_installer)
    else:
        collect_macos(release, dist, prefix)
    media_source_archive(dist, prefix, system)
    write_checksums(dist)
    print(f"Validated release assets in {dist}")


if __name__ == "__main__":
    main()
