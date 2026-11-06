"""Turn untrusted input text into capped, prefix-stripped lines.

Everything here is linear in the input size. No regex in this module can
backtrack catastrophically: patterns are anchored and use bounded or
single-character-class quantifiers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_CHARS = 5_000_000
MAX_LINE = 4000
MAX_LINES = 1_000_000


class InputError(ValueError):
    """The caller's input is unusable; the message says how to fix it."""


_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
# ISO-ish timestamp at the start of a log line, optionally with a container-runtime
# "stdout F" marker (Docker/containerd/Kubernetes log format).
_TS = re.compile(
    r"^\[?(\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:[.,]\d{1,9})?(?:Z|[+-]\d\d:?\d\d)?)\]?[ \t]+"
    r"(?:(?:stdout|stderr)[ \t]+[FP][ \t]+)?"
)


@dataclass
class Prepared:
    lines: list[str]
    timestamps: dict[int, str] = field(default_factory=dict)  # 0-based line index -> ts
    notes: list[str] = field(default_factory=list)


def prepare(text: str, *, max_chars: int = MAX_CHARS) -> Prepared:
    if len(text) > max_chars:
        raise InputError(
            f"Input is {len(text):,} characters; the limit is {max_chars:,}. "
            "Paste only the trace (or use find_traces_in_file for big logs)."
        )
    if "\x1b" in text:
        text = _ANSI.sub("", text)
    if "\r" in text:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
    return prepare_lines(text.split("\n"))


def prepare_lines(raw: list[str]) -> Prepared:
    """Cap, strip timestamps from, and right-trim already-split lines."""
    notes: list[str] = []
    if len(raw) > MAX_LINES:
        notes.append(f"Input has {len(raw):,} lines; only the first {MAX_LINES:,} were analysed.")
        raw = raw[:MAX_LINES]
    lines: list[str] = []
    ts: dict[int, str] = {}
    cut = 0
    for i, line in enumerate(raw):
        if len(line) > MAX_LINE:
            line = line[:MAX_LINE]
            cut += 1
        if line and (line[0] == "[" or line[0].isdigit()):
            m = _TS.match(line)
            if m:
                ts[i] = m.group(1)
                line = line[m.end() :]
        lines.append(line.rstrip())
    if cut:
        notes.append(f"{cut} line(s) longer than {MAX_LINE} characters were cut.")
    return Prepared(lines, ts, notes)
