"""Redaction: planted fake secrets, emails, IPs and home directories must never survive."""

from __future__ import annotations

import pytest
from helpers import fx
from stacktrace_mcp import server
from stacktrace_mcp.redact import redact

# Built from pieces at runtime so this file contains no token-shaped literals for secret scanners.
GH = "gh" + "p_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
AWS = "AK" + "IA" + "ABCDEFGHIJ234567"
JWT = "ey" + "J" + "hbGciOiJIUzI1NiJ9" + "." + "ey" + "J" + "zdWIiOiIxMjM0NTY3ODkwIn0" + "." + "dBjftJeZ4CVPmB92K27uhbUJU1p1r"
SLACK = "xo" + "xb-" + "1234567890-abcdefghijkl"
STRIPE = "sk" + "_live_" + "abcdefghij1234567890"
GOOGLE = "AI" + "za" + "SyA-1234567890abcdefghijklmnopqrstu"
OPENAI = "sk" + "-" + "proj-abcdefghijklmnop1234567890"
PASSWORD = "hunter2" + "-correct-horse"
EMAIL = "fadi.private" + "@" + "example-corp.com"
IP4 = "10.20" + ".30.41"
IP6 = "2001:0db8:85a3:0000:0000:8a2e:0370:7334"
USER_WIN = "SecretUserName"
LONG_TOKEN = "Zx9Qw8Er7Ty6Ui5Op4As3Df2Gh1Jk0LmNbVcXzQwErTyUiOp"

SECRETS = [GH, AWS, JWT, SLACK, STRIPE, GOOGLE, OPENAI, PASSWORD, EMAIL, IP4, IP6, USER_WIN, LONG_TOKEN]

TRACE = fx(
    r"""
    Traceback (most recent call last):
      File "C:\Users\@USER@\proj\app.py", line 4, in connect
        db = connect("postgres://admin:@PW@@@IP4@/db")
      File "/home/@USER@/proj/net.py", line 9, in call
        requests.get(url, headers={"Authorization": "Bearer @GH@"})
    RuntimeError: failed for @EMAIL@ from @IP4@ / @IP6@ token=@GH@ password=@PW@ key=@AWS@ jwt=@JWT@
      slack=@SLACK@ stripe=@STRIPE@ google=@GOOGLE@ openai=@OPENAI@ blob=@LONG@
    """
).replace("@USER@", USER_WIN).replace("@PW@", PASSWORD).replace("@IP4@", IP4).replace("@IP6@", IP6) \
    .replace("@GH@", GH).replace("@EMAIL@", EMAIL).replace("@AWS@", AWS).replace("@JWT@", JWT) \
    .replace("@SLACK@", SLACK).replace("@STRIPE@", STRIPE).replace("@GOOGLE@", GOOGLE) \
    .replace("@OPENAI@", OPENAI).replace("@LONG@", LONG_TOKEN)


def assert_clean(text: str) -> None:
    for s in SECRETS:
        assert s not in text, f"{s!r} leaked"


def test_redact_trace_removes_everything_planted() -> None:
    assert_clean(redact(TRACE))


def test_structure_is_preserved() -> None:
    out = redact(TRACE)
    assert "File \"C:\\Users\\<user>\\proj\\app.py\", line 4, in connect" in out
    assert "/home/<user>/proj/net.py" in out
    assert "RuntimeError:" in out


@pytest.mark.parametrize(
    "tool_call",
    [
        lambda: server.redact_trace(TRACE),
        lambda: server.parse_trace(TRACE),
        lambda: server.parse_trace(TRACE, format="json"),
        lambda: server.fingerprint(TRACE),
        lambda: server.compare_traces(TRACE, TRACE),
        lambda: server.parse_trace(TRACE, full=True, max_frames=500),
    ],
)
def test_every_tool_output_is_clean_by_default(tool_call) -> None:  # type: ignore[no-untyped-def]
    assert_clean(tool_call())


def test_redact_false_returns_the_original() -> None:
    out = server.parse_trace(TRACE, redact=False)
    assert GH in out or EMAIL in out


def test_json_output_is_clean_too() -> None:
    out = server.parse_trace(TRACE, format="json")
    assert_clean(out)
    assert '"type": "RuntimeError"' in out


def test_planted_home_directory_variants() -> None:
    samples = [
        r"C:\Users\Alice\x.py",
        r"c:\users\alice\x.py",
        r"C:\\Users\\Alice\\x.py",
        "C:/Users/Alice/x.py",
        "/home/alice/x.py",
        "/Users/alice/x.py",
    ]
    for s in samples:
        out = redact(s)
        assert "lice" not in out, (s, out)
        assert "<user>" in out


def test_ipv4_validity_and_versions() -> None:
    assert redact("host 192.168.1.20 port 80") == "host <redacted:ip> port 80"
    assert redact("v 999.1.1.1") == "v 999.1.1.1"  # not an address


def test_email_edge_cases() -> None:
    assert "a@b" in redact("a@b is not an email")
    assert redact("x user.name+tag@sub.example.co.uk y") == "x <redacted:email> y"
    assert redact("@@@@") == "@@@@"


def test_ordinary_trace_text_is_untouched() -> None:
    plain = fx(
        r"""
        Traceback (most recent call last):
          File "/app/main.py", line 10, in <module>
            main()
        ZeroDivisionError: division by zero
        """
    )
    assert redact(plain) == plain


def test_hex_commit_hashes_and_long_identifiers() -> None:
    assert "<redacted:hex>" in redact("commit " + "a" * 40)
    ident = "ThisIsAVeryLongButHarmlessJavaClassNameWithoutDigitsXX"
    assert redact(ident) == ident
