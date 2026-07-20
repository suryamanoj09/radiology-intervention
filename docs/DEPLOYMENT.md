# Deployment / Hosting

RadAssist ships as a single **Docker** image (multi-stage `Dockerfile` at the repo root):
stage 1 builds the React SPA, stage 2 runs FastAPI with the model weights **baked in** and the
built SPA served **same-origin** on port `7860`. Any Docker host works; the repo is pre-configured
for **Hugging Face Spaces**.

> Before hosting anything reachable by others, read [PRE_DEPLOYMENT_CHECKLIST.md](PRE_DEPLOYMENT_CHECKLIST.md)
> and set the production config below. This is a research prototype, not a certified clinical
> system — host only with public/de-identified data unless you have done your own compliance work.

---

## Option A — Hugging Face Spaces (recommended; zero extra config)

The root `README.md` front-matter (`sdk: docker`, `app_port: 7860`) is the Space config, so a
Space builds and runs the Dockerfile as-is.

1. Create a free Hugging Face account → **New Space** → **Docker** (blank template).
2. Push this repo to the Space's git remote:
   ```bash
   git init            # if not already a repo
   git add -A && git commit -m "RadAssist"
   git remote add space https://huggingface.co/spaces/<your-user>/<space-name>
   git push space main   # HF may require a write token as the git password
   ```
   (Or drag-and-drop the files in the Space's **Files** tab.)
3. The Space builds the Dockerfile (first build ~10–15 min — CPU torch + baking the pretrained
   weights) and starts the container. When it's green, the app is live at
   `https://<your-user>-<space-name>.hf.space`.
4. Set secrets/vars in **Space → Settings → Variables and secrets** (see production config below).

**Resources:** the CPU model needs ~1–2 GB RAM; the free CPU-basic tier (2 vCPU / 16 GB) is fine.
**Storage is ephemeral** on a Space (resets on rebuild/restart) — for durable users/feedback/audit
attach HF **persistent storage** or point `DATABASE_URL` at an external Postgres.

## Option B — any Docker host (Render, Fly.io, Railway, a VM, on-prem)

The same Dockerfile runs anywhere. Point the platform at the repo/Dockerfile and expose the port.

- **Render:** New → Web Service → Docker; set `PORT` (Render injects one; the CMD honours `${PORT}`).
- **Fly.io:** `fly launch` (detects the Dockerfile) → `fly deploy`; set secrets with `fly secrets set`.
- **Railway:** New Project → Deploy from repo (Docker) → add variables.
- **VM / on-prem:** `docker build -t radassist . && docker run -p 7860:7860 --env-file backend/.env radassist`
  behind a TLS reverse proxy (Caddy/nginx).

---

## Production configuration (set these before a real deploy)

| Variable | Set to | Why |
|---|---|---|
| `SESSION_SECRET` | a strong random 32+ char value (`python -c "import secrets;print(secrets.token_urlsafe(48))"`) | Signs session cookies. **Required** once `AUTH_ENABLED=1` — the app fail-closes on a weak/blank value in a production posture. |
| `AUTH_ENABLED` | `1` (+ `AUTH_USERS="name:sha256hex,..."`) | Gate the PHI-adjacent endpoints behind a login. Generate a hash: `python -c "import hashlib;print(hashlib.sha256(b'yourpassword').hexdigest())"`. Add `AUTH_ADMINS` for session-management access. |
| `SESSION_COOKIE_SECURE` | `1` | Required over HTTPS (HF/Render/Fly are HTTPS). Only set `0` for plain-http local dev. |
| `ENCRYPTION_KEY` | a strong value (optional) | Encrypts 2FA secrets at rest (falls back to a key derived from `SESSION_SECRET`). |
| `DATABASE_URL` | `postgresql://…` (or persistent sqlite) | Durable users/2FA/feedback/audit. Omit for the ephemeral zero-config demo. Run `alembic upgrade head` for Postgres. |
| `LLM_PROVIDER` (+ key) | `gemini`/`groq`/`ollama` | Optional richer report formatting. Works without it (template fallback). |
| `CORS_ORIGINS` | your domain(s) | If the SPA is served from a different origin than the API. Same-origin (the default Docker serve) needs nothing. |

**Just want a public demo with a working login?** Instead of the above, set `AUTH_DEMO_MODE=1`
(and `SESSION_COOKIE_SECURE=1` on HTTPS) — see [DEMO_LOGIN.md](DEMO_LOGIN.md). Do **not** use demo
mode for anything real.

---

## Recipe: temporary demo on your own domain (Fly.io + Cloudflare + demo login)

A throwaway ~1-month demo, gated by the published demo credentials, on `app.yourdomain.com`.
The repo already includes a ready `fly.toml` (rename `app`, pick a region).

**1. Deploy the app to Fly.io**
```bash
# one-time: install flyctl + sign in (https://fly.io/docs/flyctl/install/)
fly auth login
# from the repo root (fly.toml is here; it builds the Dockerfile):
fly launch --no-deploy        # accept the existing fly.toml; choose a unique app name + region
fly deploy                    # first build ~10-15 min (torch + baking weights)
# optional, so logins survive a restart:
fly secrets set SESSION_SECRET=$(python -c "import secrets;print(secrets.token_urlsafe(48))")
```
Now `https://<app>.fly.dev` works with the demo login (`radiologist` / `RadAssist-Demo-2026`).

**2. Attach your domain (Fly issues the TLS cert)**
```bash
fly certs add app.yourdomain.com
fly certs show app.yourdomain.com     # shows the exact DNS records to add
```

**3. Point the domain in Cloudflare**
In the Cloudflare dashboard → your domain → **DNS** → add the record Fly showed, typically:
- `CNAME  app  <app>.fly.dev`  — **set the proxy to DNS-only (grey cloud)** so Fly's cert
  validates cleanly (you can switch to proxied/orange later once the cert is active).
- If Fly asks for an `AAAA`/`A` + an `_acme-challenge` `CNAME` for validation, add those too.

Wait a few minutes for the cert to go **Ready** (`fly certs show`), then open `https://app.yourdomain.com`.

**4. Use it, then tear it all down (fully reversible)**
```bash
fly apps destroy <app>        # deletes the app + its machines (billing stops)
```
Then in Cloudflare → DNS, delete the `app` record. **Your domain stays yours** — the subdomain
and DNS are free to reuse for anything later, or point back here. Nothing is locked or consumed.

> Cost: Fly scales to zero when idle (per `fly.toml`), so a light month is roughly **$0–5**.
> Cloudflare DNS is free. Set `min_machines_running = 1` if you want to avoid cold starts.

## Post-deploy smoke check

1. `GET /api/health` → 200.
2. The SPA loads at `/`; open the Analyzer and upload a sample chest X-ray → a result (or an
   honest abstain) appears.
3. If `AUTH_ENABLED=1`: hitting a protected route unauthenticated returns 401; login works; the
   Profile page shows 2FA + active-sessions controls.
4. `GET /api/behavior-card` returns the measured metrics (the Evidence page renders them).

## CI

`.github/workflows/ci.yml` runs the backend suite (DB off + on), the frontend build, and
dependency audits on every push — wire it to your platform's deploy trigger to gate releases.
