"""Stable fingerprints for traces: same bug on a different run gives the same hash."""

from __future__ import annotations

import hashlib
import re

from .model import Exc, Frame, Trace

TOP_FRAMES = 3

_HEX_ADDR = re.compile(r"0x[0-9a-fA-F]+")
_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_LONG_HEX = re.compile(r"(?<![0-9A-Za-z])[0-9a-fA-F]{12,}(?![0-9A-Za-z])")
_GEN_SUFFIX = re.compile(r"\$\$[A-Za-z0-9_$]*|\$Proxy\d+|\$\$Lambda\$\d+(?:/0x[0-9a-f]+)?|\$\d+")
_NUM = re.compile(r"\d+")
_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")
_GO_GENERIC = re.compile(r"\[\.\.\.\]")
_NET_GEN = re.compile(r"`\d+")
_CLOSURE = re.compile(r"\.func\d+(?:\.\d+)*$")
_WEBPACK = re.compile(r"^(?:webpack(?:-internal)?:///?|file:///|https?://[^/]+)")


def normalize_function(fn: str) -> str:
    fn = _HEX_ADDR.sub("0x", fn)
    fn = _UUID.sub("<id>", fn)
    fn = _LONG_HEX.sub("<id>", fn)
    fn = _GEN_SUFFIX.sub("$gen", fn)
    fn = _NET_GEN.sub("", fn)
    fn = _GO_GENERIC.sub("", fn)
    fn = _CLOSURE.sub(".funcN", fn)
    return fn.strip()


def normalize_file(path: str | None) -> str:
    """File identity that survives container vs local paths: the base name only."""
    if not path:
        return ""
    p = path.replace("\\", "/")
    p = _WEBPACK.sub("", p)
    p = p.split("?", 1)[0].split("#", 1)[0]
    base = p.rstrip("/").rsplit("/", 1)[-1]
    # strip content hashes in bundled names: app.3f9a1c2d.js -> app.js, chunk-ABCD1234.js -> chunk.js
    base = re.sub(r"[.-][0-9a-fA-F]{8,}(?=\.|$)", "", base)
    return base


def frame_key(f: Frame, with_lines: bool) -> str:
    key = f"{normalize_function(f.function)}|{normalize_file(f.file)}"
    if with_lines and f.line is not None:
        key += f":{f.line}"
    return key


def _top_frames(exc: Exc) -> list[Frame]:
    app = [f for f in exc.frames if f.is_app and not f.inherited]
    if app:
        return app[:TOP_FRAMES]
    return [f for f in exc.frames if not f.inherited][:TOP_FRAMES]


def _exc_type(t: str) -> str:
    return t[len("builtins.") :] if t.startswith("builtins.") else t


def _message_class(msg: str) -> str:
    """Message with the volatile parts blanked out (numbers, quoted values, addresses)."""
    first = msg.partition(chr(10))[0][:120]
    first = _QUOTED.sub("''", first)
    first = _HEX_ADDR.sub("0x", first)
    return _NUM.sub("N", first)


def components(trace: Trace, include_lines: bool = False) -> list[str]:
    """The human-readable inputs of the hash, so a changed fingerprint can be explained."""
    root = trace.root_causes()[0]
    parts = [
        f"lang={trace.language}",
        f"top={_exc_type(trace.top.type)}",
        f"root={_exc_type(root.type)}",
    ]
    if trace.language in ("go", "rust"):
        # these runtimes have one generic exception type; the message class tells bugs apart
        parts.append(f"msg={_message_class(root.message)}")
    for k, f in enumerate(_top_frames(root)):
        parts.append(f"f{k}={frame_key(f, include_lines)}")
    if trace.top is not root:
        for f in _top_frames(trace.top)[:1]:
            parts.append(f"outer={frame_key(f, include_lines)}")
    return parts


def fingerprint(trace: Trace, include_lines: bool = False) -> str:
    h = hashlib.sha256("\n".join(components(trace, include_lines)).encode("utf-8")).hexdigest()
    return h[:16]
