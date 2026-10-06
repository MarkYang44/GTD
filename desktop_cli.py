"""Frozen console companion preserving the original GTD CLI arguments/workflow."""
from gtd_paths import initialize_desktop
initialize_desktop()
import main

if __name__ == '__main__':
    raise SystemExit(main.main())
