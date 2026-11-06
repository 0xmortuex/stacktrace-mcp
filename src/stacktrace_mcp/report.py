"""Compact text rendering of parsed traces."""

from __future__ import annotations

import re

from .fingerprint import components, fingerprint
from .model import APP, Exc, Frame, Trace

_REL = {
    "cause": "direct cause of the exception above",
    "context": "was being handled when the exception above was raised",
    "suppressed": "suppressed",
    "inner": "inner exception",
}
_SITE = re.compile(r"/(?:site|dist)-packages/([^/]+)")
_NODE_MOD = re.compile(r"node_modules/((?:@[^/]+/)?[^/]+)")


def clip(s: str, n: int = 200) -> str:
    return s if len(s) <= n else s[:n] + "..."


def lib_label(f: Frame) -> str:
    p = (f.file or "").replace("\\", "/")
    m = _SITE.search(p)
    if m:
        return m.group(1).split("-", 1)[0].removesuffix(".py")
    m2 = _NODE_MOD.search(p)
    if m2:
        return m2.group(1)
    if f.kind == "runtime" and p.startswith("node:"):
        return "node internals"
    fn = f.function
    if "::" in fn:
        return fn.lstrip("<&*").split("::", 1)[0]
    if "/" in fn and "." in fn:
        return fn.rsplit("/", 1)[0] + "/" + fn.rsplit("/", 1)[1].split(".", 1)[0]
    head = fn.split(".")
    if len(head) >= 3:
        return ".".join(head[:2])
    return f.kind


def _frame_line(f: Frame, mark: str) -> str:
    extra = ""
    if f.is_async:
        extra += " (async)"
    if f.inherited:
        extra += " (shared with enclosing trace)"
    if f.repeat:
        extra += f" (repeated {f.repeat + 1}x)"
    if f.minified:
        extra += " (minified: needs a source map)"
    out = f"  {mark} {f.kind:<9} {f.location()} in {f.function}{extra}"
    if f.source:
        out += f"\n               > {clip(f.source)}"
    return out


def render_frames(frames: list[Frame], full: bool, max_frames: int) -> list[str]:
    out: list[str] = []
    if not frames:
        return ["  (no frames)"]
    shown = 0
    hidden: list[Frame] = []

    def flush() -> None:
        if hidden:
            labels = sorted({lib_label(h) for h in hidden})
            lab = ", ".join(labels[:4]) + (", ..." if len(labels) > 4 else "")
            out.append(f"       ... {len(hidden)} non-application frame(s) hidden ({lab})")
            hidden.clear()

    for k, f in enumerate(frames):
        if shown >= max_frames:
            rest = len(frames) - k
            flush()
            out.append(f"       ... {rest} more frame(s); pass full=true and a larger max_frames to see them")
            return out
        if full or f.kind == APP or k == 0:
            flush()
            out.append(_frame_line(f, "*" if f.kind == APP else " "))
            shown += 1
        else:
            hidden.append(f)
    flush()
    return out


def _exc_line(e: Exc) -> str:
    msg = e.message.split("\n", 1)[0]
    if len(msg) > 300:
        msg = msg[:300] + "..."
    s = f"{e.type}: {msg}" if msg else e.type
    if e.code:
        s += f" [code {e.code}]"
    return s


def render_trace(t: Trace, full: bool = False, max_frames: int = 25, include_fingerprint: bool = True) -> str:
    L: list[str] = []
    head = f"Language: {t.language}"
    if t.partial:
        head += "  (PARTIAL parse)"
    if t.timestamp:
        head += f"  at {t.timestamp}"
    L.append(head)
    for note in t.notes:
        L.append(f"Note: {note}")
    L.append(f"Exception: {_exc_line(t.top)}")
    extra_lines = t.top.message.split("\n")[1:6]
    for x in extra_lines:
        L.append(f"           {x[:200]}")
    if len(t.chain) > 1:
        L.append("Chain (raised -> root cause):")
        for k, e in enumerate(t.chain, 1):
            rel = f"  [{_REL.get(e.via or '', e.via)}]" if k > 1 and e.via else ""
            tag = "   <-- ROOT CAUSE" if k == len(t.chain) and not e.group else ""
            L.append(f"  {k}. {_exc_line(e)}{rel}{tag}")
    roots = t.root_causes()
    for e in t.chain:
        if e.group:
            L.append(f"Sub-exceptions of {e.type} ({len(e.group)}):")
            for k, sub in enumerate(e.group, 1):
                leaf = sub[-1]
                chain_txt = " <- ".join(x.type for x in sub) if len(sub) > 1 else ""
                L.append(f"  {k}. {_exc_line(sub[0])}" + (f"   (chain: {chain_txt})" if chain_txt else ""))
                f0 = sub[-1].first_app_frame() or (leaf.frames[0] if leaf.frames else None)
                if f0:
                    L.append(f"       at {f0.location()} in {f0.function}")
    if t.top.thread:
        L.append(f"Thread: {t.top.thread}")
    for n in t.top.notes[:5]:
        L.append(f"Note: {n}")
    org = t.origin()
    if org is not None:
        L.append(f"Innermost application frame: {org[1].location()} in {org[1].function}")
        if org[1].source:
            L.append(f"    > {clip(org[1].source)}")
    else:
        L.append("Innermost application frame: none found (every frame looks like library/runtime code).")
    root = roots[0]
    label = "Frames of the root cause" if len(t.chain) > 1 or t.root is not root else "Frames"
    L.append(f"{label} (innermost first; * = application code):")
    L.extend(render_frames(root.frames, full, max_frames))
    for lab, frs in root.extra_stacks[:3]:
        L.append(f"{lab}:")
        L.extend(render_frames(frs, full, 8))
    if root.suppressed:
        L.append(f"Suppressed exceptions: {', '.join(_exc_line(s) for s in root.suppressed[:5])}")
    if t.goroutines:
        L.append(f"Other goroutines ({len(t.goroutines)}):")
        L.extend(f"  {g}" for g in t.goroutines[:10])
    if include_fingerprint:
        L.append(f"Fingerprint: {fingerprint(t)}  ({'; '.join(components(t))})")
    return "\n".join(L)
