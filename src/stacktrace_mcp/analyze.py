"""Text in, traces out: the facade the MCP tools sit on."""

from __future__ import annotations

import re

from .model import Exc, Trace
from .parsers import scan_lines
from .prep import InputError, Prepared, prepare

_BARE = re.compile(
    r"^(?P<thread>Exception in thread \"[^\"]*\" )?(?P<type>[A-Za-z_][\w.$]*(?:Error|Exception|Throwable|Exit|Interrupt|Warning))(?:: ?(?P<msg>.*))?$"
)


def find_traces(text: str) -> tuple[list[Trace], Prepared]:
    prep = prepare(text)
    traces = scan_lines(prep.lines, prep.timestamps)
    return traces, prep


def parse_text(text: str, index: int = 0) -> tuple[Trace, int, Prepared]:
    """The index-th trace in `text` (0-based) and how many were found."""
    traces, prep = find_traces(text)
    if not traces:
        for ln in prep.lines:
            m = _BARE.match(ln.strip())
            if m:
                typ = m.group("type")
                java_like = m.group("thread") is not None or ("." in typ and typ[0].islower())
                t = Trace(
                    "java" if java_like else "unknown",
                    [Exc(type=typ, message=m.group("msg") or "")],
                    notes=["Only the exception line was found, no stack frames."],
                    partial=True,
                    start_line=1,
                    end_line=1,
                )
                return t, 1, prep
        raise InputError(
            "No stack trace recognised. Paste the raw text including the exception line and the "
            "frame lines (Python 'File ...', 'at ...' lines for Node/Java/.NET, 'goroutine N [...]' "
            "for Go, 'thread ... panicked at' for Rust). Supported: Python, Node/V8, Java/Kotlin, "
            "Go, Rust, .NET."
        )
    if not 0 <= index < len(traces):
        raise InputError(f"index {index} is out of range: the input contains {len(traces)} trace(s) (0-based).")
    t = traces[index]
    for note in prep.notes:
        t.notes.append(note)
    return t, len(traces), prep
