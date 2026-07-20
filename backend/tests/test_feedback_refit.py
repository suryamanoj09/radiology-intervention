"""The feedback loop: dismiss/confirm feedback -> per-label threshold proposals."""
from validation.refit_from_feedback import aggregate, propose_thresholds


def _events(label, confirmed, dismissed):
    return ([{"raw_label": label, "event": "confirmed"}] * confirmed
            + [{"raw_label": label, "event": "dismissed"}] * dismissed)


def test_aggregate_counts_per_label():
    agg = aggregate(_events("Pneumonia", 3, 5) + _events("Effusion", 4, 0))
    assert agg["Pneumonia"] == {"confirmed": 3, "dismissed": 5}
    assert agg["Effusion"] == {"confirmed": 4, "dismissed": 0}


def test_frequently_dismissed_label_raises_threshold():
    # 2 confirmed / 8 dismissed -> precision 0.2 -> raise the threshold (flag less).
    p = propose_thresholds(_events("Nodule", 2, 8), current={"Nodule": 0.5}, default_threshold=0.5)
    assert "Nodule" in p and p["Nodule"]["to"] > p["Nodule"]["from"]
    assert "raise" in p["Nodule"]["reason"]


def test_reliable_label_lowers_threshold():
    # 9 confirmed / 1 dismissed -> precision 0.9 -> may lower (flag a touch more).
    p = propose_thresholds(_events("Effusion", 9, 1), current={"Effusion": 0.5}, default_threshold=0.5)
    assert "Effusion" in p and p["Effusion"]["to"] < p["Effusion"]["from"]


def test_too_few_events_no_change():
    assert propose_thresholds(_events("Mass", 1, 2), current={}, default_threshold=0.5) == {}


def test_thresholds_stay_bounded():
    # A label already at the ceiling that keeps getting dismissed is not pushed past _MAX_T.
    p = propose_thresholds(_events("Nodule", 0, 20), current={"Nodule": 0.9}, default_threshold=0.5)
    assert "Nodule" not in p or p["Nodule"]["to"] <= 0.9
