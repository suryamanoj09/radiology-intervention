"""Per-modality / per-view report behaviour (issue #4) and 'regenerate does
nothing' root-cause (issue #8).

What the backend guarantees TODAY (regression guards):
  * the requested modality/technique string flows into the report TECHNIQUE line
    verbatim (PA vs AP vs lateral vs a CT technique string a clinician typed);
  * confirmed cardiomegaly surfaces the AP-projection magnification caveat in the
    differentials (the one place the template is view-aware);
  * the template path is fully DETERMINISTIC — identical input => byte-identical
    output — which is exactly why a UI 'Regenerate' that re-POSTs the same payload
    appears to 'do nothing'. This test pins that so any future non-determinism is
    a conscious change, and the UX fix (vary only under an LLM, or message the
    user) is tracked against it.
"""


def test_technique_line_reflects_requested_modality(client):
    for modality in ("Chest X-ray (PA)", "Chest X-ray (AP)", "Chest X-ray (Lateral)"):
        r = client.post("/api/generate-report",
                        json={"modality": modality, "structured": {}})
        assert r.status_code == 200, r.text
        assert f"TECHNIQUE: {modality}." in r.json()["clinical"]


def test_default_modality_is_pa(client):
    r = client.post("/api/generate-report", json={"structured": {}})
    assert "TECHNIQUE: Chest X-ray (PA)." in r.json()["clinical"]


def test_cardiomegaly_differentials_flag_ap_magnification(client):
    r = client.post("/api/generate-report",
                    json={"modality": "Chest X-ray (AP)",
                          "structured": {"cardiomegaly": True}})
    diff = r.json()["differentials"]
    assert "Cardiomegaly" in diff
    # View-aware safety note: an AP film magnifies the heart shadow.
    assert "AP projection magnification" in diff


def test_template_report_is_deterministic_across_regenerate(client):
    payload = {"modality": "Chest X-ray (PA)",
               "structured": {"consolidation": True, "consolidation_location": "RLL"},
               "vision_findings": [{"label": "Pneumonia", "probability": 0.66, "flagged": True}]}
    a = client.post("/api/generate-report", json=payload).json()
    b = client.post("/api/generate-report", json=payload).json()
    # Root cause of 'Regenerate does nothing': the template path is pure.
    assert a["clinical"] == b["clinical"]
    assert a["patient"] == b["patient"]
    assert a["differentials"] == b["differentials"]
    assert a["generator"] == b["generator"] == "template"
