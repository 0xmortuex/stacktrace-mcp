"""Java / Kotlin / Scala stack traces (JVM format)."""

from __future__ import annotations

import re
from dataclasses import replace

from ..classify import java_kind
from ..model import Exc, Frame, Trace
from .common import MAX_TRACE_LINES, to_int

_THREAD = re.compile(r'^Exception in thread "(.*?)" (.*)$')
_TYPE = re.compile(r"^(?P<type>[A-Za-z_$][\w$.]*)(?:: ?(?P<msg>.*))?$")
_MORE = re.compile(r"^\.\.\. (\d+) (?:more|common frames omitted)$")
_JAVA_LOC = re.compile(r"^(?P<file>[\w$.\-<>]+\.(?:java|kt|kts|scala|groovy|clj)):(?P<line>\d+)$")
_STRICT = re.compile(r"(?:Exception|Error|Throwable|Failure|Fault)$")


def is_frame(s: str) -> bool:
    """True for a JVM frame: `at pkg.Class.method(File.java:12)` (also Native Method / Unknown Source)."""
    if not s.startswith("at "):
        return False
    p = s.find("(")
    if p == -1:
        return False
    q = s.find(")", p)
    if q == -1:
        return False
    loc = s[p + 1 : q]
    return bool(_JAVA_LOC.match(loc)) or loc in ("Native Method", "Unknown Source") or (
        loc.endswith((".java", ".kt", ".scala", ".groovy")) and " " not in loc
    )


def header_type(s: str, strict: bool) -> tuple[str, str, str | None] | None:
    """(type, message, thread) when s looks like a JVM exception header."""
    thread = None
    t = _THREAD.match(s)
    if t:
        thread, s = t.group(1), t.group(2)
    m = _TYPE.match(s)
    if not m:
        return None
    typ = m.group("type")
    if strict:
        last = typ.rsplit(".", 1)[-1]
        dotted = "." in typ and typ[0].islower()
        if not (_STRICT.search(last) or dotted):
            return None
    return typ, m.group("msg") or "", thread


def embedded_header(line: str) -> tuple[str, str, str | None] | None:
    """Find `pkg.SomeException: msg` inside a log line such as `ERROR Foo - failed: java.lang.X: msg`."""
    toks = line.split(" ")
    for k, tok in enumerate(toks):
        cand = tok.rstrip(":")
        if "." in cand and _STRICT.search(cand.rsplit(".", 1)[-1]) and cand[:1].isalpha() and cand[0].islower():
            rest = " ".join(toks[k + 1 :]) if tok.endswith(":") else ""
            return cand, rest, None
    return None


def parse_frame(s: str) -> Frame:
    body = s[3:].strip()
    p = body.find("(")
    q = body.find(")", p)
    qual = body[:p]
    loc = body[p + 1 : q]
    module: str | None = None
    if "/" in qual:
        module, _, qual = qual.rpartition("/")
        module = module.strip("/") or None
    cls, _, method = qual.rpartition(".")
    file: str | None = None
    line: int | None = None
    native = loc == "Native Method"
    m = _JAVA_LOC.match(loc)
    if m:
        file, line = m.group("file"), to_int(m.group("line"))
    elif loc not in ("Native Method", "Unknown Source"):
        file = loc or None
    hint = None
    if file and cls:
        pkg_cls = cls.split("$", 1)[0]
        pkg = pkg_cls.rpartition(".")[0]
        hint = (pkg.replace(".", "/") + "/" if pkg else "") + file
    return Frame(
        function=f"{cls}.{method}" if cls else method,
        file=file,
        line=line,
        kind=java_kind(cls),
        module=module,
        raw=s,
        path_hint=hint,
        native=native,
    )


def _indent(raw: str) -> int:
    tabs = 0
    spaces = 0
    for ch in raw:
        if ch == "	":
            tabs += 1
        elif ch == " ":
            spaces += 1
        else:
            break
    return tabs + spaces // 4


def parse(window: list[str]) -> tuple[Trace | None, int]:
    notes: list[str] = []
    n = len(window)
    chains: dict[int, list[Exc]] = {}  # header indent level -> chain printed so far
    top_chain: list[Exc] | None = None
    cur: Exc | None = None
    enclosing: dict[int, Exc | None] = {}
    i = 0
    end = 0
    saw_frame = False
    base = 0
    while i < n:
        raw = window[i]
        s = raw.strip()
        if not s:
            if saw_frame:
                break
            i += 1
            continue
        lvl = max(0, _indent(raw) - base)
        if is_frame(s):
            if cur is None:
                cur = Exc(type="(unknown)", message="(no exception header in input)")
                top_chain = chains[0] = [cur]
                notes.append("No exception header line found; showing frames only.")
            cur.frames.append(parse_frame(s))
            saw_frame = True
            i += 1
            end = i
            continue
        mm = _MORE.match(s)
        if mm and cur is not None:
            k = int(mm.group(1)) if len(mm.group(1)) < 9 else 0
            cur.elided = k
            parent = enclosing.get(id(cur))
            if parent is not None and k:
                shared = parent.frames[-k:] if k <= len(parent.frames) else list(parent.frames)
                for f in shared:
                    cur.frames.append(replace(f, inherited=True))
            elif k:
                notes.append(f"'... {k} more' refers to frames not present in the input.")
            i += 1
            end = i
            continue
        if s.startswith("Caused by: ") and cur is not None:
            h = header_type(s[len("Caused by: ") :], strict=False)
            if h is None:
                break
            chain = chains.get(lvl) or chains.get(max((k for k in chains if k <= lvl), default=0))
            if chain is None:
                break
            exc = Exc(type=h[0], message=h[1], via="cause")
            enclosing[id(exc)] = chain[-1]
            chain.append(exc)
            cur = exc
            saw_frame = False
            i += 1
            end = i
            continue
        if s.startswith("Suppressed: ") and cur is not None:
            h = header_type(s[len("Suppressed: ") :], strict=False)
            if h is None:
                break
            parent_chain = chains.get(lvl - 1) or top_chain
            if not parent_chain:
                break
            parent = parent_chain[-1]
            exc = Exc(type=h[0], message=h[1], via="suppressed")
            enclosing[id(exc)] = parent
            parent.suppressed.append(exc)
            chains[lvl] = [exc]
            for deeper in [k for k in chains if k > lvl]:
                del chains[deeper]
            cur = exc
            saw_frame = False
            i += 1
            end = i
            continue
        if cur is None:
            h = header_type(s, strict=False) or embedded_header(s)
            if not h:
                break
            base = lvl
            exc = Exc(type=h[0], message=h[1], thread=h[2])
            top_chain = chains[0] = [exc]
            cur = exc
            i += 1
            end = i
            continue
        if not saw_frame and not raw[:1].isspace() and header_type(s, strict=True) is None:
            cur.message += "\n" + s  # multi-line message
            i += 1
            end = i
            continue
        if not saw_frame and raw[:1].isspace() and not s.startswith(("at ", "...")):
            cur.message += "\n" + s
            i += 1
            end = i
            continue
        break
    if top_chain is None:
        return None, 1
    partial = not any(e.frames for e in top_chain)
    if partial:
        notes.append("Exception header found but no stack frames followed.")
    if end >= MAX_TRACE_LINES:
        notes.append(f"Trace cut at {MAX_TRACE_LINES} lines.")
        partial = True
    return Trace("java", top_chain, notes=notes, partial=partial), max(end, 1)
