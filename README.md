# stacktrace-mcp

**Paste a crash. Get the root cause, the line of your code that matters, and a hash that tells you whether you have seen it before.**

<!-- mcp-name: io.github.0xmortuex/stacktrace-mcp -->

stacktrace-mcp is an [MCP](https://modelcontextprotocol.io) server that turns raw crash output
(Python, Node/V8, Java/Kotlin, Go, Rust, .NET) into a compact, correct report, and maps it onto the
code in your project.

## Why another stack trace tool?

Existing MCP servers in this space are either narrow or lossy: a paid hosted "log fingerprint"
service ([Apify Log Fingerprint & Triage](https://apify.com/q_services/log-fingerprint-triage-mcp)),
regex-based log analysers that read three languages
([log-analyzer-mcp](https://github.com/Fato07/log-analyzer-mcp)), or crash-dump tooling tied to WinDbg
([mcp-windbg](https://github.com/svnscha/mcp-windbg)). What this one does differently:

- **Six hand-written parsers, one model.** Python chains and ExceptionGroup trees, Node `[cause]` /
  `AggregateError`, Java `Caused by:` with `... N more` reconstructed, Go goroutine dumps and race
  reports, Rust `RUST_BACKTRACE`, .NET inner exceptions. Every trace gets a *root cause*, not just a
  first line.
- **Application vs library frames** per language (site-packages, node_modules, JDK/framework
  packages, Go module cache, rustc std, .NET framework), so the innermost frame that is *yours* is
  highlighted.
- **Maps frames onto your checkout** even when the trace came from a container (`/app/src/x.py` vs
  `./src/x.py`), a Windows box, or a webpack bundle, with strict directory-sandbox protection.
- **Honest about bad input**: truncated or garbled traces are parsed as far as possible and flagged
  PARTIAL with a reason.
- **Local, free, zero dependencies beyond `mcp`**, linear-time parsing, and every output is
  redacted (secrets, emails, IPs, home-directory user names) by default.

## Install

Needs [uv](https://docs.astral.sh/uv/). Nothing to clone.

**Claude Code**

```
claude mcp add stacktrace -- uvx stacktrace-mcp --dir .
```

**Claude Desktop** (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "stacktrace": {
      "command": "uvx",
      "args": ["stacktrace-mcp", "--dir", "C:\\path\\to\\your\\project"]
    }
  }
}
```

`--dir` is the sandbox for `map_to_code` and `find_traces_in_file` (repeat it for several
directories). Without it, the pure-text tools (`parse_trace`, `fingerprint`, `compare_traces`,
`explain_exception`, `redact_trace`) still work.

## Try asking

- "Here is the crash from CI: *(paste)*. What is the root cause and which of my files is responsible?"
- "Map this production traceback onto my repo and show me the offending lines."
- "Scan `logs/app.log` and group every stack trace by fingerprint. Which bug happens most, and when did it first appear?"
- "Are these two tracebacks the same bug?"
- "What does `ECONNREFUSED` usually mean, and what do I check first?"
- "Redact this trace so I can paste it into a ticket."

## Tools

| Tool | What it does |
|---|---|
| `parse_trace(text)` | Auto-detects the language; returns exception chain with the root cause, frames classified app/library/stdlib/framework/runtime, innermost application frame, fingerprint, PARTIAL notes. `format="json"` for the full structure. |
| `find_traces_in_file(path)` | Streams a big log (cap 256 MB), finds every trace among normal lines, groups by fingerprint with counts and first/last seen. |
| `fingerprint(text)` | Stable hash over language + exception types + innermost application frames. Ignores messages, addresses, ids, path prefixes, generated class names and (by default) line numbers. Shows its components. |
| `map_to_code(text)` | Resolves frames to files under `--dir`, verifies the line exists, shows the line with context, warns when the source changed since the crash. |
| `compare_traces(a, b)` | SAME / LIKELY SAME / POSSIBLY related / DIFFERENT with a per-frame diff. |
| `explain_exception(type, language?)` | About 80 common exceptions: meaning, three most common causes, what to check first. |
| `redact_trace(text)` | Removes tokens, passwords, JWTs, emails, IPs and home-directory user names. |

All tools except `explain_exception` take `redact` (default `true`).

## What it understands

- **Python**: 3.8-3.13 tracebacks including `^^^^`/`~~~~` caret ranges, `__cause__`/`__context__`
  chains, `ExceptionGroup`/`TaskGroup` boxes (nested), `SyntaxError` with caret lines,
  `KeyboardInterrupt`, `[Previous line repeated N more times]`, `add_note()` lines.
- **Node/V8 and browsers**: `at fn (file:line:col)`, `at async`, `eval at`, `[cause]`,
  `AggregateError` `[errors]`, webpack-internal and Vite URLs, minified frames (flagged), props such
  as `code: 'ENOENT'`.
- **Java/Kotlin/Scala**: `Exception in thread`, `Caused by:`, `Suppressed:`, `... 23 more`
  (the elided frames are copied from the enclosing trace), `Native Method`, module prefixes
  (`java.base/`, `app//`), logback `~[jar:ver]` suffixes.
- **Go**: `panic:` (including `[recovered]` re-panics), `fatal error:` with `runtime stack:`,
  goroutine dumps with `created by`, the race detector's `WARNING: DATA RACE`.
- **Rust**: `thread 'x' panicked at` in the old and the 1.73+ message layout, `RUST_BACKTRACE`
  short and full forms, std/core frames marked, cargo registry frames marked as library.
- **.NET**: `at Ns.Class.Method() in file:line N`, `---> ` inner exceptions, `AggregateException`
  inner exception lists, async state-machine frames.

## Security

Trace text is **untrusted data**.

- Nothing in a trace is executed, imported or evaluated.
- Input is capped at 5,000,000 characters and 4,000 characters per line; every parser is
  single-pass and linear time. The test suite feeds each parser pathological shapes (a million open
  parentheses, 100k repeated headers, quadratic-regex bait) with a time limit.
- Paths in traces are data. `map_to_code` never opens a path taken from a trace: it indexes the
  files that actually exist under `--dir` and matches frames against that index by trailing path
  components, so `../../etc/passwd` can only ever select a file already inside the sandbox.
  Symlinks are resolved with `realpath` before every read and refused when they leave the sandbox;
  symlinked directories are not followed.
- `find_traces_in_file` and `map_to_code(project_dir=...)` only accept paths inside `--dir`.
- Output is redacted by default. Redaction is pattern based (see `redact_trace`); it is a safety
  net, not a guarantee, so review before publishing. IPv6 coverage is partial (full 8-group,
  `fe80::`, and bracketed forms).

## Limits

Heuristics decide app vs library: a project vendored into `site-packages` or `node_modules`
looks like a library, and a library copied into your tree looks like your code. Minified
JavaScript frames cannot be mapped without a source map. Trace formats evolve; if a real trace
parses wrongly, please open an issue with the (redacted) text.

## Development

```
uv sync --extra test
uv run pytest
uv run ruff check src tests
uv run mypy --strict src
```

MIT licensed. See also the companion course, [stacktrace-mcp-the-hard-way](https://github.com/0xmortuex/stacktrace-mcp-the-hard-way).
