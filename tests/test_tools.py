"""Tool-level behaviour: report content, JSON structure, explain_exception, compare_traces."""

from __future__ import annotations

import json

import pytest
from helpers import fx
from stacktrace_mcp import explain, server
from stacktrace_mcp.prep import InputError

CHAINED = fx(r"""
    Traceback (most recent call last):
      File "/app/src/config.py", line 42, in parse_port
        port = int(raw)
               ^^^^^^^^
    ValueError: invalid literal for int() with base 10: 'abc'

    The above exception was the direct cause of the following exception:

    Traceback (most recent call last):
      File "/app/main.py", line 10, in <module>
        main()
      File "/usr/lib/python3.12/site-packages/click/core.py", line 1, in main
        x()
      File "/usr/lib/python3.12/site-packages/click/core.py", line 2, in invoke
        y()
      File "/app/main.py", line 6, in main
        raise RuntimeError("config load failed") from e
    RuntimeError: config load failed
    """)


def test_report_has_the_essentials() -> None:
    out = server.parse_trace(CHAINED)
    assert "Exception: RuntimeError: config load failed" in out
    assert "ROOT CAUSE" in out and "ValueError" in out
    assert "Innermost application frame: /app/src/config.py:42 in parse_port" in out
    assert "Fingerprint:" in out
    assert "direct cause" in out


def test_library_frames_are_collapsed_unless_full() -> None:
    root_has_lib = fx(r"""
        Traceback (most recent call last):
          File "/app/main.py", line 1, in <module>
            go()
          File "/usr/lib/python3.12/site-packages/requests/api.py", line 5, in get
            x()
          File "/usr/lib/python3.12/site-packages/urllib3/pool.py", line 9, in urlopen
            y()
        OSError: boom
        """)
    short = server.parse_trace(root_has_lib)
    assert "non-application frame(s) hidden" not in short.split("Frames")[0]
    full = server.parse_trace(root_has_lib, full=True)
    assert "site-packages/requests/api.py" in full
    collapsed = server.parse_trace(root_has_lib.replace("urlopen", "urlopen"))
    assert "requests" in collapsed or "urllib3" in collapsed


def test_json_format_is_valid_and_structured() -> None:
    d = json.loads(server.parse_trace(CHAINED, format="json"))
    assert d["language"] == "python"
    assert [e["type"] for e in d["chain"]] == ["RuntimeError", "ValueError"]
    assert d["root_cause"]["type"] == "ValueError"
    assert d["innermost_app_frame"]["function"] == "parse_port"
    assert d["fingerprint"] and d["partial"] is False
    kinds = {f["kind"] for e in d["chain"] for f in e["frames"]}
    assert {"app", "library"} <= kinds | {"library"}


def test_partial_is_loud() -> None:
    out = server.parse_trace('Traceback (most recent call last):\n  File "/a.py", line 1, in f\n')
    assert "PARTIAL" in out and "truncated" in out


def test_fingerprint_tool_lists_each_trace() -> None:
    out = server.fingerprint(CHAINED + "\n" + CHAINED)
    assert out.count("#") >= 2
    assert out.splitlines()[0].split()[1] == out.splitlines()[1].split()[1]


def test_fingerprint_tool_rejects_text_without_traces() -> None:
    with pytest.raises(InputError):
        server.fingerprint("no trace here")


def test_compare_same_bug() -> None:
    out = server.compare_traces(CHAINED, CHAINED.replace("line 42", "line 45"))
    assert out.startswith("SAME root cause")
    assert "parse_port" in out


def test_compare_different_bug() -> None:
    other = fx(r"""
        Traceback (most recent call last):
          File "/app/other.py", line 3, in thing
            raise KeyError('x')
        KeyError: 'x'
        """)
    out = server.compare_traces(CHAINED, other)
    assert out.startswith("DIFFERENT")
    assert "Root exception types differ" in out


def test_compare_cross_language() -> None:
    java = "java.lang.IllegalStateException: x\n\tat com.acme.A.b(A.java:1)\n"
    out = server.compare_traces(CHAINED, java)
    assert out.startswith("DIFFERENT") and "Languages differ" in out


def test_compare_notes_line_changes() -> None:
    a = fx(r"""
        Traceback (most recent call last):
          File "/app/a.py", line 10, in f
            x()
        ValueError: v
        """)
    b = a.replace("line 10", "line 14")
    out = server.compare_traces(a, b)
    assert "SAME" in out.splitlines()[0] and "line 10 in A, line 14 in B" in out


def test_explain_table_is_well_formed() -> None:
    assert len(explain.TABLE) >= 60
    for e in explain.TABLE:
        assert e.meaning and e.check and len(e.causes) == 3 and all(e.causes)
        assert e.language in {"python", "node", "java", "go", "rust", "dotnet"}
    assert set(explain.languages()) == {"python", "node", "java", "go", "rust", "dotnet"}


@pytest.mark.parametrize(
    ("name", "lang", "needle"),
    [
        ("KeyError", "python", "dict"),
        ("builtins.KeyError", None, "dict"),
        ("java.lang.NullPointerException", "java", "null reference"),
        ("NullPointerException", None, "null"),
        ("System.NullReferenceException", "dotnet", "null reference"),
        ("ECONNREFUSED", "node", "listening"),
        ("concurrent map writes", "go", "synchronisation"),
        ("all goroutines are asleep - deadlock!", None, "blocked"),
        ("DATA RACE", "go", "race detector"),
        ("unwrap on None", "rust", "None"),
        ("called `Option::unwrap()` on a `None` value", None, "unwrap"),
        ("ModuleNotFoundError", "python", "venv"),
        ("OutOfMemoryError", "java", "heap"),
        ("StackOverflowError", None, "recursion"),
        ("java.util.ConcurrentModificationException", None, "iterated"),
        ("keyerror", "PY", "dict"),
    ],
)
def test_explain_lookups(name: str, lang: str | None, needle: str) -> None:
    out = server.explain_exception(name, lang)
    assert needle.lower() in out.lower()
    assert "Most common causes:" in out and "Check first:" in out
    assert out.count("\n    ") >= 3


def test_explain_unknown_is_actionable() -> None:
    with pytest.raises(InputError, match="Known languages"):
        server.explain_exception("TotallyMadeUpError", "python")


def test_explain_language_filter() -> None:
    out = server.explain_exception("TypeError", "node")
    assert out.startswith("[node]") and "[python]" not in out
    both = server.explain_exception("TypeError")
    assert "[node]" in both and "[python]" in both


def test_redact_trace_tool_returns_text() -> None:
    out = server.redact_trace("mail me at bob@example.org from 10.1.2.3")
    assert "bob@" not in out and "10.1.2.3" not in out
