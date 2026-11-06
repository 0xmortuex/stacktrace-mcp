"""Data model shared by every language parser.

Frames are always stored innermost-first (the frame where the error was raised
comes first), whatever order the language prints them in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

APP = "app"
LIBRARY = "library"
FRAMEWORK = "framework"
STDLIB = "stdlib"
RUNTIME = "runtime"
UNKNOWN = "unknown"


@dataclass
class Frame:
    function: str
    file: str | None = None
    line: int | None = None
    column: int | None = None
    kind: str = UNKNOWN
    module: str | None = None
    source: str | None = None
    raw: str = ""
    is_async: bool = False
    inherited: bool = False  # copied from the enclosing trace for a Java "... N more"
    repeat: int = 0  # Python "[Previous line repeated N more times]"
    minified: bool = False
    path_hint: str | None = None  # package-derived path, e.g. com/acme/Foo.java
    native: bool = False

    @property
    def is_app(self) -> bool:
        return self.kind == APP

    def location(self) -> str:
        if self.file is None:
            return "(no file)"
        loc = self.file
        if self.line is not None:
            loc += f":{self.line}"
            if self.column is not None:
                loc += f":{self.column}"
        return loc


@dataclass
class Exc:
    type: str
    message: str = ""
    frames: list[Frame] = field(default_factory=list)
    via: str | None = None  # how this exception relates to the one that wraps it
    suppressed: list[Exc] = field(default_factory=list)
    group: list[list[Exc]] = field(default_factory=list)  # chains of sub-exceptions
    notes: list[str] = field(default_factory=list)
    extra_stacks: list[tuple[str, list[Frame]]] = field(default_factory=list)
    elided: int = 0
    thread: str | None = None
    code: str | None = None

    def first_app_frame(self) -> Frame | None:
        for f in self.frames:
            if f.is_app:
                return f
        return None


@dataclass
class Trace:
    language: str
    chain: list[Exc]  # chain[0] is what was finally raised; chain[-1] is the root cause
    notes: list[str] = field(default_factory=list)
    partial: bool = False
    start_line: int = 0  # 1-based, in the analysed text
    end_line: int = 0
    timestamp: str | None = None
    goroutines: list[str] = field(default_factory=list)

    @property
    def top(self) -> Exc:
        return self.chain[0]

    @property
    def root(self) -> Exc:
        return self.chain[-1]

    def root_causes(self) -> list[Exc]:
        """Leaf causes: the end of the chain, or of every sub-exception chain of a group."""
        out: list[Exc] = []
        for exc in self.chain:
            for sub in exc.group:
                out.extend(_leaf(sub))
        if not out:
            out.append(self.root)
        return out

    def origin(self) -> tuple[Exc, Frame] | None:
        """Innermost application frame, looking at the root cause first."""
        for exc in [self.root_causes()[0], *reversed(self.chain)]:
            f = exc.first_app_frame()
            if f is not None:
                return exc, f
        return None


def _leaf(chain: list[Exc]) -> list[Exc]:
    last = chain[-1]
    if last.group:
        out: list[Exc] = []
        for sub in last.group:
            out.extend(_leaf(sub))
        return out or [last]
    return [last]


@dataclass
class TNode:
    """Tree node for formats where causes and sub-errors nest (Node, .NET)."""

    exc: Exc
    cause: TNode | None = None
    children: list[TNode] = field(default_factory=list)


def flatten(node: TNode) -> list[Exc]:
    chain: list[Exc] = []
    cur: TNode | None = node
    while cur is not None:
        chain.append(cur.exc)
        if cur.children:
            cur.exc.group = [flatten(c) for c in cur.children]
        if cur.cause is not None:
            cur.cause.exc.via = cur.cause.exc.via or "cause"
        cur = cur.cause
    return chain


def frame_to_dict(f: Frame) -> dict[str, Any]:
    d: dict[str, Any] = {
        "function": f.function,
        "file": f.file,
        "line": f.line,
        "column": f.column,
        "kind": f.kind,
    }
    if f.module:
        d["module"] = f.module
    if f.source:
        d["source"] = f.source
    if f.is_async:
        d["async"] = True
    if f.inherited:
        d["inherited"] = True
    if f.repeat:
        d["repeat"] = f.repeat
    if f.minified:
        d["minified"] = True
    if f.native:
        d["native"] = True
    return d


def exc_to_dict(e: Exc) -> dict[str, Any]:
    d: dict[str, Any] = {
        "type": e.type,
        "message": e.message,
        "frames": [frame_to_dict(f) for f in e.frames],
    }
    if e.via:
        d["relation"] = e.via
    if e.code:
        d["code"] = e.code
    if e.thread:
        d["thread"] = e.thread
    if e.elided:
        d["elided_frames"] = e.elided
    if e.notes:
        d["notes"] = e.notes
    if e.suppressed:
        d["suppressed"] = [exc_to_dict(s) for s in e.suppressed]
    if e.group:
        d["sub_exceptions"] = [[exc_to_dict(x) for x in chain] for chain in e.group]
    if e.extra_stacks:
        d["extra_stacks"] = [
            {"label": lab, "frames": [frame_to_dict(f) for f in fr]} for lab, fr in e.extra_stacks
        ]
    return d


def trace_to_dict(t: Trace) -> dict[str, Any]:
    d: dict[str, Any] = {
        "language": t.language,
        "partial": t.partial,
        "notes": t.notes,
        "lines": [t.start_line, t.end_line],
        "chain": [exc_to_dict(e) for e in t.chain],
        "root_cause": exc_to_dict(t.root_causes()[0]),
    }
    if t.timestamp:
        d["timestamp"] = t.timestamp
    if t.goroutines:
        d["other_goroutines"] = t.goroutines
    org = t.origin()
    if org is not None:
        d["innermost_app_frame"] = {"exception": org[0].type, **frame_to_dict(org[1])}
    return d
