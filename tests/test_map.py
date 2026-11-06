"""map_to_code: container-path rewriting, line checks, ambiguity, traversal and symlink protection."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from helpers import fx
from stacktrace_mcp import server
from stacktrace_mcp.sandbox import SandboxError

PRICING = "\n".join(
    [
        "import math",
        "",
        "",
        "def compute(order):",
        "    price = 9.99",
        "    qty = order.get('qty', 1)",
        "    # the bug is on the next line",
        "    return order['qty'] * price",
        "",
        "",
        "def refund(order):",
        "    return -compute(order)",
    ]
) + "\n"

TRACE_CONTAINER = fx(r"""
    Traceback (most recent call last):
      File "/app/src/orders.py", line 3, in handle
        total = compute(order)
      File "/app/src/pricing.py", line 8, in compute
        return order['qty'] * price
    KeyError: 'qty'
    """)


@pytest.fixture
def project(tmp_path: Path):
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "pricing.py").write_text(PRICING, encoding="utf-8", newline="\n")
    (root / "src" / "orders.py").write_text("def handle(order):\n    # call\n    total = compute(order)\n    return total\n", encoding="utf-8")
    (root / "src" / "main" / "java" / "com" / "acme").mkdir(parents=True)
    (root / "src" / "main" / "java" / "com" / "acme" / "Util.java").write_text(
        "package com.acme;\n\npublic class Util {\n    static int len(String s) {\n        return s.length();\n    }\n}\n", encoding="utf-8"
    )
    (root / "src" / "components").mkdir()
    (root / "src" / "components" / "List.jsx").write_text("export function List(p) {\n  return p.items.map(x => x);\n}\n", encoding="utf-8")
    (root / "node_modules" / "left-pad").mkdir(parents=True)
    (root / "node_modules" / "left-pad" / "index.js").write_text("module.exports = 1;\n", encoding="utf-8")
    server.configure([str(root)])
    yield root
    server.configure([])


def test_container_paths_are_rewritten_to_local_files(project: Path) -> None:
    out = server.map_to_code(TRACE_CONTAINER)
    assert "FOUND src/pricing.py" in out and "FOUND src/orders.py" in out
    assert "matched on 2 trailing path part(s)" in out
    assert ">     8 |     return order['qty'] * price" in out
    assert "      6 |     qty = order.get('qty', 1)" in out  # context before
    assert "KeyError" in out.splitlines()[0]


def test_context_size_is_respected(project: Path) -> None:
    out = server.map_to_code(TRACE_CONTAINER, context=1, max_frames=1)
    assert ">     8 |" in out and "      7 |" in out and "      9 |" in out
    assert "      6 |" not in out


def test_windows_separators_and_drive_letters(project: Path) -> None:
    trace = fx(r"""
        Traceback (most recent call last):
          File "C:\Users\fadi\work\proj\src\pricing.py", line 8, in compute
            return order['qty'] * price
        KeyError: 'qty'
        """)
    assert "FOUND src/pricing.py" in server.map_to_code(trace)


def test_line_beyond_eof_is_flagged(project: Path) -> None:
    trace = TRACE_CONTAINER.replace("line 8", "line 999")
    out = server.map_to_code(trace)
    assert "LINE 999 DOES NOT EXIST" in out and "13 lines" not in out and "12 lines" in out


def test_changed_source_line_is_warned(project: Path) -> None:
    trace = TRACE_CONTAINER.replace("return order['qty'] * price", "return OLD CODE HERE")
    assert "source line recorded in the trace differs" in server.map_to_code(trace)


def test_missing_file_is_marked_not_found(project: Path) -> None:
    trace = fx(r"""
        Traceback (most recent call last):
          File "/app/src/ghost.py", line 3, in boo
            x()
        RuntimeError: x
        """)
    out = server.map_to_code(trace)
    assert "NOT FOUND" in out and "ghost.py" in out and "Mapped 0 of 1" in out


def test_library_frames_are_skipped_not_searched(project: Path) -> None:
    trace = fx(r"""
        Traceback (most recent call last):
          File "/app/src/pricing.py", line 8, in compute
            x
          File "/usr/lib/python3.12/site-packages/left-pad/index.js", line 1, in lp
            y
        RuntimeError: x
        """)
    out = server.map_to_code(trace)
    assert "1 library/runtime frame(s) skipped" in out
    assert "left-pad" not in out


def test_java_frames_map_through_the_package_path(project: Path) -> None:
    trace = "java.lang.NullPointerException: x\n\tat com.acme.Util.len(Util.java:5)\n\tat com.acme.Main.main(Main.java:3)\n"
    out = server.map_to_code(trace)
    assert "FOUND src/main/java/com/acme/Util.java" in out
    assert ">     5 |         return s.length();" in out
    assert "Main.java" in out and "NOT FOUND" in out


def test_webpack_urls_map(project: Path) -> None:
    trace = "TypeError: x\n    at List (webpack-internal:///./src/components/List.jsx:2:12)\n"
    out = server.map_to_code(trace)
    assert "FOUND src/components/List.jsx" in out and "p.items.map" in out


def test_ambiguous_basename_is_not_guessed(project: Path) -> None:
    (project / "a").mkdir()
    (project / "b").mkdir()
    (project / "a" / "util.py").write_text("x = 1\n", encoding="utf-8")
    (project / "b" / "util.py").write_text("x = 2\n", encoding="utf-8")
    trace = 'Traceback (most recent call last):\n  File "/srv/util.py", line 1, in f\n    x\nValueError: v\n'
    out = server.map_to_code(trace)
    assert "NOT FOUND" in out and "a/util.py" in out and "b/util.py" in out


def test_longer_suffix_wins_over_same_name(project: Path) -> None:
    (project / "a").mkdir()
    (project / "a" / "pricing.py").write_text("x = 1\n", encoding="utf-8")
    out = server.map_to_code(TRACE_CONTAINER)
    assert "FOUND src/pricing.py" in out


def test_dotdot_frames_cannot_escape_the_sandbox(project: Path) -> None:
    secret = project.parent / "secret.txt"
    secret.write_text("TOP-SECRET-CONTENT-12345\n" * 10, encoding="utf-8")
    passwd_like = project.parent / "passwd"
    passwd_like.write_text("root:x:0:0:SECRETROOTLINE\n" * 5, encoding="utf-8")
    trace = fx(r"""
        Traceback (most recent call last):
          File "../../etc/passwd", line 1, in evil
            x
          File "../secret.txt", line 1, in evil2
            y
          File "/../../../../../../etc/passwd", line 2, in evil3
            z
          File "..\..\..\Windows\win.ini", line 1, in evil4
            w
        RuntimeError: x
        """)
    out = server.map_to_code(trace)
    assert "TOP-SECRET" not in out and "SECRETROOTLINE" not in out
    assert out.count("NOT FOUND") == 4


def test_absolute_path_outside_sandbox_is_data_not_a_read(project: Path) -> None:
    outside = project.parent / "outside.py"
    outside.write_text("LEAKED = 'OUTSIDE-FILE-CONTENT'\n", encoding="utf-8")
    trace = f'Traceback (most recent call last):\n  File "{outside}", line 1, in f\n    x\nValueError: v\n'
    out = server.map_to_code(trace)
    assert "OUTSIDE-FILE-CONTENT" not in out


def test_symlink_resolving_outside_is_refused(project: Path) -> None:
    secret = project.parent / "linked-secret.py"
    secret.write_text("TOKEN_VALUE = 'SYMLINK-LEAK-9999'\n", encoding="utf-8")
    link = project / "src" / "linked.py"
    try:
        os.symlink(secret, link)
    except (OSError, NotImplementedError):
        pytest.skip("this account cannot create symlinks (Windows without developer mode)")
    trace = 'Traceback (most recent call last):\n  File "/app/src/linked.py", line 1, in f\n    x\nValueError: v\n'
    out = server.map_to_code(trace)
    assert "SYMLINK-LEAK-9999" not in out and "blocked" in out


def test_symlinked_directory_is_not_followed(project: Path) -> None:
    outdir = project.parent / "outdir"
    outdir.mkdir()
    (outdir / "inside.py").write_text("DIRLEAK = 'DIR-LEAK-777'\n", encoding="utf-8")
    try:
        os.symlink(outdir, project / "linkdir", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this account cannot create symlinks (Windows without developer mode)")
    trace = 'Traceback (most recent call last):\n  File "/x/inside.py", line 1, in f\n    x\nValueError: v\n'
    out = server.map_to_code(trace)
    assert "DIR-LEAK-777" not in out and "NOT FOUND" in out


def test_project_dir_outside_sandbox_is_refused(project: Path) -> None:
    with pytest.raises(SandboxError, match="outside the sandbox"):
        server.map_to_code(TRACE_CONTAINER, project_dir=str(project.parent))
    with pytest.raises(SandboxError, match="outside the sandbox"):
        server.map_to_code(TRACE_CONTAINER, project_dir="..")


def test_project_dir_inside_sandbox_is_allowed(project: Path) -> None:
    out = server.map_to_code(TRACE_CONTAINER, project_dir="src")
    assert "FOUND pricing.py" in out


def test_enormous_path_is_a_clean_error(project: Path) -> None:
    with pytest.raises(SandboxError):
        server.map_to_code(TRACE_CONTAINER, project_dir="a" * 100_000)
    with pytest.raises(SandboxError):
        server.find_traces_in_file("b" * 100_000)
    with pytest.raises(SandboxError):
        server.find_traces_in_file("nul\x00byte")


def test_requires_sandbox() -> None:
    server.configure([])
    with pytest.raises(SandboxError, match="--dir"):
        server.map_to_code(TRACE_CONTAINER)


def test_binary_and_huge_files_are_not_dumped(project: Path) -> None:
    (project / "src" / "blob.py").write_bytes(b"\x00\x01\x02" * 100)
    trace = 'Traceback (most recent call last):\n  File "/a/src/blob.py", line 1, in f\n    x\nValueError: v\n'
    assert "binary file" in server.map_to_code(trace)


def test_output_is_redacted_by_default(project: Path) -> None:
    (project / "src" / "cfg.py").write_text("password = 'hunter2hunter2'\nmail = 'dev@example.com'\n", encoding="utf-8")
    trace = 'Traceback (most recent call last):\n  File "/a/src/cfg.py", line 1, in f\n    x\nValueError: v\n'
    out = server.map_to_code(trace)
    assert "hunter2" not in out and "dev@example.com" not in out
    raw = server.map_to_code(trace, redact=False)
    assert "hunter2hunter2" in raw
