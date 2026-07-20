# Demo login — test credentials

RadAssist runs as an **open demo by default** (no login). To experience the real
sign-in flow (login → optional 2FA → console, with a real signed session cookie),
turn on **demo mode**, which enables the auth gate and seeds a published demo user.

## Credentials

| Field | Value |
|-------|-------|
| Username | `radiologist` |
| Password | `RadAssist-Demo-2026` |

> **Insecure by design** — these are published demo credentials for evaluation only.
> The login page shows them (with a **"Fill demo credentials"** button) and `/api/me`
> reveals them **only** in demo mode when no real users are configured.

## Run it

Enable demo mode (either copy the sample env or export the vars), then start the app:

```bash
# from the repo root
cp backend/.env.demo backend/.env          # AUTH_DEMO_MODE=1, SESSION_COOKIE_SECURE=0
# start the backend (loads backend/.env automatically)
cd backend && ./.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

Or without a file:

```bash
AUTH_DEMO_MODE=1 SESSION_COOKIE_SECURE=0 uvicorn app.main:app --reload
```

Then open the app, click **Sign in**, use **Fill demo credentials**, and sign in — you
land in the console dashboard. Everything else (worklist, upload, analyze, report)
works exactly as in the open demo, but now behind the gate.

## What demo mode does / doesn't do

- **Does:** enable the auth gate, seed the `radiologist` demo user, show + autofill the
  credentials on the login page, and exercise the full hardened auth stack (scrypt hash,
  HMAC signed-cookie session, optional TOTP 2FA, CSRF, per-account lockout, session
  rotation, DB-backed revocation when a `DATABASE_URL` is set).
- **Doesn't:** require a strong `SESSION_SECRET` — demo mode intentionally keeps the
  ephemeral-key convenience, so sessions reset on a backend restart. It does **not** put
  the app into a production posture. Set a real `SESSION_SECRET` if you want demo logins
  to survive restarts.

## Turning it off / going to production

Set `AUTH_DEMO_MODE=0` (or remove it). For a real deployment, configure real users via
`AUTH_USERS` (or `AUTH_USERNAME` + `AUTH_PASSWORD_SHA256`), set `AUTH_ENABLED=1`, and set
a strong `SESSION_SECRET` (the app fail-closes on a weak one in a production posture).
See `docs/SECURITY_SCANNING.md` and the security section of
`docs/FULLSTACK_IMPLEMENTATION_PLAN.md`.
