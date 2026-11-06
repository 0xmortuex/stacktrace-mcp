"""Helpers shared by the language parsers."""

from __future__ import annotations

import re

MAX_TRACE_LINES = 3000

# A line that is obviously the next log record, not a continuation of an exception message.
_LOG_LINE = re.compile(
    r"^(?:\d{4}-\d\d-\d\d|\d\d:\d\d:\d\d|\[\d|(?:TRACE|DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL|FATAL|SEVERE)\b)"
)


def looks_like_log_line(line: str) -> bool:
    return bool(_LOG_LINE.match(line))


def to_int(s: str) -> int | None:
    return int(s) if s.isdigit() and len(s) < 10 else None


def split_loc(loc: str) -> tuple[str, int | None, int | None]:
    """'path:12:5' -> (path, 12, 5); handles Windows drive letters and URLs."""
    parts = loc.rsplit(":", 2)
    if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
        return parts[0], to_int(parts[1]), to_int(parts[2])
    parts2 = loc.rsplit(":", 1)
    if len(parts2) == 2 and parts2[1].isdigit():
        return parts2[0], to_int(parts2[1]), None
    return loc, None, None


def is_minified(file: str | None, line: int | None, col: int | None) -> bool:
    if file is None:
        return False
    base = file.rsplit("/", 1)[-1].lower()
    if ".min." in base:
        return True
    return col is not None and col > 600 and (line is None or line <= 2)
