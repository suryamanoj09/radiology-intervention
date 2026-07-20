"""Encryption at rest for users.twofa_secret (Fernet at the store boundary).

The TOTP shared secret is a bearer credential — if the DB is exfiltrated a plaintext
secret lets an attacker mint valid codes and defeat 2FA. So it is encrypted on write
and decrypted on read at app/services/store.py, leaving the rest of auth.py handling a
plain base32 string.

Only exercised when DATABASE_URL is set; the zero-config demo never stores a secret.
"""

import pytest

from app import auth, db
from app.services import store


@pytest.fixture
def db_url(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'enc.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    db.reset_engine_for_tests()
    db.init_db()
    auth._seeded_urls.clear()
    yield url
    db.reset_engine_for_tests()
    auth._seeded_urls.clear()
    monkeypatch.delenv("DATABASE_URL", raising=False)


def test_stored_column_is_ciphertext_not_base32(db_url):
    from sqlmodel import select
    from app.models.db_models import User

    secret = "JBSWY3DPEHPK3PXP"
    store.create_user("u", "scrypt$aa$bb", twofa_secret=secret, twofa_confirmed=True)

    # The raw DB column is NOT the base32 secret — it is an enc:-marked ciphertext.
    with db.get_session() as s:
        raw = s.exec(select(User).where(User.username == "u")).first().twofa_secret
    assert raw != secret
    assert raw.startswith("enc:")

    # But the store decrypts on read, so callers (auth.py) still get the plaintext.
    assert store.get_user("u")["twofa_secret"] == secret


def test_set_twofa_round_trips_through_encryption(db_url):
    store.create_user("u", "scrypt$aa$bb")
    store.set_twofa("u", "NBSWY3DPEHPK3PXQ", True)
    row = store.get_user("u")
    assert row["twofa_secret"] == "NBSWY3DPEHPK3PXQ"
    assert row["twofa_confirmed"] is True


def test_upsert_user_encrypts_secret(db_url):
    from sqlmodel import select
    from app.models.db_models import User

    store.upsert_user("u", "scrypt$aa$bb", twofa_secret="ABCDEFGHIJKLMNOP")
    with db.get_session() as s:
        raw = s.exec(select(User).where(User.username == "u")).first().twofa_secret
    assert raw.startswith("enc:") and raw != "ABCDEFGHIJKLMNOP"
    assert store.get_user("u")["twofa_secret"] == "ABCDEFGHIJKLMNOP"


def test_wrong_key_fails_to_decrypt(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "key-A-" + "x" * 40)
    store._fernet_cache.clear()
    ct = store._encrypt_secret("TOPSECRETBASE32X")
    assert ct.startswith("enc:")

    # Rotate to a DIFFERENT key: decryption must fail-closed (None), never raise or leak.
    monkeypatch.setenv("ENCRYPTION_KEY", "key-B-" + "y" * 40)
    store._fernet_cache.clear()
    assert store._decrypt_secret(ct) is None

    # The correct key still decrypts (round-trip integrity).
    monkeypatch.setenv("ENCRYPTION_KEY", "key-A-" + "x" * 40)
    store._fernet_cache.clear()
    assert store._decrypt_secret(ct) == "TOPSECRETBASE32X"


def test_legacy_plaintext_secret_passthrough():
    # A value written before encryption existed (or ENV-seeded) has no enc: marker and
    # must be returned verbatim so no historical enrollment is lost.
    assert store._decrypt_secret("PLAINBASE32SECRET") == "PLAINBASE32SECRET"
    assert store._decrypt_secret(None) is None
    assert store._encrypt_secret(None) is None


def test_encryption_derives_from_session_secret_when_no_encryption_key(db_url, monkeypatch):
    """With ENCRYPTION_KEY unset the Fernet key derives from SESSION_SECRET, so a stable
    SESSION_SECRET keeps stored 2FA secrets decryptable across the process lifetime."""
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    monkeypatch.setattr(auth, "_SECRET", "a-stable-strong-session-secret-value-123456")
    store._fernet_cache.clear()
    store.create_user("u", "scrypt$aa$bb", twofa_secret="MFRGGZDFMZTWQ2LK", twofa_confirmed=True)
    assert store.get_user("u")["twofa_secret"] == "MFRGGZDFMZTWQ2LK"
