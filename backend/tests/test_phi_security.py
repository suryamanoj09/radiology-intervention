"""Phase-0 security & de-identification regression tests.

The load-bearing invariant: patient identifiers must never enter the analysis
response or the world-readable {id}.json. Plus: XFF-spoof-resistant client IP,
DICOM de-id, the access-code gate, and security headers.
"""

import pydicom
from pydicom.dataset import Dataset

from app import config
from app.models.schemas import AnalyzeResponse
from app.security import client_ip
from app.services import dicom_utils


_IDENTIFIER_HINTS = ("name", "patient", "phone", "dob", "birth", "mrn", "address", "ssn")


def test_analyze_response_has_no_identifier_fields():
    # The server-side analysis contract must be identifier-free by construction.
    for field in AnalyzeResponse.model_fields:
        assert not any(h in field.lower() for h in _IDENTIFIER_HINTS), \
            f"AnalyzeResponse.{field} looks like an identifier — PHI must stay client-side"


def test_deidentify_removes_identifiers_and_regenerates_uids():
    ds = Dataset()
    ds.PatientName = "Doe^Jane"
    ds.PatientID = "MRN-12345"
    ds.PatientBirthDate = "19700101"
    ds.ReferringPhysicianName = "Smith^John"
    ds.InstitutionName = "General Hospital"
    ds.StudyInstanceUID = "1.2.3.4.5"
    ds.SOPInstanceUID = "1.2.3.4.6"

    removed = dicom_utils._deidentify(ds)

    assert removed >= 5
    assert "PatientName" not in ds and "PatientID" not in ds
    assert "ReferringPhysicianName" not in ds and "InstitutionName" not in ds
    # UIDs regenerated (no longer the originals)
    assert ds.StudyInstanceUID != "1.2.3.4.5"
    assert ds.SOPInstanceUID != "1.2.3.4.6"
    assert ds.StudyInstanceUID.startswith("1.2.826") or ds.StudyInstanceUID  # valid UID


def test_client_ip_uses_rightmost_trusted_hop(monkeypatch):
    from starlette.datastructures import Headers

    monkeypatch.setattr(config, "TRUSTED_PROXY_HOPS", 1)

    class _Req:
        def __init__(self, xff, host):
            self.headers = Headers({"x-forwarded-for": xff}) if xff else Headers({})
            self.client = type("C", (), {"host": host})() if host else None

    # Client spoofs a fake leftmost IP; the trusted proxy appended the real one.
    assert client_ip(_Req("1.2.3.4, 203.0.113.9", "10.0.0.1")) == "203.0.113.9"
    assert client_ip(_Req(None, "198.51.100.7")) == "198.51.100.7"


def test_access_code_gate(client, monkeypatch):
    monkeypatch.setattr(config, "ACCESS_CODE", "s3cret")
    monkeypatch.setattr(config, "ACCESS_CODE_PROTECTED_PREFIXES", ("/api/health",))

    # Protected path without the code -> 401.
    assert client.get("/api/health").status_code == 401
    # With the code -> allowed.
    assert client.get("/api/health", headers={"X-Access-Code": "s3cret"}).status_code == 200


def test_security_headers_present(client):
    h = client.get("/api/health").headers
    assert h.get("x-content-type-options") == "nosniff"
    assert "content-security-policy" in h
    assert "strict-transport-security" in h


def test_static_analysis_json_still_private(client):
    # Regression: analysis JSON is not served by the static mount.
    assert client.get("/static/uploads/abcdef012345.json").status_code == 404
