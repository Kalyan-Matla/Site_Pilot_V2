# 🏗️ SitePilot — Construction Management for Small/Medium Contractors

A complete, self-contained construction management application: projects & tasks,
daily progress (DPR/WPR), documents with versioning, materials & inventory
(indent → PO → GRN → stock → usage), labour & attendance with wage computation,
vendors, invoices, payments & credit control, reports with PDF/CSV export,
notifications, activity feeds, audit log, equipment register, and safety/quality
checklists.

**Stack:** Python 3.12+ · FastAPI · SQLite by default, or Postgres when
`DATABASE_URL` is set (needed for serverless hosts like Vercel) · buildless
ES-module SPA (no Node.js required) · reportlab for PDFs · Docker optional.

---

## Quick start (local, 2 commands)

Requires [uv](https://docs.astral.sh/uv/) (or plain `pip`, see below).

```bash
uv run python -m app.seed        # create DB, run migrations, load demo data
uv run python -m app.main       # serve API + web app on http://localhost:8000
```

Open **http://localhost:8000** (set `PORT=8123` etc. if 8000 is taken).

Without uv:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.seed
python -m app.main
```

## Quick start (Docker)

```bash
docker compose up --build
```

App on http://localhost:8000. Data (SQLite DB + uploaded files) persists in the
`sitepilot_data` volume. Seeding runs automatically on first boot only.

## Deploy a permanent public URL (share with anyone)

`localhost` is only reachable on the machine running the server. To give others
a link they can open from any device, deploy the included Docker image to a
cloud host. **Recommended: Render** (free tier, HTTPS included, simplest UI).

**Before you start (once):** put the code on GitHub.

```bash
cd construction-manager
git init && git add -A && git commit -m "SitePilot"
# create an empty repo at github.com/new (e.g. "sitepilot"), then:
git remote add origin https://github.com/<you>/sitepilot.git
git branch -M main
git push -u origin main
```

**Deploy on Render:**

1. Sign up at [render.com](https://render.com) (free) and connect your GitHub.
2. **New +  →  Blueprint**, pick the `sitepilot` repo, click **Apply**.
   Render reads [`render.yaml`](render.yaml), builds the Dockerfile, and
   generates a strong `JWT_SECRET` automatically.
3. In ~2–3 minutes you get a URL like `https://sitepilot-xxxx.onrender.com` —
   **that's the link to share.** Anyone can open it and sign in with the demo
   accounts below.

Free-tier notes: the app sleeps after ~15 min idle and cold-starts in ~30–60s
on the next visit; storage is ephemeral, so the demo reseeds on restart. To keep
real data, attach a persistent disk — see the commented block in `render.yaml`.

**Alternative: Fly.io** (deploys straight from this folder, no GitHub needed).
Install [`flyctl`](https://fly.io/docs/flyctl/install/), then:

```bash
fly launch --no-deploy --copy-config          # claims a unique app name
fly volumes create sitepilot_data --size 1    # persistent storage
fly secrets set JWT_SECRET=$(python3 -c "import secrets;print(secrets.token_hex(32))")
fly deploy                                    # prints your https://<app>.fly.dev URL
```

Railway, a VPS, or any Docker host works too — point them at the `Dockerfile`
and set `JWT_SECRET`.

> **Security when public:** the demo logins on the sign-in page are intentionally
> public, so anyone with the link can browse as any role. Keep `ALLOW_SIGNUP=0`
> (the deploy default) so strangers can't create accounts, and **treat a shared
> deployment as a demo — don't enter real business data** unless you first change
> the demo passwords and lock down access.

## Deploy to Vercel

Render/Fly/Docker keep a local disk, so SQLite works as-is. **Vercel Functions
have no persistent disk** — every cold start gets a fresh, mostly read-only
filesystem — so this repo also ships a **Postgres backend** (auto-enabled by
setting `DATABASE_URL`) and **Vercel Blob** file storage (auto-enabled by
`BLOB_READ_WRITE_TOKEN`) specifically for this target. Everything below is
already wired up in [`vercel.json`](vercel.json), [`requirements.txt`](requirements.txt),
`pyproject.toml`, and `app/db.py` / `app/storage.py` — you're just connecting
the pieces in the dashboard.

1. **Push this repo to GitHub as-is** — `app/`, `public/`, `vercel.json`,
   `requirements.txt` etc. all need to be at the **repo root** (not nested
   inside a subfolder). If you're uploading via GitHub's web UI, drag real
   folders from Finder into the drop zone in one go — a file-picker dialog
   can't select folders and will silently skip them.
2. In [vercel.com](https://vercel.com), click **Add New → Project** and import
   the repo. Vercel auto-detects the Python/FastAPI app at `app/main.py` — no
   framework preset needed.
3. **Add a Postgres database.** Vercel's own Postgres product is retired in
   favor of a **Neon** integration: **Storage → Create Database → Neon
   (Postgres)**, or install [the Neon integration](https://vercel.com/marketplace/neon)
   and link it to this project. Either path sets `DATABASE_URL` automatically —
   the app creates its schema and seeds demo data on first request.
4. **Add a Blob store** (for document/photo uploads to persist): **Storage →
   Create Database → Blob**, connect it to the project. This sets
   `BLOB_READ_WRITE_TOKEN` automatically.
5. **Set env vars** under Project Settings → Environment Variables:
   - `JWT_SECRET` — required in production; generate with `openssl rand -hex 32`.
   - `ALLOW_SIGNUP=0` if you don't want the public **Get started** button to
     create real accounts on a demo deployment.
   - `CRON_SECRET` — optional but recommended; Vercel signs its cron requests
     with it automatically once set, preventing anyone else from triggering
     `/api/cron/alerts`.
6. **Deploy.** Vercel builds from `requirements.txt` and gives you a
   `https://<project>.vercel.app` URL — that's the link to share.

**What's different from the Docker/Render deployment:**
- **Uploads are capped at 4 MB**, not 25 MB — Vercel Functions reject request
  bodies over 4.5 MB before the app ever sees them. Fine for drawings/photos;
  not for huge files.
- **The daily alerts sweep runs via Vercel Cron** (`vercel.json`'s `crons`
  entry, once a day) instead of the in-process background loop the other
  deployments use — serverless functions don't stay alive long enough for a
  loop to sleep 24 hours between runs.
- **Python version is pinned to 3.12** (`requires-python` in `pyproject.toml`
  and `.python-version`) — Vercel's Python runtime only supports 3.12/3.13/3.14,
  and an unpinned/ambiguous version can silently resolve to something older
  that can't install this project's dependencies.
- File storage note: the integration uses the community `vercel_blob` PyPI
  package (Vercel doesn't publish an official Python SDK). If an upload ever
  fails with a storage error, it's worth checking that package's current API
  against `app/storage.py`.

## Landing page & sign-up

Visiting `/` while signed out shows the marketing landing page, with **Sign in**
and **Get started** (self-signup). Sign-up creates an **Owner** account via
`POST /api/auth/register`; set `ALLOW_SIGNUP=0` to disable public registration
on production servers. Landing imagery is hotlinked from Unsplash (photos load
when the server has internet access; the page degrades gracefully without it).
The landing page is also reachable at `#/landing` while signed in (its CTAs
adapt to "Open dashboard").

## Demo logins (password for all: `Password123!`)

| Role            | Email                    | What they can do |
|-----------------|--------------------------|------------------|
| Owner           | `owner@sitepilot.test`   | Everything, incl. user management |
| Project Manager | `pm@sitepilot.test`      | Projects, tasks, approvals, POs, work orders |
| Site Engineer   | `site@sitepilot.test`    | Progress logs, attendance, indents, issues |
| Storekeeper     | `store@sitepilot.test`   | Stock, GRNs, material master, POs |
| Accountant      | `accounts@sitepilot.test`| Invoices, payments, ledgers, ageing, audit log |
| Vendor          | `vendor@sitepilot.test`  | Own POs & invoices only (portal view) |

## Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `JWT_SECRET` | `change-me-in-production` | **Set this in production.** Signing key for auth tokens |
| `JWT_HOURS` | `12` | Token lifetime |
| `PORT` / `HOST` | `8000` / `0.0.0.0` | Bind address |
| `DATA_DIR` | `./data` (`/tmp/sitepilot-data` on Vercel) | Where the SQLite DB and local uploads live |
| `DATABASE_URL` | unset (uses SQLite) | Set to a Postgres connection string (e.g. from Neon) to switch backends — needed on Vercel |
| `BLOB_READ_WRITE_TOKEN` | unset (uses local disk) | Set via a Vercel Blob store to persist uploads on serverless hosts |
| `MAX_UPLOAD_BYTES` | 25 MB (4 MB if Blob is configured) | Override the upload size cap |
| `ALERT_INTERVAL_HOURS` | `24` | Frequency of the due-invoice / credit-limit / low-stock sweep (in-process loop; ignored on Vercel, see cron above) |
| `ALLOW_SIGNUP` | `1` | Set `0` to disable public self-signup on the landing page |
| `SEED_DEMO_DATA` | `1` | Set `0` to skip auto-seeding demo data on first startup against an empty database |
| `CRON_SECRET` | unset | If set, `/api/cron/alerts` requires `Authorization: Bearer $CRON_SECRET` |

## Architecture

```
app/
  main.py          FastAPI app, SPA hosting, daily alert job / cron endpoint
  db.py            SQLite + Postgres connection layer, migration runner, query helpers
  storage.py       file storage abstraction (local disk or Vercel Blob)
  security.py      JWT, bcrypt, role & project-scope enforcement
  helpers.py       audit log, notifications, activity feed, pagination
  migrations/      ordered .sql files (SQLite dialect), tracked in schema_migrations
  migrations_pg/   the same schema in Postgres dialect, used when DATABASE_URL is set
  seed.py          idempotent demo data (skips if users exist)
  routers/
    auth_users.py  login, sign-up, users CRUD
    projects.py    projects, members, tasks, issues, progress, DPR/WPR, activity
    documents.py   uploads + versioning, linked to project/task/issue
    materials.py   material master, stock, indents, POs, GRNs, usage
    labour.py      labourers, attendance, wage/payable computation
    finance.py     vendors, work orders, invoices, payments, ageing, alerts
    reports.py     dashboard, CSV/PDF exports, audit log
    misc.py        comments, notifications, equipment, checklists
public/            buildless single-page app (ES modules, hash router)
```

- **Auth**: JWT bearer tokens; bcrypt-hashed passwords; every endpoint checks
  role and (where applicable) project membership. Owner/Accountant see all
  projects; other roles only projects they are assigned to; Vendor users are
  restricted to records of their linked vendor.
- **Business rules enforced server-side**: POs only from approved indents,
  GRN quantities capped at PO balance (stock auto-updates), usage capped at
  site stock, invoice due date = invoice date + vendor credit period,
  payments capped at invoice balance (auto-marks paid), overdue status
  computed automatically.
- **Audit log** on POs, invoices, payments, projects, requests, users, etc.
  (before/after JSON). **Notifications** on task assignment, issues, indent
  decisions, new POs/invoices, payments, plus a daily sweep for overdue
  invoices, >45-day invoices, credit-limit breaches, and low stock.
- **Pagination** on all list endpoints; indexes on all hot paths.
- API is fully documented at **`/docs`** (OpenAPI/Swagger) when running.

## Reports & exports

- DPR / WPR per project (PDF + CSV): work done, materials used, labour, issues.
- Site stock, requested-vs-ordered-vs-received-vs-used (CSV/PDF).
- Labour attendance & payable per project/vendor for any period (CSV/PDF).
- Payables ledger (vendor-wise & project-wise) and 0-30 / 31-45 / 46-60 / 60+
  ageing (CSV/PDF).

## Production deployment notes

1. Set a strong `JWT_SECRET` (e.g. `openssl rand -hex 32`).
2. Put the app behind HTTPS (nginx/Caddy/Traefik reverse proxy → port 8000).
3. Back up the data volume (`/data` in Docker): it contains `sitepilot.db`
   and all uploaded files.
4. SQLite in WAL mode comfortably serves small/medium contractor teams
   (tens of concurrent users) on Docker/Render/Fly. If you need Postgres —
   or you're on Vercel, where it's required — set `DATABASE_URL` (see
   "Deploy to Vercel" above); the app switches backends automatically.
5. To start with a clean slate, delete the data volume / `data/` directory
   and rerun the seed (or just create users via the Owner account and skip
   seeding entirely — it only loads demo data when the DB has no users).

## Running the API test suite

A ~74-assertion end-to-end smoke test exercising every module (RBAC, the full
indent→PO→GRN→usage chain, wages, ageing, exports…) is included:

```bash
uv run python -m app.seed                # fresh DB recommended
uv run python -m app.main &              # or any port via PORT=…
python tests/smoke.py                    # BASE defaults to localhost:8000
```
