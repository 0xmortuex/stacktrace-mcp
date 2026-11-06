"""Node.js / V8 (and browser Chromium) stack traces."""

from __future__ import annotations

import re

from ..classify import node_kind
from ..model import RUNTIME, Exc, Frame, TNode, Trace, flatten
from .common import MAX_TRACE_LINES, is_minified, split_loc

_HEADER = re.compile(
    r"^(?P<prefix>\[cause\]: |\[errors\]: \[)?"
    r"(?:Uncaught |Unhandled )?"
    r"(?P<type>[A-Za-z_$][\w$.]*)(?:: ?(?P<msg>.*))?$"
)
_STRICT_TYPE = re.compile(r"(?:Error|Exception|Warning|Rejection|Abort|Failure|Fault)$")
_CODE = re.compile(r"""^code: ['"]?([\w.-]+)['"]?,?$""")
_NODE_VERSION = re.compile(r"^Node\.js v\d+")
_NO_FILE_LOCS = ("native", "<anonymous>", "unknown location")


def is_frame(s: str) -> bool:
    return s.startswith("at ") and len(s) > 3


def header_match(s: str, strict: bool) -> re.Match[str] | None:
    m = _HEADER.match(s)
    if not m:
        return None
    if strict and not (_STRICT_TYPE.search(m.group("type")) or m.group("prefix")):
        return None
    return m


def parse_frame(s: str) -> Frame:
    """Parse an 'at ...' line (leading whitespace already removed)."""
    s = s.rstrip()
    while s.endswith((",", "{")):
        s = s[:-1].rstrip()
    body = s[3:].strip()
    is_async = False
    if body.startswith("async "):
        is_async = True
        body = body[6:]
    func = ""
    loc = body
    if body.endswith(")"):
        p = body.find(" (")
        if p != -1:
            func = body[:p].strip()
            loc = body[p + 2 : -1]
    # eval at <fn> (outer.js:1:1), <anonymous>:1:1  -> report the outer location
    if loc.startswith("eval at "):
        q = loc.find(" (")
        loc = loc[q + 2 :].split(")", 1)[0] if q != -1 else loc
    file: str | None
    line: int | None = None
    col: int | None = None
    if loc in _NO_FILE_LOCS or loc.startswith("index "):
        file = None
    else:
        file, line, col = split_loc(loc)
        if "://" in file and "?" in file:
            file = file.split("?", 1)[0]
    kind = RUNTIME if file is None else node_kind(file, func)
    return Frame(
        function=func or "<anonymous>",
        file=file,
        line=line,
        column=col,
        kind=kind,
        raw=s,
        is_async=is_async,
        minified=is_minified(file, line, col),
    )


def parse(window: list[str]) -> tuple[Trace | None, int]:
    """Parse one trace; window[0] is the header line (or the first frame if none was found)."""
    notes: list[str] = []
    n = len(window)
    top: TNode | None = None
    cur: TNode | None = None
    err_stack: list[tuple[int, TNode]] = []  # open `[errors]: [` lists: (indent, owner)
    depth = 0
    i = 0
    end = 0
    while i < n:
        raw = window[i]
        s = raw.strip()
        indent = len(raw) - len(raw.lstrip())
        if not s:
            if cur is not None and cur.exc.frames and depth == 0:
                break
            i += 1
            continue
        if is_frame(s):
            if cur is None:
                cur = top = TNode(Exc(type="(unknown)", message="(no exception header in input)"))
                notes.append("No exception header line found; showing frames only.")
            cur.exc.frames.append(parse_frame(s))
            if s.endswith("{"):
                depth += 1
            i += 1
            end = i
            continue
        if s.startswith(("}", "]")) and s.rstrip(",") in ("}", "]", "]}"):
            if s.startswith("]") and err_stack and indent <= err_stack[-1][0]:
                err_stack.pop()
            depth = max(0, depth - 1)
            i += 1
            end = i
            continue
        if s.startswith("[errors]: [") and cur is not None:
            err_stack.append((indent, cur))
            depth += 1
            i += 1
            end = i
            continue
        m = header_match(s, strict=False)
        if m is not None and m.group("prefix") == "[cause]: " and cur is not None:
            node = TNode(Exc(type=m.group("type"), message=m.group("msg") or "", via="cause"))
            cur.cause = node
            cur = node
            i += 1
            end = i
            continue
        if depth > 0:
            if err_stack and indent > err_stack[-1][0] and m is not None and not _CODE.match(s):
                node = TNode(Exc(type=m.group("type"), message=m.group("msg") or "", via="inner"))
                err_stack[-1][1].children.append(node)
                cur = node
            else:
                cm = _CODE.match(s)
                if cm and cur is not None:
                    cur.exc.code = cm.group(1)
            i += 1
            end = i
            continue
        if cur is None:
            if m is None:
                break
            msg = m.group("msg") or ""
            if msg.endswith(" {"):
                msg = msg[:-2]
                depth += 1
            cur = top = TNode(Exc(type=m.group("type"), message=msg))
            i += 1
            end = i
            continue
        if not cur.exc.frames:
            cur.exc.message += "\n" + s  # multi-line message
            i += 1
            end = i
            continue
        if _NODE_VERSION.match(s):
            notes.append(s)
            end = i + 1
        break
    if top is None:
        return None, 1
    chain = flatten(top)
    partial = False
    if not any(e.frames for e in chain):
        notes.append("Exception header found but no stack frames followed.")
        partial = True
    if end >= MAX_TRACE_LINES:
        notes.append(f"Trace cut at {MAX_TRACE_LINES} lines.")
        partial = True
    return Trace("node", chain, notes=notes, partial=partial), max(end, 1)
