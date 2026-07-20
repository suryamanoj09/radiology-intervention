"""Download license-clean labeled data for the validation harness via the Kaggle API.

Needs a Kaggle API token (kaggle.json). Provide it one of two ways:
  1. Put kaggle.json at  %USERPROFILE%\\.kaggle\\kaggle.json  (Windows) or ~/.kaggle/kaggle.json, or
  2. Set env vars KAGGLE_USERNAME and KAGGLE_KEY.

Datasets (both usable behind a public demo / for measurement):
  * nih-chest-xrays/sample        — NIH ChestX-ray14 sample (~5k images) + sample_labels.csv
  * paultimothymooney/chest-xray-pneumonia (CC BY 4.0) — binary NORMAL vs PNEUMONIA
Plus BBox_list_2017.csv (localization ground truth) from the full NIH metadata.

Run:  python download_data.py
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "data"
DATA.mkdir(exist_ok=True)


def kaggle(*args):
    subprocess.run([sys.executable, "-m", "kaggle", *args], check=True)


def main():
    import importlib.util
    # NB: don't `import kaggle` here — it would shadow the kaggle() helper above.
    if importlib.util.find_spec("kaggle") is None:
        raise SystemExit("Install the client first:  pip install kaggle")

    nih = DATA / "nih-sample"
    nih.mkdir(exist_ok=True)
    print("Downloading NIH ChestX-ray14 sample ...")
    kaggle("datasets", "download", "-d", "nih-chest-xrays/sample", "-p", str(nih), "--unzip")

    print("Downloading NIH bounding-box ground truth (BBox_list_2017.csv) ...")
    # The bbox CSV ships inside the full metadata dataset; grab just that file.
    kaggle("datasets", "download", "-d", "nih-chest-xrays/data",
           "-f", "BBox_List_2017.csv", "-p", str(nih))

    pneu = DATA / "pneumonia"
    pneu.mkdir(exist_ok=True)
    print("Downloading Kermany pneumonia set ...")
    kaggle("datasets", "download", "-d", "paultimothymooney/chest-xray-pneumonia",
           "-p", str(pneu), "--unzip")

    print("Done. Data under:", DATA)


if __name__ == "__main__":
    main()
