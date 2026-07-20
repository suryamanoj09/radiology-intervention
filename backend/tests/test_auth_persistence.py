"""Opt-in persistence for auth (users + 2FA) through the storage-adapter seam.

This is the WF6 auth surface routed through app/services/store.py:

  * DB DISABLED (DATABASE_URL unset) — byte-for-byte the legacy behaviour: users
    come from the ENV `_USERS` map and 2FA enrollment lives in the in-memory
    `_TOTP_SECRETS` dict. No engine, no file, no query.
  * DB ENABLED (DATABASE_URL=sqlite:///<file>) — users are read/verified from the
    DB User table, SEEDED once from the same ENV config, and runtime 2FA enrollment
    is persisted so it survives a restart (the whole point of the layer).

Torch-free: everything here is credential/2FA/DB logic; no model ever loads. The DB
is a throwaway per-test SQLite file, so the suite never touches a real database and
the DB stays disabled for every OTHER test (they never set DATABASE_URL).
"""

import time

import pytest

from app import auth, db


# --- shared state resets (mirror the auth-hardening suite) ------------------
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
    """Enable the opt-in DB against a throwaway per-test SQLite file, and tear it back
    down so no other test sees DATABASE_URL set."""
    url = f"sqlite:///{(tmp_path / 'auth.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    db.reset_engine_for_tests()
    auth._seeded_urls.clear()
    assert db.is_enabled() is True
    yield url
    db.reset_engine_for_tests()
    auth._seeded_urls.clear()
    monkeypatch.delenv("DATABASE_URL", raising=False)


def _totp_code(secret: str) -> str:
    return auth._totp_at(secret, time.time(), auth.TOTP_STEP_SECONDS, auth.TOTP_DIGITS)


# ============================================================================
# DB DISABLED — legacy env/in-memory behaviour is unchanged
# ============================================================================
def test_db_disabled_user_lookup_uses_env_map(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db.is_enabled() is False
    monkeypatch.setattr(auth, "_USERS", {"clinician": auth.hash_password("pw123")})

    assert auth.verify_credentials("clinician", "pw123") is True
    assert auth.verify_credentials("clinician", "wrong") is False
    # Unknown user still fails uniformly (dummy-hash burn, no leak, no raise).
    assert auth.verify_credentials("ghost", "pw123") is False
    # No stray DB file was created while disabled.
    assert db.get_engine() is None


def test_db_disabled_2fa_stays_in_memory(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db.is_enabled() is False

    auth._set_totp_enrollment("clinician", "JBSWY3DPEHPK3PXP", confirmed=False)
    assert auth._TOTP_SECRETS["clinician"] == {"secret": "JBSWY3DPEHPK3PXP",
                                               "confirmed": False}
    assert auth.totp_enrollment("clinician") == {"secret": "JBSWY3DPEHPK3PXP",
                                                 "confirmed": False}

    auth._confirm_totp_enrollment("clinician")
    assert auth._TOTP_SECRETS["clinician"]["confirmed"] is True
    assert auth._totp_confirmed("clinician") is True


# ============================================================================
# DB ENABLED — users seeded from ENV, verified from the DB
# ============================================================================
def test_db_seeds_users_from_env_and_verifies(db_url, monkeypatch):
    h = auth.hash_password("pw123")
    monkeypatch.setenv("AUTH_USERS", f"clinician:{h}")

    # First credential check triggers a one-time seed from ENV into the DB.
    assert auth.verify_credentials("clinician", "pw123") is True
    assert auth.verify_credentials("clinician", "wrong") is False
    assert auth.verify_credentials("ghost", "pw123") is False

    # The user is now a real DB row (not just an env map entry).
    from app.services import store
    row = store.get_user("clinician")
    assert row is not None and row["password_hash"] == h
    assert row["disabled"] is False


def test_db_seeds_single_user_and_env_confirmed_2fa(db_url, monkeypatch):
    """AUTH_USERNAME/AUTH_PASSWORD_SHA256 + AUTH_2FA_SECRETS (operator-provisioned,
    already-confirmed) seed together, so an ENV 2FA deploy migrates intact."""
    h = auth.hash_password("pw123")
    monkeypatch.setenv("AUTH_USERS", f"nurse:{h}")
    monkeypatch.setenv("AUTH_2FA_SECRETS", "nurse:JBSWY3DPEHPK3PXP")

    assert auth.verify_credentials("nurse", "pw123") is True
    enr = auth.totp_enrollment("nurse")
    assert enr == {"secret": "JBSWY3DPEHPK3PXP", "confirmed": True}
    assert auth._totp_confirmed("nurse") is True


def test_db_seed_is_idempotent_and_never_clobbers_runtime_rows(db_url, monkeypatch):
    """Seeding is emptiness-guarded: once a runtime change lands, re-running the
    ensure/seed path must NOT overwrite it with the ENV credential again."""
    h = auth.hash_password("pw123")
    monkeypatch.setenv("AUTH_USERS", f"clinician:{h}")
    assert auth.verify_credentials("clinician", "pw123") is True  # seeds

    from app.services import store
    newh = auth.hash_password("rotated")
    store.set_password("clinician", newh)

    # Force the ensure path to be re-evaluated (as a fresh process would).
    auth._seeded_urls.clear()
    assert auth.verify_credentials("clinician", "rotated") is True
    # The old ENV password is NOT re-seeded over the runtime change.
    assert auth.verify_credentials("clinician", "pw123") is False
    assert store.get_user("clinician")["password_hash"] == newh


def test_db_disabled_user_is_rejected(db_url, monkeypatch):
    h = auth.hash_password("pw123")
    monkeypatch.setenv("AUTH_USERS", f"clinician:{h}")
    assert auth.verify_credentials("clinician", "pw123") is True  # seeds

    from app.services import store
    store.set_disabled("clinician", True)
    # A disabled account cannot authenticate and does not exist for token checks.
    assert auth.verify_credentials("clinician", "pw123") is False
    assert auth._user_exists("clinician") is False
    tok = auth.issue_token("clinician")
    assert auth.verify_token(tok) is None


# ============================================================================
# DB ENABLED — 2FA enrollment is persisted (survives a "restart")
# ============================================================================
def test_2fa_enrollment_persisted_to_db(db_url, monkeypatch):
    h = auth.hash_password("pw123")
    monkeypatch.setenv("AUTH_USERS", f"clinician:{h}")
    auth.verify_credentials("clinician", "pw123")  # seed the user

    secret = auth._new_totp_secret()
    auth._set_totp_enrollment("clinician", secret, confirmed=False)

    # In DB mode nothing is written to the in-memory dict...
    assert auth._TOTP_SECRETS == {}
    # ...it lives in the DB row.
    from app.services import store
    row = store.get_user("clinician")
    assert row["twofa_secret"] == secret and row["twofa_confirmed"] is False

    auth._confirm_totp_enrollment("clinician")
    assert store.get_user("clinician")["twofa_confirmed"] is True

    # Simulate a restart: drop the shared engine + seed marker, keep only the file.
    db.reset_engine_for_tests()
    auth._seeded_urls.clear()
    auth._TOTP_SECRETS.clear()
    enr = auth.totp_enrollment("clinician")
    assert enr == {"secret": secret, "confirmed": True}
    assert auth._totp_confirmed("clinician") is True


# ============================================================================
# DB ENABLED — full endpoint flow through login + 2FA, persisted
# ============================================================================
def test_login_and_2fa_flow_persists_across_restart(client, db_url, monkeypatch):
    h = auth.hash_password("pw123")
    monkeypatch.setenv("AUTH_USERS", f"clinician:{h}")
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth, "COOKIE_SECURE", False)  # http TestClient keeps cookies

    # Login (seeds the user), then enroll + confirm 2FA via the endpoints.
    assert client.post("/api/login",
                       json={"username": "clinician", "password": "pw123"}).status_code == 200
    secret = client.post("/api/2fa/enroll").json()["secret"]
    ok = client.post("/api/2fa/verify", json={"code": _totp_code(secret)})
    assert ok.status_code == 200 and ok.json()["mfa"] is True

    # Persisted to the DB, not just the process.
    from app.services import store
    row = store.get_user("clinician")
    assert row["twofa_secret"] == secret and row["twofa_confirmed"] is True

    # Simulate a restart: only the SQLite file survives. A fresh login must now be a
    # HALF session (2FA owed) because the confirmed enrollment was durably stored.
    db.reset_engine_for_tests()
    auth._seeded_urls.clear()
    auth._TOTP_SECRETS.clear()
    client.cookies.clear()

    r = client.post("/api/login", json={"username": "clinician", "password": "pw123"})
    assert r.status_code == 200
    body = r.json()
    assert body["authenticated"] is False and body["mfa_required"] is True
    assert client.get("/api/me").json()["mfa_enrolled"] is True
