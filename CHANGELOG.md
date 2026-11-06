# Changelog

## 0.1.0 - 2026-11-06

First release.

- Parsers: Python (chains, ExceptionGroup, SyntaxError, repeats), Node/V8, Java/Kotlin,
  Go (panic, fatal error, goroutine dumps, race reports), Rust, .NET.
- Tools: `parse_trace`, `find_traces_in_file`, `fingerprint`, `map_to_code`, `compare_traces`,
  `explain_exception`, `redact_trace`.
- Directory sandbox (`--dir`, repeatable) for the two tools that read files.
- Redaction of every tool's output by default.
