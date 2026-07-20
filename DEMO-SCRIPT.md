# Demo script (~5 minutes)

Order matters: lead with the patient summary (the novel part), show the reliable core, then
the vision assist, then be honest about limits — that reads as maturity.

## Setup (before the demo)

1. `.\start-backend.ps1` and `.\start-frontend.ps1`, open http://localhost:5173.
2. Have 2–3 sample images ready (`samples/` folder, or Open-i/NIH images).
3. Optional: put a free Gemini/Groq key in `backend/.env` for fluent reports; the template
   engine works without it.

## Script

**1. The problem (30s).** "Radiologists spend a huge share of their time writing reports,
and patients almost never get their imaging explained. RadAssist drafts the paperwork so
the radiologist just validates — and it produces a plain-English summary for the patient."

**2. Findings → report, the reliable core (90s).**
- Without uploading anything… actually upload a film first (the form needs an analysis), or
  tick findings manually: nodule 12 mm RUL + pleural effusion, history "62M, smoker".
- Click **Generate report** → walk through the three tabs:
  - *Clinical report* — standard Technique/History/Comparison/Findings/Impression skeleton.
  - **Patient summary — the star.** Read a line aloud: 8th-grade English, no jargon,
    ends by directing the patient to their doctor.
  - *Differentials* — prefixed "for physician review only".
- Edit a line, then **Export PDF** — the draft disclaimer prints on the PDF.

**3. AI assist on the image (90s).**
- Upload a chest X-ray. Point out:
  - per-pathology **model confidence** bars (say "confidence", never "diagnosis"),
  - the **heatmap toggle** — "region of model attention, not a lesion boundary",
  - the pre-filled findings form — "the AI drafts, I validate; I can untick anything",
  - the **caliper** for a real measurement,
  - dictate a sentence with the **🎙 Dictate** button.
- If a high-confidence critical finding appears, show the **priority-review banner**.

**4. Prior comparison (30s).** Upload a second film as "Prior study" → the interval-change
table (stable / new / worsened / improved / resolved) and how it flows into the report's
Comparison section.

**5. Honesty as a feature (30s).** Open the CT/MRI viewer — point out the AI channels are
opt-in and off by default, with the candidate detector marked "unvalidated research" — and open
KNOWN-LIMITATIONS.md: "We know exactly what this tool can't do — that's why every output
routes through a clinician and every screen carries the disclaimer."

## One-liners to keep handy

- "The LLM never invents findings — it only formats what the clinician confirmed."
- "The heatmap shows where the model looked, not where the disease is."
- "If everything else failed, the findings-to-report core still ships value."
