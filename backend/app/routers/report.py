import json

from fastapi import APIRouter

from .. import config
from ..models.schemas import CompletenessItem, ReportRequest, ReportResponse
from ..services import completeness, llm

router = APIRouter(prefix="/api", tags=["report"])


@router.get("/behavior-card")
def behavior_card():
    """Measured model performance for the trust surface. Honest 'not yet measured'
    state when no card has been generated."""
    p = config.BEHAVIOR_CARD_PATH
    if not p.exists():
        return {"available": False,
                "detail": "Model behaviour not yet measured on labeled data."}
    try:
        card = json.loads(p.read_text(encoding="utf-8"))
        card["available"] = True
        return card
    except Exception:
        return {"available": False, "detail": "Behaviour card unreadable."}


@router.post("/generate-report", response_model=ReportResponse)
def generate_report(req: ReportRequest):
    return llm.generate_report(req)


@router.post("/completeness-check", response_model=list[CompletenessItem])
def completeness_check(req: ReportRequest):
    """Standalone completeness/'detect missing findings' check for the review gate,
    without generating the full report."""
    return completeness.check(req)
