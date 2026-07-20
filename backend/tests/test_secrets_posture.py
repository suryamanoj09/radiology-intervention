"""Secrets management — fail-closed on a weak SESSION_SECRET.

The HMAC signing key is the trust anchor for every session cookie. In a production
posture (AUTH_ENABLED=1, or REQUIRE_STRONG_SECRETS/PROD) a blank/default/short secret
must FAIL CLOSED at startup so no deploy ships a forgeable signing key. In the open
demo (AUTH_ENABLED=0) a per-process ephemeral secret is minted with a one-time
WARNING so the zero-config demo still runs.

Unit-tests the pure resolver AND the real import-time behaviour (subprocess), so the
guard is proven to actually fire at startup, not just in isolation.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app import auth

_BACKEND = Path(__file__).resolve().parents[1]


# --- pure resolver ----------------------------------------------------------
def test_weak_secret_detection():
    assert auth._is_weak_secret("") is True
    assert auth._is_weak_secret("   ") is True
    assert auth._is_weak_secret("changeme") is True
    assert auth._is_weak_secret("CHANGEME") is True     # case-insensitive
    assert auth._is_weak_secret("dev") is True
    assert auth._is_weak_secret("short-secret") is True  # < 32 chars
    assert auth._is_weak_secret("x" * 40) is False       # long + not a known default


def test_prod_posture_raises_on_weak_or_default_secret():
    for weak in ("", "changeme", "dev", "password", "abc123"):
        with pytest.raises(RuntimeError):
            auth._resolve_session_secret(weak, prod_posture=True)


def test_prod_posture_accepts_a_strong_secret():
    strong = "s" * 48
    secret, ephemeral = auth._resolve_session_secret(strong, prod_posture=True)
    assert secret == strong and ephemeral is False


def test_demo_posture_uses_ephemeral_and_does_not_raise():
    secret, ephemeral = auth._resolve_session_secret("", prod_posture=False)
    assert ephemeral is True
    assert len(secret) >= 32  # a real random key, not the (empty) input


# --- real import-time behaviour (subprocess: isolated env, fresh interpreter) ----
def _run_import(overrides: dict) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    for k in ("SESSION_SECRET", "AUTH_ENABLED", "REQUIRE_STRONG_SECRETS", "PROD",
              "DATABASE_URL"):
        env.pop(k, None)
    env.update(overrides)
    return subprocess.run([sys.executable, "-c", "import app.auth"],
                          cwd=str(_BACKEND), env=env, capture_output=True, text=True)


def test_import_fails_closed_in_prod_with_default_secret():
    r = _run_import({"AUTH_ENABLED": "1"})  # prod posture, no SESSION_SECRET
    assert r.returncode != 0
    assert "SESSION_SECRET" in r.stderr


def test_import_fails_closed_with_require_strong_secrets_flag():
    # Even with AUTH disabled, REQUIRE_STRONG_SECRETS forces the prod posture.
    r = _run_import({"REQUIRE_STRONG_SECRETS": "1"})
    assert r.returncode != 0
    assert "SESSION_SECRET" in r.stderr


def test_import_ok_in_prod_with_strong_secret():
    r = _run_import({"AUTH_ENABLED": "1", "SESSION_SECRET": "z" * 48})
    assert r.returncode == 0, r.stderr


def test_import_ok_in_demo_with_default_secret_and_warns():
    r = _run_import({})  # AUTH_ENABLED unset -> open demo
    assert r.returncode == 0, r.stderr
    # Warns (one-time) about the ephemeral key but does NOT crash the demo.
    assert "ephemeral" in r.stderr.lower()
