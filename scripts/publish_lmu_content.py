#!/usr/bin/env python3
"""Check a release or publish a reviewed content snapshot; never fetch or infer review dates."""
import argparse
from datetime import date
import json
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lmu_content import CONTENT_DIR, current_records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--version')
    parser.add_argument('--date')
    parser.add_argument('--summary-zh')
    parser.add_argument('--summary-en')
    args = parser.parse_args()
    path = CONTENT_DIR / 'releases.json'
    releases = json.loads(path.read_text(encoding='utf-8'))
    current = current_records()
    latest = json.loads((CONTENT_DIR / releases[-1]['snapshot']).read_text(encoding='utf-8'))
    if args.check:
        if current != latest:
            parser.exit(1, 'LMU content changed: review metadata and publish a new snapshot.\n')
        print('LMU content matches published snapshot.')
        return
    if not all([args.version, args.date, args.summary_zh, args.summary_en]):
        parser.error('Publishing requires --version, --date, --summary-zh and --summary-en.')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,60}', args.version):
        parser.error('Use a filename-safe version identifier.')
    try:
        release_date = date.fromisoformat(args.date)
    except ValueError:
        parser.error('Use an ISO date (YYYY-MM-DD).')
    if release_date < date.fromisoformat(releases[-1]['date']) or release_date > date.today():
        parser.error('Release date must not precede the last release or be in the future.')
    if any(item['version'] == args.version for item in releases):
        parser.error('Version already exists; snapshots are immutable.')
    if current == latest:
        parser.error('No content changes to publish.')
    snapshot = args.version + '.json'
    with (CONTENT_DIR / snapshot).open('x', encoding='utf-8') as stream:
        json.dump(current, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    releases.append(dict(version=args.version, date=args.date, summary_zh=args.summary_zh, summary_en=args.summary_en, snapshot=snapshot))
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(releases, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)
    print(f'Published LMU content {args.version}.')


if __name__ == '__main__':
    main()
