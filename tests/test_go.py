"""Go panic / fatal error / goroutine dump / race detector fixtures (<T> is a tab)."""

from __future__ import annotations

import pytest
from helpers import check, fx, parse

CASES: dict[str, tuple[str, dict]] = {}


def case(name: str, text: str, **exp: object) -> None:
    CASES[name] = (fx(text), exp)


case("nil_pointer_with_signal", r"""
    panic: runtime error: invalid memory address or nil pointer dereference
    [signal SIGSEGV: segmentation violation code=0x1 addr=0x18 pc=0x4a3b2c]

    goroutine 1 [running]:
    main.(*Server).handle(0x0, {0x4d6a28, 0xc000010018})
    <T>/app/server.go:42 +0x2c
    main.main()
    <T>/app/main.go:17 +0x45
    exit status 2
    """, lang="go", top="runtime error", msg="nil pointer dereference",
     origin=("Server).handle", "server.go", 42), frames=2)

case("index_out_of_range", r"""
    panic: runtime error: index out of range [5] with length 3

    goroutine 1 [running]:
    main.process(...)
    <T>/app/main.go:12
    main.main()
    <T>/app/main.go:20 +0x1d
    exit status 2
    """, lang="go", top="runtime error", msg="index out of range [5]", origin=("main.process", "main.go", 12))

case("custom_error_panic", r"""
    panic: open /etc/app.conf: no such file or directory

    goroutine 1 [running]:
    main.mustLoad(...)
    <T>/src/cfg.go:9
    main.main()
    <T>/src/main.go:5 +0x7a
    """, lang="go", top="panic", msg="no such file", origin=("main.mustLoad", "cfg.go", 9), frames=2)

case("deadlock_fatal_error", r"""
    fatal error: all goroutines are asleep - deadlock!

    goroutine 1 [chan receive]:
    main.main()
    <T>/app/main.go:9 +0x3e

    goroutine 6 [chan send]:
    main.worker(0xc000012120)
    <T>/app/main.go:14 +0x2a
    created by main.main in goroutine 1
    <T>/app/main.go:7 +0x66
    exit status 2
    """, lang="go", top="fatal error", msg="deadlock", origin=("main.main", "main.go", 9))

case("concurrent_map_writes", r"""
    fatal error: concurrent map writes

    goroutine 18 [running]:
    main.(*Cache).Set(...)
    <T>/app/cache.go:21
    main.handler.func1()
    <T>/app/handler.go:33 +0x5d
    created by main.handler in goroutine 7
    <T>/app/handler.go:31 +0x9c
    """, lang="go", top="fatal error", msg="concurrent map writes", origin=("Cache).Set", "cache.go", 21))

case("goroutine_created_by_old_style", r"""
    panic: boom

    goroutine 5 [running]:
    main.work()
    <T>/home/u/w/main.go:8 +0x39
    created by main.main
    <T>/home/u/w/main.go:15 +0x6f
    exit status 2
    """, lang="go", top="panic", frames=2)

case("recovered_then_repanic", r"""
    panic: first [recovered]
    <T>panic: second

    goroutine 1 [running]:
    main.f.func1()
    <T>/app/main.go:11 +0x5a
    panic({0x45f0a0, 0x4d9fb8})
    <T>/usr/local/go/src/runtime/panic.go:770 +0x132
    main.f()
    <T>/app/main.go:15 +0x1c
    main.main()
    <T>/app/main.go:20 +0x17
    """, lang="go", top="panic", msg="second", chain=1, origin=("main.f.func1", "main.go", 11))

case("data_race_report", r"""
    ==================
    WARNING: DATA RACE
    Write at 0x00c0000a4010 by goroutine 7:
      main.main.func1()
          /app/main.go:12 +0x44

    Previous read at 0x00c0000a4010 by main goroutine:
      main.main()
          /app/main.go:9 +0x7a

    Goroutine 7 (running) created at:
      main.main()
          /app/main.go:10 +0x6c
    ==================
    Found 1 data race(s)
    exit status 66
    """, lang="go", top="DATA RACE", origin=("main.main.func1", "main.go", 12))

case("go_test_panic", r"""
    --- FAIL: TestDivide (0.00s)
    panic: runtime error: integer divide by zero [recovered]
    <T>panic: runtime error: integer divide by zero

    goroutine 6 [running]:
    testing.tRunner.func1.2({0x5a8f20, 0x6e5b30})
    <T>/usr/local/go/src/testing/testing.go:1545 +0x238
    testing.tRunner.func1()
    <T>/usr/local/go/src/testing/testing.go:1548 +0x3c9
    panic({0x5a8f20, 0x6e5b30})
    <T>/usr/local/go/src/runtime/panic.go:914 +0x21f
    example.com/calc.Divide(...)
    <T>/home/u/calc/calc.go:8
    example.com/calc.TestDivide(0xc0001a4000)
    <T>/home/u/calc/calc_test.go:12 +0x1a
    testing.tRunner(0xc0001a4000, 0x5b1c68)
    <T>/usr/local/go/src/testing/testing.go:1595 +0xff
    created by testing.(*T).Run in goroutine 1
    <T>/usr/local/go/src/testing/testing.go:1648 +0x3ad
    FAIL<T>example.com/calc<T>0.004s
    """, lang="go", top="runtime error", msg="divide by zero",
     origin=("calc.Divide", "calc.go", 8), kinds={0: "stdlib", 2: "runtime"})

case("fatal_with_runtime_stack", r"""
    fatal error: unexpected signal during runtime execution
    [signal SIGSEGV: segmentation violation code=0x1 addr=0xb01dfacedebac1e pc=0x7f1c2d]

    runtime stack:
    runtime.throw({0x4b3a1f?, 0x0?})
    <T>/usr/local/go/src/runtime/panic.go:1077 +0x5c
    runtime.sigpanic()
    <T>/usr/local/go/src/runtime/signal_unix.go:825 +0x3e9

    goroutine 1 [syscall]:
    runtime.cgocall(0x4a1c10, 0xc00006fe58)
    <T>/usr/local/go/src/runtime/cgocall.go:157 +0x4b
    main.callC()
    <T>/app/cgo.go:20 +0x2a
    main.main()
    <T>/app/main.go:6 +0x17
    """, lang="go", top="fatal error", origin=("main.callC", "cgo.go", 20))

case("windows_paths", r"""
    panic: runtime error: slice bounds out of range [:10] with capacity 4

    goroutine 1 [running]:
    main.trim(...)
    <T>C:/Users/fadi/proj/main.go:14
    main.main()
    <T>C:/Users/fadi/proj/main.go:22 +0x65
    exit status 2
    """, lang="go", top="runtime error", origin=("main.trim", "main.go", 14))

case("goroutine_dump_states_and_minutes", r"""
    panic: send on closed channel

    goroutine 20 [running]:
    main.producer(0xc00001c0c0)
    <T>/app/p.go:9 +0x3c
    created by main.main in goroutine 1
    <T>/app/p.go:30 +0x88

    goroutine 1 [chan receive, 5 minutes]:
    main.main()
    <T>/app/p.go:33 +0xa1

    goroutine 21 [select]:
    main.consumer()
    <T>/app/p.go:19 +0x55
    created by main.main in goroutine 1
    <T>/app/p.go:31 +0x95
    """, lang="go", top="panic", msg="closed channel", origin=("main.producer", "p.go", 9))

case("gin_third_party_frames", r"""
    panic: runtime error: invalid memory address or nil pointer dereference [recovered]
    <T>panic: runtime error: invalid memory address or nil pointer dereference

    goroutine 36 [running]:
    github.com/gin-gonic/gin.CustomRecoveryWithWriter.func1.1(0xc0001a0100)
    <T>/go/pkg/mod/github.com/gin-gonic/gin@v1.9.1/recovery.go:101 +0x5e
    panic({0x9a1e40, 0xc2c9b0})
    <T>/usr/local/go/src/runtime/panic.go:770 +0x132
    example.com/api/handlers.GetUser(0xc0001a0100)
    <T>/src/handlers/user.go:31 +0x2d
    github.com/gin-gonic/gin.(*Context).Next(...)
    <T>/go/pkg/mod/github.com/gin-gonic/gin@v1.9.1/context.go:174
    """, lang="go", top="runtime error",
     origin=("handlers.GetUser", "user.go", 31), kinds={0: "library", 1: "runtime", 3: "library"})

case("truncated_after_panic_line", r"""
    panic: runtime error: index out of range [2] with length 2
    """, lang="go", partial=True, top="runtime error")

case("sigquit_goroutine_dump_only", r"""
    goroutine 1 [running]:
    main.main()
    <T>/app/main.go:5 +0x1d
    """, lang="go", top="goroutine dump", origin=("main.main", "main.go", 5))

case("interface_conversion", r"""
    panic: interface conversion: interface {} is string, not int

    goroutine 1 [running]:
    main.parse(...)
    <T>/app/conv.go:7
    main.main()
    <T>/app/conv.go:12 +0x6a
    """, lang="go", top="interface conversion", msg="is string, not int", origin=("main.parse", "conv.go", 7))


@pytest.mark.parametrize("name", sorted(CASES))
def test_go_fixture(name: str) -> None:
    text, exp = CASES[name]
    check(text, **exp)  # type: ignore[arg-type]


def test_there_are_at_least_twelve_go_fixtures() -> None:
    assert len(CASES) >= 12


def test_signal_note_and_args_are_stripped_from_function_names() -> None:
    t = parse(CASES["nil_pointer_with_signal"][0])
    assert any("SIGSEGV" in n for n in t.top.notes)
    assert t.top.frames[0].function == "main.(*Server).handle"


def test_other_goroutines_are_summarised_not_mixed_into_frames() -> None:
    t = parse(CASES["goroutine_dump_states_and_minutes"][0])
    assert len(t.goroutines) == 2
    assert t.goroutines[0].startswith("goroutine 1 [chan receive, 5 minutes]")
    assert len(t.top.frames) == 2


def test_created_by_is_a_frame() -> None:
    t = parse(CASES["goroutine_created_by_old_style"][0])
    assert t.top.frames[1].function == "created by main.main"
    assert t.top.frames[1].line == 15


def test_repanic_chain_order() -> None:
    t = parse(CASES["recovered_then_repanic"][0])
    assert t.chain[0].message == "second"
    assert any("earlier panic (recovered): panic: first" in n for n in t.top.notes)


def test_race_report_stacks() -> None:
    t = parse(CASES["data_race_report"][0])
    labels = [lab for lab, _ in t.top.extra_stacks]
    assert len(labels) == 2
    assert labels[0].startswith("Previous read")
    assert labels[1].startswith("Goroutine 7")


def test_runtime_stack_section() -> None:
    t = parse(CASES["fatal_with_runtime_stack"][0])
    assert t.top.extra_stacks[0][0] == "runtime stack"
    assert t.top.extra_stacks[0][1][0].function == "runtime.throw"
    assert t.top.frames[0].function == "runtime.cgocall"


def test_stdlib_vs_runtime_classification() -> None:
    t = parse(CASES["go_test_panic"][0])
    kinds = [f.kind for f in t.top.frames]
    assert kinds[:3] == ["stdlib", "stdlib", "runtime"]
    assert "app" in kinds
