"""Find traces in prepared lines and hand each to the right language parser."""

from __future__ import annotations

import re
from collections.abc import Callable

from ..model import Trace
from . import dotnet, go, java, node, python, rust
from .common import MAX_TRACE_LINES

_NODE_TAIL = re.compile(r":\d+:\d+\)?$")
_NODE_NATIVE = ("(<anonymous>)", "(native)", "<anonymous>", "(unknown location)")

Parser = Callable[[list[str]], tuple[Trace | None, int]]


def _is_node_frame(st: str) -> bool:
    if not st.startswith("at "):
        return False
    body = st.rstrip(" ,{")
    if body.startswith(("at async ", "at new ")) and not java.is_frame(body):
        return True
    return bool(_NODE_TAIL.search(body)) or body.endswith(_NODE_NATIVE) or "(index " in body


def frame_family(st: str) -> str | None:
    """Which language a stripped `at ...` line belongs to."""
    if not st.startswith("at "):
        return None
    if java.is_frame(st):
        return "java"
    if _is_node_frame(st):
        return "node"
    if dotnet.is_frame(st):
        return "dotnet"
    return None


_HEADER_FOR: dict[str, Callable[[str, bool], object]] = {
    "java": lambda s, strict: java.header_type(s, strict) or (s.startswith("Caused by: ") and java.header_type(s[11:], False)),
    "node": lambda s, strict: node.header_match(s, strict),
    "dotnet": lambda s, strict: dotnet.header_match(s.split(" ---> ")[0], strict),
}
_PARSE_FOR: dict[str, Parser] = {"java": java.parse, "node": node.parse, "dotnet": dotnet.parse}


SMALL_WINDOW = 80


def _run(parser: Parser, lines: list[str], begin: int) -> tuple[Trace | None, int]:
    """Parse with a small window first; retry with the full window only if the trace fills it."""
    w = lines[begin : begin + SMALL_WINDOW]
    result = parser(w)
    if result[0] is not None and result[1] >= len(w) - 1 and len(w) == SMALL_WINDOW:
        result = parser(lines[begin : begin + MAX_TRACE_LINES])
    return result


def _find_header(lines: list[str], i: int, floor: int, family: str) -> int:
    """Index of the exception header above the frame at i, or i when there is none."""
    check = _HEADER_FOR[family]
    block: list[int] = []
    k = i - 1
    while k >= max(floor, i - 8) and lines[k].strip():
        if node.is_frame(lines[k].strip()) or java.is_frame(lines[k].strip()):
            break
        block.append(k)
        k -= 1
    block.reverse()
    for k in block:  # furthest strict header first
        if check(lines[k].strip(), True):
            return k
    if block and check(lines[block[-1]].strip(), False):
        return block[-1]
    if family == "java":
        for k in reversed(block):
            if java.embedded_header(lines[k].strip()):
                return k
    return i


def scan_lines(
    lines: list[str],
    timestamps: dict[int, str] | None = None,
    start: int = 0,
    max_traces: int = 100_000,
    stop_before: int | None = None,
) -> list[Trace]:
    """Find every trace in lines[start:]. start_line/end_line are 1-based indexes into `lines`."""
    return scan_chunk(lines, timestamps, start, max_traces, stop_before)[0]


def scan_chunk(
    lines: list[str],
    timestamps: dict[int, str] | None = None,
    start: int = 0,
    max_traces: int = 100_000,
    stop_before: int | None = None,
) -> tuple[list[Trace], int]:
    """Like scan_lines, but also returns the index where scanning stopped."""
    out: list[Trace] = []
    n = len(lines) if stop_before is None else min(len(lines), stop_before)
    ts = timestamps or {}
    pos = start
    i = start
    while i < n and len(out) < max_traces:
        raw = lines[i]
        if not raw:
            i += 1
            continue
        st = raw.strip()
        first = st[:1]
        begin = i
        result: tuple[Trace | None, int] = (None, 1)
        if first == "T" and st.startswith("Traceback (most recent call last):"):
            result = _run(python.parse, lines, i)
        elif first == "+" and python.is_start(st):
            result = _run(python.parse, lines, i)
        elif first == "F" and python.is_bare_file_start(lines, i):
            result = _run(python.parse, lines, i)
        elif go.is_start(st) and not raw[:1].isspace():
            result = _run(go.parse, lines, i)
        elif first == "t" and rust.is_start(st):
            result = _run(rust.parse, lines, i)
        elif first == "a":
            fam = frame_family(st)
            if fam is not None:
                begin = _find_header(lines, i, pos, fam)
                result = _run(_PARSE_FOR[fam], lines, begin)
                if result[0] is not None and begin + result[1] <= i:
                    result = (None, 1)
                    begin = i
        trace, used = result
        if trace is None:
            i += 1
            continue
        trace.start_line = begin + 1
        trace.end_line = begin + used
        for k in range(begin, max(begin - 4, -1), -1):
            if k in ts:
                trace.timestamp = ts[k]
                break
        out.append(trace)
        i = begin + used
        pos = i
    return out, i
