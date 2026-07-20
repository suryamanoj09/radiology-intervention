"""DICOM and image loading with windowing.

Accepts PNG/JPG for frictionless demos and DICOM as the real-world path.
Returns an 8-bit grayscale array plus pixel spacing (mm/px) when available.
"""

import io

import numpy as np
from PIL import Image

from .. import config

# Decompression-bomb backstop: PIL raises DecompressionBombError past ~2x this
# value. We also range-check dimensions explicitly below and surface every
# oversize case as a clean ValueError (mapped to HTTP 400 by the router).
Image.MAX_IMAGE_PIXELS = config.MAX_IMAGE_PIXELS


def _window(arr: np.ndarray, center: float, width: float) -> np.ndarray:
    lo, hi = center - width / 2.0, center + width / 2.0
    arr = np.clip(arr.astype(np.float32), lo, hi)
    return ((arr - lo) / max(hi - lo, 1e-6) * 255.0).astype(np.uint8)


# CT window/level presets as (center=WL, width=WW) in HOUNSFIELD UNITS. `bone` is
# kept at its historical (600, 2800) value (temporal-bone) for backward compat;
# `skeletal` is the general-bone window. Presets are starting points — the viewer
# also lets the user hand-tune WL/WW. NEVER applied to MR (arbitrary intensity).
CT_PRESETS = {
    "brain": (40, 80),        # routine head
    "stroke": (35, 30),       # early infarct / grey-white differentiation
    "subdural": (75, 215),
    "bone": (600, 2800),      # temporal bone / high detail (stable key)
    "skeletal": (400, 1800),  # general skeletal
    "lung": (-600, 1500),
    "mediastinum": (50, 350), # a.k.a. soft tissue (chest)
    "abdomen": (40, 400),     # abdominal soft tissue (distinct from mediastinum)
    "liver": (30, 150),
    "angio": (200, 700),      # CTA / arterial, operator-tunable
}


def _flt(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _is_color(ds) -> bool:
    photometric = str(getattr(ds, "PhotometricInterpretation", "") or "")
    samples = int(getattr(ds, "SamplesPerPixel", 1) or 1)
    return samples >= 3 or photometric.startswith(("RGB", "YBR", "PALETTE"))


def _slice_position(ds) -> float:
    """Signed slice position along the acquisition normal, for GEOMETRIC ordering
    of a series (InstanceNumber/SliceLocation are optional and can be reversed).
    n = row_cosines × col_cosines; position = ImagePositionPatient · n. Falls back
    to SliceLocation then InstanceNumber."""
    try:
        iop = [float(x) for x in ds.ImageOrientationPatient]
        ipp = [float(x) for x in ds.ImagePositionPatient]
        rc, cc = np.array(iop[:3]), np.array(iop[3:6])
        n = np.cross(rc, cc)
        return float(np.dot(np.array(ipp), n))
    except Exception:
        pass
    for attr in ("SliceLocation", "InstanceNumber"):
        v = _flt(getattr(ds, attr, None))
        if v is not None:
            return v
    return 0.0


def _seq_label(ds) -> str:
    """Advisory MR sequence hint from CODED (non-PHI) tags only — ScanningSequence
    (0018,0020) and SequenceVariant (0018,0021) are controlled enums (SE/GR/IR/EP…),
    never free text, so no technologist-typed identifier can leak here. Shown as
    'auto-detected, verify', never authoritative. The free-text SeriesDescription/
    ProtocolName/SequenceName are scrubbed by _deidentify and never read."""
    parts = []
    for attr in ("ScanningSequence", "SequenceVariant"):
        v = getattr(ds, attr, None)
        if v is None:
            continue
        codes = list(v) if isinstance(v, (list, tuple)) or hasattr(v, "__iter__") and not isinstance(v, str) else [v]
        for c in codes:
            c = str(c).strip()
            if c and c not in parts:
                parts.append(c)
    return " ".join(parts)


_LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float32)


def _to_2d(ds, arr: np.ndarray) -> np.ndarray:
    """Reduce a DICOM pixel array to a single 2-D grayscale plane.

    Multi-frame series -> middle frame; RGB/YBR color -> luminance. Anything
    still not 2-D raises ValueError (surfaced as a clear 400 by the router).
    """
    if arr.ndim == 2:
        return arr
    photometric = str(getattr(ds, "PhotometricInterpretation", "") or "")
    samples = int(getattr(ds, "SamplesPerPixel", 1) or 1)
    is_color = samples >= 3 or photometric.startswith(("RGB", "YBR", "PALETTE"))
    if arr.ndim == 3:
        if is_color and arr.shape[-1] in (3, 4):
            return arr[..., :3] @ _LUMA  # (H, W, C) color -> luminance
        return arr[arr.shape[0] // 2]  # (frames, H, W) grayscale -> middle frame
    if arr.ndim == 4:  # (frames, H, W, C)
        return arr[arr.shape[0] // 2][..., :3] @ _LUMA
    raise ValueError("Unsupported DICOM pixel data; expected a 2-D grayscale image.")


# Direct identifiers (PS3.15 Table E.1-1 subset) scrubbed at ingest. Burned-in
# PIXEL text is NOT removed by this — that's disclosed as a limitation.
_IDENTIFIER_KEYWORDS = [
    "PatientName", "PatientID", "PatientBirthDate", "PatientAddress",
    "PatientTelephoneNumbers", "OtherPatientIDs", "OtherPatientNames",
    "OtherPatientIDsSequence", "PatientMotherBirthName", "AccessionNumber",
    "ReferringPhysicianName", "PerformingPhysicianName", "OperatorsName",
    "NameOfPhysiciansReadingStudy", "RequestingPhysician",
    "InstitutionName", "InstitutionAddress", "InstitutionalDepartmentName",
    "StationName", "StudyID", "IssuerOfPatientID",
    # Free-text DESCRIPTOR tags (PS3.15 Annex E "Clean Descriptors"): technologists
    # routinely type patient names/MRNs here, so they are scrubbed rather than ever
    # surfaced in a response. The sequence hint is instead derived from CODED tags.
    "SeriesDescription", "ProtocolName", "SequenceName", "StudyDescription",
    "ImageComments", "StudyComments", "SeriesComments", "PerformedProcedureStepDescription",
    # Dates/ages are quasi-identifiers (Safe-Harbor): scrub acquisition dates/times
    # and any exact age/size/weight. StudyDate etc. are removed rather than shifted
    # (a demo viewer needs none of them).
    "StudyDate", "SeriesDate", "AcquisitionDate", "ContentDate", "OverlayDate",
    "StudyTime", "SeriesTime", "AcquisitionTime", "ContentTime",
    "PatientAge", "PatientSize", "PatientWeight", "PatientSex",
    "DeviceSerialNumber", "PatientBirthTime",
]


def _deidentify(ds) -> int:
    """Remove direct identifiers + quasi-identifiers + overlay data, regenerate UIDs,
    in place. Returns the count of non-empty identifier tags removed."""
    import pydicom

    removed = 0
    for kw in _IDENTIFIER_KEYWORDS:
        if kw in ds:
            val = ds.get(kw, None)
            if val not in (None, "", [], b""):
                removed += 1
            try:
                delattr(ds, kw)
            except Exception:
                pass
    # Overlay planes (groups 0x6000-0x60FF) can carry burned-in graphics / PHI text.
    # Remove every element in those repeating groups.
    try:
        for elem in list(ds):
            if 0x6000 <= elem.tag.group <= 0x60FF:
                del ds[elem.tag]
                removed += 1
    except Exception:
        pass
    for kw in ("StudyInstanceUID", "SeriesInstanceUID", "SOPInstanceUID"):
        if kw in ds:
            try:
                setattr(ds, kw, pydicom.uid.generate_uid())
            except Exception:
                pass
    try:
        ds.remove_private_tags()  # private tags can hide identifiers
    except Exception:
        pass
    return removed


# SOP Class UIDs to QUARANTINE from the viewer: Secondary Capture (often a
# screenshot with burned-in demographics) and structured dose reports.
_QUARANTINE_SOP = {
    "1.2.840.10008.5.1.4.1.1.7",       # Secondary Capture Image Storage
    "1.2.840.10008.5.1.4.1.1.7.1",     # Multi-frame SC (single bit)
    "1.2.840.10008.5.1.4.1.1.7.2",     # Multi-frame SC (grayscale byte)
    "1.2.840.10008.5.1.4.1.1.7.3",     # Multi-frame SC (grayscale word)
    "1.2.840.10008.5.1.4.1.1.7.4",     # Multi-frame SC (true color)
    "1.2.840.10008.5.1.4.1.1.88.67",   # X-Ray Radiation Dose SR
    "1.2.840.10008.5.1.4.1.1.66",      # Raw Data
}


def _is_quarantined(ds) -> bool:
    sop = str(getattr(ds, "SOPClassUID", "") or "")
    if sop in _QUARANTINE_SOP:
        return True
    # Heuristic: a SECONDARY / DERIVED screenshot with no geometry.
    it = [str(x).upper() for x in (getattr(ds, "ImageType", []) or [])]
    return "SECONDARY" in it and "ImageOrientationPatient" not in ds


def load_dicom(data: bytes, window: str | None = None):
    """Return (img8, pixel_spacing_mm, modality, meta) from DICOM bytes.

    window: None → use file's WindowCenter/Width or min-max;
            'brain' | 'subdural' | 'bone' → CT presets.
    """
    import pydicom

    ds = pydicom.dcmread(io.BytesIO(data))
    # De-identify BEFORE any use/display/storage. We never persist the raw DICOM
    # (only a rendered PNG), but scrub in memory as belt-and-suspenders and to
    # report how many identifiers were present.
    identifiers_removed = _deidentify(ds) if config.DEIDENTIFY_DICOM else 0
    # Bound decoded pixel work before touching ds.pixel_array (which decodes the
    # full raster). A tiny DICOM header can still claim an enormous frame.
    rows = int(getattr(ds, "Rows", 0) or 0)
    cols = int(getattr(ds, "Columns", 0) or 0)
    frames = int(getattr(ds, "NumberOfFrames", 1) or 1)
    samples = int(getattr(ds, "SamplesPerPixel", 1) or 1)  # colour decodes 3x
    if rows * cols * max(frames, 1) * max(samples, 1) > config.MAX_IMAGE_PIXELS:
        raise ValueError(
            "DICOM pixel data is too large to process safely "
            f"({rows}x{cols}x{frames}x{samples} exceeds the "
            f"{config.MAX_IMAGE_PIXELS}px limit)."
        )
    arr = _to_2d(ds, np.asarray(ds.pixel_array, dtype=np.float32))

    slope = float(getattr(ds, "RescaleSlope", 1) or 1)
    intercept = float(getattr(ds, "RescaleIntercept", 0) or 0)
    arr = arr * slope + intercept

    if window in CT_PRESETS:
        center, width = CT_PRESETS[window]
    else:
        center, width = _file_window(ds, arr)

    img8 = _window(arr, center, width)

    if getattr(ds, "PhotometricInterpretation", "") == "MONOCHROME1":
        img8 = 255 - img8

    # PixelSpacing is [row, col] (mm/px). Carry BOTH so area/anisotropic math is
    # correct; `spacing` stays the row scalar for backward compat (the Viewer
    # caliper reads pixel_spacing_mm). spacing_col falls back to row when the tag
    # is a single value.
    spacing = None
    spacing_col = None
    for attr in ("PixelSpacing", "ImagerPixelSpacing"):
        val = getattr(ds, attr, None)
        if val:
            try:
                spacing = float(val[0])
                spacing_col = float(val[1]) if len(val) > 1 else float(val[0])
                break
            except (TypeError, ValueError, IndexError):
                continue

    modality = str(getattr(ds, "Modality", "OT") or "OT")
    meta = {
        "study_date": str(getattr(ds, "StudyDate", "") or ""),
        "body_part": str(getattr(ds, "BodyPartExamined", "") or ""),
        "identifiers_removed": identifiers_removed,
        "spacing_col": spacing_col,
        "view_position": str(getattr(ds, "ViewPosition", "") or ""),
    }
    return img8, spacing, modality, meta


def _file_window(ds, arr: np.ndarray) -> tuple[float, float]:
    center = getattr(ds, "WindowCenter", None)
    width = getattr(ds, "WindowWidth", None)
    try:
        if center is not None and width is not None:
            if hasattr(center, "__iter__") and not isinstance(center, str):
                center = center[0]
            if hasattr(width, "__iter__") and not isinstance(width, str):
                width = width[0]
            return float(center), float(width)
    except (TypeError, ValueError):
        pass
    lo, hi = float(arr.min()), float(arr.max())
    return (lo + hi) / 2.0, max(hi - lo, 1.0)


def load_any(data: bytes, filename: str, window: str | None = None):
    """Load DICOM or PNG/JPG. Returns (img8, pixel_spacing_mm, modality, source_format, meta)."""
    name = (filename or "").lower()
    is_dicom = name.endswith((".dcm", ".dicom")) or data[128:132] == b"DICM"
    if is_dicom:
        img8, spacing, modality, meta = load_dicom(data, window)
        return img8, spacing, modality, "dicom", meta

    try:
        img = Image.open(io.BytesIO(data))
        w, h = img.size
        if w * h > config.MAX_IMAGE_PIXELS:
            raise ValueError(
                "Image is too large to process safely "
                f"({w}x{h}px exceeds the {config.MAX_IMAGE_PIXELS}px limit)."
            )
        # Color saturation BEFORE grayscale conversion is a strong OOD signal for
        # the self-audit gate (radiographs are grayscale; photos/screenshots aren't).
        color_saturation = _mean_saturation(img)
        img = img.convert("L")
    except Image.DecompressionBombError:
        raise ValueError(
            "Image is too large to process safely (possible decompression bomb)."
        )
    return np.array(img, dtype=np.uint8), None, "CR", "image", {"color_saturation": color_saturation}


def _mean_saturation(img) -> float:
    """Mean per-pixel saturation in [0,1]; 0 for a grayscale image."""
    if img.mode in ("L", "1", "I", "F", "I;16"):
        return 0.0
    small = img.convert("RGB").resize((64, 64))
    arr = np.asarray(small, dtype=np.float32)
    mx = arr.max(axis=2)
    mn = arr.min(axis=2)
    sat = (mx - mn) / (mx + 1e-6)
    return float(sat.mean())


def _downscale(arr: np.ndarray, max_edge: int) -> np.ndarray:
    """Downscale a 2-D float slice so its longest edge <= max_edge, bounding memory
    regardless of the source raster size. No-op when already small enough."""
    h, w = arr.shape[:2]
    longest = max(h, w)
    if longest <= max_edge:
        return arr
    scale = max_edge / float(longest)
    new = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
    return np.asarray(Image.fromarray(arr).resize(new, Image.BILINEAR), dtype=np.float32)


import hashlib as _hashlib
import secrets as _secrets
_SERIES_SALT = _secrets.token_hex(8)  # per-process; makes UID hashes opaque/unlinkable


def _opaque(uid: str) -> str:
    """Stable, opaque, non-reversible id for a UID (grouping key without leaking it)."""
    if not uid:
        return "nogeom"
    return _hashlib.sha1((_SERIES_SALT + str(uid)).encode("utf-8")).hexdigest()[:12]


def _plane_of(ds) -> str:
    """axial | sagittal | coronal | oblique from ImageOrientationPatient (pure geometry)."""
    try:
        iop = [float(x) for x in ds.ImageOrientationPatient]
        r, c = np.array(iop[:3]), np.array(iop[3:6])
        n = np.abs(np.cross(r, c))
        ax = int(np.argmax(n))
        # oblique if the dominant axis isn't clearly dominant
        if n[ax] < 0.8:
            return "oblique"
        return ["sagittal", "coronal", "axial"][ax]
    except Exception:
        return "unknown"


def _first_bval(ds):
    for attr in ("DiffusionBValue",):
        v = _flt(getattr(ds, attr, None))
        if v is not None:
            return v
    return None


def _classify_sequence(ds) -> tuple[str, float]:
    """(label, confidence) from CODED/numeric tags ONLY (never scrubbed free text).
    Weak by design — 'auto — verify'. IR could be FLAIR or STIR, etc."""
    tr = _flt(getattr(ds, "RepetitionTime", None))
    te = _flt(getattr(ds, "EchoTime", None))
    ti = _flt(getattr(ds, "InversionTime", None))
    scan = [str(x).upper() for x in (getattr(ds, "ScanningSequence", []) or [])]
    itype = [str(x).upper() for x in (getattr(ds, "ImageType", []) or [])]
    bval = _first_bval(ds)
    contrast = bool(str(getattr(ds, "ContrastBolusAgent", "") or "").strip())
    if any("ADC" in x for x in itype):
        return "ADC", 0.6
    if "EP" in scan and bval is not None and bval > 0:
        return "DWI", 0.6
    if "IR" in scan and ti is not None:
        return ("STIR", 0.5) if ti < 500 else ("FLAIR", 0.5)
    if tr is not None and te is not None:
        if tr < 800 and te < 30:
            return ("T1C" if contrast else "T1"), 0.5
        if tr > 2000 and te > 80:
            return "T2", 0.5
    return "MR", 0.2


def render_series_view(files: list[bytes], window: str | None = None) -> dict:
    """MRI/CT SERIES viewer (T-MRI + B2): group files by the ORIGINAL
    SeriesInstanceUID captured BEFORE de-ID regenerates it, classify each series by
    coded tags, detect plane, order slices geometrically, and return a series[]
    array. Secondary-capture / dose-report SOP classes are quarantined (not shown).
    Model-free; no diagnosis-shaped field."""
    import pydicom
    groups: dict[str, dict] = {}
    n_ident = 0
    burned = "NO"
    n_quarantined = 0
    for data in files:
        try:
            ds = pydicom.dcmread(io.BytesIO(data))
        except Exception:
            continue
        if _is_quarantined(ds):
            n_quarantined += 1
            continue
        rows = int(getattr(ds, "Rows", 0) or 0)
        cols = int(getattr(ds, "Columns", 0) or 0)
        frames = int(getattr(ds, "NumberOfFrames", 1) or 1)
        samples = int(getattr(ds, "SamplesPerPixel", 1) or 1)
        if rows * cols * max(frames, 1) * max(samples, 1) > config.MAX_IMAGE_PIXELS:
            continue
        if frames > config.MAX_FRAMES_PER_FILE:
            continue  # refuse a pathological multi-frame count before decoding it
        # B2: capture original UIDs BEFORE de-ID regenerates them.
        orig_series_uid = str(getattr(ds, "SeriesInstanceUID", "") or "")
        forf = str(getattr(ds, "FrameOfReferenceUID", "") or "")
        modality = str(getattr(ds, "Modality", "OT") or "OT").upper()
        seq_label, seq_conf = _classify_sequence(ds)
        plane = _plane_of(ds)
        te = _flt(getattr(ds, "EchoTime", None))
        bval = _first_bval(ds)
        pos = _slice_position(ds)
        is_mono1 = str(getattr(ds, "PhotometricInterpretation", "") or "") == "MONOCHROME1"
        slope = float(getattr(ds, "RescaleSlope", 1) or 1)
        intercept = float(getattr(ds, "RescaleIntercept", 0) or 0)
        bia = str(getattr(ds, "BurnedInAnnotation", "") or "").upper()
        if bia == "YES":
            burned = "YES"
        elif not bia and burned != "YES":
            burned = "UNKNOWN"
        n_ident += _deidentify(ds) if config.DEIDENTIFY_DICOM else 0

        sid = _opaque(orig_series_uid)
        g = groups.setdefault(sid, {
            "series_id": sid, "modality": modality, "is_mr": modality in ("MR", "MRI"),
            "inferred_label": seq_label, "label_basis": "coded-tags", "label_confidence": seq_conf,
            "sequence_source": "coded-tags", "plane": plane,
            "frame_of_reference_uid": _opaque(forf),
            "slices": [], "meta": _capture_view_meta(ds),
        })
        raw = np.asarray(ds.pixel_array, dtype=np.float32)
        if raw.ndim == 3 and not _is_color(ds):
            for i in range(min(raw.shape[0], config.MAX_FRAMES_PER_FILE)):  # bounded frame loop
                g["slices"].append((float(i), _downscale(raw[i] * slope + intercept, config.VIEW_MAX_EDGE), is_mono1, te, bval))
        else:
            g["slices"].append((pos, _downscale(_to_2d(ds, raw) * slope + intercept, config.VIEW_MAX_EDGE), is_mono1, te, bval))
        del ds, raw

    if not groups:
        raise ValueError("No displayable series (all files were quarantined or unreadable).")

    series_out = []
    for sid, g in groups.items():
        g["slices"].sort(key=lambda t: t[0])
        cap = config.VIEW_MAX_SLICES
        slices = g["slices"][:cap]
        is_ct = g["modality"] == "CT"
        arrs = [s[1] for s in slices]
        if is_ct and window in CT_PRESETS:
            center, width = CT_PRESETS[window]
            wmeta = {"preset": window, "center": center, "width": width, "unit": "HU"}
        elif is_ct:
            mid = arrs[len(arrs) // 2]
            center, width = _file_window_from_arr(g["meta"], mid)
            wmeta = {"preset": None, "center": center, "width": width, "unit": "HU"}
        else:
            sample = np.concatenate([a.ravel()[::7] for a in arrs])
            sample = sample[np.isfinite(sample)]
            lo, hi = float(np.percentile(sample, 1)), float(np.percentile(sample, 99))
            center, width = (lo + hi) / 2.0, max(hi - lo, 1.0)
            wmeta = {"preset": "auto", "center": round(center, 1), "width": round(width, 1), "unit": "a.u."}
        images = []
        for (_k, arr, is_mono1, _te, _bv) in slices:
            img8 = _window(arr, center, width)
            if is_mono1:
                img8 = 255 - img8
            images.append(img8)
        m = g["meta"]
        orig_long = max(m.get("orig_rows", 0), m.get("orig_cols", 0))
        rend_long = max(images[0].shape) if images else 0
        rs = (rend_long / orig_long) if (orig_long and rend_long) else 1.0
        series_out.append({
            "series_id": sid, "modality": g["modality"], "is_mr": g["is_mr"],
            "inferred_label": g["inferred_label"], "label_basis": g["label_basis"],
            "label_confidence": g["label_confidence"], "sequence_source": g["sequence_source"],
            "plane": g["plane"], "frame_of_reference_uid": g["frame_of_reference_uid"],
            "n_slices": len(images), "n_slices_total": len(g["slices"]),
            "truncated": len(g["slices"]) > len(images),
            "_images": images,  # router saves + serves; stripped from the JSON
            "slice_positions": [round(float(s[0]), 3) for s in slices],
            "echo_times": [s[3] for s in slices if s[3] is not None][:1],
            "b_values": sorted({s[4] for s in slices if s[4] is not None}),
            "window": wmeta,
            "spacing_mm": round(m["spacing"] / rs, 5) if m.get("spacing") and rs else m.get("spacing"),
            "spacing_col_mm": round(m["spacing_col"] / rs, 5) if m.get("spacing_col") and rs else m.get("spacing_col"),
            "render_scale": round(rs, 5),
        })
    # DWI/ADC pairing by shared frame-of-reference.
    pairs = []
    for a in series_out:
        if a["inferred_label"] != "DWI":
            continue
        for b in series_out:
            if b["inferred_label"] == "ADC" and b["frame_of_reference_uid"] == a["frame_of_reference_uid"]:
                pairs.append({"dwi_series_id": a["series_id"], "adc_series_id": b["series_id"]})
                break
    return {
        "series": series_out, "pairs": pairs,
        "identifiers_removed": n_ident, "burned_in": burned,
        "n_quarantined": n_quarantined,
    }


def raw_slice_payload(files: list[bytes]) -> dict:
    """VOLUME-PIVOT FOUNDATION: instead of a baked 8-bit PNG, ship the RAW rescaled
    intensity of a series' middle slice (int16, base64) + a manifest, so the browser
    can do TRUE window/level on a <canvas> LUT (no clipped 8-bit, no server round-trip
    per window). This is the transport the full canvas/MPR viewer is built on."""
    import base64
    import pydicom
    groups: dict[str, list] = {}
    for data in files:
        try:
            ds = pydicom.dcmread(io.BytesIO(data))
        except Exception:
            continue
        if _is_quarantined(ds):
            continue
        rows = int(getattr(ds, "Rows", 0) or 0)
        cols = int(getattr(ds, "Columns", 0) or 0)
        frames = int(getattr(ds, "NumberOfFrames", 1) or 1)
        samples = int(getattr(ds, "SamplesPerPixel", 1) or 1)
        if rows * cols * max(frames, 1) * max(samples, 1) > config.MAX_IMAGE_PIXELS:
            continue
        if frames > config.MAX_FRAMES_PER_FILE:
            continue
        uid = str(getattr(ds, "SeriesInstanceUID", "") or "")
        slope = float(getattr(ds, "RescaleSlope", 1) or 1)
        intercept = float(getattr(ds, "RescaleIntercept", 0) or 0)
        is_ct = str(getattr(ds, "Modality", "") or "").upper() == "CT"
        meta = _capture_view_meta(ds)
        raw = np.asarray(ds.pixel_array, dtype=np.float32)
        arr = _downscale(_to_2d(ds, raw) * slope + intercept, config.VIEW_MAX_EDGE)
        groups.setdefault(uid, []).append((_slice_position(ds), arr, is_ct, meta))
        del ds, raw
    if not groups:
        raise ValueError("No raw slices available.")
    uid = max(groups, key=lambda k: len(groups[k]))
    g = sorted(groups[uid], key=lambda t: t[0])
    _pos, arr, is_ct, meta = g[len(g) // 2]
    a16 = np.clip(np.round(arr), -32768, 32767).astype("<i2")
    orig_long = max(meta.get("orig_rows", 0), meta.get("orig_cols", 0))
    rend_long = max(arr.shape)
    rs = (rend_long / orig_long) if (orig_long and rend_long) else 1.0
    sp = meta.get("spacing")
    return {
        "rows": int(arr.shape[0]), "cols": int(arr.shape[1]),
        "min": float(arr.min()), "max": float(arr.max()),
        "unit": "HU" if is_ct else "a.u.",
        "default_center": (40 if is_ct else float((arr.min() + arr.max()) / 2)),
        "default_width": (400 if is_ct else float(max(arr.max() - arr.min(), 1))),
        "spacing_mm": round(sp / rs, 5) if (sp and rs) else sp,
        "n_slices_in_series": len(g),
        "data_b64": base64.b64encode(a16.tobytes()).decode("ascii"),
    }


def consensus_modality(files: list[bytes]) -> tuple[str, bool]:
    """Header-only (NO pixel decode) consensus Modality + a `mixed` flag, so the
    segment router can refuse a wrong-modality upload BEFORE any pixels are read
    (a head CT can never be silently MR-segmented and vice versa)."""
    import pydicom
    mods: list[str] = []
    for data in files:
        try:
            ds = pydicom.dcmread(io.BytesIO(data), stop_before_pixels=True)
        except Exception:
            continue
        # Quarantined files (Secondary-Capture / dose reports) are dropped before
        # segmentation, so they must NOT vote on modality — otherwise a normal study
        # (a CT series + a dose-report SC) would look "mixed" and be refused.
        if _is_quarantined(ds):
            continue
        m = str(getattr(ds, "Modality", "") or "").upper()
        if m:
            mods.append(m)
    if not mods:
        return "", False
    consensus = max(set(mods), key=mods.count)
    return consensus, len(set(mods)) > 1


def build_seg_volume(files: list[bytes], series_id: str | None = None) -> dict:
    """Extract ONE ordered int16 intensity VOLUME (Z,H,W) for anatomy segmentation.

    Generalises raw_slice_payload from a single middle slice to the full stacked
    series, reusing the viewer's decode / de-ID / quarantine / downscale / ordering
    spine VERBATIM: CT => HU (slope*raw + intercept); MR => a.u. De-identifies BEFORE
    any pixel use and reports identifiers_removed / n_quarantined / burned_in. Groups
    by the ORIGINAL SeriesInstanceUID (captured before de-ID); segments the requested
    `series_id` (the one the viewer displays — so the overlay can never land on a
    different series) or, when None, the series with the most slices. Returns the
    chosen `series_id` + ordered `slice_positions` so the frontend aligns the overlay
    to the viewer BY GEOMETRIC POSITION, not by array offset (the caps/downscale differ
    between the viewer and this path). Caps Z at SEGMENT_MAX_SLICES; enforces the voxel
    budget. NEVER operates on the 8-bit windowed PNGs (that step is destructive for HU)."""
    from collections import Counter

    import pydicom
    groups: dict[str, dict] = {}
    n_ident = 0
    burned = "NO"
    n_quarantined = 0
    for data in files:
        try:
            ds = pydicom.dcmread(io.BytesIO(data))
        except Exception:
            continue
        if _is_quarantined(ds):
            n_quarantined += 1
            continue
        rows = int(getattr(ds, "Rows", 0) or 0)
        cols = int(getattr(ds, "Columns", 0) or 0)
        frames = int(getattr(ds, "NumberOfFrames", 1) or 1)
        samples = int(getattr(ds, "SamplesPerPixel", 1) or 1)
        if rows * cols * max(frames, 1) * max(samples, 1) > config.MAX_IMAGE_PIXELS:
            continue
        if frames > config.MAX_FRAMES_PER_FILE:
            continue  # refuse a pathological multi-frame count before decoding it
        orig_series_uid = str(getattr(ds, "SeriesInstanceUID", "") or "")  # B2: before de-ID
        modality = str(getattr(ds, "Modality", "OT") or "OT").upper()
        slope = float(getattr(ds, "RescaleSlope", 1) or 1)
        intercept = float(getattr(ds, "RescaleIntercept", 0) or 0)
        bia = str(getattr(ds, "BurnedInAnnotation", "") or "").upper()
        if bia == "YES":
            burned = "YES"
        elif not bia and burned != "YES":
            burned = "UNKNOWN"
        meta = _capture_view_meta(ds)
        n_ident += _deidentify(ds) if config.DEIDENTIFY_DICOM else 0  # before any pixel use
        raw = np.asarray(ds.pixel_array, dtype=np.float32)
        sid = _opaque(orig_series_uid)
        g = groups.setdefault(sid, {"modality": modality, "meta": meta, "slices": [],
                                    "frame_indexed": False})
        if raw.ndim == 3 and not _is_color(ds):
            # Enhanced multi-frame: the per-slice key is a FRAME INDEX (not mm), so
            # a diff of these is unitless — z-spacing must come from tags, not the diff.
            # Cap the frame loop so a pathological many-frame file can't append millions
            # of tiny arrays and OOM the box before the between-file budget is checked.
            g["frame_indexed"] = True
            for i in range(min(raw.shape[0], config.MAX_FRAMES_PER_FILE)):
                g["slices"].append((float(i), _downscale(raw[i] * slope + intercept, config.SEGMENT_MAX_EDGE)))
        else:
            g["slices"].append((_slice_position(ds),
                                _downscale(_to_2d(ds, raw) * slope + intercept, config.SEGMENT_MAX_EDGE)))
        del ds, raw
        # Bound peak retained memory: stop decoding once we hold well over the slice
        # budget across all series (a pathological many-frame upload could otherwise
        # retain thousands of downscaled slices before the final cap is applied).
        if sum(len(g2["slices"]) for g2 in groups.values()) >= config.SEGMENT_MAX_SLICES * 4:
            break

    if not groups:
        raise ValueError("No segmentable slices (all files were quarantined or unreadable).")

    # Segment the series the viewer displays (series_id) when supplied and present;
    # else the largest series. Either way the chosen sid is returned so the frontend
    # can refuse to paint a mask onto a different series.
    if series_id and series_id in groups:
        sid = series_id
    else:
        sid = max(groups, key=lambda k: len(groups[k]["slices"]))
    g = groups[sid]
    g["slices"].sort(key=lambda t: t[0])
    slices = g["slices"][:config.SEGMENT_MAX_SLICES]
    # Keep only the modal in-plane shape (drop odd-sized slices from geometry drift).
    shape = Counter(a.shape for _p, a in slices).most_common(1)[0][0]
    kept = [(p, a) for p, a in slices if a.shape == shape]
    positions = [float(p) for p, _a in kept]
    vol = np.stack([np.clip(np.round(a), -32768, 32767).astype("<i2") for _p, a in kept], axis=0)
    if vol.size > config.SEGMENT_MAX_VOXELS:
        raise ValueError("Volume exceeds the voxel budget.")

    meta = g["meta"]
    frame_indexed = g.get("frame_indexed", False)
    modality = g["modality"]
    is_ct = modality == "CT"
    h, w = shape
    orig_long = max(meta.get("orig_rows", 0), meta.get("orig_cols", 0))
    rend_long = max(h, w)
    rs = (rend_long / orig_long) if (orig_long and rend_long) else 1.0  # effective-spacing fix (B3)
    sp, spc = meta.get("spacing"), meta.get("spacing_col")
    row_mm = (sp / rs) if (sp and rs) else sp
    col_mm = (spc / rs) if (spc and rs) else spc
    z_mm = meta.get("between") or meta.get("thickness")
    # Position-diff fallback ONLY for real geometric positions. For multi-frame the
    # positions are frame indices, so diff==1 would be mistaken for 1 mm — leave z_mm
    # None (volume_ml suppressed) rather than reporting a wrong volume.
    if not z_mm and not frame_indexed and len(positions) > 1:
        diffs = np.abs(np.diff(sorted(positions)))
        diffs = diffs[diffs > 1e-3]
        z_mm = float(np.median(diffs)) if diffs.size else None
    return {
        "hu": vol,                       # (Z,H,W) int16 — HU for CT, a.u. for MR
        "modality": modality,
        "is_ct": is_ct,
        "series_id": sid,
        "slice_positions": positions,    # ordered, aligned to the mask slice order
        "frame_indexed": frame_indexed,
        "spacing_mm": (row_mm, col_mm, z_mm),
        "unit": "HU" if is_ct else "a.u.",
        "n_slices": int(vol.shape[0]),
        "identifiers_removed": n_ident,
        "n_quarantined": n_quarantined,
        "burned_in": burned,
    }


def roi_stats(files: list[bytes], series_id: str | None, slice_position: float | None,
              shape: dict) -> dict:
    """Compute honest region statistics on the 16-bit intensity (HU for CT, a.u. for
    MR) — NEVER the 8-bit display PNG (which is window-clipped). `shape` is a rect or
    ellipse in NORMALISED [0,1] coords {type, nx, ny, nw, nh}; the slice is chosen by
    nearest geometric position so it aligns with the viewer."""
    vol = build_seg_volume(files, series_id=series_id)
    hu = vol["hu"]
    positions = vol["slice_positions"] or []
    if slice_position is not None and positions:
        z = int(np.argmin([abs(p - float(slice_position)) for p in positions]))
    else:
        z = hu.shape[0] // 2
    sl = hu[z].astype(np.float32)
    H, W = sl.shape
    nx = min(max(float(shape.get("nx", 0.0)), 0.0), 1.0)
    ny = min(max(float(shape.get("ny", 0.0)), 0.0), 1.0)
    nw = min(max(float(shape.get("nw", 0.0)), 0.0), 1.0)
    nh = min(max(float(shape.get("nh", 0.0)), 0.0), 1.0)
    x0, y0 = int(round(nx * W)), int(round(ny * H))
    x1, y1 = min(W, x0 + max(1, int(round(nw * W)))), min(H, y0 + max(1, int(round(nh * H))))
    x0, y0 = max(0, min(x0, W - 1)), max(0, min(y0, H - 1))
    if x1 <= x0 or y1 <= y0:
        raise ValueError("ROI is outside the image.")
    patch = sl[y0:y1, x0:x1]
    if str(shape.get("type", "rect")) == "ellipse":
        yy, xx = np.mgrid[0:(y1 - y0), 0:(x1 - x0)]
        cy, cx = (y1 - y0 - 1) / 2.0, (x1 - x0 - 1) / 2.0
        ry, rx = max(1.0, (y1 - y0) / 2.0), max(1.0, (x1 - x0) / 2.0)
        mask = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1.0
        region = patch[mask]
    else:
        region = patch.ravel()
    if region.size == 0:
        raise ValueError("Empty ROI.")
    row_mm, col_mm, _z = vol["spacing_mm"]
    area = float(region.size * row_mm * col_mm) if (row_mm and col_mm) else None
    return {
        "mean": round(float(region.mean()), 2), "sd": round(float(region.std()), 2),
        "min": round(float(region.min()), 1), "max": round(float(region.max()), 1),
        "n_px": int(region.size),
        "area_mm2": round(area, 1) if area is not None else None,
        "unit": vol["unit"], "slice_index": int(z),
        "series_id": vol["series_id"],
    }


def render_view(files: list[bytes], window: str | None = None,
                max_slices: int | None = None) -> dict:
    """Render a CT/MRI DICOM (single file, multi-frame, or a multi-file SERIES) for
    an HONEST no-AI viewer. Returns rendered uint8 slices (ORDERED) + technical
    metadata. NO classifier, NO Grad-CAM, NO findings — this path is model-free by
    construction so a CT/MR is never scored by the chest model.

    * CT  -> Hounsfield rescale + a window PRESET (or the file's own window).
    * MR  -> percentile window derived from the stack (arbitrary intensity; no HU,
             CT presets are never applied).

    Memory is bounded at DECODE time: each slice is downscaled to <= VIEW_MAX_EDGE
    BEFORE it is retained, no per-slice ds/pixel-array is kept (which would pin the
    full raster), and accumulation stops at max_slices. So a small compressed upload
    that decodes to gigapixels cannot OOM the Space.
    """
    import pydicom

    cap = max_slices if max_slices is not None else config.VIEW_MAX_SLICES
    # entries: (sort_key, small_float_arr, is_mono1) — NO ds retained (would pin the
    # decoded pixel array in memory).
    entries: list[tuple[float, np.ndarray, bool]] = []
    n_ident = 0
    burned = "NO"
    modalities: list[str] = []
    n_total = 0                 # slices seen (even beyond the cap), for honest reporting
    truncated_decode = False
    meta_src = {}               # spacing/thickness/seq/body_part from the first valid file

    for data in files:
        if len(entries) >= cap:
            truncated_decode = True
            # Still count remaining files' declared frames for n_total, cheaply.
            try:
                hdr = pydicom.dcmread(io.BytesIO(data), stop_before_pixels=True)
                n_total += int(getattr(hdr, "NumberOfFrames", 1) or 1)
            except Exception:
                n_total += 1
            continue

        ds = pydicom.dcmread(io.BytesIO(data))
        # Quarantine Secondary-Capture / dose-report SOP classes (often a PACS
        # screenshot with burned-in demographics) BEFORE decoding pixels — parity
        # with render_series_view / raw_slice_payload, which already do this.
        if _is_quarantined(ds):
            continue
        if config.DEIDENTIFY_DICOM:
            n_ident += _deidentify(ds)
        rows = int(getattr(ds, "Rows", 0) or 0)
        cols = int(getattr(ds, "Columns", 0) or 0)
        frames = int(getattr(ds, "NumberOfFrames", 1) or 1)
        samples = int(getattr(ds, "SamplesPerPixel", 1) or 1)  # colour decodes 3x
        if rows * cols * max(frames, 1) * max(samples, 1) > config.MAX_IMAGE_PIXELS:
            raise ValueError("DICOM pixel data is too large to process safely.")
        if frames > config.MAX_FRAMES_PER_FILE:
            continue  # refuse a pathological multi-frame count before decoding it
        modalities.append(str(getattr(ds, "Modality", "OT") or "OT").upper())
        bia = str(getattr(ds, "BurnedInAnnotation", "") or "").upper()
        if bia == "YES":
            burned = "YES"
        elif not bia and burned != "YES":
            burned = "UNKNOWN"  # tag absent -> cannot assert the pixels are clean
        slope = float(getattr(ds, "RescaleSlope", 1) or 1)
        intercept = float(getattr(ds, "RescaleIntercept", 0) or 0)
        is_mono1 = str(getattr(ds, "PhotometricInterpretation", "") or "") == "MONOCHROME1"
        if not meta_src:
            meta_src = _capture_view_meta(ds)

        raw = np.asarray(ds.pixel_array, dtype=np.float32)
        if raw.ndim == 3 and not _is_color(ds):  # multi-frame grayscale
            # Bounded loop: append at most (cap - retained) frames and account for the
            # rest ARITHMETICALLY, so a many-frame file never spins a multi-million
            # iteration Python loop (CPU DoS) even though the append is capped.
            nframes = raw.shape[0]
            take = min(nframes, max(0, cap - len(entries)))
            for i in range(take):
                small = _downscale(raw[i] * slope + intercept, config.VIEW_MAX_EDGE)
                entries.append((float(i), small, is_mono1))
            n_total += nframes
            if take < nframes:
                truncated_decode = True
        else:
            n_total += 1
            small = _downscale(_to_2d(ds, raw) * slope + intercept, config.VIEW_MAX_EDGE)
            entries.append((_slice_position(ds), small, is_mono1))
        del ds, raw  # release the full decoded raster before the next file

    if not entries:
        raise ValueError("No displayable slices in the uploaded DICOM.")
    entries.sort(key=lambda t: t[0])
    # Modality = series consensus (most common), not whichever file happened to be last.
    modality = max(set(modalities), key=modalities.count) if modalities else "OT"
    is_ct = modality == "CT"
    is_mr = modality in ("MR", "MRI")

    mid = entries[len(entries) // 2]
    if is_ct and window in CT_PRESETS:
        center, width = CT_PRESETS[window]
        wmeta = {"preset": window, "center": center, "width": width, "unit": "HU"}
    elif is_ct:
        center, width = _file_window_from_arr(meta_src, mid[1])
        wmeta = {"preset": None, "center": center, "width": width, "unit": "HU"}
    else:
        # MR / other: percentile window across the stack (robust to hot voxels);
        # arbitrary units, so never labelled HU and CT presets are ignored.
        sample = np.concatenate([e[1].ravel()[::7] for e in entries])
        sample = sample[np.isfinite(sample)]
        lo, hi = float(np.percentile(sample, 1)), float(np.percentile(sample, 99))
        center, width = (lo + hi) / 2.0, max(hi - lo, 1.0)
        wmeta = {"preset": "auto", "center": round(center, 1), "width": round(width, 1),
                 "unit": "a.u."}

    images = []
    for _key, arr, is_mono1 in entries:
        img8 = _window(arr, center, width)
        if is_mono1:
            img8 = 255 - img8
        images.append(img8)

    # B3 fix: slices were downscaled to VIEW_MAX_EDGE, so the physical size per
    # RENDERED pixel is larger than the original PixelSpacing. Scale the returned
    # spacing to the rendered raster so the client caliper measures correctly.
    orig_long = max(meta_src.get("orig_rows", 0), meta_src.get("orig_cols", 0))
    rend_long = max(images[0].shape[0], images[0].shape[1]) if images else 0
    render_scale = (rend_long / orig_long) if (orig_long and rend_long) else 1.0
    sp = meta_src.get("spacing")
    spc = meta_src.get("spacing_col")
    eff_sp = (sp / render_scale) if (sp and render_scale) else sp
    eff_spc = (spc / render_scale) if (spc and render_scale) else spc

    return {
        "modality": modality,
        "is_ct": is_ct,
        "is_mr": is_mr,
        "images": images,  # ordered list of uint8 HxW arrays; the router saves + serves them
        "n_slices": len(images),
        "n_slices_total": n_total,
        "truncated": truncated_decode,
        # Ordered geometric positions (one per rendered slice) so an anatomy overlay
        # can align to the viewer BY POSITION, not by array offset.
        "slice_positions": [float(k) for k, _a, _m in entries],
        "spacing_mm": round(eff_sp, 5) if eff_sp else eff_sp,        # EFFECTIVE (rendered-pixel)
        "spacing_col_mm": round(eff_spc, 5) if eff_spc else eff_spc,  # EFFECTIVE (rendered-pixel)
        "render_scale": round(render_scale, 5),
        "slice_thickness_mm": meta_src.get("thickness"),
        "spacing_between_mm": meta_src.get("between"),
        "identifiers_removed": n_ident,
        "burned_in": burned,  # YES | NO | UNKNOWN — residual PHI warning
        "window": wmeta,
        # Advisory MR sequence label from the DICOM's own description fields (capped;
        # shown "auto — verify"). Free text, so treated as low-trust.
        "sequence_label": (meta_src.get("seq", "") if is_mr else "")[:80],
        "body_part": meta_src.get("body_part", "")[:64],
    }


def _capture_view_meta(ds) -> dict:
    """Pull the small metadata we need out of a dataset so we never RETAIN the ds
    (its cached pixel_array would pin the full raster in memory)."""
    spacing = spacing_col = None
    for attr in ("PixelSpacing", "ImagerPixelSpacing"):
        v = getattr(ds, attr, None)
        if v:
            try:
                spacing = float(v[0])
                spacing_col = float(v[1]) if len(v) > 1 else float(v[0])
                break
            except (TypeError, ValueError, IndexError):
                continue
    return {
        "spacing": spacing,
        "spacing_col": spacing_col,
        "thickness": _flt(getattr(ds, "SliceThickness", None)),
        "between": _flt(getattr(ds, "SpacingBetweenSlices", None)),
        "seq": _seq_label(ds),
        "body_part": str(getattr(ds, "BodyPartExamined", "") or ""),
        "win_center": getattr(ds, "WindowCenter", None),
        "win_width": getattr(ds, "WindowWidth", None),
        # ORIGINAL raster size, so effective (rendered) spacing can be derived after
        # the slice is downscaled to VIEW_MAX_EDGE (bug B3: returning original
        # spacing for a downscaled image under-reports every measured distance).
        "orig_rows": int(getattr(ds, "Rows", 0) or 0),
        "orig_cols": int(getattr(ds, "Columns", 0) or 0),
    }


def _file_window_from_arr(meta_src: dict, arr: np.ndarray) -> tuple[float, float]:
    """CT file window from the captured WindowCenter/Width, else min-max of arr."""
    center, width = meta_src.get("win_center"), meta_src.get("win_width")
    try:
        if center is not None and width is not None:
            if hasattr(center, "__iter__") and not isinstance(center, str):
                center = center[0]
            if hasattr(width, "__iter__") and not isinstance(width, str):
                width = width[0]
            return float(center), float(width)
    except (TypeError, ValueError):
        pass
    lo, hi = float(arr.min()), float(arr.max())
    return (lo + hi) / 2.0, max(hi - lo, 1.0)
