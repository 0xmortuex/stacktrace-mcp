"""Decide whether a frame is application code or library / stdlib / framework code.

The rules are per language and based on path and package conventions only. They
are heuristics: a project that vendors a library under its own tree will look
like application code, which is the safe direction (nothing gets hidden).
"""

from __future__ import annotations

import re

from .model import APP, FRAMEWORK, LIBRARY, RUNTIME, STDLIB, UNKNOWN


def norm_path(p: str) -> str:
    return p.replace("\\", "/")


# ---------------------------------------------------------------- Python

_PY_FRAMEWORKS = (
    "django", "flask", "fastapi", "starlette", "uvicorn", "gunicorn", "werkzeug", "tornado",
    "aiohttp", "celery", "sqlalchemy", "pytest", "_pytest", "asgiref", "hypercorn", "sanic",
)  # fmt: skip
_PY_STDLIB = re.compile(r"/(?:lib|Lib)(?:64)?/(?:python3?(?:\.\d+)?/)?(?!site-packages|dist-packages)", re.I)


def python_kind(path: str) -> str:
    p = norm_path(path)
    if p.startswith("<frozen") or p.startswith("<built-in"):
        return STDLIB
    if p.startswith("<"):  # <stdin>, <string>, <ipython-input-3-...>
        return APP
    for marker in ("/site-packages/", "/dist-packages/"):
        if marker in p:
            rest = p.split(marker, 1)[1]
            top = rest.split("/", 1)[0].lower()
            if any(top == fw or top.startswith(fw + "-") for fw in _PY_FRAMEWORKS):
                return FRAMEWORK
            return LIBRARY
    low = p.lower()
    if re.search(r"/lib(?:64)?/python3?(?:\.\d+)?/", low):
        return STDLIB
    if re.search(r"/python3?\d*(?:\.\d+)*/lib/", low) or re.search(r"/python\d+/lib/", low):
        return STDLIB
    if re.search(r"/python3?\d*/lib/", low):
        return STDLIB
    # Windows installs: C:/Users/x/AppData/Local/Programs/Python/Python312/Lib/json/__init__.py
    if re.search(r"/python\d*/lib/", low) and "site-packages" not in low:
        return STDLIB
    return APP


# ---------------------------------------------------------------- Node

_NODE_FRAMEWORKS = ("express", "next", "react-dom", "react", "koa", "fastify", "@nestjs", "nestjs", "vue", "webpack", "vite")


def node_kind(path: str | None, function: str = "") -> str:
    if path is None:
        return RUNTIME
    p = norm_path(path)
    if p.startswith("node:") or p.startswith("internal/") or p in ("<anonymous>", "native"):
        return RUNTIME
    if p.startswith("file:///") or "://" in p:
        pass
    if "/node_modules/" in p or p.startswith("node_modules/") or "/.vite/deps/" in p or "/.pnpm/" in p:
        tail = p.rsplit("node_modules/", 1)[-1].lower()
        for fw in _NODE_FRAMEWORKS:
            if tail == fw or tail.startswith(fw + "/"):
                return FRAMEWORK
        return LIBRARY
    if p.startswith("webpack-internal:///") and ("node_modules" in p or p.startswith("webpack-internal:///(")):
        return LIBRARY
    if p.startswith("<"):
        return RUNTIME
    return APP


# ---------------------------------------------------------------- Java / Kotlin

_JAVA_STD = ("java.", "javax.", "jdk.", "sun.", "com.sun.", "kotlin.", "scala.", "org.w3c.", "org.xml.")
_JAVA_FRAMEWORK = (
    "org.springframework.", "org.hibernate.", "org.apache.catalina.", "org.apache.tomcat.",
    "org.eclipse.jetty.", "io.netty.", "io.micronaut.", "io.quarkus.", "org.junit.", "org.testng.",
    "jakarta.servlet.", "org.jboss.", "io.vertx.", "play.", "akka.", "kotlinx.coroutines.",
)  # fmt: skip
_JAVA_LIB = (
    "org.apache.", "com.google.", "com.fasterxml.", "org.slf4j.", "ch.qos.", "org.json.",
    "com.zaxxer.", "io.reactivex.", "reactor.", "okhttp3.", "okio.", "retrofit2.", "org.mockito.",
    "net.bytebuddy.", "org.postgresql.", "com.mysql.", "org.mariadb.", "com.amazonaws.",
    "software.amazon.", "io.grpc.", "org.objectweb.", "org.yaml.", "com.squareup.", "jakarta.", "org.glassfish.",
)  # fmt: skip


def java_kind(cls: str) -> str:
    if cls.startswith(_JAVA_STD):
        return STDLIB
    if cls.startswith(_JAVA_FRAMEWORK):
        return FRAMEWORK
    if cls.startswith(_JAVA_LIB):
        return LIBRARY
    if cls.startswith(("org.junit", "jdk")):
        return FRAMEWORK
    return APP


# ---------------------------------------------------------------- Go

_GO_ROOT_FILE = re.compile(r"(?:^|/)(?:go|golang|goroot)(?:[-\d.]*)/src/", re.I)


def go_package(function: str) -> str:
    """Package path of a Go function name: 'net/http.(*conn).serve' -> 'net/http'."""
    slash = function.rfind("/")
    dot = function.find(".", slash + 1)
    return function if dot == -1 else function[:dot]


def go_kind(function: str, file: str | None) -> str:
    pkg = go_package(function)
    f = norm_path(file) if file else ""
    if f:
        if "/pkg/mod/" in f or "/vendor/" in f or "@v" in f.rsplit("/", 1)[0]:
            return LIBRARY
        if _GO_ROOT_FILE.search(f) or f.startswith("$GOROOT"):
            if pkg.startswith("runtime") or function == "panic" or "/src/runtime/" in f:
                return RUNTIME
            return STDLIB
    if pkg == "main" or pkg.startswith("main_test") or function.startswith("main."):
        return APP
    if pkg.startswith("runtime") or function in ("panic", "created by runtime"):
        return RUNTIME
    first = pkg.split("/", 1)[0]
    if "." not in first and first not in ("main",):
        # net/http, sync, os, testing ... : standard library has no dot in its first path element
        if first in ("testing",):
            return FRAMEWORK
        return STDLIB
    if f:
        return APP
    return UNKNOWN


# ---------------------------------------------------------------- Rust

_RUST_STD_CRATES = ("std", "core", "alloc", "proc_macro", "test", "panic_unwind", "backtrace", "std_detect")
_RUST_RUNTIME = (
    "rust_begin_unwind", "__rust_", "_start", "__libc_start", "_main", "start_thread", "clone",
    "__GI_", "BaseThreadInitThunk", "RtlUserThreadStart", "_pthread", "std_detect",
)  # fmt: skip


def rust_crate(function: str) -> str:
    s = function.lstrip("<&*")
    return s.split("::", 1)[0].split(" ", 1)[0]


def rust_kind(function: str, file: str | None) -> str:
    f = norm_path(file) if file else ""
    if f.startswith("/rustc/") or "/library/std/" in f or "/library/core/" in f or "/library/alloc/" in f:
        return STDLIB
    if "/registry/src/" in f or "/.cargo/registry" in f or "/cargo/git/checkouts" in f:
        return LIBRARY
    if function.startswith(_RUST_RUNTIME):
        return RUNTIME
    crate = rust_crate(function)
    if crate in _RUST_STD_CRATES:
        return STDLIB
    if f:
        return APP
    if crate in ("tokio", "futures", "hyper", "serde", "serde_json", "actix_web", "axum", "tower", "reqwest"):
        return LIBRARY
    return UNKNOWN


# ---------------------------------------------------------------- .NET

_NET_FRAMEWORK = ("Microsoft.AspNetCore.", "Microsoft.EntityFrameworkCore.", "Microsoft.Extensions.Hosting.")
_NET_LIB = ("Newtonsoft.", "Dapper.", "Npgsql.", "MySql.", "Serilog.", "Polly.", "AutoMapper.", "MediatR.", "Moq.", "xunit.", "Xunit.", "NUnit.")


def dotnet_kind(function: str, file: str | None) -> str:
    f = norm_path(file) if file else ""
    if "/.nuget/" in f or "/nuget/packages/" in f:
        return LIBRARY
    if function.startswith(_NET_FRAMEWORK):
        return FRAMEWORK
    if function.startswith(("System.", "Microsoft.", "Windows.", "Interop.")):
        return STDLIB
    if function.startswith(_NET_LIB):
        return LIBRARY
    if f.startswith(("/_/", "/build/", "D:/a/_work", "/src/Libraries")) and "/src/libraries/" in f.lower():
        return STDLIB
    return APP
