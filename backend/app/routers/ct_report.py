"""CT/MRI research report endpoints (#9 / WF7).

POST /api/ct-report  — build a research report for a CT study
POST /api/mr-report  — build a research report for an MR study

The report is a SUMMARY of clinician-CONFIRMED research candidates + anatomy
measurements — NOT a diagnosis, NOT triage, NOT a calibrated probability. The builder
is deterministic (services/ct_report.py) and runs a server-side guard that REFUSES to
emit any diagnostic/probability language. This path never runs detection and never
touches the chest X-ray analyze path.
"""
from fastapi import APIRouter, HTTPException

from ..models.ct_report import CtReportRequest, CtReportResponse
from ..services import ct_report as ct_report_service

router = APIRouter(prefix="/api", tags=["ct-report"])


def _build(req: CtReportRequest, modality: str) -> CtReportResponse:
    req.modality = modality                     # endpoint forces modality; body ignored
    try:
        return ct_report_service.build_ct_report(req)
    except ct_report_service.CtReportUnsafe as e:
        # The guard tripped — refuse to emit rather than return unsafe framing.
        raise HTTPException(500, f"Report refused by safety guard: {e}")


@router.post("/ct-report", response_model=CtReportResponse)
def ct_report(req: CtReportRequest):
    return _build(req, "CT")


@router.post("/mr-report", response_model=CtReportResponse)
def mr_report(req: CtReportRequest):
    return _build(req, "MR")
