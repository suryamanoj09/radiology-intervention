"""Dynamic login/logout auth (issue #12).

Two layers:
  * UNIT — the stdlib-signed token + credential primitives in app.auth, driven by
    monkeypatching the module globals (no reimport, no env dance).
  * ENDPOINT — /api/login, /api/logout, /api/me and the AuthMiddleware gate on a
    PHI-adjacent POST. These require app.main to WIRE the auth router + middleware
    (see the apply-ready main.py modification). AUTH_ENABLED / COOKIE_SECURE /
    _USERS are flipped at runtime because the handlers + middleware read the
    module globals at call time.

Torch-free: the gate rejects before any model runs, and the allowed path we probe
(/api/generate-report) is the deterministic template.
"""

import pytest

from app import auth


@pytest.fixture(autouse=True)
def _reset_login_throttle():
    auth._login_hits.clear()
    yield
    auth._login_hits.clear()


@pytest.fixture(autouse=True)
def _pin_inmemory_user_backend(monkeypatch):
    """Pin the ENV/in-memory user backend for this suite.

    These are UNIT/ENDPOINT tests of the auth primitives + the ENV/in-memory user
    backend, which they provision by monkeypatching ``auth._USERS``. The opt-in DB
    user backend is covered end-to-end (seed-from-ENV, verify, 2FA persistence,
    disabled users, full login+2FA flow across a restart) by test_auth_persistence.py.
    So when the whole suite is run with an ambient DATABASE_URL set, pin this backend
    to in-memory — otherwise the ``_USERS`` provisioning never reaches the DB and every
    login fails. Nothing DB-specific is lost: CSRF/lockout/rotation are user-store
    agnostic, and the DB user path has its own dedicated coverage."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from app import db

    db.reset_engine_for_tests()
    yield
    db.reset_engine_for_tests()


@pytest.fixture
def demo_user(monkeypatch):
    """A single configured user: clinician / pw123."""
    monkeypatch.setattr(auth, "_USERS", {"clinician": auth._sha256_hex("pw123")})
    return ("clinician", "pw123")


# --------------------------- UNIT: credentials ------------------------------
def test_verify_credentials_good_bad_and_unknown_user(demo_user):
    assert auth.verify_credentials("clinician", "pw123") is True
    assert auth.verify_credentials("clinician", "wrong") is False
    # Unknown user must fail without leaking existence (returns False, no raise).
    assert auth.verify_credentials("nobody", "pw123") is False
    assert auth.verify_credentials("", "") is False


# --------------------------- UNIT: signed token -----------------------------
def test_token_round_trips_and_carries_subject(demo_user):
    tok = auth.issue_token("clinician")
    payload = auth.verify_token(tok)
    assert payload is not None
    assert payload["sub"] == "clinician"


def test_tampered_signature_is_rejected(demo_user):
    tok = auth.issue_token("clinician")
    body, _, sig = tok.partition(".")
    # Flip a character in the signature segment.
    forged = body + "." + ("A" if sig[0] != "A" else "B") + sig[1:]
    assert auth.verify_token(forged) is None
    # A token with a swapped-in different-user payload also fails (sig won't match).
    assert auth.verify_token("bogus.payload") is None
    assert auth.verify_token("") is None


def test_expired_token_is_rejected(demo_user, monkeypatch):
    monkeypatch.setattr(auth, "SESSION_TTL_SECONDS", -10)  # already expired at issue
    tok = auth.issue_token("clinician")
    assert auth.verify_token(tok) is None


def test_token_for_removed_user_is_rejected(monkeypatch):
    monkeypatch.setattr(auth, "_USERS", {"clinician": auth._sha256_hex("pw123")})
    tok = auth.issue_token("clinician")
    assert auth.verify_token(tok) is not None
    # User removed from config after issue -> outstanding token no longer valid.
    monkeypatch.setattr(auth, "_USERS", {})
    assert auth.verify_token(tok) is None


# --------------------------- UNIT: brute-force throttle ---------------------
def test_login_throttle_trips_after_max_attempts(monkeypatch):
    monkeypatch.setattr(auth, "LOGIN_MAX_ATTEMPTS", 3)
    ip = "203.0.113.5"
    assert [auth._login_throttled(ip) for _ in range(3)] == [False, False, False]
    assert auth._login_throttled(ip) is True  # 4th attempt is throttled


# --------------------------- ENDPOINT: open demo (auth off) -----------------
def test_login_and_me_report_open_state_when_auth_disabled(client, monkeypatch):
    monkeypatch.setattr(auth, "AUTH_ENABLED", False)
    r = client.post("/api/login", json={"username": "x", "password": "y"})
    assert r.status_code == 200
    body = r.json()
    assert body["authenticated"] is False and body["auth_enabled"] is False

    me = client.get("/api/me").json()
    assert me["auth_enabled"] is False and me["authenticated"] is False


# --------------------------- ENDPOINT: full login/logout cycle --------------
def test_login_success_sets_session_then_logout_clears_it(client, monkeypatch, demo_user):
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth, "COOKIE_SECURE", False)  # so the http TestClient keeps the cookie

    r = client.post("/api/login", json={"username": "clinician", "password": "pw123"})
    assert r.status_code == 200, r.text
    assert r.json()["authenticated"] is True
    assert auth.COOKIE_NAME in r.cookies

    me = client.get("/api/me").json()
    assert me["authenticated"] is True and me["user"] == "clinician"

    client.post("/api/logout")
    assert client.get("/api/me").json()["authenticated"] is False


def test_login_wrong_password_is_401_and_grants_no_session(client, monkeypatch, demo_user):
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth, "COOKIE_SECURE", False)
    r = client.post("/api/login", json={"username": "clinician", "password": "nope"})
    assert r.status_code == 401
    assert client.get("/api/me").json()["authenticated"] is False


# --------------------------- ENDPOINT: middleware gate ----------------------
def test_protected_endpoint_401_without_login_then_allowed_after(client, monkeypatch, demo_user):
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth, "COOKIE_SECURE", False)
    monkeypatch.setattr(auth, "PROTECTED_PREFIXES", ("/api/generate-report",))

    # No session -> the gate blocks a PHI-adjacent POST with a machine-readable code.
    blocked = client.post("/api/generate-report", json={"structured": {}})
    assert blocked.status_code == 401
    assert blocked.json().get("code") == "auth_required"

    # After login the same POST passes the gate (deterministic template, no torch).
    # Cookie-authed POSTs now also require the double-submit CSRF token.
    client.post("/api/login", json={"username": "clinician", "password": "pw123"})
    csrf = client.get("/api/csrf").json()["csrf_token"]
    allowed = client.post("/api/generate-report", json={"structured": {}},
                          headers={"X-CSRF-Token": csrf})
    assert allowed.status_code == 200
    assert allowed.json()["generator"] == "template"


def test_unprotected_paths_stay_open_when_auth_enabled(client, monkeypatch, demo_user):
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth, "PROTECTED_PREFIXES", ("/api/analyze",))
    # Health + behaviour card are never gated, so the SPA/login screen can load.
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/behavior-card").status_code == 200
