"""Auth-hardening coverage (issue: high-assurance login).

Exercises the additions layered onto the stateless signed-cookie session WITHOUT
regressing it:
  * optional TOTP 2FA — enroll, verify, and required-before-access;
  * CSRF double-submit required on cookie-authed state-changing POSTs;
  * per-account lockout after N consecutive failures (+ reset on success);
  * username-enumeration uniformity (same message/status + scrypt always runs);
  * session-cookie flags (HttpOnly / Secure / SameSite / Path);
  * session-token rotation on login and on 2FA completion (fixation defence).

Torch-free: the one allowed protected path we probe (/api/generate-report) is the
deterministic template generator, and every gate rejects before any model runs.
"""

import time

import pytest

from app import auth


# --- shared state resets ----------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_auth_state():
    auth._login_hits.clear()
    auth._account_fails.clear()
    auth._TOTP_SECRETS.clear()
    yield
    auth._login_hits.clear()
    auth._account_fails.clear()
    auth._TOTP_SECRETS.clear()


@pytest.fixture(autouse=True)
def _pin_inmemory_user_backend(monkeypatch):
    """Pin the ENV/in-memory user backend for this hardening suite.

    The tests provision the user via ``auth._USERS`` and 2FA via the in-memory
    ``_TOTP_SECRETS`` dict. The opt-in DB user/2FA backend is covered end-to-end by
    test_auth_persistence.py (including login + 2FA across a simulated restart). So
    when the full suite runs with an ambient DATABASE_URL set, pin this backend to
    in-memory — otherwise the ``_USERS`` provisioning never reaches the DB and login
    fails. CSRF/lockout/session-rotation are user-store agnostic, so no DB-mode
    coverage is lost by pinning here."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from app import db

    db.reset_engine_for_tests()
    yield
    db.reset_engine_for_tests()


@pytest.fixture
def demo_user(monkeypatch):
    """A single configured user: clinician / pw123 (legacy sha256 hash is fine —
    verify_credentials accepts it)."""
    monkeypatch.setattr(auth, "_USERS", {"clinician": auth._sha256_hex("pw123")})
    return ("clinician", "pw123")


@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth, "COOKIE_SECURE", False)  # http TestClient keeps cookies


def _totp_code(secret: str) -> str:
    return auth._totp_at(secret, time.time(), auth.TOTP_STEP_SECONDS, auth.TOTP_DIGITS)


def _login(client, user="clinician", pw="pw123"):
    return client.post("/api/login", json={"username": user, "password": pw})


def _csrf(client) -> str:
    return client.get("/api/csrf").json()["csrf_token"]


# ============================================================================
# TOTP 2FA
# ============================================================================
def test_totp_enroll_returns_secret_and_otpauth_uri(client, auth_on, demo_user):
    _login(client)
    r = client.post("/api/2fa/enroll")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["secret"] and body["confirmed"] is False
    assert body["otpauth_uri"].startswith("otpauth://totp/")
    assert f"issuer={auth.TOTP_ISSUER}" in body["otpauth_uri"]
    # A generated code for the returned secret must verify (round-trip of our RFC6238).
    assert auth.verify_totp(body["secret"], _totp_code(body["secret"])) is True


def test_totp_verify_confirms_enrollment_and_completes_session(client, auth_on, demo_user):
    _login(client)
    secret = client.post("/api/2fa/enroll").json()["secret"]
    # A wrong code is rejected...
    bad = client.post("/api/2fa/verify", json={"code": "000000"})
    assert bad.status_code == 401 and bad.json()["code"] == "totp_invalid"
    # ...a correct code confirms enrollment and marks the session 2FA-satisfied.
    ok = client.post("/api/2fa/verify", json={"code": _totp_code(secret)})
    assert ok.status_code == 200 and ok.json()["mfa"] is True
    assert client.get("/api/me").json()["mfa_enrolled"] is True


def test_2fa_required_before_access_once_enrolled(client, auth_on, demo_user, monkeypatch):
    monkeypatch.setattr(auth, "PROTECTED_PREFIXES", ("/api/generate-report",))
    # Enroll + confirm 2FA.
    _login(client)
    secret = client.post("/api/2fa/enroll").json()["secret"]
    client.post("/api/2fa/verify", json={"code": _totp_code(secret)})
    client.post("/api/logout")

    # Fresh login now yields only a HALF session: authenticated False, mfa owed.
    r = _login(client)
    body = r.json()
    assert body["authenticated"] is False and body["mfa_required"] is True
    me = client.get("/api/me").json()
    assert me["authenticated"] is False and me["mfa_pending"] is True

    # Protected access is blocked with a machine-readable mfa_required code...
    csrf = _csrf(client)
    blocked = client.post("/api/generate-report", json={"structured": {}},
                          headers={"X-CSRF-Token": csrf})
    assert blocked.status_code == 401 and blocked.json()["code"] == "mfa_required"

    # ...until the TOTP code upgrades the session, after which the POST passes.
    client.post("/api/2fa/verify", json={"code": _totp_code(secret)})
    csrf = _csrf(client)
    allowed = client.post("/api/generate-report", json={"structured": {}},
                          headers={"X-CSRF-Token": csrf})
    assert allowed.status_code == 200
    assert allowed.json()["generator"] == "template"


def test_2fa_enroll_from_half_session_cannot_downgrade_confirmed(client, auth_on, demo_user, monkeypatch):
    """2FA-bypass defence: a password-only (MFA-pending) session must NOT be able to
    re-enroll an account that already has CONFIRMED 2FA. Re-enrollment overwrites the
    stored secret with confirmed=False, which would drop the MFA requirement and let
    the half session reach protected routes without ever proving the second factor."""
    monkeypatch.setattr(auth, "PROTECTED_PREFIXES", ("/api/generate-report",))
    # Victim enrolls + confirms 2FA, then signs out.
    _login(client)
    secret = client.post("/api/2fa/enroll").json()["secret"]
    client.post("/api/2fa/verify", json={"code": _totp_code(secret)})
    client.post("/api/logout")

    # Attacker knows ONLY the password -> half (MFA-pending) session.
    assert _login(client).json()["mfa_required"] is True

    # The enroll attempt is refused (mfa_required) and does NOT touch the enrollment.
    er = client.post("/api/2fa/enroll")
    assert er.status_code == 401 and er.json()["code"] == "mfa_required"
    me = client.get("/api/me").json()
    assert me["mfa_enrolled"] is True and me["authenticated"] is False and me["mfa_pending"] is True

    # Protected access is STILL blocked with mfa_required (no bypass).
    csrf = _csrf(client)
    blocked = client.post("/api/generate-report", json={"structured": {}},
                          headers={"X-CSRF-Token": csrf})
    assert blocked.status_code == 401 and blocked.json()["code"] == "mfa_required"

    # The original confirmed secret still works to finish login (legit flow intact).
    client.post("/api/2fa/verify", json={"code": _totp_code(secret)})
    csrf = _csrf(client)
    ok = client.post("/api/generate-report", json={"structured": {}},
                     headers={"X-CSRF-Token": csrf})
    assert ok.status_code == 200


def test_2fa_initial_enroll_still_works_for_user_without_2fa(client, auth_on, demo_user):
    """The downgrade guard must not break INITIAL enrollment: a user with no confirmed
    2FA is fully authenticated on password alone, so enroll + verify must still work."""
    _login(client)
    r = client.post("/api/2fa/enroll")
    assert r.status_code == 200 and r.json()["confirmed"] is False
    ok = client.post("/api/2fa/verify", json={"code": _totp_code(r.json()["secret"])})
    assert ok.status_code == 200 and ok.json()["mfa"] is True


# ============================================================================
# CSRF double-submit
# ============================================================================
def test_csrf_required_on_cookie_authed_post(client, auth_on, demo_user, monkeypatch):
    monkeypatch.setattr(auth, "PROTECTED_PREFIXES", ("/api/generate-report",))
    _login(client)

    # No CSRF header -> 403 even with a valid session cookie.
    blocked = client.post("/api/generate-report", json={"structured": {}})
    assert blocked.status_code == 403 and blocked.json()["code"] == "csrf_failed"

    # A header that does NOT match the csrf cookie is also rejected.
    _csrf(client)  # sets the cookie
    mismatch = client.post("/api/generate-report", json={"structured": {}},
                           headers={"X-CSRF-Token": "not-the-cookie-value"})
    assert mismatch.status_code == 403

    # Matching double-submit token passes.
    csrf = _csrf(client)
    ok = client.post("/api/generate-report", json={"structured": {}},
                     headers={"X-CSRF-Token": csrf})
    assert ok.status_code == 200


def test_csrf_exempts_header_auth_flows(client, auth_on, demo_user, monkeypatch):
    """A request carrying an Authorization/access-code header is a header (not a
    browser-cookie) flow — not CSRF-forgeable — so the double-submit requirement is
    skipped, keeping the bearer/access-code paths working."""
    monkeypatch.setattr(auth, "PROTECTED_PREFIXES", ("/api/generate-report",))
    _login(client)
    ok = client.post("/api/generate-report", json={"structured": {}},
                     headers={"Authorization": "Bearer anything"})
    assert ok.status_code == 200


# ============================================================================
# Per-account lockout + brute force
# ============================================================================
def test_account_locks_after_n_consecutive_failures(client, auth_on, demo_user, monkeypatch):
    monkeypatch.setattr(auth, "LOGIN_LOCKOUT_THRESHOLD", 3)
    monkeypatch.setattr(auth, "LOGIN_LOCKOUT_SECONDS", 900.0)

    for _ in range(3):
        assert _login(client, pw="wrong").status_code == 401
    # 4th attempt is locked out (429) — even the CORRECT password is refused while locked.
    locked = _login(client, pw="pw123")
    assert locked.status_code == 429
    assert "locked" in locked.json()["detail"].lower()


def test_lockout_counter_resets_on_success(client, auth_on, demo_user, monkeypatch):
    monkeypatch.setattr(auth, "LOGIN_LOCKOUT_THRESHOLD", 3)
    # Two failures (below threshold), then a success resets the streak.
    assert _login(client, pw="wrong").status_code == 401
    assert _login(client, pw="wrong").status_code == 401
    assert _login(client, pw="pw123").status_code == 200
    # Two more failures would only lock if the counter had NOT reset -> still open.
    assert _login(client, pw="wrong").status_code == 401
    assert _login(client, pw="wrong").status_code == 401
    assert _login(client, pw="pw123").status_code == 200


# ============================================================================
# Username-enumeration uniformity
# ============================================================================
def test_unknown_and_wrong_password_are_indistinguishable(client, auth_on, demo_user):
    wrong = _login(client, user="clinician", pw="wrong")
    unknown = _login(client, user="ghost", pw="wrong")
    assert wrong.status_code == unknown.status_code == 401
    # Byte-identical body: no field distinguishes "bad password" from "no such user".
    assert wrong.json() == unknown.json() == {"detail": "Invalid username or password."}


def test_scrypt_runs_even_for_unknown_user(demo_user, monkeypatch):
    """Timing-uniformity primitive: the full password hash executes for an unknown
    user (against the dummy) so response time cannot reveal account existence."""
    calls = []
    real = auth._verify_password
    monkeypatch.setattr(auth, "_verify_password",
                        lambda pw, stored: calls.append(stored) or real(pw, stored))
    assert auth.verify_credentials("ghost", "whatever") is False
    assert calls == [auth._DUMMY_HASH]  # the dummy-hash burn ran exactly once


# ============================================================================
# Cookie flags
# ============================================================================
def _set_cookie_for(resp, name):
    for c in resp.headers.get_list("set-cookie"):
        if c.startswith(name + "="):
            return c
    return ""


def test_session_and_csrf_cookie_flags(client, demo_user, monkeypatch):
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth, "COOKIE_SECURE", True)   # assert Secure is emitted
    monkeypatch.setattr(auth, "COOKIE_SAMESITE", "lax")

    r = _login(client)
    sess = _set_cookie_for(r, auth.COOKIE_NAME).lower()
    assert "httponly" in sess
    assert "secure" in sess
    assert "samesite=lax" in sess
    assert "path=/" in sess

    csrf = _set_cookie_for(r, auth.CSRF_COOKIE_NAME).lower()
    assert csrf, "login should also mint a CSRF cookie"
    assert "httponly" not in csrf           # JS must read it (double-submit)
    assert "secure" in csrf and "path=/" in csrf


# ============================================================================
# Session rotation (fixation defence)
# ============================================================================
def test_session_token_rotates_on_login_and_2fa(client, auth_on, demo_user):
    # Two logins mint distinct session ids (a pre-set cookie can never be fixed).
    _login(client)
    tok1 = client.cookies.get(auth.COOKIE_NAME)
    client.post("/api/logout")
    _login(client)
    tok2 = client.cookies.get(auth.COOKIE_NAME)
    assert tok1 and tok2 and tok1 != tok2
    assert auth.verify_token(tok1)["sid"] != auth.verify_token(tok2)["sid"]

    # Enroll 2FA, then confirm: the token is rotated again (new sid) on 2FA completion.
    secret = client.post("/api/2fa/enroll").json()["secret"]
    before = client.cookies.get(auth.COOKIE_NAME)
    client.post("/api/2fa/verify", json={"code": _totp_code(secret)})
    after = client.cookies.get(auth.COOKIE_NAME)
    assert before != after
    assert auth.verify_token(before)["sid"] != auth.verify_token(after)["sid"]
    assert auth.verify_token(after)["mfa"] is True
