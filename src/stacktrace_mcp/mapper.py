"""Map trace frames onto files in the sandboxed project directory.

Paths inside a trace are DATA. This module never opens a path taken from a trace.
It walks the project directory once, builds an index of the files that really exist
there, and then looks frames up in that index by their trailing path components.
Whatever a frame claims ('../../etc/passwd', 'C:\\Windows\\...', '/app/src/x.py') can only
ever select a file that is already inside the sandbox; symlinks are re-checked with
realpath before a file is read.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from .model import APP, UNKNOWN, Exc, Frame, Trace
from .sandbox import SandboxError, is_inside, real

MAX_INDEX_FILES = 100_000
MAX_READ_BYTES = 2_000_000
MAX_LINE_SHOWN = 200
_PRUNE = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".tox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".gradle", ".idea", ".next", "site-packages", ".cache", ".hg", ".svn",
}  # fmt: skip
_URL_PREFIX = re.compile(r"^(?:webpack-internal:///|webpack://[^/]*/|file:///|[a-zA-Z][a-zA-Z0-9+.-]*://[^/]*/)")
_DRIVE = re.compile(r"^[A-Za-z]:")


@dataclass
class Index:
    by_name: dict[str, list[str]] = field(default_factory=dict)  # lower-case basename -> rel posix paths
    files: int = 0
    truncated: bool = False


def build_index(root_real: str) -> Index:
    idx = Index()
    for dirpath, dirnames, filenames in os.walk(root_real, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in _PRUNE]
        rel_dir = os.path.relpath(dirpath, root_real)
        for fn in filenames:
            if idx.files >= MAX_INDEX_FILES:
                idx.truncated = True
                return idx
            rel = fn if rel_dir == "." else (rel_dir.replace(os.sep, "/") + "/" + fn)
            idx.by_name.setdefault(fn.lower(), []).append(rel)
            idx.files += 1
    return idx


def path_segments(path: str) -> list[str]:
    """Normalise a trace path into comparable segments (no drive, scheme, query, '.' or '..')."""
    p = path.replace("\\", "/")
    p = p.split("?", 1)[0].split("#", 1)[0]
    p = _URL_PREFIX.sub("", p)
    p = _DRIVE.sub("", p)
    return [s for s in p.split("/") if s and s not in (".", "..") and not s.startswith("(")]


@dataclass
class Match:
    rel: str | None
    score: int = 0
    note: str = ""
    ambiguous: list[str] = field(default_factory=list)


def match_path(idx: Index, path: str) -> Match:
    segs = path_segments(path)
    if not segs:
        return Match(None, note="empty path")
    base = segs[-1].lower()
    cands = idx.by_name.get(base)
    if not cands:
        return Match(None, note=f"no file named {segs[-1]!r} under the project directory")
    want = [s.lower() for s in segs]
    best: list[str] = []
    best_score = 0
    for c in cands:
        parts = c.lower().split("/")
        score = 0
        while score < len(parts) and score < len(want) and parts[-1 - score] == want[-1 - score]:
            score += 1
        if score > best_score:
            best, best_score = [c], score
        elif score == best_score:
            best.append(c)
    if len(best) == 1:
        note = f"matched on {best_score} trailing path part(s)"
        if best_score == 1 and len(segs) > 1:
            note += " (file name only: the directories differ, so double-check it is the right file)"
        return Match(best[0], best_score, note)
    return Match(None, best_score, f"{len(best)} files with the same best match", sorted(best)[:6])


def _read_lines(root_real: str, rel: str, cache: dict[str, list[str] | str]) -> list[str] | str:
    """Lines of a project file, or an error string. Re-checks symlinks with realpath."""
    if rel in cache:
        return cache[rel]
    full = os.path.join(root_real, *rel.split("/"))
    try:
        rr = real(full)
    except SandboxError as e:
        cache[rel] = str(e)
        return cache[rel]
    if not is_inside(root_real, rr):
        cache[rel] = "blocked: the file is a symlink that resolves outside the sandbox"
        return cache[rel]
    try:
        with open(rr, "rb") as fh:
            data = fh.read(MAX_READ_BYTES + 1)
    except OSError as e:
        cache[rel] = f"cannot read: {e.strerror or type(e).__name__}"
        return cache[rel]
    if len(data) > MAX_READ_BYTES:
        cache[rel] = f"file larger than {MAX_READ_BYTES:,} bytes; not shown"
        return cache[rel]
    if b"\x00" in data[:4096]:
        cache[rel] = "binary file; not shown"
        return cache[rel]
    lines = data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()  # a trailing newline does not start another line
    cache[rel] = lines
    return lines


def candidate_frames(trace: Trace, limit: int) -> tuple[list[tuple[Exc, Frame]], int]:
    """Application (or unclassified) frames worth mapping, root cause first, plus the skipped count."""
    seen: set[tuple[str | None, int | None, str]] = set()
    out: list[tuple[Exc, Frame]] = []
    skipped = 0
    order: list[Exc] = list(trace.root_causes()) + [e for e in reversed(trace.chain) if e not in trace.root_causes()]
    for exc in order:
        for f in exc.frames:
            if f.kind not in (APP, UNKNOWN):
                skipped += 1
                continue
            key = (f.file or f.path_hint, f.line, f.function)
            if key in seen:
                continue
            seen.add(key)
            out.append((exc, f))
    return out[:limit], skipped + max(0, len(out) - limit)


def map_trace(trace: Trace, root_real: str, context: int = 3, max_frames: int = 8) -> str:
    context = max(0, min(context, 10))
    idx = build_index(root_real)
    cache: dict[str, list[str] | str] = {}
    frames, skipped = candidate_frames(trace, max_frames)
    out: list[str] = []
    found = 0
    for k, (exc, f) in enumerate(frames, 1):
        label = f"[{k}] {f.location()} in {f.function}   ({exc.type})"
        raw_path = f.file
        if f.path_hint and (raw_path is None or "/" not in raw_path.replace("\\", "/")):
            raw_path = f.path_hint
        if raw_path is None:
            out.append(f"{label}\n    NO FILE: the trace gives no file for this frame.")
            continue
        m = match_path(idx, raw_path)
        if m.rel is None:
            extra = f" Candidates: {', '.join(m.ambiguous)}." if m.ambiguous else ""
            out.append(f"{label}\n    NOT FOUND: {m.note}.{extra}")
            continue
        content = _read_lines(root_real, m.rel, cache)
        if isinstance(content, str):
            out.append(f"{label}\n    FOUND {m.rel} but {content}.")
            continue
        found += 1
        block = [f"{label}", f"    FOUND {m.rel}  ({m.note})"]
        if f.line is None:
            block.append("    (the trace gives no line number)")
        elif f.line < 1 or f.line > len(content):
            block.append(f"    LINE {f.line} DOES NOT EXIST: the file has {len(content)} lines (changed since the trace?)")
        else:
            lo, hi = max(1, f.line - context), min(len(content), f.line + context)
            for ln in range(lo, hi + 1):
                text = content[ln - 1]
                if len(text) > MAX_LINE_SHOWN:
                    text = text[:MAX_LINE_SHOWN] + "..."
                block.append(f"    {'>' if ln == f.line else ' '} {ln:>5} | {text}")
            if f.source and f.source.strip() != content[f.line - 1].strip():
                block.append("    WARNING: the source line recorded in the trace differs from the file (file edited since the crash?)")
        out.append("\n".join(block))
    head = f"Project directory: {os.path.basename(root_real) or root_real}  ({idx.files} files indexed"
    head += ", index truncated" if idx.truncated else ""
    head += f"). Mapped {found} of {len(frames)} application frame(s)."
    if skipped:
        head += f" {skipped} library/runtime frame(s) skipped."
    if not frames:
        out.append("No application frames in this trace to map.")
    return head + "\n" + "\n".join(out)
