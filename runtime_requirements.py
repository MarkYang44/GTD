"""Check Python compatibility before importing application dependencies."""

import sys


def require_supported_python(version=None):
    """Exit with an actionable message on unsupported Python interpreters."""
    version = sys.version_info if version is None else version
    if tuple(version[:2]) < (3, 10):
        current = ".".join(str(part) for part in version[:3])
        raise SystemExit(
            "GTD requires Python 3.10+ (current: {}). "
            "Upgrade Python and recreate the virtual environment.\n"
            "GTD 需要 Python 3.10+（当前：{}）。"
            "请升级 Python 并重新创建虚拟环境。".format(current, current)
        )
