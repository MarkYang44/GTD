"""Synchronize the LMU circuit-guide's official local WebP assets."""

from __future__ import annotations

import sys
import subprocess
from shutil import which
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lmu_guide_data import CARS, CIRCUITS


class AssetSyncError(RuntimeError):
    """Raised after one or more official asset conversions fail."""


def _asset_sources() -> tuple[tuple[str, str], ...]:
    recommended_slugs = {
        recommendation.car_slug
        for circuit in CIRCUITS
        for recommendation in (*circuit.lmgt3, *circuit.hypercar)
    }
    circuits = tuple((circuit.image, circuit.image_source_url) for circuit in CIRCUITS)
    cars = tuple(
        (CARS[slug].image, CARS[slug].image_source_url)
        for slug in sorted(recommended_slugs)
    )
    return circuits + cars


def _ffmpeg_supports_libwebp(ffmpeg: str) -> bool:
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-encoders"],
        capture_output=True,
        check=True,
        text=True,
    )
    return "libwebp" in result.stdout


def _convert_to_webp(
    source_path: Path,
    output_path: Path,
    temporary_path: Path,
    ffmpeg: str,
    cwebp: str,
) -> None:
    if _ffmpeg_supports_libwebp(ffmpeg):
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source_path),
                "-vf",
                "scale=1024:576:force_original_aspect_ratio=decrease",
                "-frames:v",
                "1",
                "-c:v",
                "libwebp",
                "-quality",
                "82",
                "-compression_level",
                "6",
                str(output_path),
            ],
            check=True,
        )
        return

    resized_path = temporary_path / f"{source_path.stem}.resized.png"
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source_path),
            "-vf",
            "scale=1024:576:force_original_aspect_ratio=decrease",
            "-frames:v",
            "1",
            str(resized_path),
        ],
        check=True,
    )
    subprocess.run(
        [cwebp, "-quiet", "-q", "82", "-m", "6", str(resized_path), "-o", str(output_path)],
        check=True,
    )


def sync_assets(destination: Path, opener=urlopen, ffmpeg="ffmpeg") -> tuple[Path, ...]:
    """Download official source images and convert them into local WebP files."""
    destination = Path(destination)
    completed: list[Path] = []
    failures: list[str] = []
    cwebp = which("cwebp") or "cwebp"

    with TemporaryDirectory() as temporary_directory:
        temporary_path = Path(temporary_directory)
        for relative_path, source_url in _asset_sources():
            final_path = destination / relative_path
            source_path = temporary_path / f"{Path(relative_path).stem}.source"
            converted_path = temporary_path / f"{Path(relative_path).stem}.webp"
            try:
                request = Request(
                    source_url,
                    headers={"User-Agent": "GTD LMU guide asset sync"},
                )
                with opener(request, timeout=30) as response:
                    source_data = response.read()
                if not source_data:
                    raise ValueError("official source returned an empty response")
                source_path.write_bytes(source_data)
                _convert_to_webp(
                    source_path,
                    converted_path,
                    temporary_path,
                    ffmpeg,
                    cwebp,
                )
                if not converted_path.is_file() or not converted_path.stat().st_size:
                    raise ValueError("converter produced an empty WebP")
                final_path.parent.mkdir(parents=True, exist_ok=True)
                converted_path.replace(final_path)
                completed.append(final_path)
            except Exception as error:
                message = f"Failed {relative_path}: {error}"
                print(message, file=sys.stderr)
                failures.append(message)

    if failures:
        raise AssetSyncError(f"{len(failures)} LMU guide asset(s) failed to sync")
    return tuple(completed)


def main() -> int:
    try:
        completed = sync_assets(PROJECT_ROOT / "static", ffmpeg="ffmpeg")
    except AssetSyncError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Synced {len(completed)} official LMU guide assets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
