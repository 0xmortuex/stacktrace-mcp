"""Shared test helpers. Fixtures are written as raw strings; <T> stands for a tab."""

from __future__ import annotations

import textwrap
from typing import Any

from stacktrace_mcp.analyze import parse_text
from stacktrace_mcp.model import Trace


def fx(s: str) -> str:
    """Dedent a fixture, drop the leading newline, and expand <T> to a tab."""
    s = textwrap.dedent(s)
    if s.startswith("\n"):
        s = s[1:]
    return s.replace("<T>", "\t")


def parse(text: str, index: int = 0) -> Trace:
    return parse_text(text, index)[0]


def check(
    text: str,
    *,
    lang: str,
    top: str | None = None,
    root: str | None = None,
    msg: str | None = None,
    origin: tuple[str, str, int | None] | None = None,
    chain: int | None = None,
    partial: bool = False,
    frames: int | None = None,
    kinds: dict[int, str] | None = None,
    **_: Any,
) -> Trace:
    t = parse(text)
    assert t.language == lang, (t.language, lang)
    if top is not None:
        assert t.top.type == top, (t.top.type, top)
    if root is not None:
        assert t.root_causes()[0].type == root, (t.root_causes()[0].type, root)
    if msg is not None:
        assert msg in t.top.message or msg in t.root_causes()[0].message, (t.top.message, msg)
    if chain is not None:
        assert len(t.chain) == chain, [e.type for e in t.chain]
    assert t.partial is partial, (t.partial, t.notes)
    r = t.root_causes()[0]
    if frames is not None:
        assert len(r.frames) == frames, [(f.function, f.location()) for f in r.frames]
    if origin is not None:
        o = t.origin()
        assert o is not None, "no application frame found"
        fn, file, line = origin
        assert fn in o[1].function, (o[1].function, fn)
        assert file in (o[1].file or ""), (o[1].file, file)
        if line is not None:
            assert o[1].line == line, (o[1].line, line)
    if kinds:
        for i, k in kinds.items():
            assert r.frames[i].kind == k, (i, r.frames[i].function, r.frames[i].kind, k)
    return t
