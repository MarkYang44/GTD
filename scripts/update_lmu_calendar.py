#!/usr/bin/env python3
"""Manually validate/import an official-source calendar JSON; never fetches data."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lmu_calendar import DEFAULT_DIR, missing_fields, publish_calendar, read_calendar, record_failure


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='Manually prepared JSON file')
    parser.add_argument('--check', action='store_true', help='Validate only; do not change any files')
    parser.add_argument('--directory', type=Path, default=DEFAULT_DIR, help='Calendar storage directory')
    args = parser.parse_args()
    try:
        data = read_calendar(args.input)
    except (OSError, ValueError, TypeError, OverflowError) as error:
        if not args.check:
            try:
                record_failure(args.directory)
            except OSError:
                print('Could not record the failure status; calendar files were not changed.', file=sys.stderr)
        print(f'Update rejected: {error}', file=sys.stderr)
        return 1
    try:
        changed = False if args.check else publish_calendar(data, args.directory)
    except (OSError, ValueError, TypeError, OverflowError) as error:
        print(f'Update rejected: {error}', file=sys.stderr)
        return 1
    print('Valid calendar.' if args.check else ('Calendar published.' if changed else 'Unchanged; nothing to publish.'))
    for field in missing_fields(data):
        print('Not published / review manually: ' + field)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
