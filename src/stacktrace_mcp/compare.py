"""Compare two traces: same root cause, and where they differ."""

from __future__ import annotations

from .fingerprint import fingerprint, frame_key
from .model import Frame, Trace


def _app_keys(frames: list[Frame]) -> list[str]:
    app = [f for f in frames if f.is_app and not f.inherited] or [f for f in frames if not f.inherited]
    out: list[str] = []
    for f in app:
        k = frame_key(f, False)
        if k not in out:
            out.append(k)
    return out


def _line_of(frames: list[Frame], key: str) -> int | None:
    for f in frames:
        if frame_key(f, False) == key:
            return f.line
    return None


def compare(a: Trace, b: Trace) -> str:
    ra, rb = a.root_causes()[0], b.root_causes()[0]
    fa, fb = fingerprint(a), fingerprint(b)
    ka, kb = _app_keys(ra.frames), _app_keys(rb.frames)
    common = [k for k in ka if k in kb]
    only_a = [k for k in ka if k not in kb]
    only_b = [k for k in kb if k not in ka]
    same_type = ra.type == rb.type
    top3a, top3b = ka[:3], kb[:3]
    shared_top = [k for k in top3a if k in top3b]
    if fa == fb:
        verdict = "SAME root cause (identical fingerprints)."
    elif a.language == b.language and same_type and shared_top and ka[:1] == kb[:1]:
        verdict = "LIKELY the same root cause: same language, same root exception type and the same innermost frame, but the fingerprints differ (see differences)."
    elif same_type and shared_top:
        verdict = "POSSIBLY related: same root exception type and some shared frames, but a different innermost frame."
    else:
        verdict = "DIFFERENT root causes."
    L = [
        verdict,
        f"A: {a.language} {a.top.type} (root cause {ra.type}) fingerprint {fa}",
        f"B: {b.language} {b.top.type} (root cause {rb.type}) fingerprint {fb}",
    ]
    if a.language != b.language:
        L.append(f"Languages differ: {a.language} vs {b.language}.")
    if not same_type:
        L.append(f"Root exception types differ: {ra.type} vs {rb.type}.")
    elif ra.message.split("\n", 1)[0] != rb.message.split("\n", 1)[0]:
        L.append("Same root exception type; the messages differ (expected for ids, paths and values).")
    if a.top.type != b.top.type:
        L.append(f"Top-level exception types differ: {a.top.type} vs {b.top.type}.")
    L.append(f"Common application frames ({len(common)}):")
    for k in common[:10]:
        la, lb = _line_of(ra.frames, k), _line_of(rb.frames, k)
        suffix = "" if la == lb else f"   (line {la} in A, line {lb} in B: the code changed or a different branch ran)"
        L.append(f"  = {k}{suffix}")
    L.append(f"Only in A ({len(only_a)}):")
    L.extend(f"  - {k}" for k in only_a[:10])
    L.append(f"Only in B ({len(only_b)}):")
    L.extend(f"  + {k}" for k in only_b[:10])
    if not ka and not kb:
        L.append("Neither trace has frames to compare.")
    return "\n".join(L)
