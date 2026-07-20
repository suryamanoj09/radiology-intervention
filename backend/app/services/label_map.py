"""Single source of truth mapping vision-model labels to the structured findings
vocabulary, plus free-text synonyms. Used by the frontend prefill, the
completeness checker, and the report templates so they can never drift apart.
"""

# Vision label -> structured findings key.
LABEL_TO_KEY = {
    "Nodule": "nodule_present",
    "Mass": "nodule_present",
    "Lung Lesion": "nodule_present",
    "Effusion": "pleural_effusion",
    "Pneumothorax": "pneumothorax",
    "Consolidation": "consolidation",
    "Pneumonia": "consolidation",
    "Infiltration": "consolidation",
    "Lung Opacity": "consolidation",
    "Cardiomegaly": "cardiomegaly",
    "Enlarged Cardiomediastinum": "cardiomegaly",
    "Fracture": "rib_fracture",
}

# Structured key -> words that count as "addressed in free text".
KEY_SYNONYMS = {
    "nodule_present": ["nodule", "mass", "lesion"],
    "pleural_effusion": ["effusion", "fluid"],
    "pneumothorax": ["pneumothorax", "ptx"],
    "consolidation": ["consolidation", "opacity", "pneumonia", "infiltrate", "infiltration", "airspace"],
    "cardiomegaly": ["cardiomegaly", "enlarged heart", "cardiac silhouette", "heart size"],
    "rib_fracture": ["fracture", "rib"],
}

# UNIQUE, faithful display name per RAW model label (one-to-one; asserted in tests
# to equal model.pathologies exactly and to have no duplicate values). A display
# name may only GENERALIZE, never SPECIALIZE: the generic CheXpert `Fracture` is
# "Fracture (site unspecified)", NEVER "Rib fracture".
RAW_DISPLAY = {
    "Atelectasis": "Atelectasis",
    "Consolidation": "Consolidation",
    "Infiltration": "Infiltration",
    "Pneumothorax": "Pneumothorax",
    "Edema": "Pulmonary edema",
    "Emphysema": "Emphysema",
    "Fibrosis": "Fibrosis",
    "Effusion": "Pleural effusion",
    "Pneumonia": "Pneumonia",
    "Pleural_Thickening": "Pleural thickening",
    "Cardiomegaly": "Cardiomegaly",
    "Nodule": "Nodule",
    "Mass": "Mass",
    "Hernia": "Hernia",
    "Lung Lesion": "Lung lesion",
    "Fracture": "Fracture (site unspecified)",
    "Lung Opacity": "Lung opacity",
    "Enlarged Cardiomediastinum": "Enlarged cardiomediastinum",
}


def raw_display(label: str) -> str:
    return RAW_DISPLAY.get(label, label)


# Human-readable name per structured key (for the CONFIRMED structured form only).
KEY_DISPLAY = {
    "nodule_present": "pulmonary nodule/mass",
    "pleural_effusion": "pleural effusion",
    "pneumothorax": "pneumothorax",
    "consolidation": "consolidation/opacity",
    "cardiomegaly": "enlarged cardiac silhouette",
    "rib_fracture": "rib fracture",
}


def key_for_label(label: str) -> str | None:
    return LABEL_TO_KEY.get(label)


def mentioned_in_text(key: str, text: str) -> bool:
    t = (text or "").lower()
    return any(syn in t for syn in KEY_SYNONYMS.get(key, []))


# NOTE: an earlier group_flagged() collapsed distinct raw labels (e.g. Pneumonia +
# Lung Opacity) into one "display" card. That is the exact T1 anti-pattern — the
# display layer must never merge two things the model reports separately — so it was
# removed. Surfacing is now one card PER RAW LABEL (RAW_DISPLAY / distinctFlagged),
# never grouped by a fabricated shared display name.
