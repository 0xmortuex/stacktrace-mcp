"""Node.js / V8 / Chromium stack trace fixtures (Node 12-24 and browser forms)."""

from __future__ import annotations

import pytest
from helpers import check, fx, parse

CASES: dict[str, tuple[str, dict]] = {}


def case(name: str, text: str, **exp: object) -> None:
    CASES[name] = (fx(text), exp)


case("uncaught_with_source_preamble", r"""
    /home/u/app/index.js:10
        throw new Error('boom');
        ^

    Error: boom
        at Object.<anonymous> (/home/u/app/index.js:10:11)
        at Module._compile (node:internal/modules/cjs/loader:1256:14)
        at Module._extensions..js (node:internal/modules/cjs/loader:1310:10)
        at Module.load (node:internal/modules/cjs/loader:1119:32)
        at Module._load (node:internal/modules/cjs/loader:960:12)
        at Function.executeUserEntryPoint [as runMain] (node:internal/modules/run_main:81:12)
        at node:internal/main/run_main_module:23:47

    Node.js v18.17.0
    """, lang="node", top="Error", msg="boom", origin=("Object.<anonymous>", "index.js", 10),
     frames=7, kinds={0: "app", 1: "runtime", 6: "runtime"})

case("typeerror_undefined_property", r"""
    TypeError: Cannot read properties of undefined (reading 'name')
        at getUserName (/srv/app/src/users.js:23:20)
        at /srv/app/src/routes.js:8:15
        at Layer.handle [as handle_request] (/srv/app/node_modules/express/lib/router/layer.js:95:5)
        at next (/srv/app/node_modules/express/lib/router/route.js:144:13)
    """, lang="node", top="TypeError", msg="reading 'name'", origin=("getUserName", "users.js", 23),
     kinds={0: "app", 1: "app", 2: "framework", 3: "framework"})

case("reference_error", r"""
    ReferenceError: foo is not defined
        at Object.<anonymous> (C:\work\app\main.js:3:1)
        at Module._compile (internal/modules/cjs/loader.js:1085:14)
        at Object.Module._extensions..js (internal/modules/cjs/loader.js:1114:10)
    """, lang="node", top="ReferenceError", origin=("Object.<anonymous>", "main.js", 3),
     kinds={0: "app", 1: "runtime"})

case("fs_enoent_with_props", r"""
    Error: ENOENT: no such file or directory, open '/etc/app/config.json'
        at Object.openSync (node:fs:601:3)
        at Object.readFileSync (node:fs:469:35)
        at loadConfig (/srv/app/config.js:7:19) {
      errno: -2,
      syscall: 'open',
      code: 'ENOENT',
      path: '/etc/app/config.json'
    }

    Node.js v20.10.0
    """, lang="node", top="Error", msg="ENOENT", origin=("loadConfig", "config.js", 7))

case("async_frames", r"""
    Error: request failed
        at fetchData (/app/src/api.js:15:11)
        at async Promise.all (index 1)
        at async loadAll (/app/src/api.js:30:5)
        at async main (/app/src/index.js:4:3)
    """, lang="node", top="Error", origin=("fetchData", "api.js", 15), frames=4)

case("cause_chain", r"""
    Error: could not start server
        at start (/app/server.js:12:11)
        at Object.<anonymous> (/app/server.js:20:1) {
      [cause]: Error: listen EADDRINUSE: address already in use :::3000
          at Server.setupListenHandle [as _listen2] (node:net:1740:16)
          at listenInCluster (node:net:1788:12)
          at Server.listen (node:net:1876:7)
          at start (/app/server.js:10:8) {
        code: 'EADDRINUSE',
        errno: -98
      }
    }
    """, lang="node", top="Error", root="Error", chain=2, msg="could not start",
     origin=("start", "server.js", 10))

case("aggregate_error", r"""
    AggregateError: all promises were rejected
        at Promise.any (<anonymous>)
        at async run (/app/any.js:5:3) {
      [errors]: [
        Error: first
            at a (/app/any.js:1:9),
        Error: second
            at b (/app/any.js:2:9)
      ]
    }
    """, lang="node", top="AggregateError")

case("webpack_internal_eval", r"""
    TypeError: Cannot read properties of null (reading 'map')
        at eval (webpack-internal:///./src/components/List.jsx:14:22)
        at renderWithHooks (webpack-internal:///./node_modules/react-dom/cjs/react-dom.development.js:16305:18)
        at mountIndeterminateComponent (webpack-internal:///./node_modules/react-dom/cjs/react-dom.development.js:20074:13)
    """, lang="node", top="TypeError", origin=("eval", "List.jsx", 14), kinds={0: "app", 1: "framework"})

case("vite_dev_server_urls", r"""
    TypeError: x.map is not a function
        at Items (http://localhost:5173/src/Items.tsx?t=1712345678:9:20)
        at renderWithHooks (http://localhost:5173/node_modules/.vite/deps/react-dom_client.js?v=a1b2c3d4:11596:26)
        at updateFunctionComponent (http://localhost:5173/node_modules/.vite/deps/react-dom_client.js?v=a1b2c3d4:14630:28)
    """, lang="node", top="TypeError", origin=("Items", "Items.tsx", 9), kinds={0: "app", 1: "library"})

case("native_and_anonymous_frames", r"""
    TypeError: Reduce of empty array with no initial value
        at Array.reduce (<anonymous>)
        at total (/app/cart.js:4:18)
        at new Promise (<anonymous>)
        at Object.<anonymous> (/app/cart.js:9:1)
    """, lang="node", top="TypeError", origin=("total", "cart.js", 4), kinds={0: "runtime", 2: "runtime"})

case("capture_stack_trace_custom_error", r"""
    ValidationError: email is invalid
        at validate (/app/lib/validate.js:22:11)
        at Object.<anonymous> (/app/lib/validate.js:40:3)
        at Module._compile (node:internal/modules/cjs/loader:1376:14) {
      field: 'email',
      code: 'E_VALIDATION'
    }
    """, lang="node", top="ValidationError", origin=("validate", "validate.js", 22))

case("minified_browser_frame", r"""
    TypeError: Cannot read properties of undefined (reading 'id')
        at t.exports (https://cdn.example.com/static/app.min.js:1:23456)
        at https://cdn.example.com/static/app.min.js:2:998
        at Object.next (https://cdn.example.com/static/vendor.4f3a9c2d.js:1:5120)
    """, lang="node", top="TypeError")

case("windows_and_file_url", r"""
    Error: bad input
        at parse (file:///C:/Users/fadi/proj/src/parse.mjs:12:9)
        at ModuleJob.run (node:internal/modules/esm/module_job:217:25)
        at async main (C:\Users\fadi\proj\src\main.js:5:3)
    """, lang="node", top="Error", origin=("parse", "parse.mjs", 12))

case("eval_frame", r"""
    SyntaxError: Unexpected token ')'
        at eval (eval at <anonymous> (/app/template.js:30:12), <anonymous>:1:7)
        at render (/app/template.js:31:5)
    """, lang="node", top="SyntaxError", origin=("eval", "template.js", 30))

case("express_stack_with_node_modules", r"""
    Error: db timeout
        at Timeout._onTimeout (/app/db.js:44:21)
        at listOnTimeout (node:internal/timers:569:17)
        at process.processTimers (node:internal/timers:512:7)
    """, lang="node", top="Error", origin=("Timeout._onTimeout", "db.js", 44))

case("headerless_frames_only", r"""
        at foo (/app/a.js:1:1)
        at bar (/app/b.js:2:2)
    """, lang="node", top="(unknown)", origin=("foo", "a.js", 1), partial=False)

case("error_name_only_no_message", r"""
    Error
        at x (/app/x.js:1:1)
    """, lang="node", top="Error", origin=("x", "x.js", 1))


@pytest.mark.parametrize("name", sorted(CASES))
def test_node_fixture(name: str) -> None:
    text, exp = CASES[name]
    check(text, **exp)  # type: ignore[arg-type]


def test_there_are_at_least_twelve_node_fixtures() -> None:
    assert len(CASES) >= 12


def test_cause_relation() -> None:
    t = parse(CASES["cause_chain"][0])
    assert t.chain[1].via == "cause"
    assert t.chain[1].code == "EADDRINUSE"
    assert t.root_causes()[0].message.startswith("listen EADDRINUSE")


def test_aggregate_error_children() -> None:
    t = parse(CASES["aggregate_error"][0])
    assert [c[0].message for c in t.top.group] == ["first", "second"]
    assert [e.message for e in t.root_causes()] == ["first", "second"]


def test_props_do_not_leak_into_frames() -> None:
    t = parse(CASES["fs_enoent_with_props"][0])
    assert t.top.code == "ENOENT"
    assert len(t.top.frames) == 3


def test_minified_frames_are_flagged() -> None:
    t = parse(CASES["minified_browser_frame"][0])
    assert all(f.minified for f in t.top.frames[:2])
    assert t.origin() is not None


def test_query_strings_are_stripped_from_urls() -> None:
    t = parse(CASES["vite_dev_server_urls"][0])
    assert "?" not in (t.top.frames[0].file or "")


def test_async_flag() -> None:
    t = parse(CASES["async_frames"][0])
    assert [f.is_async for f in t.top.frames] == [False, True, True, True]


def test_eval_frame_reports_outer_location() -> None:
    t = parse(CASES["eval_frame"][0])
    assert t.top.frames[0].file == "/app/template.js" and t.top.frames[0].line == 30


def test_headerless_note() -> None:
    t = parse(CASES["headerless_frames_only"][0])
    assert any("No exception header" in n for n in t.notes)
