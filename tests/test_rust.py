"""Rust panic fixtures (Rust 1.6x - 1.9x message layouts, RUST_BACKTRACE short and full)."""

from __future__ import annotations

import pytest
from helpers import check, fx, parse

CASES: dict[str, tuple[str, dict]] = {}


def case(name: str, text: str, **exp: object) -> None:
    CASES[name] = (fx(text), exp)


RUSTC = "/rustc/90b35a6239c3d8bdabc530a6a0816f7ff89a0aaf"

case("unwrap_none_173_layout", rf"""
    thread 'main' panicked at src/main.rs:4:37:
    called `Option::unwrap()` on a `None` value
    stack backtrace:
       0: rust_begin_unwind
                 at {RUSTC}/library/std/src/panicking.rs:645:5
       1: core::panicking::panic_fmt
                 at {RUSTC}/library/core/src/panicking.rs:72:14
       2: core::panicking::panic
                 at {RUSTC}/library/core/src/panicking.rs:144:5
       3: core::option::Option<T>::unwrap
                 at {RUSTC}/library/core/src/option.rs:931:21
       4: myapp::first_word
                 at ./src/main.rs:4:37
       5: myapp::main
                 at ./src/main.rs:9:13
       6: core::ops::function::FnOnce::call_once
                 at {RUSTC}/library/core/src/ops/function.rs:250:5
    note: Some details are omitted, run with `RUST_BACKTRACE=full` for a verbose backtrace.
    """, lang="rust", top="panic", msg="`None` value", origin=("myapp::first_word", "main.rs", 4),
     frames=7, kinds={0: "stdlib", 4: "app", 6: "stdlib"})

case("old_style_message_in_quotes", r"""
    thread 'main' panicked at 'called `Result::unwrap()` on an `Err` value: ParseIntError { kind: InvalidDigit }', src/main.rs:5:28
    note: run with `RUST_BACKTRACE=1` environment variable to display a backtrace
    """, lang="rust", top="panic", msg="InvalidDigit", origin=("(panic site)", "src/main.rs", 5), frames=1)

case("expect_err_with_backtrace_old", r"""
    thread 'main' panicked at 'config: Os { code: 2, kind: NotFound, message: "No such file or directory" }', src/config.rs:12:10
    stack backtrace:
       0: rust_begin_unwind
                 at /rustc/a28077b28a02b92985b3a3faecf9c3e9e4a1cd05/library/std/src/panicking.rs:517:5
       1: core::result::unwrap_failed
                 at /rustc/a28077b28a02b92985b3a3faecf9c3e9e4a1cd05/library/core/src/result.rs:1355:5
       2: myapp::config::load
                 at ./src/config.rs:12:10
       3: myapp::main
                 at ./src/main.rs:3:5
    note: Some details are omitted, run with `RUST_BACKTRACE=full` for a verbose backtrace.
    """, lang="rust", top="panic", msg="NotFound", origin=("myapp::config::load", "config.rs", 12))

case("index_out_of_bounds", rf"""
    thread 'main' panicked at src/lib.rs:20:5:
    index out of bounds: the len is 3 but the index is 7
    stack backtrace:
       0: rust_begin_unwind
                 at {RUSTC}/library/std/src/panicking.rs:645:5
       1: core::panicking::panic_bounds_check
                 at {RUSTC}/library/core/src/panicking.rs:208:5
       2: mylib::pick
                 at ./src/lib.rs:20:5
    """, lang="rust", msg="the len is 3 but the index is 7", origin=("mylib::pick", "lib.rs", 20))

case("subtract_overflow", rf"""
    thread 'main' panicked at src/main.rs:6:13:
    attempt to subtract with overflow
    stack backtrace:
       0: rust_begin_unwind
                 at {RUSTC}/library/std/src/panicking.rs:645:5
       1: core::panicking::panic_const::panic_const_sub_overflow
                 at {RUSTC}/library/core/src/panicking.rs:179:17
       2: calc::dec
                 at ./src/main.rs:6:13
    """, lang="rust", msg="subtract with overflow", origin=("calc::dec", "main.rs", 6))

case("refcell_already_borrowed", rf"""
    thread 'main' panicked at src/graph.rs:41:20:
    already borrowed: BorrowMutError
    stack backtrace:
       0: rust_begin_unwind
                 at {RUSTC}/library/std/src/panicking.rs:645:5
       1: core::cell::panic_already_borrowed
                 at {RUSTC}/library/core/src/cell.rs:757:5
       2: graph::Node::link
                 at ./src/graph.rs:41:20
    """, lang="rust", msg="BorrowMutError", origin=("graph::Node::link", "graph.rs", 41))

case("tokio_worker_thread", rf"""
    thread 'tokio-runtime-worker' panicked at src/handler.rs:33:14:
    called `Option::unwrap()` on a `None` value
    stack backtrace:
       0: rust_begin_unwind
                 at {RUSTC}/library/std/src/panicking.rs:645:5
       1: svc::handler::get
                 at ./src/handler.rs:33:14
       2: tokio::runtime::task::core::Core<T,S>::poll
                 at /home/u/.cargo/registry/src/index.crates.io-6f17d22bba15001f/tokio-1.35.1/src/runtime/task/core.rs:328:17
       3: tokio::runtime::task::harness::poll_future
                 at /home/u/.cargo/registry/src/index.crates.io-6f17d22bba15001f/tokio-1.35.1/src/runtime/task/harness.rs:476:19
    """, lang="rust", origin=("svc::handler::get", "handler.rs", 33), kinds={0: "stdlib", 2: "library", 3: "library"})

case("full_backtrace_with_addresses", rf"""
    thread 'main' panicked at src/main.rs:2:5:
    explicit panic
    stack backtrace:
       0:     0x55d4b3c7a5ba - std::backtrace_rs::backtrace::libunwind::trace::h1a2b3c4d5e6f7081
                                   at {RUSTC}/library/std/src/../../backtrace/src/backtrace/libunwind.rs:93:5
       1:     0x55d4b3c7a5ba - std::panicking::default_hook::h2a2b3c4d5e6f7081
                                   at {RUSTC}/library/std/src/panicking.rs:292:22
      13:     0x55d4b3c4a3d9 - app::run::h3a2b3c4d5e6f7081
                                   at /build/app/src/main.rs:2:5
      14:     0x7f0b1c229d90 - __libc_start_call_main
      15:                0x0 - <unknown>
    """, lang="rust", msg="explicit panic", origin=("app::run", "main.rs", 2), frames=5,
     kinds={0: "stdlib", 2: "app", 3: "runtime"})

case("assert_eq_left_right", rf"""
    thread 'tests::adds' panicked at src/lib.rs:15:9:
    assertion `left == right` failed
      left: 3
     right: 4
    stack backtrace:
       0: rust_begin_unwind
                 at {RUSTC}/library/std/src/panicking.rs:645:5
       1: core::panicking::assert_failed_inner
                 at {RUSTC}/library/core/src/panicking.rs:362:17
       2: mylib::tests::adds
                 at ./src/lib.rs:15:9
    """, lang="rust", msg="left: 3", origin=("mylib::tests::adds", "lib.rs", 15))

case("no_backtrace_only_note", r"""
    thread 'main' panicked at src/main.rs:3:5:
    not yet implemented: parse args
    note: run with `RUST_BACKTRACE=1` environment variable to display a backtrace
    """, lang="rust", msg="not yet implemented", origin=("(panic site)", "src/main.rs", 3))

case("unnamed_thread", rf"""
    thread '<unnamed>' panicked at src/worker.rs:9:9:
    worker failed
    stack backtrace:
       0: rust_begin_unwind
                 at {RUSTC}/library/std/src/panicking.rs:645:5
       1: app::worker::run
                 at ./src/worker.rs:9:9
       2: std::sys_common::backtrace::__rust_begin_short_backtrace
                 at {RUSTC}/library/std/src/sys_common/backtrace.rs:155:18
       3: core::ops::function::FnOnce::call_once{{{{vtable.shim}}}}
                 at {RUSTC}/library/core/src/ops/function.rs:250:5
    """, lang="rust", origin=("app::worker::run", "worker.rs", 9))

case("thread_id_19x_layout", rf"""
    thread 'main' (48213) panicked at src/main.rs:7:20:
    called `Result::unwrap()` on an `Err` value: "bad"
    stack backtrace:
       0: __rustc::rust_begin_unwind
                 at {RUSTC}/library/std/src/panicking.rs:698:5
       1: app::main
                 at ./src/main.rs:7:20
    """, lang="rust", msg='"bad"', origin=("app::main", "main.rs", 7))

case("windows_backtrace", r"""
    thread 'main' panicked at src\main.rs:3:5:
    boom
    stack backtrace:
       0: std::panicking::begin_panic_handler
                 at /rustc/90b35a6239c3d8bdabc530a6a0816f7ff89a0aaf/library/std/src/panicking.rs:645
       1: tool::run
                 at C:\Users\fadi\tool\src\main.rs:3
    """, lang="rust", origin=("tool::run", "main.rs", 3))

case("truncated_backtrace_no_location", rf"""
    thread 'main' panicked at src/main.rs:3:5:
    boom
    stack backtrace:
       0: rust_begin_unwind
                 at {RUSTC}/library/std/src/panicking.rs:645:5
       1: app::deep
    """, lang="rust", partial=True)

case("divide_by_zero", rf"""
    thread 'main' panicked at src/main.rs:5:13:
    attempt to divide by zero
    stack backtrace:
       0: rust_begin_unwind
                 at {RUSTC}/library/std/src/panicking.rs:645:5
       1: app::ratio
                 at ./src/main.rs:5:13
    """, lang="rust", msg="divide by zero", origin=("app::ratio", "main.rs", 5))


@pytest.mark.parametrize("name", sorted(CASES))
def test_rust_fixture(name: str) -> None:
    text, exp = CASES[name]
    check(text, **exp)  # type: ignore[arg-type]


def test_there_are_at_least_twelve_rust_fixtures() -> None:
    assert len(CASES) >= 12


def test_thread_and_panic_site_are_recorded() -> None:
    t = parse(CASES["tokio_worker_thread"][0])
    assert t.top.thread == "tokio-runtime-worker"
    assert any("src/handler.rs:33:14" in n for n in t.top.notes)


def test_hash_suffix_is_stripped_from_symbols() -> None:
    t = parse(CASES["full_backtrace_with_addresses"][0])
    assert t.top.frames[0].function == "std::backtrace_rs::backtrace::libunwind::trace"
    assert t.top.frames[2].function == "app::run"


def test_multiline_message_is_kept() -> None:
    t = parse(CASES["assert_eq_left_right"][0])
    assert "assertion `left == right` failed" in t.top.message and "right: 4" in t.top.message


def test_no_backtrace_note() -> None:
    t = parse(CASES["no_backtrace_only_note"][0])
    assert any("RUST_BACKTRACE=1" in n for n in t.notes)
