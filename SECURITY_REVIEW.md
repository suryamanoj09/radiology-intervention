# Security Review — RadAssist Backend

Adversarial review across authentication/session, upload/DoS, DICOM parsing & PHI,
path traversal & file serving, injection & SSRF, and HTTP headers/secrets/CORS.
Each finding was independently verified against the code before inclusion;
speculative issues with no reachable path were dropped.

**Result:** no critical/unauthenticated cross-tenant breach on the default
deployment. One High (PHI egress) and a cluster of Medium DoS/robustness items
were **fixed**; the remainder are low-severity, gated behind the opt-in demo auth,
and documented as accepted with recommendations.

## Already done well (kept)
- Constant-time comparison (`secrets.compare_digest`) for session token + access code.
- DICOM de-identification on by default; analysis JSON in a **non-served** private dir keyed by unguessable 16-hex ids.
- Restrictive CSP (no third-party origins) + HSTS + COOP + `Referrer-Policy: no-referrer`; `/docs` off in prod.
- Per-IP rate limiting on expensive POSTs and id-enumeration GETs; per-IP login throttle.
- Decompression / pixel-count guards; **model-free CT/MRI path** (a chest model can never score a head CT).
- Filenames never build write paths (server mints token ids); id inputs regex-validated before any filesystem use.

---

## Findings & status

### HIGH

**H1 — Free-text DICOM descriptor tags egress as `sequence_label` (PHI). ✅ FIXED**
`_seq_label` concatenated `SeriesDescription`/`ProtocolName`/`SequenceName` — fields technologists routinely fill with patient names/MRNs — into the `/api/dicom-view` response, while the same response reported identifiers as removed.
*Fix:* those free-text descriptors are now scrubbed in `_deidentify` (added to the identifier list, per PS3.15 Annex E "Clean Descriptors"), and the sequence hint is derived only from **coded** tags (`ScanningSequence`/`SequenceVariant`, controlled enums — no free text). Regression test in `tests/test_viewer.py`.

### MEDIUM

**M2 — Pixel-count guard ignored `SamplesPerPixel` (3× colour undercount). ✅ FIXED**
An "allowed" 64 MP colour DICOM decoded to ~192 MP (3×). *Fix:* both guard sites (`load_dicom`, `render_view`) now multiply by `SamplesPerPixel`.

**M4 — `Content-Length` early-reject bypassed by chunked upload. ✅ FIXED**
`/api/analyze` fully buffered a chunked (no Content-Length) body before the size check. *Fix:* new `upload_guard.read_capped` reads in 1 MB chunks and aborts at the byte budget; applied to `/api/analyze`.

**M5 — `/api/analyze-study` had no early reject and no aggregate cap. ✅ FIXED**
*Fix:* early Content-Length reject against `STUDY_MAX_IMAGES × MAX_UPLOAD_BYTES` + bounded per-part reads + running aggregate cap.

**M6 — Prompt-injection: several user fields concatenated into the LLM prompt unfenced. ✅ FIXED**
`modality`, `nodule_location`, `effusion_side`, `pneumothorax_side`, `consolidation_location` (all free-text-capable) landed raw. *Fix:* `_safe()` whitelists + length-caps every inline field (free-text history/notes/comparison were already nonce-fenced). Only reachable with a provider configured (non-default); output still passes a human attestation gate.

**M1 — Client-IP keying inconsistent between auth and rate limiter. ✅ FIXED**
`auth._client_ip` hardcoded `X-Forwarded-For[-1]` and ignored `TRUSTED_PROXY_HOPS`, disagreeing with the rate limiter at hop≠1. *Fix:* auth now delegates to the shared `security.client_ip` (single derivation, honors the hop count).

**M3 — `VIEW_MAX_SLICES` doesn't bound per-file multi-frame decode. ⚠️ MITIGATED**
A multi-frame `pixel_array` decodes all frames before the slice loop. Already hard-bounded by the `MAX_IMAGE_PIXELS` (now × `SamplesPerPixel`) pre-decode guard, so a single request cannot OOM; a per-frame incremental decoder would remove the transient entirely (recommended, not yet done).

**M7 — LLM output trusted with a weak single-substring check. ⚠️ ACCEPTED (default-off) + hardened.**
The provenance invariant (see below) now also rejects fabricated measurements in the LLM prose. Recommended further: strict structural validation (reject stray delimiter residue, length cap). Reachable only with a provider configured.

**M8 — Unsalted single-round SHA-256 password hashing. ⚠️ ACCEPTED (gated).**
Reachable only via a separate env/secrets compromise; no in-app path discloses the hashes. Recommend a salted memory-hard KDF (argon2id/scrypt) before any real-auth deployment. Auth is off by default.

### LOW

**L2 — `/api/feedback` and `/api/analysis` not in `PROTECTED_PREFIXES`. ✅ FIXED** (added; enforced when `AUTH_ENABLED`).

**L3 — Access code accepted via `?access_code=` query param (log/history leak). ✅ FIXED** (header `X-Access-Code` only now).

**L1 — Stateless session token not revocable before `exp`. ⚠️ ACCEPTED** (documented tradeoff; rotate `SESSION_SECRET` to invalidate; recommend a per-user token epoch for a real deployment).

**L4 — Burned-in pixel PHI persists to publicly-served PNGs. ⚠️ MITIGATED** (the viewer surfaces a `burned_in` YES/UNKNOWN warning; automatic pixel-text removal is out of scope and disclosed).

---

## Prioritized remaining recommendations
1. (M8) Salted memory-hard password KDF before enabling auth in production.
2. (M7) Strict LLM-output structural validation + length cap.
3. (M3) Per-frame incremental multi-frame decode to remove the transient buffer.
4. (L1) Server-side session revocation (token epoch / `jti` denylist).
5. Consider narrowing PIL to an explicit allow-list of decoders (PNG/JPEG) to shrink native-decoder CVE surface.

## Fixes verified
`89 backend tests pass` after the changes, including a regression test that a free-text `SeriesDescription` carrying a name is scrubbed and never surfaced in the viewer response.
