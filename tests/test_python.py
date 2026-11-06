"""Python traceback fixtures, written from real CPython 3.8-3.13 output shapes."""

from __future__ import annotations

import pytest
from helpers import check, fx, parse

CASES: dict[str, tuple[str, dict]] = {}


def case(name: str, text: str, **exp: object) -> None:
    CASES[name] = (fx(text), exp)


case("zero_division_311_carets", r"""
    Traceback (most recent call last):
      File "/app/main.py", line 14, in <module>
        print(compute(0))
              ^^^^^^^^^^
      File "/app/main.py", line 10, in compute
        return 100 / x
               ~~~~^~~
    ZeroDivisionError: division by zero
    """, lang="python", top="ZeroDivisionError", root="ZeroDivisionError", msg="division by zero",
     origin=("compute", "/app/main.py", 10), frames=2, kinds={0: "app", 1: "app"})

case("keyerror_no_message_type_only", r"""
    Traceback (most recent call last):
      File "/srv/api/handlers.py", line 88, in get_user
        return users[uid]
               ~~~~~^^^^^
    KeyError: 'u-1001'
    """, lang="python", top="KeyError", msg="'u-1001'", origin=("get_user", "handlers.py", 88))

case("attributeerror_in_site_packages", r"""
    Traceback (most recent call last):
      File "/app/client.py", line 31, in fetch
        resp = session.get(url, timeout=5)
      File "/usr/local/lib/python3.12/site-packages/requests/sessions.py", line 602, in get
        return self.request("GET", url, **kwargs)
      File "/usr/local/lib/python3.12/site-packages/requests/sessions.py", line 589, in request
        resp = self.send(prep, **send_kwargs)
      File "/usr/local/lib/python3.12/site-packages/requests/adapters.py", line 700, in send
        raise ConnectionError(e, request=request)
    requests.exceptions.ConnectionError: HTTPConnectionPool(host='x', port=80): Max retries exceeded
    """, lang="python", top="requests.exceptions.ConnectionError", frames=4,
     origin=("fetch", "client.py", 31), kinds={0: "library", 1: "library", 2: "library", 3: "app"})

case("direct_cause_chain", r"""
    Traceback (most recent call last):
      File "/app/src/config.py", line 42, in parse_port
        port = int(raw)
               ^^^^^^^^
    ValueError: invalid literal for int() with base 10: 'abc'

    The above exception was the direct cause of the following exception:

    Traceback (most recent call last):
      File "/app/main.py", line 10, in <module>
        main()
      File "/app/main.py", line 6, in main
        raise RuntimeError("config load failed") from e
    RuntimeError: config load failed
    """, lang="python", top="RuntimeError", root="ValueError", chain=2,
     origin=("parse_port", "config.py", 42))

case("context_chain", r"""
    Traceback (most recent call last):
      File "/app/db.py", line 20, in connect
        sock.connect(addr)
    ConnectionRefusedError: [Errno 111] Connection refused

    During handling of the above exception, another exception occurred:

    Traceback (most recent call last):
      File "/app/db.py", line 24, in connect
        raise DatabaseUnavailable("db down")
    db.DatabaseUnavailable: db down
    """, lang="python", top="db.DatabaseUnavailable", root="ConnectionRefusedError", chain=2,
     origin=("connect", "db.py", 20))

case("three_level_chain", r"""
    Traceback (most recent call last):
      File "/app/a.py", line 1, in a
        raise KeyError('k')
    KeyError: 'k'

    During handling of the above exception, another exception occurred:

    Traceback (most recent call last):
      File "/app/b.py", line 2, in b
        raise ValueError('v') from None
    ValueError: v

    The above exception was the direct cause of the following exception:

    Traceback (most recent call last):
      File "/app/c.py", line 3, in c
        raise RuntimeError('r')
    RuntimeError: r
    """, lang="python", top="RuntimeError", root="KeyError", chain=3)

case("exception_group_taskgroup", r"""
      + Exception Group Traceback (most recent call last):
      |   File "/app/t.py", line 12, in <module>
      |     asyncio.run(main())
      |   File "/usr/lib/python3.11/asyncio/runners.py", line 190, in run
      |     return runner.run(main)
      |   File "/app/t.py", line 9, in main
      |     async with asyncio.TaskGroup() as tg:
      |   File "/usr/lib/python3.11/asyncio/taskgroups.py", line 147, in __aexit__
      |     raise me from None
      | ExceptionGroup: unhandled errors in a TaskGroup (2 sub-exceptions)
      +-+---------------- 1 ----------------
        | Traceback (most recent call last):
        |   File "/app/t.py", line 4, in boom
        |     raise ValueError("a")
        | ValueError: a
        +---------------- 2 ----------------
        | Traceback (most recent call last):
        |   File "/app/t.py", line 6, in other
        |     {}["b"]
        | KeyError: 'b'
        +------------------------------------
    """, lang="python", top="ExceptionGroup", msg="2 sub-exceptions")

case("nested_exception_group", r"""
      + Exception Group Traceback (most recent call last):
      |   File "<stdin>", line 1, in <module>
      | ExceptionGroup: outer (2 sub-exceptions)
      +-+---------------- 1 ----------------
        | ExceptionGroup: inner (1 sub-exception)
        +-+---------------- 1 ----------------
          | ValueError: deep
          +------------------------------------
        +---------------- 2 ----------------
        | TypeError: shallow
        +------------------------------------
    """, lang="python", top="ExceptionGroup", msg="outer")

case("syntax_error_caret", r"""
      File "/app/broken.py", line 3
        print("a"
             ^
    SyntaxError: '(' was never closed
    """, lang="python", top="SyntaxError", msg="never closed", origin=("(syntax)", "broken.py", 3))

case("syntax_error_with_traceback_import", r"""
    Traceback (most recent call last):
      File "/app/main.py", line 1, in <module>
        import plugin
      File "/app/plugin.py", line 7
        def f(:
              ^
    SyntaxError: invalid syntax
    """, lang="python", top="SyntaxError", origin=("(syntax)", "plugin.py", 7))

case("keyboard_interrupt", r"""
    Traceback (most recent call last):
      File "/app/worker.py", line 40, in <module>
        time.sleep(1000)
    KeyboardInterrupt
    """, lang="python", top="KeyboardInterrupt", origin=("<module>", "worker.py", 40))

case("recursion_error_repeat", r"""
    Traceback (most recent call last):
      File "/app/r.py", line 5, in <module>
        f(1)
      File "/app/r.py", line 2, in f
        return f(n + 1)
               ^^^^^^^^
      File "/app/r.py", line 2, in f
        return f(n + 1)
               ^^^^^^^^
      [Previous line repeated 996 more times]
    RecursionError: maximum recursion depth exceeded
    """, lang="python", top="RecursionError", origin=("f", "r.py", 2))

case("windows_paths", r"""
    Traceback (most recent call last):
      File "C:\Users\fadi\proj\app\main.py", line 8, in <module>
        run()
      File "C:\Users\fadi\AppData\Local\Programs\Python\Python312\Lib\json\decoder.py", line 355, in raw_decode
        raise JSONDecodeError("Expecting value", s, err.value) from None
    json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
    """, lang="python", top="json.decoder.JSONDecodeError", kinds={0: "stdlib", 1: "app"},
     origin=("<module>", "main.py", 8))

case("py313_notes", r"""
    Traceback (most recent call last):
      File "/app/job.py", line 20, in <module>
        run_job(cfg)
        ~~~~~~~^^^^^
      File "/app/job.py", line 15, in run_job
        raise ValueError("bad config")
    ValueError: bad config
    job=nightly shard=3
    retry with --force
    """, lang="python", top="ValueError", msg="shard=3", origin=("run_job", "job.py", 15))

case("module_not_found_frozen", r"""
    Traceback (most recent call last):
      File "/app/main.py", line 1, in <module>
        import yaml
    ModuleNotFoundError: No module named 'yaml'
    """, lang="python", top="ModuleNotFoundError", origin=("<module>", "main.py", 1))

case("frozen_importlib_frames", r"""
    Traceback (most recent call last):
      File "<frozen runpy>", line 198, in _run_module_as_main
      File "<frozen runpy>", line 88, in _run_code
      File "/app/pkg/__main__.py", line 3, in <module>
        from . import cli
    ImportError: cannot import name 'cli' from partially initialized module 'pkg'
    """, lang="python", top="ImportError", frames=3, kinds={0: "app", 1: "stdlib", 2: "stdlib"})

case("flask_framework_frames", r"""
    Traceback (most recent call last):
      File "/venv/lib/python3.12/site-packages/flask/app.py", line 1473, in wsgi_app
        response = self.full_dispatch_request()
      File "/venv/lib/python3.12/site-packages/flask/app.py", line 882, in full_dispatch_request
        rv = self.handle_user_exception(e)
      File "/app/views.py", line 19, in index
        return render(data["items"][3])
    IndexError: list index out of range
    """, lang="python", top="IndexError", origin=("index", "views.py", 19), kinds={0: "app", 1: "framework"})

case("truncated_no_exception_line", r"""
    Traceback (most recent call last):
      File "/app/main.py", line 5, in <module>
        main()
      File "/app/main.py", line 3, in main
    """, lang="python", partial=True, origin=("main", "main.py", 3))

case("multiline_message", r"""
    Traceback (most recent call last):
      File "/app/q.py", line 3, in <module>
        cur.execute(sql)
    psycopg2.errors.UndefinedTable: relation "users" does not exist
    LINE 1: SELECT * FROM users
                          ^

    """, lang="python", top="psycopg2.errors.UndefinedTable", msg="LINE 1")

case("logging_with_timestamp_prefix", r"""
    2024-05-01 12:00:00,123 ERROR [app] request failed
    Traceback (most recent call last):
      File "/app/h.py", line 9, in handle
        return int(x)
    ValueError: invalid literal for int() with base 10: 'z'
    2024-05-01 12:00:01,000 INFO next request
    """, lang="python", top="ValueError", origin=("handle", "h.py", 9))

case("pytest_assertion", r"""
    Traceback (most recent call last):
      File "/venv/lib/python3.12/site-packages/_pytest/runner.py", line 341, in from_call
        result: TResult | None = func()
      File "/app/tests/test_x.py", line 12, in test_add
        assert add(1, 2) == 4
    AssertionError: assert 3 == 4
    """, lang="python", top="AssertionError", origin=("test_add", "test_x.py", 12))


@pytest.mark.parametrize("name", sorted(CASES))
def test_python_fixture(name: str) -> None:
    text, exp = CASES[name]
    check(text, **exp)  # type: ignore[arg-type]


def test_there_are_at_least_twelve_python_fixtures() -> None:
    assert len(CASES) >= 12


def test_chain_relations_and_order() -> None:
    t = parse(CASES["three_level_chain"][0])
    assert [e.type for e in t.chain] == ["RuntimeError", "ValueError", "KeyError"]
    assert t.chain[1].via == "cause"  # ValueError was the direct cause of RuntimeError
    assert t.chain[2].via == "context"  # KeyError was being handled when ValueError was raised


def test_exception_group_children() -> None:
    t = parse(CASES["exception_group_taskgroup"][0])
    grp = t.top
    assert [c[0].type for c in grp.group] == ["ValueError", "KeyError"]
    assert grp.group[0][0].frames[0].function == "boom"
    assert [e.type for e in t.root_causes()] == ["ValueError", "KeyError"]
    # the innermost application frame comes from the first leaf, not from asyncio internals
    org = t.origin()
    assert org is not None and org[1].function == "boom"


def test_nested_exception_group() -> None:
    t = parse(CASES["nested_exception_group"][0])
    outer = t.top
    assert len(outer.group) == 2
    inner = outer.group[0][0]
    assert inner.type == "ExceptionGroup" and inner.group[0][0].type == "ValueError"
    assert outer.group[1][0].type == "TypeError"
    assert {e.type for e in t.root_causes()} == {"ValueError", "TypeError"}


def test_recursion_repeat_is_recorded() -> None:
    t = parse(CASES["recursion_error_repeat"][0])
    assert t.top.frames[0].repeat == 996


def test_source_lines_are_kept_without_caret_noise() -> None:
    t = parse(CASES["zero_division_311_carets"][0])
    assert t.top.frames[0].source == "return 100 / x"
    assert t.top.frames[1].source == "print(compute(0))"


def test_notes_lines_are_part_of_the_message() -> None:
    t = parse(CASES["py313_notes"][0])
    assert "retry with --force" in t.top.message


def test_log_line_after_trace_is_not_swallowed() -> None:
    t = parse(CASES["logging_with_timestamp_prefix"][0])
    assert "next request" not in t.top.message
    assert t.timestamp == "2024-05-01 12:00:00,123"


def test_truncated_reports_a_reason() -> None:
    t = parse(CASES["truncated_no_exception_line"][0])
    assert t.partial and any("truncated" in n for n in t.notes)
