"""Completeness / 'detect missing findings': an AI-flagged pathology the clinician
neither confirmed nor mentioned must surface as a discordance WARN."""


def test_unconfirmed_flagged_finding_produces_discordance_warn(client):
    payload = {
        "structured": {},  # nothing confirmed, no free text
        "vision_findings": [
            {"label": "Effusion", "probability": 0.82, "flagged": True}
        ],
    }
    r = client.post("/api/completeness-check", json=payload)
    assert r.status_code == 200, r.text
    items = r.json()

    discordance = [i for i in items if i["category"] == "discordance"]
    assert discordance, f"expected a discordance item, got {items}"
    item = discordance[0]
    assert item["severity"] == "warn"
    assert item["label"] == "Effusion"
    assert "confirm" in item["message"].lower()


def test_confirmed_finding_does_not_trigger_discordance(client):
    # Same AI flag, but the clinician confirmed it -> no discordance for effusion.
    payload = {
        "structured": {"pleural_effusion": True, "effusion_side": "right"},
        "vision_findings": [
            {"label": "Effusion", "probability": 0.82, "flagged": True}
        ],
    }
    r = client.post("/api/completeness-check", json=payload)
    items = r.json()
    effusion_discordance = [
        i for i in items
        if i["category"] == "discordance" and i["label"] == "Effusion"
    ]
    assert not effusion_discordance, f"unexpected discordance: {effusion_discordance}"


def test_unflagged_finding_is_not_discordance(client):
    # Below the flag threshold: no discordance warn (may be borderline info at most).
    payload = {
        "structured": {},
        "vision_findings": [
            {"label": "Effusion", "probability": 0.20, "flagged": False}
        ],
    }
    r = client.post("/api/completeness-check", json=payload)
    items = r.json()
    assert not [i for i in items if i["category"] == "discordance"]
