"""Marker-ablation shortcut test.

Run the SAME chest X-ray twice — once with its burned-in corner markers intact,
once with them inpainted — and print the per-label confidence delta. If a
finding's confidence collapses when the marker disappears, the model was reading
the TEXT, not the pathology: the classic shortcut-learning failure (Zech et al.,
PLOS Medicine 2018; DeGrave et al., Nature Machine Intelligence 2021, "AI for
radiographic COVID-19 detection selects shortcuts over signal").

This is the five-minute test that turns "your model reads the marker" from an
argument into a measurement. Production analysis always runs with masking ON
(see vision_xray.analyze_xray); this tool exists to VERIFY that defence.

Usage:
    python -m tools.marker_ablation path/to/xray.png [more.png ...]
    python tools/marker_ablation.py path/to/xray.dcm

Exit code is 0 always; the table is the output. A large positive delta on
edema/effusion for a portable film is the fingerprint of the shortcut — and, with
masking working, that delta should be small.
"""
import sys
from pathlib import Path

import numpy as np

# Allow running as a bare script (python tools/marker_ablation.py ...) as well as
# a module (python -m tools.marker_ablation ...).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import vision_xray  # noqa: E402


def _load_gray_uint8(path: Path) -> np.ndarray:
    """Load PNG/JPG or DICOM to a uint8 grayscale array, matching how the app
    ingests each format (windowed for DICOM, plain grayscale for pixel images)."""
    if path.suffix.lower() in (".dcm", ".dicom"):
        from app.services import dicom_utils
        img8, _meta = dicom_utils.load_dicom(path.read_bytes())
        return img8
    from PIL import Image
    return np.asarray(Image.open(path).convert("L"), dtype=np.uint8)


def ablate(path: Path) -> None:
    img8 = _load_gray_uint8(path)

    # How many marker pixels get inpainted (on the capped working image, exactly
    # as production does), so the report states what was actually removed.
    capped, _ = vision_xray._cap_resolution(img8, None)
    _inpainted, n_px = vision_xray._mask_burned_in_markers(capped)

    intact = vision_xray.predict_probs(img8, mask_markers=False)
    masked = vision_xray.predict_probs(img8, mask_markers=True)

    labels = sorted(
        set(intact) | set(masked),
        key=lambda k: intact.get(k, 0.0) - masked.get(k, 0.0),
        reverse=True,
    )

    print(f"\n=== {path.name} ===")
    print(f"Inpainted {n_px} burned-in marker pixel(s) before the 'masked' pass.")
    print(f"{'Label':26} {'intact':>8} {'masked':>8} {'delta':>8}  shortcut?")
    print("-" * 66)
    for k in labels:
        a = intact.get(k, 0.0)
        b = masked.get(k, 0.0)
        d = a - b
        # A big drop when the marker is removed == the flag was riding on the text.
        flag = "  <== reads marker" if d >= 0.15 else ""
        print(f"{k:26} {a:8.3f} {b:8.3f} {d:+8.3f}{flag}")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 0
    for arg in argv[1:]:
        p = Path(arg)
        if not p.exists():
            print(f"skip (not found): {arg}")
            continue
        try:
            ablate(p)
        except Exception as exc:  # noqa: BLE001 — a CLI tool should report, not crash
            print(f"error on {arg}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
