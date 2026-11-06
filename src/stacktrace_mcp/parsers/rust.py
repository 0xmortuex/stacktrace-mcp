"""Rust panics and RUST_BACKTRACE output."""

from __future__ import annotations

import re

from ..classify import rust_kind
from ..model import Exc, Frame, Trace
from .common import MAX_TRACE_LINES, split_loc

_PANIC = re.compile(r"^thread '(?P<thread>.*?)'(?: \(\d+\))? panicked at (?P<rest>.*)$")
_FRAME = re.compile(r"^(?P<idx>\d+):\s+(?:0x[0-9a-fA-F]+ - )?(?P<fn>.*)$")
_AT = re.compile(r"^at (?P<loc>.+)$")
_HASH = re.compile(r"::h[0-9a-f]{16}$")


def is_start(s: str) -> bool:
    return s.startswith("thread '") and " panicked at " in s


def _classify(fn: str, file: str | None) -> str:
    return rust_kind(fn, file)


def parse(window: list[str]) -> tuple[Trace | None, int]:
    m = _PANIC.match(window[0].strip())
    if not m:
        return None, 1
    n = len(window)
    rest = m.group("rest")
    msg_lines: list[str] = []
    i = 1
    if rest.endswith(":"):  # Rust 1.73+: location, then the message on the following lines
        loc = rest[:-1]
        while i < n:
            t = window[i].strip()
            if window[i].strip() == "stack backtrace:" or t.startswith("note: ") or (
                not t and (i + 1 >= n or not window[i + 1].strip() or window[i + 1].strip() in ("stack backtrace:",)
                           or window[i + 1].strip().startswith("note: "))
            ):
                break
            msg_lines.append(window[i].rstrip())
            i += 1
        while msg_lines and not msg_lines[-1].strip():
            msg_lines.pop()
    else:  # old style: 'message', file:line:col
        idx = rest.rfind("', ")
        if rest.startswith("'") and idx != -1:
            msg_lines = [rest[1:idx]]
            loc = rest[idx + 3 :]
        else:
            msg_lines = []
            loc = rest
    file, line, col = split_loc(loc)
    message = "\n".join(msg_lines)
    exc = Exc(type="panic", message=message, thread=m.group("thread"))
    panic_site = Frame(function="(panic site)", file=file, line=line, column=col, kind=rust_kind("", file), raw=loc)
    exc.notes.append(f"panicked at {loc}")
    # backtrace
    frames: list[Frame] = []
    notes: list[str] = []
    end = i
    while i < n and not window[i].strip():
        i += 1
    if i < n and window[i].strip() == "stack backtrace:":
        i += 1
        end = i
        cur: Frame | None = None
        while i < n:
            t = window[i].strip()
            fm = _FRAME.match(t)
            am = _AT.match(t)
            if fm and not t.startswith("at "):
                fn = _HASH.sub("", fm.group("fn").strip())
                cur = Frame(function=fn, kind=_classify(fn, None), raw=t)
                frames.append(cur)
            elif am and cur is not None and cur.file is None:
                f, ln, cl = split_loc(am.group("loc").strip())
                cur.file, cur.line, cur.column = f, ln, cl
                cur.kind = _classify(cur.function, f)
            elif t.startswith("note:") or not t:
                if t.startswith("note:"):
                    end = i + 1
                break
            else:
                break
            i += 1
            end = i
            if i - 0 >= MAX_TRACE_LINES - 1:
                notes.append(f"Trace cut at {MAX_TRACE_LINES} lines.")
                break
    elif i < n and window[i].strip().startswith("note: run with `RUST_BACKTRACE"):
        end = i + 1
        notes.append("No backtrace in the input; re-run with RUST_BACKTRACE=1 for frames.")
    else:
        notes.append("No backtrace in the input; re-run with RUST_BACKTRACE=1 for frames.")
    if frames:
        exc.frames = frames
    else:
        exc.frames = [panic_site]
        panic_site.function = "(panic site)"
        if panic_site.file is not None:
            panic_site.kind = rust_kind("", panic_site.file)
            if panic_site.kind == "unknown":
                panic_site.kind = "app"
    partial = False
    if frames and frames[-1].file is None and frames[-1].kind in ("app", "unknown") and frames[-1].function != "<unknown>":
        notes.append("Last frame has no location (input truncated?).")
        partial = True
    return Trace("rust", [exc], notes=notes, partial=partial), max(end, 1)
