"""CT/MRI viewer: model-free by construction + memory/DoS bounds + honest windowing.

Uses tiny synthetic DICOMs (pydicom) — no network, no weights."""
import io

import numpy as np
import pydicom
import pytest
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, MRImageStorage, generate_uid

from app.services import dicom_utils


def _ct(z=0.0, size=48, modality="CT", sop=CTImageStorage):
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = sop
    ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.Modality = modality
    ds.PatientName = "DOE^JOHN"
    ds.PatientID = "SECRET123"
    ds.Rows = size
    ds.Columns = size
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 1 if modality == "CT" else 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.RescaleSlope = 1
    ds.RescaleIntercept = -1024 if modality == "CT" else 0
    ds.PixelSpacing = [0.5, 0.7]
    ds.SliceThickness = 1.0
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.ImagePositionPatient = [0, 0, float(z)]
    ds.InstanceNumber = int(z)
    if modality == "MR":
        ds.SeriesDescription = "Ax T2 FLAIR PATIENT JOHN DOE"  # free-text PHI risk -> must be scrubbed
        ds.ScanningSequence = "SE"   # coded, non-PHI -> safe to surface
        ds.SequenceVariant = "SK"
    dtype = np.int16 if modality == "CT" else np.uint16
    arr = np.full((size, size), 524, dtype)
    arr[5:15, 5:15] = 1400
    ds.PixelData = arr.tobytes()
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    b = io.BytesIO()
    pydicom.dcmwrite(b, ds, write_like_original=False)
    return b.getvalue()


def test_render_view_orders_slices_and_deidentifies():
    v = dicom_utils.render_view([_ct(2), _ct(0), _ct(1)], window="bone")
    assert v["modality"] == "CT" and v["is_ct"] is True
    assert v["n_slices"] == 3
    assert v["identifiers_removed"] >= 2  # PatientName + PatientID at least
    assert v["window"]["unit"] == "HU" and v["window"]["preset"] == "bone"


def test_render_view_downscales_large_slice_to_bound_memory():
    v = dicom_utils.render_view([_ct(0, size=2048)])
    assert max(v["images"][0].shape) <= 1024, "a huge raster must be downscaled at decode"


def test_render_view_caps_slice_count_and_reports_total():
    v = dicom_utils.render_view([_ct(i) for i in range(10)], max_slices=4)
    assert v["n_slices"] == 4
    assert v["n_slices_total"] == 10
    assert v["truncated"] is True


def test_mr_uses_percentile_never_ct_presets():
    v = dicom_utils.render_view([_ct(0, modality="MR", sop=MRImageStorage)], window="brain")
    assert v["is_mr"] is True
    assert v["window"]["unit"] == "a.u.", "MR must not claim HU"
    assert v["window"]["preset"] == "auto", "CT presets must never apply to MR"
    # Sequence hint comes from CODED tags; free-text SeriesDescription (PHI risk)
    # must be scrubbed and never surfaced.
    assert v["sequence_label"] == "SE SK"
    assert "DOE" not in v["sequence_label"] and "PATIENT" not in v["sequence_label"]


def test_dicom_view_endpoint_is_model_free_and_has_no_diagnosis_field(client):
    files = [("files", (f"s{z}.dcm", _ct(z), "application/dicom")) for z in (1, 0)]
    r = client.post("/api/dicom-view", files=files, data={"window": "brain"})
    assert r.status_code == 200, r.text
    body = r.json()
    # The whole point: NO diagnosis-shaped output on the viewer path.
    for banned in ("findings", "probability", "top_finding", "impression", "triage", "heatmap_url"):
        assert banned not in body, f"viewer response must not contain '{banned}'"
    assert body["slice_urls"] and body["disclaimer"]
    assert "no ai" in body["disclaimer"].lower()


def test_dicom_view_rejects_non_dicom(client):
    r = client.post("/api/dicom-view",
                    files=[("files", ("x.png", b"\x89PNG not dicom", "image/png"))])
    assert r.status_code == 422, r.text


def test_deid_scrubs_dates_and_overlays():
    import pydicom
    from app.services import dicom_utils
    ds = pydicom.dcmread(io.BytesIO(_ct(0)))
    ds.StudyDate = "20240101"
    ds.PatientAge = "045Y"
    ds.add_new(0x60000010, "US", 32)  # an overlay-group element
    dicom_utils._deidentify(ds)
    assert "StudyDate" not in ds and "PatientAge" not in ds
    assert not any(0x6000 <= e.tag.group <= 0x60FF for e in ds), "overlay group not scrubbed"


def _secondary_capture(size=48):
    """A Secondary-Capture screenshot (e.g. a PACS export with demographics burned
    into the pixels) — the class the single/CT viewer path must quarantine."""
    from pydicom.uid import SecondaryCaptureImageStorage
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.SOPClassUID = SecondaryCaptureImageStorage  # _is_quarantined reads this
    ds.Modality = "OT"
    ds.PatientName = "DOE^JOHN"  # would be burned into pixels on a real screenshot
    ds.Rows = size
    ds.Columns = size
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    arr = np.full((size, size), 800, np.uint16)
    ds.PixelData = arr.tobytes()
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    b = io.BytesIO()
    pydicom.dcmwrite(b, ds, write_like_original=False)
    return b.getvalue()


def test_render_view_quarantines_secondary_capture():
    # #1: the single/CT viewer path must drop a Secondary-Capture screenshot (burned-in
    # PHI risk) BEFORE decoding pixels — parity with the series/raw paths.
    v = dicom_utils.render_view([_ct(0), _secondary_capture(), _ct(1)])
    assert v["n_slices"] == 2, "the Secondary-Capture file must not be rendered"


def test_render_view_all_quarantined_raises_not_renders_phi():
    # A pure Secondary-Capture upload yields NO rendered slices (never leaks the PNG).
    with pytest.raises(ValueError):
        dicom_utils.render_view([_secondary_capture()])


def test_series_grouping_and_sequence_classification():
    from pydicom.uid import generate_uid
    from app.services import dicom_utils

    def mr(series_uid, tr, te, z):
        ds = _mk_mr(series_uid, tr, te, z)
        b = io.BytesIO(); pydicom.dcmwrite(b, ds, write_like_original=False); return b.getvalue()

    import pydicom
    t1uid, t2uid = generate_uid(), generate_uid()
    files = [mr(t1uid, 500, 15, 0), mr(t1uid, 500, 15, 1), mr(t2uid, 3000, 90, 0)]
    v = dicom_utils.render_series_view(files)
    assert len(v["series"]) == 2  # grouped by original SeriesInstanceUID (B2)
    labels = {s["inferred_label"] for s in v["series"]}
    assert labels == {"T1", "T2"}
    assert all(s["plane"] == "axial" for s in v["series"])
    assert v["identifiers_removed"] >= 1


def _mk_mr(series_uid, tr, te, z):
    import pydicom
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, MRImageStorage, generate_uid
    ds = Dataset(); ds.file_meta = FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = MRImageStorage
    ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.SOPClassUID = MRImageStorage
    ds.Modality = "MR"; ds.PatientName = "X^Y"; ds.PatientID = "P"
    ds.SeriesInstanceUID = series_uid; ds.FrameOfReferenceUID = "1.2.3"
    ds.Rows = 32; ds.Columns = 32; ds.BitsAllocated = 16; ds.BitsStored = 16; ds.HighBit = 15
    ds.PixelRepresentation = 0; ds.SamplesPerPixel = 1; ds.PhotometricInterpretation = "MONOCHROME2"
    ds.RepetitionTime = tr; ds.EchoTime = te; ds.ScanningSequence = "SE"
    ds.PixelSpacing = [1, 1]
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]; ds.ImagePositionPatient = [0, 0, float(z)]
    import numpy as np
    ds.PixelData = (np.random.RandomState(int(z)).rand(32, 32) * 1000).astype(np.uint16).tobytes()
    ds.is_little_endian = True; ds.is_implicit_VR = False
    return ds
