"""The license+anatomy whitelist fails CLOSED on BOTH axes (commercial_ok AND
anatomy_only), and the guard is REACHABLE at the API boundary (a disallowed task
-> 403 before any pixels are read)."""
import _dicom_factory as F
from app import config


def test_allowed_anatomy_task_passes():
    config.assert_task_allowed("total")          # Apache-2.0, anatomy-only
    config.assert_task_allowed("total_mr")
    config.assert_task_allowed("classical-hu-threshold")


def test_non_commercial_weights_are_blocked():
    for t in ("brain_aneurysm", "tissue_types", "tissue_types_mr", "heartchambers_highres",
              "coronary_arteries", "appendicular_bones", "vertebrae_body", "face"):
        try:
            config.assert_task_allowed(t)
            assert False, f"non-commercial task {t} was allowed"
        except config.ModelNotAllowed:
            pass


def test_disease_shaped_trap_tasks_are_blocked():
    # Apache-clean segmentation labels, but they read as DETECTION -> anatomy_only False.
    for t in ("cerebral_bleed", "lung_nodules", "liver_lesions", "pleural_pericard_effusion"):
        try:
            config.assert_task_allowed(t)
            assert False, f"disease-shaped task {t} was allowed"
        except config.ModelNotAllowed:
            pass


def test_unknown_task_fails_closed():
    for t in ("", "totally_made_up", "../etc/passwd"):
        try:
            config.assert_task_allowed(t)
            assert False, f"unknown task {t!r} was allowed"
        except config.ModelNotAllowed:
            pass


def test_whitelist_is_intersection_of_commercial_and_anatomy():
    for t in config.TOTALSEG_TASK_WHITELIST:
        m = config.MODEL_REGISTRY[t]
        assert m["commercial_ok"] and m["anatomy_only"]


def test_endpoint_returns_403_for_disallowed_task(client, monkeypatch):
    # The guard must be REACHABLE from the API: a disallowed task 403s BEFORE decode.
    F.enable_segmentation(monkeypatch)
    r = client.post("/api/segment", files=F.as_upload(F.ct_series(2)),
                    data={"task": "brain_aneurysm"})
    assert r.status_code == 403, r.text
