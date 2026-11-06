"""MCP stdio test: launches the real server as a subprocess, lists tools, calls them over the
wire, attacks the sandbox, and checks that errors and redaction survive the trip."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402

EXPECTED_TOOLS = {
    "parse_trace",
    "find_traces_in_file",
    "fingerprint",
    "map_to_code",
    "compare_traces",
    "explain_exception",
    "redact_trace",
}

FAKE_TOKEN = "gh" + "p_" + "Q1w2E3r4T5y6U7i8O9p0A1s2D3f4G5h6J7k8"
FAKE_EMAIL = "victim.person" + "@" + "corp-example.com"

TRACE = (
    "Traceback (most recent call last):\n"
    '  File "/app/src/pricing.py", line 4, in compute\n'
    "    return order['qty'] * price\n"
    f'KeyError: \'qty\' for {FAKE_EMAIL} token={FAKE_TOKEN} at C:\\Users\\RealPerson\\x\n'
)


def _params(directory: Path | None) -> StdioServerParameters:
    args = ["-m", "stacktrace_mcp"]
    if directory is not None:
        args += ["--dir", str(directory)]
    return StdioServerParameters(command=sys.executable, args=args, env={**os.environ, "PYTHONIOENCODING": "utf-8"})


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "pricing.py").write_text(
        "def compute(order):\n    price = 2\n    qty = 1\n    return order['qty'] * price\n", encoding="utf-8"
    )
    (tmp_path / "app.log").write_text(
        "2024-05-01 10:00:00,000 ERROR boom\n" + TRACE + "2024-05-01 10:05:00,000 ERROR boom\n" + TRACE, encoding="utf-8", newline="\n"
    )
    return tmp_path


@pytest.mark.anyio
async def test_tools_listed_and_described(project: Path) -> None:
    async with stdio_client(_params(project)) as (read, write), ClientSession(read, write) as session:
        init = await session.initialize()
        assert init.server_info.name == "stacktrace"
        tools = (await session.list_tools()).tools
        assert {t.name for t in tools} == EXPECTED_TOOLS
        for t in tools:
            assert t.description and len(t.description) > 80, t.name


@pytest.mark.anyio
async def test_every_tool_over_stdio_and_redaction(project: Path) -> None:
    async with stdio_client(_params(project)) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        outputs: list[str] = []

        res = await session.call_tool("parse_trace", {"text": TRACE})
        assert not res.is_error
        outputs.append(res.content[0].text)
        assert "KeyError" in outputs[-1] and "pricing.py:4" in outputs[-1]

        res = await session.call_tool("fingerprint", {"text": TRACE})
        outputs.append(res.content[0].text)
        assert not res.is_error and "KeyError" in outputs[-1]

        res = await session.call_tool("compare_traces", {"a": TRACE, "b": TRACE})
        outputs.append(res.content[0].text)
        assert outputs[-1].startswith("SAME")

        res = await session.call_tool("map_to_code", {"text": TRACE})
        outputs.append(res.content[0].text)
        assert "FOUND src/pricing.py" in outputs[-1] and "return order['qty'] * price" in outputs[-1]

        res = await session.call_tool("find_traces_in_file", {"path": "app.log"})
        outputs.append(res.content[0].text)
        assert "x2" in outputs[-1] and "first seen 2024-05-01 10:00:00,000" in outputs[-1]

        res = await session.call_tool("explain_exception", {"type": "KeyError", "language": "python"})
        assert "Check first" in res.content[0].text

        res = await session.call_tool("redact_trace", {"text": TRACE})
        outputs.append(res.content[0].text)

        for text in outputs:
            assert FAKE_TOKEN not in text
            assert FAKE_EMAIL not in text
            assert "RealPerson" not in text


@pytest.mark.anyio
async def test_errors_reach_the_agent_with_their_message(project: Path) -> None:
    async with stdio_client(_params(project)) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        res = await session.call_tool("parse_trace", {"text": "nothing useful here"})
        assert res.is_error and "No stack trace recognised" in res.content[0].text
        res = await session.call_tool("explain_exception", {"type": "NopeError"})
        assert res.is_error and "Known languages" in res.content[0].text
        res = await session.call_tool("parse_trace", {"text": TRACE, "format": "xml"})
        assert res.is_error and "format must be" in res.content[0].text
        res = await session.call_tool("parse_trace", {"text": "x" * 5_000_001})
        assert res.is_error and "5,000,000" in res.content[0].text


@pytest.mark.anyio
async def test_sandbox_attacks_over_stdio(project: Path) -> None:
    secret = project.parent / "secret-outside.txt"
    secret.write_text("OUTSIDE-SECRET-VALUE\n" * 5, encoding="utf-8")
    evil = (
        "Traceback (most recent call last):\n"
        '  File "../secret-outside.txt", line 1, in x\n    y\n'
        f'  File "{secret}", line 1, in z\n    y\n'
        "ValueError: v\n"
    )
    async with stdio_client(_params(project)) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        res = await session.call_tool("map_to_code", {"text": evil})
        assert "OUTSIDE-SECRET-VALUE" not in res.content[0].text
        for bad in (str(secret), "../secret-outside.txt", "..", "/etc/passwd", "C:\\Windows\\win.ini", "a" * 100_000):
            res = await session.call_tool("find_traces_in_file", {"path": bad})
            assert res.is_error, bad
            assert "OUTSIDE-SECRET-VALUE" not in res.content[0].text
            assert len(res.content[0].text) < 2_000
        res = await session.call_tool("map_to_code", {"text": TRACE, "project_dir": str(project.parent)})
        assert res.is_error and "outside the sandbox" in res.content[0].text


@pytest.mark.anyio
async def test_without_dir_text_tools_work_and_file_tools_explain() -> None:
    async with stdio_client(_params(None)) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        res = await session.call_tool("parse_trace", {"text": TRACE})
        assert not res.is_error
        res = await session.call_tool("map_to_code", {"text": TRACE})
        assert res.is_error and "--dir" in res.content[0].text
        res = await session.call_tool("find_traces_in_file", {"path": "x.log"})
        assert res.is_error and "--dir" in res.content[0].text


def test_bad_dir_argument_exits_with_a_message(tmp_path: Path) -> None:
    import subprocess

    proc = subprocess.run(
        [sys.executable, "-m", "stacktrace_mcp", "--dir", str(tmp_path / "does-not-exist")],
        capture_output=True,
        text=True,
        timeout=60,
        stdin=subprocess.DEVNULL,
    )
    assert proc.returncode == 2 and "not an existing directory" in proc.stderr
