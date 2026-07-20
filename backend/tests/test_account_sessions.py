"""Per-user account/session self-management (own the auth.py endpoints added here).

These endpoints let an ORDINARY signed-in user manage their own footprint (no admin
role): list their own sessions, revoke one, sign out of all other devices, and disable
their 2FA. Everything is scoped to the caller's own rows — one user can never see or
kill another user's session — and server-side session history requires the DB, which is
reported honestly (supported:false) when DATABASE_URL is unset.

Torch-free: the single protected model-adjacent path probed is /api/generate-report
(deterministic template generator); every auth gate rejects before any model runs.
"""

import time

import pytest
from fastapi.testclient import TestClient

from app import auth, db


# --- shared state resets (mirror the session-revocation suite) --------------
@pytest.fixture(autouse=True)
def _reset_auth_state():
    for d in (auth._login_hits, auth._account_fails, auth._TOTP_SECRETS, auth._seeded_urls):
        d.clear()
    yield
    for d in (auth._login_hits, auth._account_fails, auth._TOTP_SECRETS, auth._seeded_urls):
        d.clear()


@pytest.fixture
def db_url(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'account.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    db.reset_engine_for_tests()
    db.init_db()
    auth._seeded_urls.clear()
    assert db.is_enabled() is True
    yield url
    db.reset_engine_for_tests()
    auth._seeded_urls.clear()
    monkeypatch.delenv("DATABASE_URL", raising=False)


def _login(c, user="clinician", pw="pw123"):
    return c.post("/api/login", json={"username": user, "password": pw})


def _csrf(c) -> str:
    return c.get("/api/csrf").json()["csrf_token"]


def _report(c):
    """A protected POST — 200 only while the session is live + 2FA-satisfied."""
    return c.post("/api/generate-report", json={"structured": {}},
                  headers={"X-CSRF-Token": _csrf(c)})


def _sessions(c):
    return c.get("/api/sessions")


def _current_sid(c) -> str:
    body = _sessions(c).json()
    return next(s["sid"] for s in body["sessions"] if s["is_current"])


def _seed_two_users(monkeypatch):
    h = auth.hash_password("pw123")
    monkeypatch.setenv("AUTH_USERS", f"alice:{h},bob:{h}")
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth, "COOKIE_SECURE", False)


# ============================================================================
# 1. LIST — only the caller's own sessions, current one marked, no raw IP
# ============================================================================
def test_list_shows_only_own_sessions_and_marks_current(app_module, db_url, monkeypatch):
    _seed_two_users(monkeypatch)
    alice = TestClient(app_module)
    bob = TestClient(app_module)
    assert _login(alice, "alice").status_code == 200
    assert _login(bob, "bob").status_code == 200

    body = _sessions(alice).json()
    assert body["supported"] is True
    assert len(body["sessions"]) == 1, "alice must see ONLY her own session"
    item = body["sessions"][0]
    # Actionable id == sid; current session flagged; no raw IP field is ever present.
    assert item["id"] == item["sid"]
    assert item["is_current"] is True
    assert "ip" not in item and "ip_address" not in item
    assert set(item) >= {"id", "sid", "created_at", "last_seen", "user_agent",
                         "ip_hash", "is_current"}

    # Bob likewise sees only his own; the two sids are disjoint.
    alice_sid = item["sid"]
    bob_body = _sessions(bob).json()
    assert len(bob_body["sessions"]) == 1
    assert bob_body["sessions"][0]["sid"] != alice_sid


# ============================================================================
# 2. REVOKE OWN works; revoking another user's session is refused
# ============================================================================
def test_revoke_own_session_logs_it_out(app_module, db_url, monkeypatch):
    _seed_two_users(monkeypatch)
    a1 = TestClient(app_module)
    a2 = TestClient(app_module)
    assert _login(a1, "alice").status_code == 200
    assert _login(a2, "alice").status_code == 200

    a1_sid = _current_sid(a1)
    a2_sid = _current_sid(a2)
    assert a1_sid != a2_sid

    # a1 lists both of alice's sessions and revokes the OTHER one (a2).
    listed = _sessions(a1).json()["sessions"]
    assert {s["sid"] for s in listed} == {a1_sid, a2_sid}
    rv = a1.post("/api/sessions/revoke", json={"sid": a2_sid},
                 headers={"X-CSRF-Token": _csrf(a1)})
    assert rv.status_code == 200 and rv.json()["revoked"] == 1

    # a2's next protected request is now dead server-side; a1 still works.
    assert _report(a2).json()["code"] == "session_revoked"
    assert _report(a1).status_code == 200


def test_revoke_another_users_session_is_refused(app_module, db_url, monkeypatch):
    _seed_two_users(monkeypatch)
    alice = TestClient(app_module)
    bob = TestClient(app_module)
    assert _login(alice, "alice").status_code == 200
    assert _login(bob, "bob").status_code == 200

    bob_sid = _current_sid(bob)
    # Alice tries to kill Bob's session -> 403, and Bob is untouched.
    rv = alice.post("/api/sessions/revoke", json={"sid": bob_sid},
                    headers={"X-CSRF-Token": _csrf(alice)})
    assert rv.status_code == 403 and rv.json()["code"] == "forbidden"
    assert _report(bob).status_code == 200

    # An entirely unknown sid -> 404 (never confirms another user's session exists).
    rv2 = alice.post("/api/sessions/revoke", json={"sid": "deadbeefdeadbeef"},
                     headers={"X-CSRF-Token": _csrf(alice)})
    assert rv2.status_code == 404 and rv2.json()["code"] == "not_found"


# ============================================================================
# 3. REVOKE-OTHERS — kills every other session, keeps the current one
# ============================================================================
def test_revoke_others_keeps_current(app_module, db_url, monkeypatch):
    _seed_two_users(monkeypatch)
    a1, a2, a3 = (TestClient(app_module) for _ in range(3))
    for c in (a1, a2, a3):
        assert _login(c, "alice").status_code == 200

    current = _current_sid(a1)
    rv = a1.post("/api/sessions/revoke-others", headers={"X-CSRF-Token": _csrf(a1)})
    assert rv.status_code == 200
    assert rv.json()["revoked"] == 2 and rv.json()["kept"] == current

    # The current device stays signed in; the other two are dead.
    assert _report(a1).status_code == 200
    assert _report(a2).json()["code"] == "session_revoked"
    assert _report(a3).json()["code"] == "session_revoked"


# ============================================================================
# 4. 2FA DISABLE — requires a valid current code, then me() reports not enrolled
# ============================================================================
def _totp_now(secret: str) -> str:
    return auth._totp_at(secret, time.time(), auth.TOTP_STEP_SECONDS, auth.TOTP_DIGITS)


def _enroll_and_confirm_2fa(c) -> str:
    secret = c.post("/api/2fa/enroll", headers={"X-CSRF-Token": _csrf(c)}).json()["secret"]
    r = c.post("/api/2fa/verify", json={"code": _totp_now(secret)},
               headers={"X-CSRF-Token": _csrf(c)})
    assert r.status_code == 200 and r.json()["mfa"] is True
    return secret


def test_2fa_disable_requires_valid_code(client, monkeypatch):
    # In-memory path (DB off): enrollment lives in auth._TOTP_SECRETS.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db.reset_engine_for_tests()
    monkeypatch.setattr(auth, "_USERS", {"clinician": auth.hash_password("pw123")})
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth, "COOKIE_SECURE", False)

    assert _login(client).status_code == 200
    secret = _enroll_and_confirm_2fa(client)
    assert client.get("/api/me").json()["mfa_enrolled"] is True

    # Wrong code -> refused, enrollment still active.
    bad = client.post("/api/2fa/disable", json={"code": "000000"},
                      headers={"X-CSRF-Token": _csrf(client)})
    assert bad.status_code == 401 and bad.json()["code"] == "totp_invalid"
    assert client.get("/api/me").json()["mfa_enrolled"] is True

    # Valid current code -> disabled; me() now reports not enrolled.
    ok = client.post("/api/2fa/disable", json={"code": _totp_now(secret)},
                     headers={"X-CSRF-Token": _csrf(client)})
    assert ok.status_code == 200 and ok.json()["disabled"] is True
    assert client.get("/api/me").json()["mfa_enrolled"] is False


def test_2fa_disable_db_path(client, db_url, monkeypatch):
    # DB path: enrollment lives in the users table (encrypted at rest); disable clears it.
    h = auth.hash_password("pw123")
    monkeypatch.setenv("AUTH_USERS", f"clinician:{h}")
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth, "COOKIE_SECURE", False)

    assert _login(client).status_code == 200
    secret = _enroll_and_confirm_2fa(client)
    assert client.get("/api/me").json()["mfa_enrolled"] is True

    ok = client.post("/api/2fa/disable", json={"code": _totp_now(secret)},
                     headers={"X-CSRF-Token": _csrf(client)})
    assert ok.status_code == 200 and ok.json()["mfa_enrolled"] is False
    assert client.get("/api/me").json()["mfa_enrolled"] is False


# ============================================================================
# 5. GATING — 401 when not authed; graceful when the DB is off
# ============================================================================
def test_unauthenticated_is_rejected(client, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db.reset_engine_for_tests()
    monkeypatch.setattr(auth, "_USERS", {"clinician": auth.hash_password("pw123")})
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth, "COOKIE_SECURE", False)

    # No cookie at all -> middleware 401 on every per-user endpoint.
    assert client.get("/api/sessions").status_code == 401
    assert client.post("/api/sessions/revoke", json={"sid": "x"}).status_code == 401
    assert client.post("/api/sessions/revoke-others").status_code == 401
    assert client.post("/api/2fa/disable", json={"code": "123456"}).status_code == 401


def test_db_off_is_graceful(client, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db.reset_engine_for_tests()
    assert db.is_enabled() is False
    monkeypatch.setattr(auth, "_USERS", {"clinician": auth.hash_password("pw123")})
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth, "COOKIE_SECURE", False)
    assert _login(client).status_code == 200

    # List: honest "needs the database" shape, not a crash.
    body = client.get("/api/sessions").json()
    assert body == {"supported": False, "sessions": []}

    # Revoke / revoke-others: clear db_disabled 400 (nothing server-side to revoke).
    r1 = client.post("/api/sessions/revoke", json={"sid": "x"},
                     headers={"X-CSRF-Token": _csrf(client)})
    assert r1.status_code == 400 and r1.json()["code"] == "db_disabled"
    r2 = client.post("/api/sessions/revoke-others", headers={"X-CSRF-Token": _csrf(client)})
    assert r2.status_code == 400 and r2.json()["code"] == "db_disabled"
