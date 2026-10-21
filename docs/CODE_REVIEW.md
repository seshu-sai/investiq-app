# Investment research code review

This document describes the original reliability review. The subsequent preference-based valuation and conditional buy-candidate feature is documented in [VALUATION.md](VALUATION.md).

Scope: all application modules, React components, API tests, dependency declarations, container configuration and startup documentation. Existing local valuation/capital-structure additions were retained and integrated. Generated files, dependency source trees and secret values were excluded.

## Findings addressed

| Finding | Impact | Change |
| --- | --- | --- |
| API derived a price from EPS × P/E | Scenarios could use a synthetic, stale entry price | Use a retrieved provider quote; return insufficient scenarios if price/currency/earnings are unusable |
| Same EPS growth assumptions produced a verdict for every company | Generic assumptions appeared to justify an investment | Scenario output is labeled sensitivity analysis and has no buy/avoid verdict |
| Quote validator was unused and allowed four-day data without a real-time distinction | Recent retrieval could be mistaken for recent trading | Integrated price validation, timestamps, separate research usability and real-time checks |
| Daily bars were easy to confuse with quotes | Misleading intraday decisions, especially CA/IN | Explicit daily-bar labels, session-date warning and provisional-close caveat |
| Provider news failures discarded good quotes | An optional component could block research | News failure returns quote plus a warning |
| AI analysis repeated provider requests serially | Extra latency, inconsistent inputs and rate-limit pressure | One snapshot with concurrent independent components and bounded TTL caches |
| Saved investor preferences were unused in AI analysis | Research ignored risk, horizon and market preferences | Pass saved profile to deterministic checks and the model; display profile warnings |
| Ownership was unknown | HOLD could be recommended to someone with no position | Explicit ownership confirmation and server-side eligibility checks |
| AI response only checked a decision string | Malformed, truncated or unsupported responses could reach users | Strict Pydantic schema, completion check, valid evidence IDs and policy checks; replace the entire failed narrative |
| Missing AI key/provider outage prevented any assessment | No useful analysis under partial outages | Labeled deterministic fallback; essential gaps force INSUFFICIENT DATA |
| Server erased all data timestamps | Users could not judge the age of a decision | Separate quote timestamp, annual fiscal date and analysis timestamp |
| SEC extractor selected earliest filings | Current research could ignore a restatement | Latest available filing per period; same-filing revenue/income/cash components; retain accession provenance |
| Multi-year gaps could count as one year | Overstated annual growth/CAGR and concealed negative years | Consecutive-period checks; no growth calculation across missing periods; CAGR uses elapsed dates |
| Non-finite values and negative earnings handling | JSON failures or hidden loss-making businesses | Reject booleans/NaN/infinity, preserve negative EPS, validate cash arithmetic and filing dates |
| Canadian venture tickers gained `.TO` | Research could resolve the wrong security | Shared market validation preserves `.V` and rejects conflicting exchange suffixes |
| Unsafe/unordered news links | Untrusted URLs or future articles could reach the UI/model | Restrict URLs to HTTP(S), drop future/out-of-window items, deduplicate and sort by publication date |
| No reproducible assessment record | Difficult to inspect why an assessment changed | Append research snapshots with profile, evidence, timestamps and policy version |
| Old tests expected a disconnected placeholder API | Tests did not verify current behavior | Isolated mocked API/provider/decision/valuation regression coverage |
| Documentation/UI claimed implemented features were unavailable | Product behavior was unclear | Updated run instructions, labels, data boundaries and configuration example |

## Decision contract

Deterministic checks control eligible verdicts. AI cannot enable BUY, generate an entry/target price, extend the user's horizon, or issue HOLD without explicit ownership and the required context. A rejected verdict replaces all of its prose, avoiding a neutral headline with contradictory buy reasoning. Missing essential data prevents an AI call entirely.

These checks validate structure, provenance references and verdict eligibility; they do not prove every natural-language statement correct. A well-formed AI response can still contain mistakes. News relevance is provider-associated, not independently verified. P/E uses provider currency metadata; ADR ratios, unusual capital structures and financial reporting currencies require additional review.

No model confidence percentage is presented: there is no calibration dataset. No expected profit is reported from historical revenue or cash-flow growth. Hypothetical sensitivities are not probability-weighted forecasts.

## Remaining constraints

1. **Valuation:** CFO minus asset purchases is not fully adjusted FCFF/FCFE. Discount rates, terminal growth, dilution, financing flows, excess cash and capital structure need company-specific validation. Existing capital-structure checks explicitly keep `valuation_ready` false. BUY therefore stays disabled. A simple low P/E or growing cash flow cannot bypass this.
2. **Real-time coverage:** US data freshness depends on timestamp and configured entitlement. There is no streaming integration or independent exchange calendar, and a quote is not an executable bid/ask. CA/IN remain daily-bar research. Closed markets and stale feeds are not conclusively distinguished.
3. **Investor suitability:** Risk/horizon preferences are considered, but holdings, emergency cash, debts, liquidity needs, tax circumstances, concentration, income, and loss capacity are not collected. No position size is supplied.
4. **Performance evidence:** No strategy/backtest or walk-forward validation exists. Current SEC extraction incorporates available restatements; it is explicitly unsuitable for point-in-time backtests. Future evaluation needs historical constituents, filing availability dates, delisted securities, corporate actions, FX, fees, slippage and untouched holdout periods. Unit tests do not show profitability.
5. **Operations:** Shared workspace, no authentication, no rate limit or scheduled monitoring; API calls can consume provider quota. Caches are per process, and concurrent cache misses may duplicate work. Annual-only evidence omits recent quarterly filings. Provider access and billing were not exercised during this review.
6. **Deployment:** SQLite/PostgreSQL persistence works with startup table creation; Alembic migrations, audit retention and backups remain to be implemented. The frontend's standalone Nginx target is deployment-specific. Do not publish this shared workspace as a multi-user advisory service.

## Sources consulted

- [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs): schema use, explicit refusals and incomplete-response handling. API compatibility was checked against the locally installed SDK; no paid model calls were made.
- [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces): companyfacts units, filing/period context and API update behavior.
- [FINRA automated investment tools](https://syndication.finra.org/content/what-you-should-know-about-automated-investment-tools): limits of automated tools and the investor information needed for suitability.
