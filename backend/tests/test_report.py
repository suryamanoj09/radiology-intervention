"""Report generation trust-chain (deterministic template path; LLM_PROVIDER=none):
differentials safety header, mandated patient closing line, disclaimer, and the
core invariant that an AI flag is NOT emitted as a clinician-confirmed finding."""

PATIENT_CLOSING = "Discuss these results with your doctor, who knows your full medical history."
DIFFERENTIALS_HEADER = "For physician review only"


def test_generator_is_template_without_llm(client):
    r = client.post("/api/generate-report", json={"structured": {"nodule_present": True}})
    assert r.status_code == 200, r.text
    assert r.json()["generator"] == "template"


def test_differentials_present_with_safety_header(client):
    r = client.post("/api/generate-report", json={"structured": {"nodule_present": True}})
    body = r.json()
    assert body["differentials"]
    assert DIFFERENTIALS_HEADER in body["differentials"]
    # Differentials come verbatim from the vetted template map.
    assert "Granuloma (prior infection)" in body["differentials"]


def test_differentials_header_present_even_with_no_findings(client):
    # Even an empty study still carries the "physician review only" framing.
    r = client.post("/api/generate-report", json={"structured": {}})
    body = r.json()
    assert DIFFERENTIALS_HEADER in body["differentials"]
    assert "no differentials suggested" in body["differentials"].lower()


def test_patient_summary_has_mandated_closing_line(client):
    r = client.post("/api/generate-report", json={"structured": {"consolidation": True}})
    assert PATIENT_CLOSING in r.json()["patient"]


def test_disclaimer_present_on_report(client):
    r = client.post("/api/generate-report", json={"structured": {}})
    body = r.json()
    assert body["disclaimer"]
    assert "not a diagnosis" in body["disclaimer"].lower()


def test_ai_flag_not_emitted_as_confirmed_when_structured_empty(client):
    # AI flags an effusion but the clinician confirmed nothing.
    payload = {
        "structured": {},
        "vision_findings": [
            {"label": "Effusion", "probability": 0.82, "flagged": True}
        ],
    }
    r = client.post("/api/generate-report", json=payload)
    body = r.json()
    clinical = body["clinical"]

    # It must appear ONLY as an unconfirmed model flag...
    assert "unconfirmed" in clinical.lower()
    # ...never promoted into the confirmed impression.
    assert "No findings confirmed by the reviewing clinician." in clinical
    # The confirmed pleura line stays negative (effusion not adopted).
    assert "No pleural effusion or pneumothorax." in clinical
    # And no differentials are suggested off an unconfirmed flag.
    assert "no differentials suggested" in body["differentials"].lower()
    # Patient summary must not claim a confirmed effusion.
    assert "No specific problems were confirmed" in body["patient"]
