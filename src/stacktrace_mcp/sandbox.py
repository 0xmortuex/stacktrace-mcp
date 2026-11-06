"""Directory sandbox: every filesystem path the tools touch must resolve inside a --dir root."""

from __future__ import annotations

import os
import stat


class SandboxError(ValueError):
    """A path is unusable or outside the sandbox; the message tells the caller what to do."""


def real(path: str) -> str:
    """os.path.realpath that turns every failure mode into SandboxError.

    realpath raises OSError for some inputs and a bare ValueError for others (embedded NUL,
    "path too long" on Windows with Python 3.10), so both are converted here and nowhere else.
    """
    try:
        return os.path.realpath(path)
    except (OSError, ValueError) as e:
        raise SandboxError(f"Cannot resolve path ({type(e).__name__}): the path is invalid or too long.") from e


def is_inside(root_real: str, candidate_real: str) -> bool:
    a = os.path.normcase(root_real)
    b = os.path.normcase(candidate_real)
    if a == b:
        return True
    prefix = a if a.endswith(os.sep) else a + os.sep
    return b.startswith(prefix)


class Sandbox:
    def __init__(self, roots: list[str]) -> None:
        self.roots: list[str] = []
        for r in roots:
            rr = real(r)
            if not os.path.isdir(rr):
                raise SandboxError(f"--dir {r!r} is not an existing directory.")
            self.roots.append(rr)

    @property
    def enabled(self) -> bool:
        return bool(self.roots)

    def require(self, what: str) -> None:
        if not self.roots:
            raise SandboxError(
                f"{what} needs a directory sandbox. Start the server with --dir <path> "
                "(for example: stacktrace-mcp --dir C:\\path\\to\\project)."
            )

    def resolve(self, path: str, what: str = "path") -> str:
        """Resolve `path` (absolute, or relative to the first root) to a real path inside a root."""
        self.require(what)
        if not path or "\x00" in path:
            raise SandboxError(f"{what} must be a non-empty path without NUL characters.")
        cand = path if os.path.isabs(path) else os.path.join(self.roots[0], path)
        rr = real(cand)
        for root in self.roots:
            if is_inside(root, rr):
                return rr
        raise SandboxError(
            f"{what} {path[:200]!r} is outside the sandbox. Allowed root(s): {', '.join(self.roots)}. "
            "Symlinks are resolved before this check."
        )

    def root_of(self, resolved: str) -> str:
        for root in self.roots:
            if is_inside(root, resolved):
                return root
        raise SandboxError("path is outside the sandbox.")

    def regular_file(self, path: str, what: str = "file") -> str:
        rr = self.resolve(path, what)
        try:
            st = os.stat(rr)
        except (OSError, ValueError) as e:  # ValueError: "path too long" on Windows, Python 3.10
            why = (e.strerror if isinstance(e, OSError) else None) or type(e).__name__
            raise SandboxError(f"Cannot read {what} {path[:200]!r}: {why}.") from e
        if not stat.S_ISREG(st.st_mode):
            raise SandboxError(f"{what} {path[:200]!r} is not a regular file.")
        return rr

    def directory(self, path: str, what: str = "directory") -> str:
        rr = self.resolve(path, what)
        if not os.path.isdir(rr):  # isdir() returns False for missing and for too-long paths
            raise SandboxError(f"{what} {path[:200]!r} is not an existing directory inside the sandbox.")
        return rr
