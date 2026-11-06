"""Fingerprints: same bug on another run/host => same hash; different bug => different hash."""

from __future__ import annotations

from helpers import fx, parse
from stacktrace_mcp.fingerprint import components, fingerprint

PY_A = fx(r"""
    Traceback (most recent call last):
      File "/app/src/orders.py", line 40, in handle
        total = compute(order)
      File "/app/src/pricing.py", line 12, in compute
        return order["qty"] * price
    KeyError: 'qty'
    """)
# same bug: different container path, different line numbers (code edited), different key text
PY_A2 = fx(r"""
    Traceback (most recent call last):
      File "C:\Users\fadi\proj\src\orders.py", line 47, in handle
        total = compute(order)
      File "C:\Users\fadi\proj\src\pricing.py", line 15, in compute
        return order["quantity"] * price
    KeyError: 'quantity'
    """)
# different bug: same files but another exception type
PY_B = fx(r"""
    Traceback (most recent call last):
      File "/app/src/orders.py", line 40, in handle
        total = compute(order)
      File "/app/src/pricing.py", line 12, in compute
        return order["qty"] * price
    TypeError: unsupported operand type(s) for *: 'NoneType' and 'int'
    """)
# different bug: same type, different function
PY_C = fx(r"""
    Traceback (most recent call last):
      File "/app/src/orders.py", line 40, in handle
        total = refund(order)
      File "/app/src/refunds.py", line 5, in refund
        return order["qty"]
    KeyError: 'qty'
    """)


def fp(text: str, lines: bool = False) -> str:
    return fingerprint(parse(text), lines)


def test_same_bug_different_run_same_fingerprint() -> None:
    assert fp(PY_A) == fp(PY_A2)


def test_different_exception_type_different_fingerprint() -> None:
    assert fp(PY_A) != fp(PY_B)


def test_different_function_different_fingerprint() -> None:
    assert fp(PY_A) != fp(PY_C)


def test_line_numbers_only_matter_when_asked() -> None:
    assert fp(PY_A, lines=True) != fp(PY_A2, lines=True)
    assert fp(PY_A, lines=False) == fp(PY_A2, lines=False)


def test_library_frames_do_not_change_the_fingerprint() -> None:
    with_lib = fx(r"""
        Traceback (most recent call last):
          File "/app/src/orders.py", line 40, in handle
            total = compute(order)
          File "/usr/local/lib/python3.12/site-packages/pydantic/main.py", line 99, in validate
            return self._v(x)
          File "/app/src/pricing.py", line 12, in compute
            return order["qty"] * price
        KeyError: 'qty'
        """)
    assert fp(with_lib) == fp(PY_A)


def test_components_are_explainable() -> None:
    comps = components(parse(PY_A))
    assert comps[0] == "lang=python"
    assert "root=KeyError" in comps
    assert "f0=compute|pricing.py" in comps


def test_hash_is_stable_across_calls() -> None:
    assert len({fp(PY_A) for _ in range(5)}) == 1
    assert len(fp(PY_A)) == 16


JAVA_1 = fx(r"""
    java.lang.IllegalStateException: no tenant 4411
    <T>at com.acme.Svc$$EnhancerBySpringCGLIB$$3fa1b2c4.find(<generated>)
    <T>at com.acme.Svc.find(Svc.java:30)
    <T>at com.acme.Web.get(Web.java:12)
    """)
JAVA_2 = fx(r"""
    java.lang.IllegalStateException: no tenant 9
    <T>at com.acme.Svc$$EnhancerBySpringCGLIB$$99ee0011.find(<generated>)
    <T>at com.acme.Svc.find(Svc.java:34)
    <T>at com.acme.Web.get(Web.java:14)
    """)


def test_java_generated_class_names_are_normalised() -> None:
    assert fp(JAVA_1) == fp(JAVA_2)


GO_1 = fx(r"""
    panic: runtime error: index out of range [5] with length 3

    goroutine 1 [running]:
    main.process(0xc000012345, {0x4d6a3a, 0x5})
    <T>/app/main.go:12 +0x2c
    main.main()
    <T>/app/main.go:20 +0x1d
    """)
GO_2 = fx(r"""
    panic: runtime error: index out of range [9] with length 2

    goroutine 7 [running]:
    main.process(0xc000099999, {0x4d6a3a, 0x9})
    <T>/build/src/main.go:14 +0x4e
    main.main()
    <T>/build/src/main.go:22 +0x1d
    """)
GO_NIL = fx(r"""
    panic: runtime error: invalid memory address or nil pointer dereference

    goroutine 1 [running]:
    main.process(0x0, {0x4d6a3a, 0x5})
    <T>/app/main.go:12 +0x2c
    main.main()
    <T>/app/main.go:20 +0x1d
    """)


def test_go_addresses_goroutine_ids_and_numbers_ignored() -> None:
    assert fp(GO_1) == fp(GO_2)


def test_go_generic_panic_type_still_distinguishes_message_class() -> None:
    assert fp(GO_1) != fp(GO_NIL)


def test_node_bundle_hashes_and_urls_ignored() -> None:
    a = fx(r"""
        TypeError: x is undefined
            at render (https://cdn.a.com/static/app.3f9a1c2d.js:1:100)
            at https://cdn.a.com/static/vendor.aabbccdd.js:2:5
        """)
    b = fx(r"""
        TypeError: y is undefined
            at render (https://cdn.b.com/assets/app.99887766.js:1:5000)
            at https://cdn.b.com/assets/vendor.11223344.js:9:9
        """)
    assert fp(a) == fp(b)


def test_rust_symbol_hashes_ignored() -> None:
    a = fx(r"""
        thread 'main' panicked at src/main.rs:2:5:
        explicit panic
        stack backtrace:
           0: app::run::h0123456789abcdef
                     at /build/app/src/main.rs:2:5
        """)
    b = fx(r"""
        thread 'main' panicked at src/main.rs:2:5:
        explicit panic
        stack backtrace:
           0: app::run::hfedcba9876543210
                     at /other/app/src/main.rs:2:5
        """)
    assert fp(a) == fp(b)


def test_dotnet_generic_arity_and_paths_ignored() -> None:
    a = fx(r"""
        System.InvalidOperationException: x
           at MyApp.Repo`1.Get(Int32 id) in C:\a\Repo.cs:line 4
        """)
    b = fx(r"""
        System.InvalidOperationException: y
           at MyApp.Repo.Get(Int32 id) in /build/Repo.cs:line 99
        """)
    assert fp(a) == fp(b)


def test_chain_top_type_participates() -> None:
    wrapped = fx(r"""
        Traceback (most recent call last):
          File "/app/a.py", line 1, in a
            raise KeyError('k')
        KeyError: 'k'

        The above exception was the direct cause of the following exception:

        Traceback (most recent call last):
          File "/app/b.py", line 2, in b
            raise RuntimeError('r')
        RuntimeError: r
        """)
    bare = fx(r"""
        Traceback (most recent call last):
          File "/app/a.py", line 1, in a
            raise KeyError('k')
        KeyError: 'k'
        """)
    assert fp(wrapped) != fp(bare)
