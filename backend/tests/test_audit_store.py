"""Audit logging is routed through the storage adapter.

Two paths, mutually exclusive on DATABASE_URL:
  * DB DISABLED (zero-config demo): behaves EXACTLY as before — a JSONL line is
    appended to the flat-file sink, raw IP included, and nothing touches a DB.
  * DB ENABLED: the event lands in the AuditLog table via store.add_audit, the IP
    is HASHED (never raw), and the flat file is NOT written. PHI-free by construction.
"""
import json

import pytest

from app import config, db
from app.services import audit, store


@pytest.fixture(autouse=True)
def _clean_engine(monkeypatch):
    # Start each test with the DB dormant and no cached engine, and tear the engine
    # down afterwards so a DATABASE_URL set here never leaks into the wider suite.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db.reset_engine_for_tests()
    yield
    db.reset_engine_for_tests()


# --- DB DISABLED: legacy flat-file behaviour is unchanged -------------------
def test_disabled_path_writes_flat_file_with_raw_ip(tmp_path, monkeypatch):
    sink = tmp_path / "audit.jsonl"
    monkeypatch.setattr(audit, "_SINK", sink)
    monkeypatch.setattr(config, "AUDIT_ENABLED", True)

    assert not db.is_enabled()
    audit.log_event("alice", "GET", "/v1/whoami", "203.0.113.7", 200)

    lines = sink.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["user"] == "alice"
    assert rec["resource"] == "/v1/whoami"
    assert rec["status"] == 200
    # Legacy flat file keeps the raw IP + status exactly as before (unchanged demo).
    assert rec["ip"] == "203.0.113.7"


def test_disabled_path_respects_audit_enabled_flag(tmp_path, monkeypatch):
    sink = tmp_path / "audit.jsonl"
    monkeypatch.setattr(audit, "_SINK", sink)
    monkeypatch.setattr(config, "AUDIT_ENABLED", False)

    audit.log_event("bob", "POST", "/v1/segment/abc", "203.0.113.7", 200)
    assert not sink.exists()  # disabled => no write, as today


# --- DB ENABLED: routed through the adapter, IP hashed, no flat file --------
def _enable_db(tmp_path, monkeypatch):
    dbfile = tmp_path / "audit_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{dbfile.as_posix()}")
    db.reset_engine_for_tests()
    assert db.init_db() is True


def test_enabled_path_writes_to_audit_table_and_hashes_ip(tmp_path, monkeypatch):
    _enable_db(tmp_path, monkeypatch)
    # Point the flat-file sink somewhere we can prove it is NOT written.
    sink = tmp_path / "audit.jsonl"
    monkeypatch.setattr(audit, "_SINK", sink)
    monkeypatch.setattr(config, "AUDIT_ENABLED", True)

    audit.log_event("alice", "segment", "/v1/segment/deadbeef", "198.51.100.9", 200)

    rows = store.list_audit()
    assert len(rows) == 1
    r = rows[0]
    assert r["actor"] == "alice"
    assert r["action"] == "segment"
    assert r["path"] == "/v1/segment/deadbeef"
    # created_at is an ISO-8601 string per the store contract.
    assert isinstance(r["created_at"], str) and "T" in r["created_at"]

    # IP is HASHED, never raw: no substring of the address survives, and the digest
    # is a 64-char hex HMAC-SHA256.
    assert r["ip_hash"] and r["ip_hash"] != "198.51.100.9"
    assert "198.51.100.9" not in r["ip_hash"]
    assert len(r["ip_hash"]) == 64
    int(r["ip_hash"], 16)  # valid hex

    # The flat file must NOT be touched when the DB owns the audit trail.
    assert not sink.exists()


def test_enabled_ip_hash_is_deterministic_and_distinguishes_ips(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "fixed-test-secret")
    _enable_db(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "AUDIT_ENABLED", True)

    audit.log_event("u1", "detect", "/v1/detect/1", "10.0.0.1", 200)
    audit.log_event("u2", "detect", "/v1/detect/2", "10.0.0.1", 200)
    audit.log_event("u3", "detect", "/v1/detect/3", "10.0.0.2", 200)

    rows = {r["actor"]: r["ip_hash"] for r in store.list_audit()}
    # Same IP -> same hash (stable); different IP -> different hash.
    assert rows["u1"] == rows["u2"]
    assert rows["u1"] != rows["u3"]


def test_enabled_audit_disabled_flag_writes_nothing(tmp_path, monkeypatch):
    _enable_db(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "AUDIT_ENABLED", False)

    audit.log_event("alice", "GET", "/v1/whoami", "198.51.100.9", 200)
    assert store.list_audit() == []


def test_enabled_db_write_failure_never_raises(tmp_path, monkeypatch):
    _enable_db(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "AUDIT_ENABLED", True)

    def _boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(store, "add_audit", _boom)
    # A durable-store failure is swallowed so it cannot break the audited request.
    audit.log_event("alice", "GET", "/v1/whoami", "198.51.100.9", 200)
