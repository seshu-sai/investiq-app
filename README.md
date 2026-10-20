# InvestIQ — full-stack development starter

Responsive React/TypeScript frontend, FastAPI backend, PostgreSQL via Docker Compose, saved investor settings and a watchlist.

## Requirements
- Docker Desktop with Docker Compose
- Node.js 20.19+ or 22.12+ and npm

## Run
1. From this folder: `docker compose up --build -d`
2. Check API: http://localhost:8000/docs
3. `cd frontend`
4. `npm install`
5. `npm run dev`
6. Open http://localhost:5173

The frontend dev server proxies `/api` to port 8000. Backend saves settings and watchlist in PostgreSQL. The application is currently a **single shared workspace** (no authentication). Do not expose it publicly.

## Tests
From `backend`, with Python dependencies installed: `python -m pytest -q`. By default the test module uses local SQLite; run it in a clean working directory.

## Status
- Working: responsive dashboard, investor settings, watchlist CRUD, API docs, database persistence, health check, placeholder research API.
- Not yet implemented: user authentication/authorization, Alembic migrations, real market/news data, licensed feeds, AI research, forecasts, scheduled listener, alerts, backtesting, audit trails, rate limiting, monitoring, deployment hardening.
- This prototype does **not** provide investment recommendations, current prices or forecasts. Research endpoint returns `not_connected` intentionally.

## Security / production backlog
Implement user accounts with OIDC and per-user authorization; migrations and database backups; encrypted secrets and credentials; TLS; restricted CORS; CSRF protections where applicable; provider terms/licensing; audit logs; request throttling; observability; CI/CD and integration tests; vulnerability scanning; regional securities-law review before personalized investment recommendations are offered to the public. Use a managed database and a strong unique POSTGRES_PASSWORD for deployments.
