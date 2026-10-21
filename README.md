# InvestIQ

React/TypeScript investment research workspace with a FastAPI backend, saved investor preferences, a watchlist, provider prices/news, annual financial evidence and AI-assisted assessments.

This is a single shared workspace without authentication. Run it locally. It cannot guarantee profitable decisions. The AI Research page keeps BUY disabled. The Valuation page offers a conditional BUY CANDIDATE research screen when quantitative checks and cited news support it; portfolio suitability remains incomplete.

## Run

Requirements: Docker Desktop, Node.js 20.19+ or 22.12+, and npm. Local backend development requires Python 3.12+.

1. Copy `.env.example` to `.env` if you do not already have one. Supply your Finnhub key and a real SEC contact identity. The OpenAI key is optional.
2. Run `docker compose up --build -d` from the project root.
3. Run `npm ci` and `npm run dev` inside `frontend`.
4. Open http://localhost:5173. The API documentation is at http://localhost:8000/docs.
5. Save your risk tolerance and time horizon, add a ticker, and open its research. The **AI Research** tab runs a new assessment on demand. Confirm existing ownership there if applicable.

For a local backend without Docker:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -m uvicorn app.main:app --app-dir backend --env-file .env --host 127.0.0.1 --port 8000
```

The local backend defaults to SQLite. Docker Compose uses PostgreSQL. Existing tables are preserved, and the new `research_runs` audit table is created on startup. There are no production migrations yet.

## Data and decision behavior

- US quotes/news: Finnhub. Quotes refresh every 60 seconds while the research page is visible. Quote cache: 15 seconds; news cache: 5 minutes. A timestamp within two minutes and explicitly configured exchange entitlement are both required for the real-time label. Polling is not streaming, and market sessions are not independently verified.
- Canada/India: unofficial Yahoo Finance daily bars, cached for 60 seconds. The timestamp represents the session date. A current day's bar may still be provisional. These are never labeled real-time.
- Annual financials: SEC companyfacts for supported US-GAAP US filers, with clearly labeled Yahoo fallback. Annual data and fundamentals are cached for 5 minutes. The shared SEC ticker directory is cached for 24 hours. Annual statement freshness is distinct from price freshness.
- P/E scenarios use a retrieved provider price and earnings in the provider's matching quote currency. EPS × reported P/E is never substituted for a missing price. Scenarios contain generic assumptions and never determine the investment verdict.
- Assessments use saved preferences, ownership confirmation, dated evidence, growth trends, risk flags and data gaps. Missing essential data produces **INSUFFICIENT DATA**. **WAIT** means a purchase is not justified; **AVOID** and **HOLD** require appropriate evidence/context. AI Research does not permit **BUY** or numerical AI entry/target prices. The separate Valuation screen can show **BUY CANDIDATE**, with explicit conditions and model-calculated sensitivities; see the valuation guide.
- If OpenAI is unconfigured, unavailable, refuses, truncates its response, or violates the structural/evidence-reference/decision checks, deterministic research remains available. The UI identifies the mode. AI prose still requires human review.
- Every assessment stores its inputs, profile, policy version and output. Inspect the last ten runs at `/api/analysis-history/{market}/{symbol}`. AI runs are manual; refreshing prices does not call OpenAI.

`OPENAI_MODEL` defaults to `gpt-4.1-mini`. `FINNHUB_REALTIME_ENTITLED` defaults to `false`; set it to `true` only after confirming your subscription's applicable exchange entitlements. This flag does not grant data access or enable trading.

## Verification

```sh
.venv/bin/python -m pytest backend/tests -q
```

Tests use temporary SQLite databases and mocked providers; they do not call paid APIs or alter your data. Run `npm run build` in `frontend` for TypeScript and production bundle validation.

See [the valuation guide](docs/VALUATION.md) for preference-based gains, historical replays and cited web assessments. The original SEC endpoint is now `/api/cash-flow-valuation/{market}/{symbol}`.

In **Valuation**, set your own return goal, historical drawdown, volatility and modeled downside limits. Expand **More screening criteria** for history coverage, trade quote age and benchmark return requirements. **Apply criteria** updates the checklist; **Research latest news** reviews those same values. The applied limits are displayed together, and changing them clears the previous news review. These overrides apply to the current stock screen; **Reset to profile defaults** restores your saved profile's starting limits.

See [the code review](docs/CODE_REVIEW.md) for resolved issues and remaining work. Live NVIDIA price/history/FX/news retrieval and web search have been smoke-tested locally. Provider entitlements and investment performance must be evaluated separately.

## Remaining work

There is no broker execution, portfolio import, full suitability questionnaire, FX conversion, independently verified market calendar, streaming feed, background scanner, alert delivery, calibrated forecasting or out-of-sample strategy validation. Before public hosting, add authentication and per-user authorization, migrations/backups, rate limiting, monitoring, secret management and a production deployment configuration. The standalone frontend defaults to `investiq-app.railway.internal:8000`; override its `API_UPSTREAM` for another backend. See [Railway connectivity](docs/RAILWAY.md) for private DNS, dual-stack startup and 499 troubleshooting.
