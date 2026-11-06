"""Python tracebacks, including chained exceptions and 3.11+ ExceptionGroup boxes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..classify import python_kind
from ..model import Exc, Frame, Trace
from .common import MAX_TRACE_LINES, looks_like_log_line

_FRAME = re.compile(r'^\s*File "(.*)", line (\d+)(?:, in (.*))?$')
_EXC = re.compile(r"^([A-Za-z_][\w.]*)(?::[ ]?(.*))?$")
_REPEAT = re.compile(r"^\s*\[Previous line repeated (\d+) more times?\]$")
_CAUSE = "The above exception was the direct cause of the following exception:"
_CONTEXT = "During handling of the above exception, another exception occurred:"
_SYNTAX = ("SyntaxError", "IndentationError", "TabError")

# ExceptionGroup box drawing
_PIPE = re.compile(r"^( *)\|(?: (.*))?$")
_PLUS_HEAD = re.compile(r"^( *)\+ (.*)$")
_CHILD_START = re.compile(r"^( *)\+-\+-+")
_SEP = re.compile(r"^( *)\+-+ *(\d+)? *-*$")


def is_start(line: str) -> bool:
    s = line.strip()
    return s.startswith(("Traceback (most recent call last):", "+ Exception Group Traceback"))


def is_bare_file_start(lines: list[str], i: int) -> bool:
    """`File "x.py", line 3` followed by a SyntaxError (no Traceback header)."""
    if not _FRAME.match(lines[i]):
        return False
    for j in range(i + 1, min(i + 6, len(lines))):
        s = lines[j]
        if s and not s[0].isspace():
            return s.startswith(_SYNTAX)
    return False


@dataclass
class _Region:
    content: list[str] = field(default_factory=list)
    children: list[_Region] = field(default_factory=list)


def _region(lines: list[str], i: int, col: int) -> tuple[_Region, int]:
    reg = _Region()
    n = len(lines)
    while i < n:
        line = lines[i]
        m = _PIPE.match(line)
        if m and len(m.group(1)) == col:
            reg.content.append(m.group(2) or "")
            i += 1
            continue
        m = _PLUS_HEAD.match(line)
        if m and len(m.group(1)) == col and not line.lstrip().startswith("+-"):
            reg.content.append(m.group(2))
            i += 1
            continue
        m = _CHILD_START.match(line)
        if m and len(m.group(1)) == col:
            i += 1
            while True:
                child, i = _region(lines, i, col + 2)
                reg.children.append(child)
                if i < n:
                    sm = _SEP.match(lines[i])
                    if sm and len(sm.group(1)) == col + 2:
                        i += 1
                        if sm.group(2) is None:
                            break
                        continue
                break
            break
        break
    return reg, i


def _parse_exc_line(line: str) -> tuple[str, str] | None:
    m = _EXC.match(line)
    if not m:
        return None
    return m.group(1), m.group(2) or ""


def _unit(lines: list[str], i: int, notes: list[str]) -> tuple[Exc | None, int, bool]:
    """Parse one traceback. Returns (exception, next index, truncated)."""
    n = len(lines)
    s = lines[i].strip()
    if s.startswith(("Traceback (most recent", "Exception Group Traceback")):
        i += 1
    frames: list[Frame] = []
    while i < n:
        m = _FRAME.match(lines[i])
        if m:
            path, lineno, func = m.group(1), int(m.group(2)) if len(m.group(2)) < 10 else 0, m.group(3)
            fr = Frame(
                function=func or "<module>" if func is not None else "(syntax)",
                file=path,
                line=lineno,
                kind=python_kind(path),
                raw=lines[i].strip(),
            )
            i += 1
            srcs: list[str] = []
            while i < n and lines[i].startswith("    ") and not _FRAME.match(lines[i]):
                t = lines[i].strip()
                if t and set(t) <= set("~^ "):
                    pass  # caret line
                elif t:
                    srcs.append(t)
                i += 1
            if srcs:
                fr.source = srcs[0]
            frames.append(fr)
            continue
        m2 = _REPEAT.match(lines[i])
        if m2 and frames:
            frames[-1].repeat = int(m2.group(1)) if len(m2.group(1)) < 10 else 0
            i += 1
            continue
        break
    frames.reverse()  # innermost first
    if i < n and lines[i] and not lines[i][0].isspace():
        parsed = _parse_exc_line(lines[i])
        if parsed is not None and lines[i].strip() not in (_CAUSE, _CONTEXT):
            exc = Exc(type=parsed[0], message=parsed[1], frames=frames)
            i += 1
            extra = 0
            while (
                i < n
                and lines[i]
                and extra < 20
                and not is_start(lines[i])
                and lines[i].strip() not in (_CAUSE, _CONTEXT)
                and not looks_like_log_line(lines[i])
                and not _PIPE.match(lines[i])
                and not _SEP.match(lines[i])
            ):
                exc.message += "\n" + lines[i].strip()
                i += 1
                extra += 1
            return exc, i, False
    if not frames:
        return None, i, True
    notes.append("Traceback ended without an exception line (input truncated?).")
    return Exc(type="<missing exception line>", frames=frames), i, True


def _items(
    lines: list[str], i: int, notes: list[str], bare: bool = False
) -> tuple[list[Exc], int, bool]:
    """Parse units joined by chain separators. Returns exceptions in printed order."""
    out: list[Exc] = []
    n = len(lines)
    partial = False
    while i < n:
        s = lines[i].strip()
        if _PLUS_HEAD.match(lines[i]) and s.startswith("+ Exception Group Traceback"):
            reg, i = _region(lines, i, len(lines[i]) - len(lines[i].lstrip()))
            sub, _, p = _items(reg.content, 0, notes, True)
            partial = partial or p
            if sub:
                grp = sub[-1]
                for child in reg.children:
                    csub, _, cp = _items(child.content, 0, notes, True)
                    partial = partial or cp
                    if csub:
                        _attach_nested(child, csub, notes)
                        grp.group.append(list(reversed(csub)))
                out.extend(sub)
        elif s.startswith(("Traceback (most recent", "Exception Group Traceback")) or (
            _FRAME.match(lines[i]) and (is_bare_file_start(lines, i) or not out)
        ) or (bare and _bare_exc(lines[i])):
            exc, i, trunc = _unit(lines, i, notes)
            if exc is None:
                partial = True
                break
            out.append(exc)
            partial = partial or trunc
        else:
            break
        j = i
        while j < n and not lines[j].strip():
            j += 1
        if j < n and lines[j].strip() in (_CAUSE, _CONTEXT):
            out[-1].via = "cause" if lines[j].strip() == _CAUSE else "context"
            i = j + 1
            while i < n and not lines[i].strip():
                i += 1
            if i >= n:
                notes.append("Input ends right after a chain separator (the next exception is missing).")
                partial = True
            continue
        break
    return out, i, partial


def _bare_exc(line: str) -> bool:
    return bool(line) and not line[0].isspace() and _parse_exc_line(line) is not None


def _attach_nested(child: _Region, csub: list[Exc], notes: list[str]) -> None:
    """A sub-exception that is itself an ExceptionGroup carries its own children."""
    if not child.children:
        return
    grp = csub[-1]
    for gc in child.children:
        gsub, _, _ = _items(gc.content, 0, notes, True)
        if gsub:
            _attach_nested(gc, gsub, notes)
            grp.group.append(list(reversed(gsub)))


def parse(window: list[str]) -> tuple[Trace | None, int]:
    """Parse one trace starting at window[0]. Returns (trace, lines consumed)."""
    notes: list[str] = []
    items, j, partial = _items(window, 0, notes)
    if not items:
        return None, 1
    chain = list(reversed(items))
    if j >= MAX_TRACE_LINES:
        notes.append(f"Trace cut at {MAX_TRACE_LINES} lines.")
        partial = True
    return Trace("python", chain, notes=notes, partial=partial), max(j, 1)
