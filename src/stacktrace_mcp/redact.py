"""Remove secrets and personal data from text.

Linear-time by construction: every regex either starts with a distinctive literal
prefix or consumes a single character class greedily; emails and long tokens are
found with str.find / bounded scans instead of backtracking patterns.
"""

from __future__ import annotations

import re

_SIMPLE: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*"), "<redacted:jwt>"),
    (re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA)[0-9A-Z]{16}\b"), "<redacted:aws-key>"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "<redacted:github-token>"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "<redacted:github-token>"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), "<redacted:slack-token>"),
    (re.compile(r"\b[sr]k_(?:live|test)_[0-9A-Za-z]{10,}"), "<redacted:stripe-key>"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}"), "<redacted:google-key>"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), "<redacted:api-key>"),
    (re.compile(r"\bnpm_[A-Za-z0-9]{30,}"), "<redacted:npm-token>"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "<redacted:private-key>"),
    (re.compile(r"(?i)\b(Bearer|Basic)[ \t]+[A-Za-z0-9._~+/=-]{8,}"), r"\1 <redacted:token>"),
    (
        re.compile(r"(?i)\b(authorization|proxy-authorization|x-api-key|cookie|set-cookie)(\s*[:=]\s*)[^\r\n]{4,}"),
        r"\1\2<redacted:header>",
    ),
    (re.compile(r"(?i)\b([a-z][a-z0-9+.-]{1,15}://)[^\s/@:]+:[^\s/@]+@"), r"\1<redacted:credentials>@"),
    (
        re.compile(
            r"(?i)([?&;](?:access_token|refresh_token|id_token|token|api_key|apikey|key|sig|"
            r"signature|password|secret|auth)=)[^&\s\"']+"
        ),
        r"\1<redacted:query-secret>",
    ),
    (
        re.compile(
            r"(?i)\b(password|passwd|pwd|secret|client_secret|api[_-]?key|apikey|access[_-]?key|"
            r"auth[_-]?token|access[_-]?token|private[_-]?key|credentials?|token)"
            r"([\"']?[ \t]*[:=][ \t]*[\"']?)([^\s\"',;&)}\]]{3,})"
        ),
        r"\1\2<redacted:secret>",
    ),
    # Home directories: C:\Users\name\, C:\\Users\\name\\ (JSON-escaped), /home/name/, /Users/name/
    (re.compile(r"(?i)\b([a-z]:[\\/]+users[\\/]+)[^\\/\s\"'<>|:*?]+"), r"\1<user>"),
    (re.compile(r"(/home/|/Users/)[^/\s\"'<>:*?\\]+"), r"\1<user>"),
    (re.compile(r"(?i)(%USERPROFILE%|%HOMEPATH%)"), "<home>"),
    (re.compile(r"\b(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}\b"), "<redacted:ip>"),
    (re.compile(r"\bfe80::[0-9A-Fa-f:]*[0-9A-Fa-f]"), "<redacted:ip>"),
    (re.compile(r"\[([0-9A-Fa-f]{1,4}:){2,7}[0-9A-Fa-f:]*\](?=:\d)"), "[<redacted:ip>]"),
]
_IPV4 = re.compile(r"(?<![\w.])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?![\w])")
_LONG_TOKEN = re.compile(r"[A-Za-z0-9_-]{40,}")
_HEX_RUN = re.compile(r"\b[0-9a-fA-F]{32,}\b")
_LOCAL = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._%+-")
_DOMAIN = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-")


def _ipv4(m: re.Match[str]) -> str:
    if all(int(g) <= 255 for g in m.groups()):
        return "<redacted:ip>"
    return m.group(0)


def _long_token(m: re.Match[str]) -> str:
    s = m.group(0)
    classes = (any(c.islower() for c in s), any(c.isupper() for c in s), any(c.isdigit() for c in s))
    if sum(classes) >= 3:
        return "<redacted:token>"
    return s


def _emails(line: str) -> str:
    if "@" not in line:
        return line
    out: list[str] = []
    pos = 0
    at = line.find("@")
    while at != -1:
        ls = at
        while ls > pos and at - ls < 64 and line[ls - 1] in _LOCAL:
            ls -= 1
        de = at + 1
        while de < len(line) and de - at < 256 and line[de] in _DOMAIN:
            de += 1
        domain = line[at + 1 : de].rstrip(".-")
        tld = domain.rpartition(".")[2]
        if ls < at and "." in domain and len(tld) >= 2 and tld.isalpha() and not domain.startswith("."):
            out.append(line[pos:ls])
            out.append("<redacted:email>")
            pos = at + 1 + len(domain)
            at = line.find("@", pos)
        else:
            at = line.find("@", at + 1)
    out.append(line[pos:])
    return "".join(out)


def redact(text: str) -> str:
    """Return text with secrets, emails, IP addresses and home-directory user names removed."""
    out_lines: list[str] = []
    for line in text.split("\n"):
        if len(line) > 20000:
            line = line[:20000] + "...[line cut]"
        line = _emails(line)
        for pat, repl in _SIMPLE:
            line = pat.sub(repl, line)
        line = _IPV4.sub(_ipv4, line)
        line = _LONG_TOKEN.sub(_long_token, line)
        line = _HEX_RUN.sub("<redacted:hex>", line)
        out_lines.append(line)
    return "\n".join(out_lines)
