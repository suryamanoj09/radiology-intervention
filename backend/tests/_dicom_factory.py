"""Synthetic DICOM builders for the segmentation test suite.

No network, no real weights, no real PHI. Every builder embeds obviously-fake
identifiers (DOE^JOHN / SECRET123) so the PHI-scrub tests can assert they are gone.
"""
import io

import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import (CTImageStorage, ExplicitVRLittleEndian, MRImageStorage,
                         SecondaryCaptureImageStorage, generate_uid)


def _write(ds) -> bytes:
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    b = io.BytesIO()
    pydicom.dcmwrite(b, ds, write_like_original=False)
    return b.getvalue()


def _base(ds, sop, modality, size, name, pid):
    ds.file_meta = FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = sop
    ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.SOPClassUID = sop
    ds.Modality = modality
    ds.PatientName = name
    ds.PatientID = pid
    ds.Rows = size
    ds.Columns = size
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"


def ct_slice(z, series_uid, size=48, name="DOE^JOHN", pid="SECRET123",
             spacing=(1.0, 1.0), z_spacing=2.0):
    """A CT slice with air background + a soft-tissue block, a fat block, and a bone
    core — distinct HU bands the labeler must separate. Stored pixel = HU + 1024."""
    ds = Dataset()
    _base(ds, CTImageStorage, "CT", size, name, pid)
    ds.PixelRepresentation = 1
    ds.SeriesInstanceUID = series_uid
    ds.RescaleSlope = 1
    ds.RescaleIntercept = -1024
    ds.PixelSpacing = [float(spacing[0]), float(spacing[1])]
    ds.SliceThickness = float(z_spacing)
    ds.SpacingBetweenSlices = float(z_spacing)
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.ImagePositionPatient = [0, 0, float(z)]
    arr = np.full((size, size), -1000 + 1024, np.int16)  # air
    arr[8:40, 8:40] = 50 + 1024      # soft tissue
    arr[14:34, 14:34] = -70 + 1024   # fat
    arr[20:28, 20:28] = 800 + 1024   # cortical bone
    ds.PixelData = arr.astype("<i2").tobytes()
    return _write(ds)


def mr_slice(z, series_uid, size=48, name="DOE^JOHN", pid="SECRET123"):
    """An MR slice (arbitrary a.u.) with a bright central blob on a dim field."""
    ds = Dataset()
    _base(ds, MRImageStorage, "MR", size, name, pid)
    ds.PixelRepresentation = 0
    ds.SeriesInstanceUID = series_uid
    ds.FrameOfReferenceUID = "1.2.3"
    ds.RepetitionTime = 500
    ds.EchoTime = 15
    ds.ScanningSequence = "SE"
    ds.PixelSpacing = [1.0, 1.0]
    ds.SliceThickness = 3.0
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.ImagePositionPatient = [0, 0, float(z)]
    arr = np.full((size, size), 100, np.uint16)
    arr[10:38, 10:38] = 500
    arr[18:30, 18:30] = 1200
    ds.PixelData = arr.astype("<u2").tobytes()
    return _write(ds)


def secondary_capture(size=48, name="DOE^JOHN", pid="SECRET123"):
    """A Secondary-Capture screenshot (burned-in PHI risk) that must be quarantined."""
    ds = Dataset()
    _base(ds, SecondaryCaptureImageStorage, "OT", size, name, pid)
    ds.PixelRepresentation = 0
    arr = np.full((size, size), 800, np.uint16)
    ds.PixelData = arr.astype("<u2").tobytes()
    return _write(ds)


def ct_chest_slice(z, series_uid, size=64, nodule=False, name="DOE^JOHN", pid="SECRET123",
                   z_spacing=3.0):
    """A chest-CT slice: outside air, a soft-tissue body, two internal lungs, and an
    optional compact soft-tissue nodule in the left lung. Stored pixel = HU + 1024."""
    ds = Dataset()
    _base(ds, CTImageStorage, "CT", size, name, pid)
    ds.PixelRepresentation = 1
    ds.SeriesInstanceUID = series_uid
    ds.RescaleSlope = 1
    ds.RescaleIntercept = -1024
    ds.PixelSpacing = [1.0, 1.0]
    ds.SliceThickness = float(z_spacing)
    ds.SpacingBetweenSlices = float(z_spacing)
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.ImagePositionPatient = [0, 0, float(z)]
    hu = np.full((size, size), -1000, np.int16)      # outside-body air
    hu[8:56, 8:56] = -30                              # body (soft tissue)
    hu[16:48, 16:30] = -800                           # left lung
    hu[16:48, 34:48] = -800                           # right lung
    if nodule:
        hu[26:34, 20:26] = 50                         # compact nodule in the left lung
    ds.PixelData = (hu + 1024).astype("<i2").tobytes()
    return _write(ds)


def ct_chest_series(n=14, size=64, with_nodule=True):
    suid = generate_uid()
    lo, hi = n // 2 - 2, n // 2 + 2                    # nodule on the middle slices only
    return [ct_chest_slice(z, suid, size=size, nodule=(with_nodule and lo <= z <= hi))
            for z in range(n)]


def ct_series(n=5, size=48, **kw):
    suid = generate_uid()
    return [ct_slice(z, suid, size=size, **kw) for z in range(n)]


def mr_series(n=5, size=48, **kw):
    suid = generate_uid()
    return [mr_slice(z, suid, size=size, **kw) for z in range(n)]


def as_upload(blobs, prefix="s"):
    """Wrap raw DICOM bytes as multipart ('files', (name, bytes, mime)) tuples."""
    return [("files", (f"{prefix}{i}.dcm", b, "application/dicom")) for i, b in enumerate(blobs)]


def _poll(client, path_prefix, job_id, tries=40):
    import time
    res = None
    for _ in range(tries):
        res = client.get(f"{path_prefix}/{job_id}").json()
        if res.get("status") in ("done", "error"):
            return res
        time.sleep(0.05)
    return res


def poll_segment(client, job_id, tries=40):
    """Poll a segment job to a terminal state. (TestClient runs the background task
    synchronously after the POST, so this usually returns 'done' on the first GET.)"""
    return _poll(client, "/api/segment", job_id, tries)


def poll_detect(client, job_id, tries=40):
    """Poll a research-CADe (ct-detect) job to a terminal state."""
    return _poll(client, "/api/ct-detect", job_id, tries)


def enable_segmentation(monkeypatch, ct=True, mr=True):
    """Flip the opt-in flags for a test (read at call time by the route handlers)."""
    from app import config
    monkeypatch.setattr(config, "SEGMENT_ENABLED", ct)
    monkeypatch.setattr(config, "MR_SEGMENT_ENABLED", mr)
