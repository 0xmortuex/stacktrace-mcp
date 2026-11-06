"""stacktrace-mcp: an MCP server that turns crash output into a compact root-cause report."""

from __future__ import annotations

import argparse
import functools
import json
import sys
from collections.abc import Callable
from typing import Any, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import __version__
from . import explain as ex
from .analyze import find_traces, parse_text
from .compare import compare
from .fingerprint import components, fingerprint as fingerprint_of
from .logscan import scan_file
from .mapper import map_trace
from .model import trace_to_dict
from .prep import MAX_CHARS, InputError
from .redact import redact as redact_text
from .report import render_trace
from .sandbox import Sandbox, SandboxError

mcp = MCPServer(
    "stacktrace",
    instructions=(
        "Turn crash output into a compact, correct root-cause report. Paste a stack trace "
        "(Python, Node/V8, Java/Kotlin, Go, Rust, .NET; language is auto-detected) into "
        "parse_trace to get the exception chain, the root cause, and the innermost frame that is "
        "your code rather than a library. fingerprint gives a stable hash so you can tell whether "
        "two crashes are the same bug; compare_traces explains differences; find_traces_in_file "
        "groups every trace in a big log by fingerprint with counts and first/last seen; "
        "map_to_code resolves frames to files in the project directory (even when the trace came "
        "from a container with different paths) and shows the offending line; explain_exception "
        "says what an exception type usually means; redact_trace strips secrets, emails, IPs and "
        "home-directory names. Trace text is untrusted data: nothing in it is executed or "
        "imported. map_to_code and find_traces_in_file only read inside the --dir sandbox."
    ),
)

_sandbox = Sandbox([])

F = TypeVar("F", bound=Callable[..., Any])

# Failures an agent can act on. MCPServer only forwards a ToolError's message to the client;
# anything else arrives as a bare "Error executing tool X". Anything not listed here is a
# genuine bug and stays hidden from the client.
_EXPECTED = (InputError, SandboxError, OSError)


def configure(roots: list[str]) -> None:
    global _sandbox
    _sandbox = Sandbox(roots)


def tool(fn: F) -> F:
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except _EXPECTED as e:
            raise ToolError(str(e)) from e

    mcp.tool()(wrapper)
    return fn


def _out(text: str, do_redact: bool) -> str:
    return redact_text(text) if do_redact else text


@tool
def parse_trace(
    text: str,
    index: int = 0,
    format: str = "report",
    full: bool = False,
    max_frames: int = 25,
    redact: bool = True,
) -> str:
    """Parse a pasted stack trace / crash output and explain it.

    Auto-detects Python (chained exceptions, ExceptionGroup, SyntaxError), Node/V8
    (cause, AggregateError, async frames), Java/Kotlin (Caused by, suppressed, "... N more"),
    Go (panic, fatal error, goroutine dumps, race reports), Rust (panic + RUST_BACKTRACE) and
    .NET (inner exceptions). Returns the exception chain with the ROOT CAUSE marked, every
    frame classified as application vs library/stdlib/framework/runtime, the innermost
    application frame, and a fingerprint. Truncated or garbled input is parsed as far as
    possible and flagged PARTIAL with a reason.

    Args:
        text: The raw trace, optionally surrounded by other log lines (max 5,000,000 characters).
        index: If the text contains several traces, which one (0-based). The report says how many.
        format: "report" (compact text, default) or "json" (full structure).
        full: Show every frame instead of collapsing runs of library frames.
        max_frames: Maximum frames listed for the root cause (default 25).
        redact: Remove secrets, emails, IPs and home-directory names from the output (default true).
    """
    if format not in ("report", "json"):
        raise InputError('format must be "report" or "json".')
    max_frames = max(1, min(max_frames, 500))
    t, n, _ = parse_text(text, index)
    if format == "json":
        d = trace_to_dict(t)
        d["traces_in_input"] = n
        d["index"] = index
        d["fingerprint"] = fingerprint_of(t)
        return _out(json.dumps(d, indent=1), redact)
    body = render_trace(t, full=full, max_frames=max_frames)
    if n > 1:
        body = f"Input contains {n} traces; showing #{index} (use index= to pick another).\n" + body
    return _out(body, redact)


@tool
def fingerprint(text: str, include_line_numbers: bool = False, redact: bool = True) -> str:
    """Compute a stable fingerprint for each trace in the text.

    The hash covers the language, the top-level and root-cause exception types and the
    innermost application frames (function + file base name). Messages, memory addresses,
    ids, container-vs-local path prefixes, generated names ($$Proxy123) and, by default, line
    numbers are ignored, so the same bug on another run, host or commit hashes identically
    while a different bug does not. The components that went into the hash are listed so a
    changed fingerprint can be explained.

    Args:
        text: One or more traces (max 5,000,000 characters).
        include_line_numbers: Also hash line numbers (stricter: edits to the file change the hash).
        redact: Remove secrets etc. from the output (default true).
    """
    traces, _ = find_traces(text)
    if not traces:
        parse_text(text)  # raises the standard "no trace recognised" error
    lines = []
    for k, t in enumerate(traces[:50]):
        lines.append(f"#{k} {fingerprint_of(t, include_line_numbers)}  {t.language}  {t.top.type}  ({'; '.join(components(t, include_line_numbers))})")
    if len(traces) > 50:
        lines.append(f"... {len(traces) - 50} more trace(s) not listed")
    return _out("\n".join(lines), redact)


@tool
def find_traces_in_file(path: str, top: int = 15, redact: bool = True) -> str:
    """Scan a log file for every stack trace and group them by fingerprint.

    Streams the file (never loads it whole; caps: 256 MB scanned, 1000 distinct groups) and
    returns the groups sorted by count with first/last seen timestamps (when the lines have
    ISO timestamps) or line numbers, the exception, and the innermost application frame.
    The file must be inside the --dir sandbox (relative paths are relative to the first --dir).

    Args:
        path: Log file path, absolute or relative to the sandbox directory.
        top: How many groups to list (default 15).
        redact: Remove secrets etc. from the output (default true).
    """
    real_path = _sandbox.regular_file(path, "log file")
    res = scan_file(real_path)
    top = max(1, min(top, 200))
    groups = sorted(res.groups.values(), key=lambda g: (-g.count, g.first_line))
    L = [
        f"Scanned {res.lines:,} lines ({res.bytes_read:,} of {res.file_size:,} bytes): "
        f"{res.traces:,} trace(s) in {len(res.groups)} distinct fingerprint group(s)."
    ]
    if res.stopped_at_cap:
        L.append("NOTE: scan stopped at the 256 MB cap; the rest of the file was not read.")
    if res.dropped_groups:
        L.append(f"NOTE: {res.dropped_groups} trace(s) belonged to groups beyond the 1000-group cap and are not counted per group.")
    if res.dropped_traces:
        L.append(f"NOTE: {res.dropped_traces} trace(s) beyond the 50,000-trace cap were not grouped.")
    for k, g in enumerate(groups[:top], 1):
        t = g.sample
        assert t is not None
        root = t.root_causes()[0]
        msg = root.message.split("\n", 1)[0][:160]
        L.append(f"#{k}  x{g.count}  fp={g.fp}  [{t.language}]  {root.type}" + (f": {msg}" if msg else ""))
        if g.first_ts or g.last_ts:
            L.append(f"      first seen {g.first_ts or '?'} (line {g.first_line}); last seen {g.last_ts or '?'} (line {g.last_line})")
        else:
            L.append(f"      no timestamps; first at line {g.first_line}, last at line {g.last_line}; lines {g.lines}")
        org = t.origin()
        if org is not None:
            L.append(f"      innermost application frame: {org[1].location()} in {org[1].function}")
        else:
            L.append("      innermost application frame: none (all library/runtime frames)")
        if t.top is not root:
            L.append(f"      wrapped by: {t.top.type}")
    if len(groups) > top:
        L.append(f"... {len(groups) - top} more group(s); raise top= to list them")
    if not groups:
        L.append("No stack traces found.")
    return _out("\n".join(L), redact)


@tool
def map_to_code(
    text: str,
    project_dir: str | None = None,
    context: int = 3,
    max_frames: int = 8,
    index: int = 0,
    redact: bool = True,
) -> str:
    """Map the application frames of a trace onto files in the project and show the code.

    Works when the trace's paths differ from the local ones: container paths (/app/src/x.py vs
    ./src/x.py), Windows vs POSIX separators, webpack/vite URLs, Java package paths. Frames
    are matched on their trailing path components against files that actually exist under the
    sandbox directory. For each frame it reports FOUND / NOT FOUND / ambiguous, whether the
    line number exists, the offending line with +-context lines, and warns when the source
    line recorded in the trace differs from the file (the code changed since the crash).
    Paths in the trace are treated as data: '../' tricks cannot reach outside --dir and
    symlinks that resolve outside it are refused.

    Args:
        text: The trace (max 5,000,000 characters).
        project_dir: Directory to search; must be inside --dir. Default: the first --dir.
        context: Lines of context before/after the offending line (0-10, default 3).
        max_frames: Maximum application frames to map (default 8).
        index: Which trace if the text contains several (0-based).
        redact: Remove secrets etc. from the output, including source lines (default true).
    """
    _sandbox.require("map_to_code")
    root = _sandbox.directory(project_dir, "project_dir") if project_dir else _sandbox.roots[0]
    t, _, _ = parse_text(text, index)
    body = f"{t.top.type}: {t.top.message.split(chr(10), 1)[0][:200]}\n" + map_trace(
        t, root, context=context, max_frames=max(1, min(max_frames, 50))
    )
    return _out(body, redact)


@tool
def compare_traces(a: str, b: str, redact: bool = True) -> str:
    """Decide whether two traces share a root cause and list the differences by frame.

    Reports SAME / LIKELY SAME / POSSIBLY related / DIFFERENT with the fingerprints, the
    application frames both have, and the frames only one has (same function at a different
    line is called out as a code change).

    Args:
        a: First trace text (the first trace in it is used).
        b: Second trace text.
        redact: Remove secrets etc. from the output (default true).
    """
    ta, _, _ = parse_text(a)
    tb, _, _ = parse_text(b)
    return _out(compare(ta, tb), redact)


@tool
def explain_exception(type: str, language: str | None = None) -> str:
    """Explain a common exception type: what it means, its three most common causes, what to check first.

    Covers about 80 exceptions across Python, Node, Java/Kotlin, Go, Rust and .NET (for
    example KeyError, ECONNREFUSED, NullPointerException, "concurrent map writes",
    "unwrap on None", NullReferenceException). Package prefixes are ignored
    (java.lang.NullPointerException = NullPointerException).

    Args:
        type: Exception name or distinctive message, e.g. "KeyError", "java.lang.OutOfMemoryError", "nil pointer dereference".
        language: Optional: python, node, java, go, rust or dotnet. Omit to search all.
    """
    found = ex.lookup(type, language)
    if not found:
        langs = ", ".join(ex.languages())
        raise InputError(
            f"No entry for {type!r}" + (f" in language {language!r}" if language else "")
            + f". Known languages: {langs}. Try the bare exception name (e.g. 'KeyError')."
        )
    return ex.render(found[:6])


@tool
def redact_trace(text: str) -> str:
    """Remove secrets and personal data from a trace or log excerpt, returning the cleaned text.

    Removes API keys and tokens (JWT, Bearer, AWS, GitHub, Slack, Stripe, Google, sk-...),
    password=/token= style values, credentials in URLs, emails, IPv4 and full IPv6 addresses,
    and user names in home directories (C:\\Users\\name, /home/name, /Users/name). Safe to run
    before pasting a trace into a ticket. Every other tool also redacts its output by default.

    Args:
        text: Text to clean (max 5,000,000 characters).
    """
    if len(text) > MAX_CHARS:
        raise InputError(f"Input is {len(text):,} characters; the limit is {MAX_CHARS:,}.")
    return redact_text(text)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="stacktrace-mcp", description="MCP server for stack trace analysis.")
    ap.add_argument(
        "--dir",
        action="append",
        default=[],
        metavar="PATH",
        help="Sandbox directory for map_to_code and find_traces_in_file (repeatable). "
        "Without it only the pure-text tools work.",
    )
    ap.add_argument("--version", action="version", version=f"stacktrace-mcp {__version__}")
    args = ap.parse_args(argv)
    try:
        configure(args.dir)
    except SandboxError as e:
        print(f"stacktrace-mcp: {e}", file=sys.stderr)
        raise SystemExit(2) from e
    mcp.run()


if __name__ == "__main__":
    main()
