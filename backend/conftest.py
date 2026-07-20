"""Root pytest fixtures for the RadAssist backend test suite.

Design goals baked in here:
  * NO torch, NO model weights, NO network. The app's import chain is already
    torch-free (every `import torch` lives inside a function), and we never enter
    the FastAPI lifespan (which would call vision_xray.warm_up -> load weights).
    We construct TestClient WITHOUT the `with` context manager on purpose.
  * Hermetic storage. STORAGE_DIR is redirected to a throwaway temp dir BEFORE
    app.config is imported, so config.py creates its uploads/heatmaps/analysis
    dirs there and the StaticFiles mounts point at the temp tree — tests never
    touch the real backend/storage.
"""

import os
import sys
import tempfile
from pathlib import Path

# --- Environment must be set BEFORE app.config is imported anywhere. ---------
_TMP_STORAGE = Path(tempfile.mkdtemp(prefix="radassist_test_storage_"))
os.environ["STORAGE_DIR"] = str(_TMP_STORAGE)
# Force the deterministic template report path (no LLM provider, no API keys).
os.environ["LLM_PROVIDER"] = "none"
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("GROQ_API_KEY", None)
# Effectively disable the per-IP rate limiter so a fast test run (many POSTs from
# the single TestClient IP) can't trip a 429 and flake the suite.
os.environ["RATE_LIMIT_MAX"] = "1000000"
# Same for the dedicated segmentation launch limiter (tests fire many seg POSTs).
os.environ["SEGMENT_RATE_LIMIT_MAX"] = "1000000"
# Keep the self-audit AUTOENCODER off in tests (no torch/weights); the gate still
# exercises the color + heuristic signals deterministically.
os.environ["SELF_AUDIT_AE"] = "0"
# Keep the anatomy segmentation model out of tests (no torch/weights).
os.environ["ANATOMY_GATE_ENABLED"] = "0"

# Make the `app` package importable no matter which dir pytest is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parent))
# Make shared test helpers (tests/_dicom_factory.py) importable as top-level modules.
sys.path.insert(0, str(Path(__file__).resolve().parent / "tests"))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PIL import Image  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def app_module():
    # Imported lazily (after env is set) so config picks up the temp STORAGE_DIR.
    from app.main import app
    return app


@pytest.fixture
def client(app_module, monkeypatch):
    """A TestClient that never triggers the lifespan warm-up.

    Not using `with TestClient(app) as client:` is deliberate — the context
    manager runs startup, which loads the DenseNet weights. We also stub warm_up
    as belt-and-suspenders in case a future test enters the context.
    """
    from app.services import vision_xray
    monkeypatch.setattr(vision_xray, "warm_up", lambda: None)
    return TestClient(app_module)


@pytest.fixture
def png_bytes() -> bytes:
    """A tiny valid grayscale PNG (real bytes, so dicom_utils.load_any -> PIL works)."""
    import io

    arr = (np.random.default_rng(0).integers(0, 255, size=(32, 32))).astype("uint8")
    buf = io.BytesIO()
    Image.fromarray(arr, mode="L").save(buf, format="PNG")
    return buf.getvalue()
