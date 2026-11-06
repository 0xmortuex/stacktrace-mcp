"""Go panics, fatal errors, goroutine dumps and race detector reports."""

from __future__ import annotations

import re

from ..classify import go_kind
from ..model import Exc, Frame, Trace
from .common import MAX_TRACE_LINES, split_loc

_GOROUTINE = re.compile(r"^goroutine (\d+)(?: gp=\S+ m=\S+(?: mp=\S+)?)? \[([^\]]*)\]:?$")
_PANIC = re.compile(r"^panic: (.*)$")
_FATAL = re.compile(r"^fatal error: (.*)$")
_SIGNAL = re.compile(r"^\[signal (.*)\]$")
_RACE_SEC = re.compile(r"^(?:(?:Previous )?(?:[Aa]tomic )?(?:[Ww]rite|[Rr]ead)|Goroutine \d+ \(\w+\) created|Mutex \S+) .*:$")
_FILE_LINE = re.compile(r"^\s+(\S.*?):(\d+)(?: \+0x[0-9a-fA-F]+)?$")
_ELIDED = re.compile(r"^\.\.\.(?:\d+ )?(?:additional )?frames elided\.\.\.$")
_CREATED = re.compile(r"^created by (.+?)(?: in goroutine (\d+))?$")


def is_start(s: str) -> bool:
    return bool(
        s.startswith(("panic: ", "fatal error: ", "WARNING: DATA RACE", "SIGQUIT:", "SIGSEGV:", "SIGABRT:"))
        or _GOROUTINE.match(s)
    )


def _func_name(s: str) -> str:
    """'main.(*T).run(0xc000, {0x1, 0x2})' -> 'main.(*T).run'; 'main.main()' -> 'main.main'."""
    if not s.endswith(")"):
        return s
    depth = 0
    for k in range(len(s) - 1, -1, -1):
        c = s[k]
        if c == ")":
            depth += 1
        elif c == "(":
            depth -= 1
            if depth == 0:
                name = s[:k]
                # a method receiver like '(*T)' directly after a dot is part of the name
                if name.endswith(".") or name == "":
                    continue
                return name
    return s


def _frames(lines: list[str], i: int) -> tuple[list[Frame], int]:
    frames: list[Frame] = []
    n = len(lines)
    while i < n:
        raw = lines[i]
        s = raw.strip()
        if not s:
            break
        if _ELIDED.match(s):
            i += 1
            continue
        if i + 1 < n and _FILE_LINE.match(lines[i + 1]) and not _FILE_LINE.match(raw):
            cm = _CREATED.match(s)
            name = _func_name(cm.group(1)) if cm else _func_name(s)
            fm = _FILE_LINE.match(lines[i + 1])
            assert fm is not None
            path, ln = fm.group(1), int(fm.group(2)) if len(fm.group(2)) < 10 else 0
            frames.append(
                Frame(
                    function=("created by " + name) if cm else name,
                    file=path,
                    line=ln,
                    kind=go_kind(name, path),
                    module=name.rsplit(".", 1)[0] if "." in name else None,
                    raw=s,
                )
            )
            i += 2
            continue
        cm = _CREATED.match(s)
        if cm or s.endswith(")"):
            # frame without a following file line (truncated input)
            name = _func_name(cm.group(1)) if cm else _func_name(s)
            frames.append(Frame(function=name, kind=go_kind(name, None), raw=s))
            i += 1
            continue
        break
    return frames, i


def _exc_from_panic(msg: str) -> Exc:
    recovered = msg.endswith(" [recovered]")
    if recovered:
        msg = msg[: -len(" [recovered]")]
    if msg.startswith("runtime error: "):
        e = Exc(type="runtime error", message=msg[len("runtime error: ") :])
    elif msg.startswith("interface conversion: "):
        e = Exc(type="interface conversion", message=msg[len("interface conversion: ") :])
    else:
        e = Exc(type="panic", message=msg)
    if recovered:
        e.notes.append("recovered and re-panicked")
    return e


def _parse_race(lines: list[str], i: int) -> tuple[Trace | None, int]:
    n = len(lines)
    exc = Exc(type="DATA RACE", message="")
    sections: list[tuple[str, list[Frame]]] = []
    i += 1
    while i < n:
        s = lines[i].strip()
        if s.startswith("====") or s.startswith("Found ") or (not s and sections and i + 1 < n and not lines[i + 1].strip()):
            break
        if _RACE_SEC.match(s):
            frames, i = _frames(lines, i + 1)
            sections.append((s.rstrip(":"), frames))
            continue
        i += 1
    if not sections:
        return None, 1
    exc.message = sections[0][0]
    exc.frames = sections[0][1]
    exc.extra_stacks = sections[1:]
    # swallow the closing ==== line
    while i < n and lines[i].strip() and not lines[i].startswith("===="):
        i += 1
    if i < n and lines[i].startswith("===="):
        i += 1
    return Trace("go", [exc], notes=["Race detector report: the first stack is the access that was caught, "
                                      "the next stacks are the conflicting access and goroutine creation sites."]), i


def parse(window: list[str]) -> tuple[Trace | None, int]:
    n = len(window)
    if window[0].strip().startswith("WARNING: DATA RACE"):
        return _parse_race(window, 0)
    items: list[Exc] = []
    notes: list[str] = []
    goroutines: list[str] = []
    main_frames: list[Frame] | None = None
    i = 0
    end = 0
    seen_section = False
    while i < n:
        s = window[i].strip()
        pm = _PANIC.match(s)
        fm = _FATAL.match(s)
        if (pm or fm) and not seen_section:
            if pm:
                items.append(_exc_from_panic(pm.group(1)))
            else:
                assert fm is not None
                items.append(Exc(type="fatal error", message=fm.group(1)))
            i += 1
            end = i
            # continuation lines of a multi-line panic value
            while i < n:
                t = window[i].strip()
                if not t or _SIGNAL.match(t) or _GOROUTINE.match(t) or _PANIC.match(t) or t == "runtime stack:":
                    break
                if window[i][:1] in (chr(9), " "):
                    break
                items[-1].message += chr(10) + t
                i += 1
                end = i
            continue
        sig = _SIGNAL.match(s)
        if sig and items and not seen_section:
            items[-1].notes.append("signal " + sig.group(1))
            i += 1
            end = i
            continue
        if s == "runtime stack:" and items:
            fr, i = _frames(window, i + 1)
            items[-1].extra_stacks.append(("runtime stack", fr))
            end = i
            seen_section = True
            continue
        gm = _GOROUTINE.match(s)
        if gm:
            seen_section = True
            fr, j = _frames(window, i + 1)
            label = f"goroutine {gm.group(1)} [{gm.group(2)}]"
            if main_frames is None:
                main_frames = fr
                if not items:
                    items.append(Exc(type="goroutine dump", message=label))
                items[-1].frames = fr
                items[-1].thread = label
            else:
                top = next((f for f in fr if f.kind != "runtime"), fr[0] if fr else None)
                goroutines.append(label + (f" in {top.function}" if top else ""))
            i = j
            end = i
            continue
        if not s:
            i += 1
            nxt = i
            while nxt < n and not window[nxt].strip():
                nxt += 1
            nxt_s = window[nxt].strip() if nxt < n else ""
            ok = _GOROUTINE.match(nxt_s) or nxt_s == "runtime stack:" or (not seen_section and _SIGNAL.match(nxt_s))
            if not ok:
                break
            continue
        if s.startswith(("exit status", "exit code", "FAIL" + chr(9))):
            end = i + 1
        break
    if not items:
        return None, 1
    if end >= MAX_TRACE_LINES:
        notes.append(f"Trace cut at {MAX_TRACE_LINES} lines.")
    # Go prints the panic that killed the program last; earlier ones were recovered and the
    # printed goroutine stack belongs to the final panic, so they become notes on it.
    final = items[-1]
    for earlier in items[:-1]:
        final.notes.append(f"earlier panic (recovered): {earlier.type}: {earlier.message.splitlines()[0] if earlier.message else ''}")
    chain = [final]
    if len(goroutines) > 40:
        notes.append(f"{len(goroutines) - 40} more goroutines not listed.")
        goroutines = goroutines[:40]
    partial = not main_frames
    if partial:
        notes.append("No goroutine stack followed the panic message (input truncated?).")
    elif main_frames and main_frames[-1].file is None:
        notes.append("Last frame has no file:line (input truncated?).")
        partial = True
    return Trace("go", chain, notes=notes, partial=partial, goroutines=goroutines), max(end, 1)


__all__ = ["parse", "is_start", "split_loc"]
