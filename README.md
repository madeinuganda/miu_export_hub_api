# MIU Export Hub API

FastAPI backend for the **Made in Uganda Export Hub** B2B export marketplace.

## Stack

- FastAPI + Uvicorn
- PostgreSQL + SQLAlchemy 2.x (async) + Alembic
- Pydantic v2
- JWT access + refresh tokens

## Docker (recommended)

Requires [Docker](https://docs.docker.com/get-docker/) and Docker Compose.

```bash
cd miu_api_v2
docker compose up -d --build
```

- API: http://localhost:8030 (override with `API_PORT=8031 docker compose up -d`)
- OpenAPI: http://localhost:8030/docs
- **pgAdmin:** http://localhost:5050 — login `admin@miu.local` / `admin` (dev only)
- PostgreSQL: `localhost:5432` (user `miu`, **no password** in dev — `POSTGRES_HOST_AUTH_METHOD=trust`, db `miu_export_hub`)

pgAdmin ships with the **MIU Export Hub** server pre-registered (`db:5432`). Open it in the browser tree — no DB password prompt.

> If you previously started Postgres with password auth, reset the volume: `docker compose down -v && docker compose up -d --build`

The API container waits for Postgres, runs the idempotent seed (`SEED_ON_START=true` by default), then starts Uvicorn.

```bash
# Logs
docker compose logs -f api

# Stop
docker compose down

# Reset database and uploads
docker compose down -v
```

Optional env overrides (copy `.env.docker.example` to `.env`):

| Variable | Default in Compose |
|----------|-------------------|
| `JWT_SECRET` | dev docker secret |
| `CORS_ORIGINS` | `http://localhost:5173` |
| `SEED_ON_START` | `true` |

Production-style run (no DB port exposed, 4 workers, no auto-seed):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

## Local development (without Docker)

```bash
cd miu_api_v2
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit DATABASE_URL and JWT_SECRET in .env
```

Create the database and run migrations:

```bash
createdb miu_export_hub
alembic upgrade head   # or: python -m scripts.seed (creates tables + seeds)
python -m scripts.seed
```

Run the API:

```bash
uvicorn app.main:app --reload --port 8030
```

- API: http://localhost:8030
- OpenAPI: http://localhost:8030/docs
- Health: http://localhost:8030/health

## Demo accounts (after seed)

| Role     | Email                         | Password      |
|----------|-------------------------------|---------------|
| Admin    | admin@miu.ug                  | MIU@2026      |
| Buyer    | hans.mueller@naturkost.de     | Buyer123!     |
| Supplier | amara@rwenzoriorganics.ug    | Supplier123!  |

## Project layout

```
app/
  main.py              # FastAPI app, CORS, exception handlers
  core/                # config, database, security, dependencies
  models/              # SQLAlchemy models (audit columns on all tables)
  services/            # Business logic per domain
  api/v1/              # Routers: auth, public, buyer, supplier, admin
  utils/               # formatting, pagination, audit helpers
alembic/               # Migrations
scripts/seed.py        # Demo data
tests/
```

## Authentication

Each portal has **separate account tables** (`buyer_accounts`, `supplier_accounts`, `admin_accounts`) and **separate auth routes**. The same email may exist on buyer and supplier (different passwords).

JWT payload includes `account_type`: `buyer` | `supplier` | `admin`. Tokens are not interchangeable across portals.

### Buyer

| Action | Endpoint |
|--------|----------|
| Register | `POST /api/v1/auth/buyer/register` |
| Login | `POST /api/v1/auth/buyer/login` |
| Me | `GET /api/v1/auth/buyer/me` |
| Refresh / logout | `POST /api/v1/auth/buyer/refresh`, `POST /api/v1/auth/buyer/logout` |
| Change password | `POST /api/v1/auth/buyer/change-password` |

Returns `account` (not `user`) plus `onboarding_required` until MIU approves buyer onboarding.

### Supplier

| Action | Endpoint |
|--------|----------|
| Register | `POST /api/v1/auth/supplier/register` |
| Login | `POST /api/v1/auth/supplier/login` |
| Me / refresh / logout / change-password | `/api/v1/auth/supplier/*` |

### Admin (invite only)

1. Existing admin: `POST /api/v1/admin/invites` → `temporary_password` (once).
2. Login: `POST /api/v1/auth/admin/login`
3. Change password: `POST /api/v1/auth/admin/change-password` (clears `must_change_password`)

### Headers

| Endpoint | Header |
|----------|--------|
| Protected routes | `Authorization: Bearer <access_token>` |
| Refresh / logout | `Authorization: Bearer <refresh_token>` |

Use **Authorize** in `/docs` (BearerAuth).

## API base path

All routes are under `/api/v1`:

- `GET /api/v1/public/home` — landing page CMS aggregate
- `POST /api/v1/auth/register` | `/login` | `/refresh`
- `GET /api/v1/buyer/browse` — buyer catalog (supplier names masked)
- `POST /api/v1/buyer/rfqs` — create RFQ
- `GET /api/v1/supplier/dashboard` — supplier home (pending vs approved)
- `POST /api/v1/admin/suppliers/{id}/verify` — approve supplier
- `GET /api/v1/buyer/onboarding` — buyer onboarding wizard (company → contact → sourcing → submit)
- `POST /api/v1/admin/buyers/{id}/verify` — approve buyer onboarding

See the master spec in the project brief for the full endpoint map.

## Environment variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/db` |
| `JWT_SECRET` | Signing key for access tokens |
| `CORS_ORIGINS` | Comma-separated origins (e.g. `http://localhost:5173`) |
| `STORAGE_PATH` | Local upload directory (default `./uploads`) |

## Tests

```bash
pytest
```

## Notes (v1)

- Payments and escrow are **simulated** (no real gateway).
- Email/SMS are stubbed (queue + log pattern ready).
- Buyer–supplier identity is **mediated** until order placement (anonymized labels in API responses).
# miu_export_hub_api
