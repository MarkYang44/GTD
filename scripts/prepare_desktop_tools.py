#!/usr/bin/env python3
"""Prepare relocatable platform tools and provenance in tools/desktop-bin."""
import argparse
import hashlib
import json
import importlib.metadata
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ('ffmpeg', 'ffprobe', 'aria2c', 'node')

def run(*args):
    return subprocess.check_output(args, text=True).strip()

def download(url, destination):
    request = urllib.request.Request(url, headers={'User-Agent': 'GTD-Desktop-Build'})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open('wb') as output:
        shutil.copyfileobj(response, output)
    return hashlib.sha256(destination.read_bytes()).hexdigest()

def windows(output):
    records = []
    pinned_hashes = {
        'node': '21c2d9735c80b8f86dab19305aa6a9f6f59bbc808f68de3eef09d5832e3bfbbd',
        'aria2': '67d015301eef0b612191212d564c5bb0a14b5b9c4796b76454276a4d28d9b288',
        'ffmpeg': '60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba',
    }
    sources = [
        ('node', 'https://nodejs.org/dist/v22.16.0/node-v22.16.0-win-x64.zip', 'https://nodejs.org/dist/v22.16.0/SHASUMS256.txt', 'https://github.com/nodejs/node/tree/v22.16.0'),
        ('aria2', 'https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0-win-64bit-build1.zip', None, 'https://github.com/aria2/aria2/tree/release-1.37.0'),
        ('ffmpeg', 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip', 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256', 'https://www.gyan.dev/ffmpeg/builds/'),
    ]
    with tempfile.TemporaryDirectory() as directory:
        scratch = Path(directory)
        for name, url, checksum_url, source_url in sources:
            archive = scratch / (name + '.zip')
            digest = download(url, archive)
            if digest != pinned_hashes[name]:
                raise RuntimeError(f'{name}: pinned build SHA256 mismatch; review upstream release before updating the pin')
            if checksum_url:
                checksum = scratch / (name + '.sha256')
                download(checksum_url, checksum)
                lines = checksum.read_text().splitlines()
                expected = next((line.split()[0] for line in lines if url.rsplit('/', 1)[1] in line), lines[0].split()[0])
                if digest != expected.lower():
                    raise RuntimeError(f'{name}: publisher SHA256 mismatch')
            with zipfile.ZipFile(archive) as bundle:
                for member in bundle.infolist():
                    member_path = Path(member.filename)
                    if member_path.is_absolute() or '..' in member_path.parts:
                        raise RuntimeError(f'Unsafe archive entry: {member.filename}')
                    basename = member_path.name
                    if basename.lower() in {tool + '.exe' for tool in TOOLS}:
                        (output / 'bin' / basename).write_bytes(bundle.read(member))
                    elif any(word in basename.lower() for word in ('license', 'copying', 'notice', 'readme')) and not member.is_dir():
                        destination = output / 'notices' / name / member.filename
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(bundle.read(member))
            records.append({'name': name, 'url': url, 'sha256': digest, 'publisher_checksum': checksum_url, 'source': source_url})
    return records

def macos(output):
    binaries = []
    originals = {}
    def copy_binary(source, executable=False):
        source = source.resolve()
        if source in originals:
            return originals[source]
        destination = output / ('bin' if executable else 'lib') / source.name
        if destination.exists() and hashlib.sha256(destination.read_bytes()).digest() != hashlib.sha256(source.read_bytes()).digest():
            raise RuntimeError(f'Conflicting library names: {source.name}')
        shutil.copy2(source, destination)
        destination.chmod(0o755)
        originals[source] = destination
        binaries.append((source, destination))
        dependencies = run('otool', '-L', str(source)).splitlines()[1:]
        for line in dependencies:
            dependency = line.strip().split(' (', 1)[0]
            if dependency.startswith(('/opt/homebrew/', '/usr/local/')):
                replacement = copy_binary(Path(dependency))
                relative = os.path.relpath(replacement, destination.parent)
                subprocess.run(['install_name_tool', '-change', dependency, '@loader_path/' + relative, str(destination)], check=True)
            elif dependency.startswith('@'):
                candidates = []
                if dependency.startswith(('@loader_path/', '@executable_path/')):
                    candidates.append(source.parent / dependency.split('/', 1)[1])
                elif dependency.startswith('@rpath/'):
                    load_commands = run('otool', '-l', str(source))
                    for rpath in re.findall(r'cmd LC_RPATH\s+cmdsize \d+\s+path (.+?) \(offset', load_commands):
                        expanded = rpath.replace('@loader_path', str(source.parent)).replace('@executable_path', str(source.parent))
                        candidates.append(Path(expanded) / dependency.split('/', 1)[1])
                resolved = next((candidate for candidate in candidates if candidate.is_file()), None)
                if resolved is None:
                    raise RuntimeError(f'Unresolved relocatable dependency {dependency} in {source}')
                replacement = copy_binary(resolved)
                relative = os.path.relpath(replacement, destination.parent)
                subprocess.run(['install_name_tool', '-change', dependency, '@loader_path/' + relative, str(destination)], check=True)
        if not executable:
            subprocess.run(['install_name_tool', '-id', '@loader_path/' + destination.name, str(destination)], check=True)
        return destination
    for tool in TOOLS:
        source = shutil.which(tool)
        if not source:
            raise RuntimeError(f'Install {tool} with Homebrew before preparing macOS tools')
        copy_binary(Path(source), executable=True)
    # Retain formula source/build metadata and every installed license notice from used kegs.
    kegs = set()
    for source, destination in binaries:
        parts = source.parts
        if 'Cellar' in parts:
            index = parts.index('Cellar')
            kegs.add(Path(*parts[:index + 3]))
        subprocess.run(['codesign', '--force', '--sign', '-', str(destination)], check=True)
        for line in run('otool', '-L', str(destination)).splitlines()[1:]:
            if line.strip().startswith(('/opt/homebrew/', '/usr/local/')):
                raise RuntimeError(f'Unrelocated dependency in {destination}: {line}')
    records = []
    for keg in sorted(kegs):
        destination = output / 'notices' / keg.parent.name
        destination.mkdir(parents=True, exist_ok=True)
        for path in keg.rglob('*'):
            if path.is_file() and not path.is_symlink() and (any(word in path.name.lower() for word in ('license', 'copying', 'copyright', 'notice')) or path.parent.name == '.brew'):
                target = destination / path.relative_to(keg)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        formula_file = next((keg / '.brew').glob('*.rb'), None)
        formula = formula_file.read_text() if formula_file else ''
        records.append({'name': keg.parent.name, 'version': keg.name, 'license': re.findall(r'^\s*license (.+)$', formula, re.MULTILINE), 'source_urls': re.findall(r'^\s*(?:url|homepage) [\"\'](.+?)[\"\']', formula, re.MULTILINE), 'formula': str(formula_file)})
    return records

def python_qt_notices(output):
    notices = output / 'notices'
    python_license = Path(sys.base_prefix) / 'LICENSE'
    if not python_license.is_file():
        candidates = list(Path(sys.base_prefix).glob('**/LICENSE.txt'))
        python_license = next(iter(candidates), python_license)
    if python_license.is_file():
        (notices / 'Python-LICENSE.txt').write_bytes(python_license.read_bytes())
    for distribution_name in ('pyinstaller',):
        distribution = importlib.metadata.distribution(distribution_name)
        for item in distribution.files or []:
            if 'licenses' in item.parts and distribution.locate_file(item).is_file():
                target = notices / distribution_name / Path(*item.parts[item.parts.index('licenses') + 1:])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(distribution.locate_file(item).read_bytes())
    qt = notices / 'qt'
    qt.mkdir(exist_ok=True)
    for name in ('LGPL-3.0-only.txt', 'GPL-3.0-only.txt'):
        download('https://raw.githubusercontent.com/qt/qtbase/v6.11.2/LICENSES/' + name, qt / name)
    (qt / 'SOURCE-NOTICES.txt').write_text('Qt/PySide6 6.11.2 dynamically linked runtime. Source and build instructions: https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v6.11.2 ; Qt source: https://code.qt.io/cgit/qt/qtbase.git/tag/?h=v6.11.2 ; QtWebEngine Chromium third-party source/licenses: https://code.qt.io/cgit/qt/qtwebengine-chromium.git/ ; licensing details: https://doc.qt.io/qt-6/qtwebengine-licensing.html . Users may replace compatible dynamically linked Qt libraries in the portable bundle. This app provides no proprietary restriction on debugging such modifications.\n')

def prepare(output):
    if output.exists():
        shutil.rmtree(output)
    for name in ('bin', 'lib', 'notices'):
        (output / name).mkdir(parents=True)
    records = windows(output) if sys.platform == 'win32' else macos(output)
    python_qt_notices(output)
    manifest = {'platform': sys.platform, 'sources': records, 'files': {str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest() for path in output.rglob('*') if path.is_file()}}
    (output / 'notices/manifest.json').write_text(json.dumps(manifest, indent=2))
    (output / 'notices/README.txt').write_text('Bundled tools retain their upstream licenses and source/build provenance in this directory. FFmpeg builds may be GPL-enabled; aria2 is GPL, Node contains MIT and third-party notices. Source URLs and exact downloaded binary hashes are in manifest.json. Qt/PySide LGPL libraries are dynamically linked; their notices accompany the frozen distribution. This is an unsigned local build, not a notarized release.\n')
    print(output)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'tools/desktop-bin')
    prepare(parser.parse_args().output.resolve())
