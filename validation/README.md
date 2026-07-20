# Validation harness — measure behaviour, don't overclaim

This characterizes the **existing pretrained model** honestly. We do **not** train a model
(that is out of scope and, for Open-i, license-prohibited). Instead we measure detection and
region accuracy on license-clean labeled data and publish a versioned **behaviour card**, so
no performance claim in the demo is misleading.

## Datasets used (both license-clean)

- **NIH ChestX-ray14** (`nih-chest-xrays/sample` + `BBox_List_2017.csv`) — no usage
  restrictions; the 984 boxes are the only open localization ground truth.
- **Kermany pneumonia** (`paultimothymooney/chest-xray-pneumonia`) — CC BY 4.0.

MIMIC-CXR and CheXpert are deliberately **not** used here — they are credentialed and cannot
back a public demo. Open-i is not used for measurement (its images are CC BY-NC-ND).

## 1. Provide your Kaggle token

Create an API token at https://www.kaggle.com/settings → "Create New Token" (downloads
`kaggle.json`). Then either:

- **Windows:** copy it to `%USERPROFILE%\.kaggle\kaggle.json`, or
- set env vars `KAGGLE_USERNAME` and `KAGGLE_KEY`.

The token stays on your machine; it is git-ignored and never committed or bundled.

## 2. Install the client and download

```powershell
..\backend\.venv\Scripts\pip install kaggle scikit-learn
..\backend\.venv\Scripts\python download_data.py
```

## 3. Run the harness

```powershell
..\backend\.venv\Scripts\python run_validation.py --limit 800
```

Outputs `behavior_card.json` and `behavior_card.md`:

- **Detection** — per-pathology AUROC, and sensitivity/specificity at the app's flag
  threshold (0.5 banded), so you can see exactly how the shipped thresholds behave.
- **Localization** — for each NIH ground-truth box, whether the Grad-CAM attention region
  overlaps it (hit-rate) and mean IoU — a region-of-attention check, not segmentation.

## What the numbers do and don't mean

They are **engineering sanity checks** on a research model, on data it was trained on
relatives of (so optimistic/in-distribution). They are **not** clinical validation and **not**
a guarantee. That caveat is printed on the card and belongs in the demo. This is what makes
the accuracy story honest rather than misleading.
