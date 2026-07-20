# RadAssist — Pre-Deployment Checklist

Run through this **before** exposing RadAssist to the public internet or using it with
real patient data. Full technical detail and rationale for each item is in
[`SECURITY_NOTES.md`](SECURITY_NOTES.md) — this file is the short, actionable version.

None of these are fixed in code (deliberately — they're environment-specific deploy
decisions, not bugs). The app ships in an "open demo" posture by default; these steps
turn it into a gated one.

---

## ☐ 1. Turn authentication on

The single biggest gap: `AUTH_ENABLED` and `ACCESS_CODE` both **default OFF**. One
missing env var = a fully open app ingesting medical images with no login.

- [ ] Set `AUTH_ENABLED=1`
- [ ] Configure real user credentials (see `app/auth.py` for how accounts are set up)
- [ ] Set `SESSION_SECRET` to a strong, persistent secret (an unset one is regenerated
      on every restart, silently logging everyone out)
- [ ] Optionally also set `ACCESS_CODE` as a second gate on PHI-adjacent routes
- [ ] Pin `ALLOWED_ORIGINS` to your real frontend origin(s) — never leave it as `*`
- [ ] Set `TRUSTED_PROXY_HOPS` to match your actual reverse-proxy depth (wrong value
      breaks IP-based rate limiting; see `SECURITY_NOTES.md` #7)

## ☐ 2. Decide how to handle burned-in pixel PHI

De-identification today only scrubs DICOM **header** tags. If a name, MRN, or DOB is
burned into the image **pixels** (common on secondary-capture/scanner-exported films),
it is NOT removed and will appear in any rendered slice PNG.

- [ ] Confirm whether your real source images can contain burned-in pixel PHI (ask your
      imaging source / PACS export process)
- [ ] If yes: do not deploy with real patient films until one of these lands —
      (a) an OCR/inpaint pass over the image margins before rendering, or
      (b) a hard quarantine on any file with `BurnedInAnnotation == YES`
- [ ] If no (e.g. all inputs are freshly exported clean DICOM): document that
      assumption and proceed, but keep the `⚠ Burned-in: UNKNOWN/YES` warning visible
      in the UI — it's the only signal a reviewer currently has

## ☐ 3. Other deploy-time items worth a deliberate decision

- [ ] **Multi-tenant isolation** — stored analyses/images are currently one shared pool
      keyed by unguessable ids (not exploitable as-is, but there's no per-user
      ownership check). Fine for a single-clinic/demo deployment; revisit if this
      becomes a multi-tenant SaaS.
- [ ] **Storage is ephemeral** — uploads/heatmaps/segments are TTL-purged
      (`STORAGE_TTL_SECONDS`, default 6h) and are NOT a durability guarantee. Don't
      treat this box as a PACS or long-term record store.
- [ ] **HTTPS/TLS** — confirmed terminated in front of the app (the security headers
      assume it; `Strict-Transport-Security` is sent unconditionally).
- [ ] Re-run `pytest` and confirm all tests pass on the exact commit being deployed.

---

**Do not skip #1 and #2 if real patient data is involved.** Everything else is
lower-severity and can be revisited post-launch.
