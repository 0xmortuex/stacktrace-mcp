"""Mixed logs and find_traces_in_file: interleaved traces, timestamps, grouping, caps, streaming."""

from __future__ import annotations

from pathlib import Path

import pytest
from helpers import fx
from stacktrace_mcp import logscan, server
from stacktrace_mcp.analyze import find_traces
from stacktrace_mcp.sandbox import SandboxError


def tb(key: str, lineno: int = 40) -> str:
    return (
        "Traceback (most recent call last):\n"
        f'  File "/app/src/orders.py", line {lineno}, in handle\n'
        "    total = compute(order)\n"
        '  File "/app/src/pricing.py", line 12, in compute\n'
        f'    return order["{key}"] * price\n'
        f"KeyError: '{key}'\n"
    )


JAVA = (
    "java.lang.IllegalStateException: no tenant\n"
    "\tat com.acme.Svc.find(Svc.java:30)\n"
    "\tat com.acme.Web.get(Web.java:12)\n"
)
NODE = (
    "TypeError: Cannot read properties of undefined (reading 'x')\n"
    "    at render (/app/ui.js:10:5)\n"
    "    at Object.<anonymous> (/app/ui.js:30:1)\n"
)
GO = (
    "panic: runtime error: index out of range [5] with length 3\n"
    "\n"
    "goroutine 1 [running]:\n"
    "main.process(...)\n"
    "\t/app/main.go:12\n"
    "main.main()\n"
    "\t/app/main.go:20 +0x1d\n"
    "exit status 2\n"
)


def build_log() -> str:
    L: list[str] = []
    L.append("2024-05-01 10:00:00,001 INFO server started on :8080\n")
    L.append("2024-05-01 10:00:05,100 ERROR [web] request failed\n")
    L.append(tb("qty"))
    L.append("2024-05-01 10:00:06,000 INFO GET /health 200\n")
    L.append("2024-05-01 11:30:00,500 ERROR [web] request failed\n")
    L.append(tb("quantity", 47))
    L.append("2024-05-01 11:30:01,000 WARN slow query 1200ms\n")
    L.append("2024-05-01 12:15:00,000 ERROR [web] request failed\n")
    L.append(tb("qty"))
    L.append("2024-05-01 12:20:00,000 ERROR tenant lookup\n")
    L.append(JAVA)
    L.append("2024-05-01 12:25:00,000 ERROR ui\n")
    L.append(NODE)
    L.append("2024-05-01 12:30:00,000 FATAL worker died\n")
    L.append(GO)
    L.append("2024-05-01 12:31:00,000 INFO restarting\n")
    return "".join(L)


@pytest.fixture
def sandbox(tmp_path: Path):
    server.configure([str(tmp_path)])
    yield tmp_path
    server.configure([])


def write(p: Path, text: str, newline: str = "\n") -> None:
    with open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(text.replace("\n", newline))


def test_traces_interleaved_with_normal_lines_are_all_found() -> None:
    traces, _ = find_traces(build_log())
    assert [t.language for t in traces] == ["python", "python", "python", "java", "node", "go"]
    assert traces[0].timestamp == "2024-05-01 10:00:05,100" or traces[0].timestamp == "2024-05-01 10:00:00,001"


def test_find_traces_in_file_groups_counts_and_times(sandbox: Path) -> None:
    write(sandbox / "app.log", build_log())
    out = server.find_traces_in_file("app.log")
    assert "6 trace(s) in 4 distinct fingerprint group(s)" in out
    first = out.splitlines()[1]
    assert first.startswith("#1  x3") and "KeyError" in first
    assert "first seen 2024-05-01 10:00" in out and "last seen 2024-05-01 12:" in out
    assert "innermost application frame: /app/src/pricing.py:12 in compute" in out


def test_crlf_log_is_parsed_the_same(sandbox: Path) -> None:
    write(sandbox / "crlf.log", build_log(), newline="\r\n")
    out = server.find_traces_in_file("crlf.log")
    assert "6 trace(s) in 4 distinct" in out


def test_docker_style_prefix_on_every_line(sandbox: Path) -> None:
    lines = []
    for ln in (tb("qty") + JAVA).splitlines():
        lines.append(f"2024-06-02T08:00:00.123456789Z stderr F {ln}")
    write(sandbox / "docker.log", "\n".join(lines) + "\n")
    out = server.find_traces_in_file("docker.log")
    assert "2 trace(s) in 2 distinct" in out
    assert "2024-06-02T08:00:00.123456789Z" in out


def test_no_timestamps_reports_line_numbers(sandbox: Path) -> None:
    write(sandbox / "plain.log", "hello\n" + tb("qty") + "bye\n" + tb("qty"))
    out = server.find_traces_in_file("plain.log")
    assert "x2" in out and "no timestamps; first at line 2" in out


def test_traces_across_chunk_boundaries(sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logscan, "CHUNK_LINES", 50)
    body = ""
    for k in range(40):
        body += "noise line\n" * (k % 7 + 40) + tb("qty", 40 + k) + "more noise\n"
    write(sandbox / "big.log", body)
    out = server.find_traces_in_file("big.log")
    assert "40 trace(s) in 1 distinct" in out


def test_trace_larger_than_a_chunk_is_not_split(sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logscan, "CHUNK_LINES", 20)
    frames = "".join(f'  File "/app/m{i}.py", line {i + 1}, in f{i}\n    x()\n' for i in range(300))
    write(sandbox / "deep.log", "Traceback (most recent call last):\n" + frames + "ValueError: deep\n" + "tail\n" * 100)
    out = server.find_traces_in_file("deep.log")
    assert "1 trace(s) in 1 distinct" in out


def test_scan_cap_is_reported(sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logscan, "MAX_SCAN_BYTES", 2000)
    write(sandbox / "cap.log", "x" * 50 + "\n" + tb("qty") * 1 + ("filler line here\n" * 2000))
    out = server.find_traces_in_file("cap.log")
    assert "scan stopped at the 256 MB cap" in out


def test_giant_single_line_does_not_blow_memory_or_hide_traces(sandbox: Path) -> None:
    write(sandbox / "long.log", ("A" * 3_000_000) + "\n" + tb("qty"))
    out = server.find_traces_in_file("long.log")
    assert "1 trace(s) in 1 distinct" in out


def test_group_cap(sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logscan, "MAX_GROUPS", 3)
    body = "".join(tb("k").replace("compute", f"compute{i}") for i in range(10))
    write(sandbox / "many.log", body)
    out = server.find_traces_in_file("many.log")
    assert "10 trace(s) in 3 distinct" in out and "beyond the 1000-group cap" in out


def test_empty_and_traceless_files(sandbox: Path) -> None:
    write(sandbox / "empty.log", "")
    assert "No stack traces found." in server.find_traces_in_file("empty.log")
    write(sandbox / "none.log", "INFO fine\nERROR: something failed: but no trace\n")
    assert "No stack traces found." in server.find_traces_in_file("none.log")


def test_bare_headers_in_normal_log_text_are_not_traces(sandbox: Path) -> None:
    write(sandbox / "prose.log", "fatal error: foo.h: No such file or directory\npanic: this is just text\n")
    assert "No stack traces found." in server.find_traces_in_file("prose.log")


def test_file_outside_sandbox_is_refused(sandbox: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    other = tmp_path_factory.mktemp("other") / "x.log"
    other.write_text(tb("qty"), encoding="utf-8")
    with pytest.raises(SandboxError, match="outside the sandbox"):
        server.find_traces_in_file(str(other))
    with pytest.raises(SandboxError, match="outside the sandbox"):
        server.find_traces_in_file("../" + other.parent.name + "/x.log")


def test_directory_is_not_a_log_file(sandbox: Path) -> None:
    (sandbox / "d").mkdir()
    with pytest.raises(SandboxError, match="not a regular file"):
        server.find_traces_in_file("d")


def test_no_sandbox_configured_is_an_actionable_error() -> None:
    server.configure([])
    with pytest.raises(SandboxError, match="--dir"):
        server.find_traces_in_file("x.log")


def test_mixed_log_text_via_parse_trace_index() -> None:
    out = server.parse_trace(build_log(), index=3)
    assert "Input contains 6 traces; showing #3" in out
    assert "java.lang.IllegalStateException" in out
    with pytest.raises(Exception, match="out of range"):
        server.parse_trace(build_log(), index=9)


def test_unrecognised_text_gives_actionable_error() -> None:
    with pytest.raises(Exception, match="No stack trace recognised"):
        server.parse_trace(fx("hello world\nnothing to see\n"))
