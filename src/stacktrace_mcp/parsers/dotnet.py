"""C# / .NET stack traces (Exception.ToString() format)."""

from __future__ import annotations

import re

from ..classify import dotnet_kind
from ..model import Exc, Frame, TNode, Trace, flatten
from .common import MAX_TRACE_LINES, to_int

_HEADER = re.compile(
    r"^(?:Unhandled [Ee]xception[.:]? ?)?(?:\(Inner Exception #(?P<idx>\d+)\) )?"
    r"(?P<type>[A-Za-z_][\w.`+<>]*)(?: \((?:0x[0-9A-Fa-f]+|\d+)\))?(?:: ?(?P<msg>.*))?$"
)
_STRICT = re.compile(r"(?:Exception|Error|Fault)$")
_LINE_IN = re.compile(r"^(?P<file>.*?)(?::line |:)(?P<line>\d+)$")
_END_INNER = "--- End of inner exception stack trace ---"
_END_PREV = "--- End of stack trace from previous location"


def is_frame(s: str) -> bool:
    if not s.startswith("at "):
        return False
    p = s.find("(")
    return p >= 4 and s.find(")", p) != -1


def header_match(s: str, strict: bool) -> re.Match[str] | None:
    m = _HEADER.match(s)
    if not m:
        return None
    typ = m.group("type")
    if strict and not (_STRICT.search(typ) or ("." in typ and typ[0].isupper())):
        return None
    return m


def parse_frame(s: str) -> Frame:
    body = s[3:].strip()
    file: str | None = None
    line: int | None = None
    where = body
    if " in " in body:
        where, _, loc = body.rpartition(" in ")
        m = _LINE_IN.match(loc)
        if m:
            file, line = m.group("file"), to_int(m.group("line"))
        else:
            file = loc
    p = where.find("(")
    fn = where[:p].strip() if p != -1 else where.strip()
    cls, _, method = fn.rpartition(".")
    return Frame(
        function=fn,
        file=file,
        line=line,
        kind=dotnet_kind(fn, file),
        module=cls or None,
        raw=s,
        is_async="MoveNext" in method or "<" in fn and "d__" in fn,
    )


def _open_inner(body: str, stack: list[TNode]) -> bool:
    m = header_match(body, strict=False)
    if m is None:
        return False
    node = TNode(Exc(type=m.group("type"), message=m.group("msg") or "", via="inner"))
    parent = stack[-1]
    if m.group("idx") is not None or parent.exc.type.endswith("AggregateException"):
        parent.children.append(node)
    else:
        parent.cause = node
    stack.append(node)
    return True


def parse(window: list[str]) -> tuple[Trace | None, int]:
    notes: list[str] = []
    n = len(window)
    top: TNode | None = None
    stack: list[TNode] = []  # open nodes; frames go to stack[-1]
    i = 0
    end = 0
    saw_frame = False
    while i < n:
        raw = window[i]
        s = raw.strip()
        if not s:
            if saw_frame:
                break
            i += 1
            continue
        if is_frame(s):
            if not stack:
                node = TNode(Exc(type="(unknown)", message="(no exception header in input)"))
                top = node
                stack.append(node)
                notes.append("No exception header line found; showing frames only.")
            stack[-1].exc.frames.append(parse_frame(s))
            saw_frame = True
            i += 1
            end = i
            continue
        if s == _END_INNER:
            if len(stack) > 1:
                stack.pop()
            i += 1
            end = i
            continue
        if s.startswith(_END_PREV):
            i += 1
            end = i
            continue
        if s.startswith("--->") and stack:
            if not _open_inner(s[4:].strip(), stack):
                break
            saw_frame = False
            i += 1
            end = i
            continue
        if not stack:
            parts = s.split(" ---> ")
            m = header_match(parts[0], strict=False)
            if m is None:
                break
            top = TNode(Exc(type=m.group("type"), message=m.group("msg") or ""))
            stack.append(top)
            for extra in parts[1:]:
                if not _open_inner(extra, stack):
                    break
            i += 1
            end = i
            continue
        if not saw_frame:
            stack[-1].exc.message += "\n" + s  # multi-line message
            i += 1
            end = i
            continue
        break
    if top is None:
        return None, 1
    chain = flatten(top)
    partial = not any(e.frames for e in chain)
    if partial:
        notes.append("Exception header found but no stack frames followed.")
    if len(stack) > 1 and saw_frame:
        notes.append("Inner exception section not closed with '--- End of inner exception stack trace ---' (truncated?).")
        partial = True
    if end >= MAX_TRACE_LINES:
        notes.append(f"Trace cut at {MAX_TRACE_LINES} lines.")
        partial = True
    return Trace("dotnet", chain, notes=notes, partial=partial), max(end, 1)
