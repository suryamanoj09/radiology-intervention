"""Security: DoS-resistance of the DICOM decode paths (frame-count reject, bounded
frame loop) + the ROI shape input guards."""
import io

import numpy as np
import pydicom
import pytest
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

import _dicom_factory as F
from app import config
from app.services import decode_limit, dicom_utils


def _multiframe_ct(nframes=6, size=32):
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = CTImageStorage
    ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.SOPClassUID = CTImageStorage
    ds.Modality = "CT"; ds.PatientName = "X"; ds.PatientID = "Y"
    ds.SeriesInstanceUID = generate_uid()
    ds.Rows = size; ds.Columns = size; ds.NumberOfFrames = nframes
    ds.BitsAllocated = 16; ds.BitsStored = 16; ds.HighBit = 15; ds.PixelRepresentation = 1
    ds.SamplesPerPixel = 1; ds.PhotometricInterpretation = "MONOCHROME2"
    ds.RescaleSlope = 1; ds.RescaleIntercept = -1024
    ds.PixelSpacing = [1, 1]; ds.SliceThickness = 2
    arr = np.full((nframes, size, size), 40 + 1024, np.int16)
    ds.PixelData = arr.astype("<i2").tobytes()
    ds.is_little_endian = True; ds.is_implicit_VR = False
    b = io.BytesIO(); pydicom.dcmwrite(b, ds, write_like_original=False)
    return b.getvalue()


def test_multiframe_ct_renders_bounded():
    v = dicom_utils.build_seg_volume([_multiframe_ct(6)])
    assert v["n_slices"] == 6


def test_pathological_frame_count_refused(monkeypatch):
    # A file whose frame count exceeds the cap is skipped BEFORE the per-frame loop,
    # so it cannot OOM the box (the whole upload then yields no volume).
    monkeypatch.setattr(config, "MAX_FRAMES_PER_FILE", 3)
    with pytest.raises(ValueError):
        dicom_utils.build_seg_volume([_multiframe_ct(6)])


def test_config_dos_bounds_present():
    assert config.MAX_FRAMES_PER_FILE >= 1
    assert 1 <= config.MAX_CONCURRENT_DECODES <= 16
    assert config.MAX_IMAGE_PIXELS <= 25_000_000
    assert hasattr(decode_limit, "heavy")


def test_roi_shape_too_long_rejected(client):
    files = F.as_upload(F.ct_chest_series(4))
    r = client.post("/api/dicom-roi", files=files, data={"shape": "[" * 5000})
    assert r.status_code == 422


def test_roi_shape_non_dict_rejected(client):
    files = F.as_upload(F.ct_chest_series(4))
    assert client.post("/api/dicom-roi", files=files, data={"shape": "[1,2,3]"}).status_code == 422
