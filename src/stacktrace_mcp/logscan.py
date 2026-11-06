"""Stream a (possibly huge) log file and group the traces in it by fingerprint."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .fingerprint import fingerprint
from .model import Trace
from .parsers import scan_chunk
from .parsers.common import MAX_TRACE_LINES
from .prep import MAX_LINE, prepare_lines

MAX_SCAN_BYTES = 256 * 1024 * 1024
MAX_GROUPS = 1000
CHUNK_LINES = 20_000
LOOKBACK = 10


@dataclass
class Group:
    fp: str
    count: int = 0
    first_ts: str | None = None
    last_ts: str | None = None
    first_line: int = 0
    last_line: int = 0
    sample: Trace | None = None
    lines: list[int] = field(default_factory=list)


@dataclass
class ScanResult:
    groups: dict[str, Group] = field(default_factory=dict)
    traces: int = 0
    lines: int = 0
    bytes_read: int = 0
    file_size: int = 0
    stopped_at_cap: bool = False
    dropped_groups: int = 0
    dropped_traces: int = 0
    notes: list[str] = field(default_factory=list)


def _tskey(ts: str) -> str:
    return ts.replace("T", " ").replace(",", ".")


def _read_raw_lines(fh: object, budget: int) -> tuple[list[str], int, bool]:
    """Read up to CHUNK_LINES lines; every single read is bounded so a 1 GB 'line' cannot blow memory."""
    out: list[str] = []
    used = 0
    eof = False
    readline = fh.readline  # type: ignore[attr-defined]
    cap = MAX_LINE * 4
    while len(out) < CHUNK_LINES:
        if used >= budget:
            break
        chunk: bytes = readline(cap)
        if not chunk:
            eof = True
            break
        used += len(chunk)
        if not chunk.endswith(b"\n") and len(chunk) >= cap:
            # over-long line: keep its start, discard the rest up to the newline
            while True:
                rest: bytes = readline(cap)
                used += len(rest)
                if not rest or rest.endswith(b"\n"):
                    break
        out.append(chunk.decode("utf-8", errors="replace").rstrip("\r\n"))
    return out, used, eof


def scan_file(real_path: str, max_traces: int = 50_000) -> ScanResult:
    res = ScanResult(file_size=os.path.getsize(real_path))
    lines: list[str] = []
    tss: list[str | None] = []
    base = 0  # absolute 0-based index of lines[0]
    pos = 0  # relative index where scanning resumes
    with open(real_path, "rb") as fh:
        eof = False
        while not eof:
            budget = MAX_SCAN_BYTES - res.bytes_read
            if budget <= 0:
                res.stopped_at_cap = True
                break
            raw, used, eof = _read_raw_lines(fh, budget)
            res.bytes_read += used
            prep = prepare_lines(raw)
            for k, ln in enumerate(prep.lines):
                lines.append(ln)
                tss.append(prep.timestamps.get(k))
            res.lines = base + len(lines)
            final = eof or res.bytes_read >= MAX_SCAN_BYTES
            ts_map = {i: t for i, t in enumerate(tss) if t is not None}
            stop = None if final else max(pos, len(lines) - MAX_TRACE_LINES - 1)
            found, pos = scan_chunk(lines, ts_map, pos, stop_before=stop)
            for t in found:
                _add(res, t, base, max_traces)
            if final:
                break
            drop = max(0, pos - LOOKBACK)
            if drop:
                del lines[:drop]
                del tss[:drop]
                base += drop
                pos -= drop
    if res.bytes_read >= MAX_SCAN_BYTES and res.file_size > res.bytes_read:
        res.stopped_at_cap = True
    return res


def _add(res: ScanResult, t: Trace, base: int, max_traces: int) -> None:
    if not any(e.frames for e in t.chain):
        return  # a bare header with no frames is not worth a group (could be any log text)
    res.traces += 1
    if res.traces > max_traces:
        res.dropped_traces += 1
        return
    fp = fingerprint(t)
    g = res.groups.get(fp)
    line_no = base + t.start_line
    if g is None:
        if len(res.groups) >= MAX_GROUPS:
            res.dropped_groups += 1
            return
        g = Group(fp=fp, first_line=line_no, sample=t)
        res.groups[fp] = g
    g.count += 1
    g.last_line = line_no
    if len(g.lines) < 5:
        g.lines.append(line_no)
    if t.timestamp:
        k = _tskey(t.timestamp)
        if g.first_ts is None or k < _tskey(g.first_ts):
            g.first_ts = t.timestamp
        if g.last_ts is None or k > _tskey(g.last_ts):
            g.last_ts = t.timestamp
