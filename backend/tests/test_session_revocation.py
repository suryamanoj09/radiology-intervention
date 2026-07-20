"""DB-backed session revocation (opt-in) + the admin session-management surface.

Stateless signed cookies alone cannot be force-revoked; with the DB enabled the
session `sid` is recorded server-side so logout AND an admin can kill a live session.
When the DB is disabled the app stays purely stateless — proven here too, so the
zero-config demo is unchanged.

Torch-free: the one protected path probed is /api/generate-report (deterministic
template generator); every gate rejects before any model runs.
"""

import pytest

from app import auth, db


# --- shared state resets (mirror the auth-persistence suite) ----------------
@pytest.fixture(autouse=True)
def _reset_auth_state():
    auth._login_hits.clear()
    auth._account_fails.clear()
    auth._TOTP_SECRETS.clear()
    auth._seeded_urls.clear()
    yield
    auth._login_hits.clear()
    auth._account_fails.clear()
    auth._TOTP_SECRETS.clear()
    auth._seeded_urls.clear()


@pytest.fixture
def db_url(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'sessions.db').as_posix()}"
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


def _report(c, csrf):
    return c.post("/api/generate-report", json={"structured": {}},
                  headers={"X-CSRF-Token": csrf})


# ============================================================================
# DB ENABLED — logout force-revokes a live (still-signed) session
# ============================================================================
def test_logout_revokes_session(client, db_url, monkeypatch):
    h = auth.hash_password("pw123")
    monkeypatch.setenv("AUTH_USERS", f"clinician:{h}")
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth, "COOKIE_SECURE", False)

    assert _login(client).status_code == 200
    # The session is recorded server-side, so a protected POST works.
    assert _report(client, _csrf(client)).status_code == 200

    # Capture the STILL-VALID signed cookies before logout.
    tok = client.cookies.get(auth.COOKIE_NAME)
    csrf_cookie = client.cookies.get(auth.CSRF_COOKIE_NAME)
    assert tok

    assert client.post("/api/logout").status_code == 200

    # Replay the captured cookie: its signature/expiry still verify, but the session
    # was revoked at logout -> 401 session_revoked. This is exactly what a purely
    # stateless cookie could NOT do.
    client.cookies.clear()
    client.cookies.set(auth.COOKIE_NAME, tok)
    client.cookies.set(auth.CSRF_COOKIE_NAME, csrf_cookie)
    r = _report(client, csrf_cookie)
    assert r.status_code == 401 and r.json()["code"] == "session_revoked"


# ============================================================================
# DB ENABLED — an admin can list + revoke ANOTHER user's session
# ============================================================================
def test_admin_revoke_kills_another_session(app_module, db_url, monkeypatch):
    from fastapi.testclient import TestClient

    h = auth.hash_password("pw123")
    monkeypatch.setenv("AUTH_USERS", f"admin:{h},victim:{h}")
    monkeypatch.setattr(auth, "AUTH_ADMINS", frozenset({"admin"}))
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth, "COOKIE_SECURE", False)

    victim = TestClient(app_module)
    admin = TestClient(app_module)

    # Victim signs in and can use a protected endpoint.
    assert _login(victim, "victim").status_code == 200
    assert _report(victim, _csrf(victim)).status_code == 200

    # Admin signs in and lists the victim's server-side sessions.
    assert _login(admin, "admin").status_code == 200
    listed = admin.get("/api/admin/sessions", params={"username": "victim"})
    assert listed.status_code == 200, listed.text
    sids = [s["sid"] for s in listed.json()["sessions"]]
    assert sids, "victim should have a recorded session"

    # Admin revokes it (CSRF required on this protected POST).
    rv = admin.post("/api/admin/sessions/revoke", json={"sid": sids[0]},
                    headers={"X-CSRF-Token": _csrf(admin)})
    assert rv.status_code == 200 and rv.json()["revoked"] == 1

    # The victim's next protected request is now rejected server-side.
    blocked = _report(victim, _csrf(victim))
    assert blocked.status_code == 401 and blocked.json()["code"] == "session_revoked"


def test_admin_endpoints_forbidden_for_non_admin(app_module, db_url, monkeypatch):
    from fastapi.testclient import TestClient

    h = auth.hash_password("pw123")
    monkeypatch.setenv("AUTH_USERS", f"admin:{h},victim:{h}")
    monkeypatch.setattr(auth, "AUTH_ADMINS", frozenset({"admin"}))
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth, "COOKIE_SECURE", False)

    victim = TestClient(app_module)
    assert _login(victim, "victim").status_code == 200
    r = victim.get("/api/admin/sessions")
    assert r.status_code == 403 and r.json()["code"] == "forbidden"


def test_admin_revoke_all_for_user(app_module, db_url, monkeypatch):
    from fastapi.testclient import TestClient

    h = auth.hash_password("pw123")
    monkeypatch.setenv("AUTH_USERS", f"admin:{h},victim:{h}")
    monkeypatch.setattr(auth, "AUTH_ADMINS", frozenset({"admin"}))
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth, "COOKIE_SECURE", False)

    # Victim opens two independent sessions (two clients / cookie jars).
    v1, v2, admin = (TestClient(app_module) for _ in range(3))
    assert _login(v1, "victim").status_code == 200
    assert _login(v2, "victim").status_code == 200
    assert _login(admin, "admin").status_code == 200

    rv = admin.post("/api/admin/sessions/revoke", json={"username": "victim"},
                    headers={"X-CSRF-Token": _csrf(admin)})
    assert rv.status_code == 200 and rv.json()["revoked"] == 2

    # Both victim sessions are dead.
    assert _report(v1, _csrf(v1)).json()["code"] == "session_revoked"
    assert _report(v2, _csrf(v2)).json()["code"] == "session_revoked"


# ============================================================================
# DB DISABLED — stateless behaviour is byte-for-byte unchanged
# ============================================================================
def test_db_disabled_logout_is_stateless(client, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db.reset_engine_for_tests()
    assert db.is_enabled() is False
    monkeypatch.setattr(auth, "_USERS", {"clinician": auth.hash_password("pw123")})
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth, "COOKIE_SECURE", False)

    assert _login(client).status_code == 200
    assert _report(client, _csrf(client)).status_code == 200
    tok = client.cookies.get(auth.COOKIE_NAME)
    csrf_cookie = client.cookies.get(auth.CSRF_COOKIE_NAME)
    client.post("/api/logout")

    # No server-side revocation exists when the DB is off: replaying the still-valid
    # signed cookie STILL works (stateless, exactly as before this feature).
    client.cookies.clear()
    client.cookies.set(auth.COOKIE_NAME, tok)
    client.cookies.set(auth.CSRF_COOKIE_NAME, csrf_cookie)
    assert _report(client, csrf_cookie).status_code == 200

    # And the middleware revocation helper is a no-op when disabled.
    assert auth._session_revoked("any-sid") is False


def test_db_disabled_admin_endpoint_reports_db_required(client, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db.reset_engine_for_tests()
    monkeypatch.setattr(auth, "_USERS", {"admin": auth.hash_password("pw123")})
    monkeypatch.setattr(auth, "AUTH_ADMINS", frozenset({"admin"}))
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth, "COOKIE_SECURE", False)

    assert _login(client, "admin").status_code == 200
    r = client.get("/api/admin/sessions")
    assert r.status_code == 400 and r.json()["code"] == "db_disabled"
