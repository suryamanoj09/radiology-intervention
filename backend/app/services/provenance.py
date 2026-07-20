"""Generation-time provenance invariant.

The strong version of "we caught the hallucination": a clinical sentence may not
assert a MEASUREMENT that no confirmed structured field backs. The template path
is clean by construction (it only prints structured data); this guard exists for
the optional LLM path, whose prose could invent "a 12 mm nodule" out of nothing.
A violating draft is rejected (the caller falls back to the deterministic
template), so a fabricated measurement is structurally unable to reach the report.
"""
import re

from ..models.schemas import StructuredFindings

# A size expressed in mm/cm. Percentages (model confidence) and years are ignored.
_SIZE_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(mm|cm|millimet(?:er|re)s?|centimet(?:er|re)s?)\b",
                      re.IGNORECASE)


def measurement_violations(clinical_text: str, structured: StructuredFindings) -> list[str]:
    """Measurements in the prose with NO backing clinician-entered size field.

    The only clinician-measured size in the confirmed schema is nodule_size_mm, so
    ANY size in the text requires that field to be set. Returns human-readable
    violations; empty list == clean."""
    if not clinical_text:
        return []
    backed = structured.nodule_size_mm is not None
    if backed:
        return []
    return [f"unbacked measurement '{m.group(0).strip()}' — no clinician-entered size"
            for m in _SIZE_RE.finditer(clinical_text)]


def is_backed(clinical_text: str, structured: StructuredFindings) -> bool:
    return not measurement_violations(clinical_text, structured)
