import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from ..models.schemas import ComparisonSummary
from ..services import compare as compare_service
from ..services import vision_xray

router = APIRouter(prefix="/api", tags=["compare"])

# Same shape vision_xray.load_saved enforces. Validating at the request
# boundary rejects a malformed / path-traversal id (LFI defense) with a 422
# before it can reach the filesystem — defense in depth on top of load_saved.
_ID_RE = re.compile(r"^[0-9a-f]{12}$")


class CompareRequest(BaseModel):
    prior_image_id: str
    current_image_id: str
    prior_date: str | None = None

    @field_validator("prior_image_id", "current_image_id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        if not _ID_RE.match(v or ""):
            raise ValueError(
                "image_id must be exactly 12 lowercase hex characters")
        return v


@router.post("/compare", response_model=ComparisonSummary)
def compare_studies(req: CompareRequest):
    prior = vision_xray.load_saved(req.prior_image_id)
    current = vision_xray.load_saved(req.current_image_id)
    if not prior or not current:
        raise HTTPException(404, "One or both image ids have no stored analysis")
    return compare_service.compare(prior, current, req.prior_date)
