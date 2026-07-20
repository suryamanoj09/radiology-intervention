# RadAssist — Security Notes

Record of the critical security audit (adversarial pentest, 5 lenses) and what was
fixed vs what is a deploy-time responsibility.

## Verdict (as audited)
- **RCE / auth-bypass / SQLi / pickle / path-traversal:** none found. The 12-hex id
  validation holds; `/api` auth gate is sound when enabled.
- **Unauthenticated one-request DoS:** was the standout risk — **FIXED** (see below).
- **PHI confidentiality:** the `/static` image mounts were reachable without a session
  even with auth on — **FIXED** (now behind the auth gate).

## Fixed in code
| # | Issue | Fix |
|---|-------|-----|
| 1 | One crafted many-frame DICOM OOM-kills the box (unbounded per-frame loop in `build_seg_volume` / `render_series_view` / `render_view`). | Reject `NumberOfFrames > MAX_FRAMES_PER_FILE` **before** decode; cap every frame loop; render_view accounts for skipped frames arithmetically (no multi-million-iteration loop). |
| 2 | No process-wide decode concurrency / byte budget; RLE/JPEG amplification. | New `services/decode_limit.py` semaphore (`MAX_CONCURRENT_DECODES=3`) around every viewer/ROI decode; `MAX_IMAGE_PIXELS` lowered 64→25 MP (≈100 MB/file cap). |
| 3 | `/static/uploads,/heatmaps,/segments` PHI PNGs served with no auth even when `AUTH_ENABLED`. | Added those prefixes to `AuthMiddleware` protected set — a leaked image URL is no longer an unauthenticated PHI fetch. |
| 4 | Post-cap full-frame CPU loop in `render_view`. | Bounded loop + arithmetic `n_total`. |
| 5 | Disk/inode exhaustion via rendered PNGs (hourly sweep). | Sweep interval capped at 10 min. |
| 7 | Rate-limit bypass via attacker-controlled XFF when not behind a trusted proxy. | `client_ip` ignores XFF unless `TRUSTED_PROXY_HOPS > 0` (else uses the direct peer). |
| 10 | `RecursionError`/huge `shape` escaping the ROI JSON guard → 500. | Length-bound (`≤2048`) before parse + catch `RecursionError` → 422. |
| 11 | Unbounded append-only `feedback.jsonl`. | Hard size ceiling (`FEEDBACK_MAX_MB=50`); writes past it are dropped + logged. |

Tests: `tests/test_decode_limits.py` (frame reject, bounded multi-frame, ROI input guards) + existing PHI/auth/quarantine suites. **197 tests pass.**

## Deploy-time responsibilities (NOT code bugs)
- **#6 Fail-open auth default.** `AUTH_ENABLED` and `ACCESS_CODE` default OFF (the "open
  demo" posture). **Before exposing to the internet with real/PHI data, set
  `AUTH_ENABLED=1` with credentials** (and ideally `ACCESS_CODE`). Also set
  `SESSION_SECRET`, pin `ALLOWED_ORIGINS` (no `*`), and set `TRUSTED_PROXY_HOPS` to your
  actual proxy depth.
- **#8 No per-user tenancy isolation.** Stored analyses/images are a single shared pool
  keyed by unguessable 48-bit ids (rate-limited, no listing endpoint) — not exploitable
  today, but any future id leak/listing becomes cross-patient. Bind records to the
  session `sub` if multi-tenant isolation is required.
- **#9 Burned-in pixel PHI.** Header de-ID only; burned-in name/MRN in pixels persists
  into served PNGs. `BurnedInAnnotation` is surfaced as a warning. A real deployment
  needs an OCR/inpaint margin pass or a `BurnedInAnnotation==YES` quarantine.
- **#12 Segmentation watchdog.** `SEGMENT_TIMEOUT_SECONDS` is advisory; the opt-in
  segment/detect job has no hard interrupt. Only relevant when those default-off
  features are enabled.
- **#13 CSP `style-src 'unsafe-inline'`** is retained deliberately — React inline
  `style={{}}` props require it and `script-src` stays `'self'` (no live XSS sink).

## Secrets & configuration (WF-security core)

Three hardenings landed here. All are **gated so the zero-config demo is unchanged**
(no `DATABASE_URL` ⇒ stateless, in-memory, exactly as before).

### Required secrets / env
| Var | When required | Purpose | If unset |
|-----|---------------|---------|----------|
| `SESSION_SECRET` | **Mandatory in prod** (`AUTH_ENABLED=1` or `REQUIRE_STRONG_SECRETS=1`/`PROD=1`) | HMAC signing key for session cookies (the trust anchor) | **Fail-closed: startup raises.** In the open demo (`AUTH_ENABLED=0`) a per-process **ephemeral** key is minted with a one-time WARNING (logins don't survive a restart). |
| `ENCRYPTION_KEY` | Optional | Fernet key source for 2FA-secret encryption at rest | Falls back to deriving the key from `SESSION_SECRET` (HKDF-SHA256). |
| `DATABASE_URL` | Optional (off = demo) | Enables persistence (users/2FA/feedback/audit **and** server-side sessions) | DB layer stays fully dormant; app is stateless. |
| `AUTH_USERS` / `AUTH_USERNAME`+`AUTH_PASSWORD_SHA256` | With `AUTH_ENABLED=1` | Credentials (scrypt/sha256 hashes; no plaintext in code) | Every login fails (logged error). |
| `AUTH_ADMINS` | Optional | Comma-separated usernames granted `role=admin` (session management) | No admins; the admin endpoints 403. |

A **weak** `SESSION_SECRET` = blank, a known dev-default (`changeme`, `dev`, …), or
`< 32` chars. Generate one with
`python -c "import secrets; print(secrets.token_urlsafe(48))"`.

### 1. Fail-closed on a weak signing secret (`app/auth.py`)
`_resolve_session_secret()` raises at import in a production posture if the secret is
weak; the demo keeps the ephemeral-key convenience. No deploy can ship a default key.

### 2. DB-backed session revocation (`sessions` table)
Stateless signed cookies can't be force-revoked. When the DB is on, each session `sid`
(already carried in the signed cookie) is recorded server-side and checked by
`AuthMiddleware`. **Logout revokes** the current sid; an **admin can list/kill** any
session. Endpoints (auth-gated + `role==admin`): `GET /api/admin/sessions`,
`POST /api/admin/sessions/revoke` (`{sid}` or `{username}`). A revoked/unknown sid on a
protected path ⇒ `401 session_revoked`. DB off ⇒ check skipped (stateless as today).

### 3. Encryption at rest for the 2FA secret (`app/services/store.py`)
`users.twofa_secret` (a TOTP bearer credential) is **Fernet-encrypted** on write and
decrypted on read at the store boundary — the stored column is `enc:`-marked ciphertext,
never the base32 secret; `auth.py` still handles plaintext. Wrong key ⇒ fail-closed
(secret treated as absent, no bypass). Legacy/ENV-seeded plaintext is read back verbatim.
Depends on `cryptography` (pinned); on a broken install it logs a one-time warning and
stores plaintext (documented gap — **no fabricated encryption claim**).

Tests: `tests/test_secrets_posture.py`, `tests/test_session_revocation.py`,
`tests/test_twofa_encryption.py` — **286 tests pass in both DB modes.**

## Dropped as non-issues
Deterministic content-hash job cache (needs a SHA-256 collision to cross-contaminate);
DOMPurify CVE in jsPDF (vulnerable `doc.html()` path never called — still worth
upgrading jsPDF to 3.x); CORS `*` methods/headers (no `allow_credentials`, no cookie
state cross-origin).
